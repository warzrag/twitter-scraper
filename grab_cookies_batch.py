"""
Extraction batch des cookies X pour le pool, avec 2FA TOTP auto.

Entree : credentials.txt (1 ligne par compte)
Format :
    user:password:totp_secret
    user:password:totp_secret:email

totp_secret = la cle TOTP brute (ex: JBSWY3DPEHPK3PXP), celle que tu
mettrais dans 2fa.live ou Google Authenticator. Sans espaces.

Sortie : cookies_pool.json (auth_token + ct0 pour chaque compte)

Usage:
    pip install playwright pyotp
    playwright install chromium
    python grab_cookies_batch.py
"""

import json
import asyncio
from pathlib import Path
import pyotp
from playwright.async_api import async_playwright

CREDS_FILE = "credentials.txt"
POOL_FILE = "cookies_pool.json"
TIMEOUT_LOGIN_MS = 90_000  # 90s de marge si X demande captcha


def load_credentials(path: str) -> list:
    """Charge les credentials depuis credentials.txt."""
    p = Path(path)
    if not p.exists():
        print(f"[ERREUR] Fichier {path} introuvable.")
        print("Cree le fichier avec une ligne par compte au format :")
        print("  user1:password1")
        print("  user2:password2:email2")
        return []
    creds = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split(":")
        if len(parts) < 2:
            continue
        creds.append({
            "user": parts[0].strip(),
            "password": parts[1].strip(),
            "totp": parts[2].strip().replace(" ", "") if len(parts) > 2 else None,
            "email": parts[3].strip() if len(parts) > 3 else None,
        })
    return creds


def gen_totp(secret: str) -> str:
    """Genere le code 2FA actuel (6 chiffres) a partir de la cle secrete."""
    return pyotp.TOTP(secret).now()


def load_existing_pool(path: str) -> list:
    p = Path(path)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_pool(pool: list, path: str):
    Path(path).write_text(json.dumps(pool, indent=2), encoding="utf-8")


async def grab_one(page, cred: dict) -> dict | None:
    """Connecte un compte et recupere ses cookies."""
    user = cred["user"]
    print(f"\n=== {user} ===")
    try:
        await page.goto("https://x.com/i/flow/login", timeout=30_000)
        await page.wait_for_timeout(2000)

        # Etape 1 : username
        try:
            await page.fill('input[autocomplete="username"]', user, timeout=15_000)
            await page.keyboard.press("Enter")
        except Exception:
            print(f"  [SKIP] Champ username introuvable pour {user}")
            return None

        await page.wait_for_timeout(2500)

        # Etape 2 : si X demande email/phone (compte suspect)
        try:
            verif = page.locator('input[data-testid="ocfEnterTextTextInput"]')
            if await verif.count() > 0 and cred.get("email"):
                print(f"  [INFO] X demande verif email pour {user}, je remplis...")
                await verif.fill(cred["email"])
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(2000)
        except Exception:
            pass

        # Etape 3 : password
        try:
            await page.fill('input[name="password"]', cred["password"], timeout=15_000)
            await page.keyboard.press("Enter")
        except Exception:
            print(f"  [SKIP] Champ password introuvable pour {user}")
            return None

        await page.wait_for_timeout(2500)

        # Etape 4 : 2FA TOTP auto
        if cred.get("totp"):
            try:
                # Le champ 2FA peut avoir plusieurs selecteurs selon la version X
                tfa_selectors = [
                    'input[data-testid="ocfEnterTextTextInput"]',
                    'input[name="text"]',
                    'input[autocomplete="one-time-code"]',
                ]
                for sel in tfa_selectors:
                    field = page.locator(sel)
                    if await field.count() > 0:
                        code = gen_totp(cred["totp"])
                        print(f"  [2FA] Code genere : {code}")
                        await field.first.fill(code)
                        await page.keyboard.press("Enter")
                        break
            except Exception as e:
                print(f"  [2FA] Pas de champ 2FA detecte ou erreur: {e}")

        # Attendre la home
        print(f"  [WAIT] Connexion en cours (max 90s, captcha si besoin)...")
        try:
            await page.wait_for_url("**/home", timeout=TIMEOUT_LOGIN_MS)
        except Exception:
            pass

        await page.wait_for_timeout(2000)

        # Extraire les cookies
        cookies = await page.context.cookies("https://x.com")
        cookie_dict = {c["name"]: c["value"] for c in cookies}
        auth = cookie_dict.get("auth_token")
        ct0 = cookie_dict.get("ct0")

        if not auth or not ct0:
            print(f"  [FAIL] Cookies manquants pour {user} (login echoue ?)")
            return None

        print(f"  [OK] {user} -> cookies recuperes")
        return {"user": user, "auth_token": auth, "ct0": ct0}

    except Exception as e:
        print(f"  [ERREUR] {user}: {e}")
        return None


async def logout(page):
    """Vide les cookies pour la session suivante."""
    await page.context.clear_cookies()


async def main():
    creds = load_credentials(CREDS_FILE)
    if not creds:
        return

    print(f"Comptes a traiter : {len(creds)}")
    pool = load_existing_pool(POOL_FILE)
    existing_users = {p.get("user") for p in pool}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        for i, cred in enumerate(creds, 1):
            print(f"\n[{i}/{len(creds)}]", end=" ")
            if cred["user"] in existing_users:
                print(f"{cred['user']} deja dans le pool, skip.")
                continue

            result = await grab_one(page, cred)
            if result:
                pool.append(result)
                save_pool(pool, POOL_FILE)
                print(f"  [SAVED] Pool : {len(pool)} comptes")
            await logout(page)
            await page.wait_for_timeout(1500)

        await browser.close()

    print(f"\n=== FINI ===")
    print(f"Pool final : {len(pool)} comptes dans {POOL_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
