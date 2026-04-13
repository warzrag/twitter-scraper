#!/usr/bin/env python3
"""
Twitter/X Scraper avec Playwright (comme Apify)
Scrape les followers avec le VRAI can_dm via GraphQL
"""

import json
import asyncio
import random
from typing import Optional, AsyncGenerator
from playwright.async_api import async_playwright, Page, BrowserContext, Response

from gender_detector import detect_gender


class TwitterPlaywrightScraper:
    """
    Scraper Twitter utilisant Playwright (comme Apify).
    Intercepte les réponses GraphQL pour récupérer le VRAI can_dm.
    """

    def __init__(self, cookies: list, headless: bool = True, proxy: str = None):
        """
        Args:
            cookies: Liste de cookies au format [{"name": "auth_token", "value": "xxx"}, ...]
            headless: True pour navigateur invisible, False pour voir le navigateur
            proxy: Proxy optionnel (format: http://user:pass@host:port)
        """
        self.cookies = cookies
        self.headless = headless
        self.proxy = proxy
        self.browser = None
        self.context = None
        self.page = None
        self.captured_users = []
        self.is_capturing = False
        self.rate_limited = False
        self.rate_limit_wait = 0

    async def start(self):
        """Démarre le navigateur et injecte les cookies."""
        print("[PLAYWRIGHT] Démarrage du navigateur...")

        playwright = await async_playwright().start()

        # Config du navigateur
        launch_options = {
            "headless": self.headless,
            "args": ["--disable-blink-features=AutomationControlled"]
        }

        if self.proxy:
            # Parser l'auth si presente dans l'URL: http://user:pass@host:port
            from urllib.parse import urlparse
            parsed = urlparse(self.proxy)
            proxy_cfg = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
            if parsed.username:
                proxy_cfg["username"] = parsed.username
            if parsed.password:
                proxy_cfg["password"] = parsed.password
            launch_options["proxy"] = proxy_cfg

        self.browser = await playwright.chromium.launch(**launch_options)

        # Créer le contexte avec les cookies
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )

        # Convertir et ajouter les cookies
        twitter_cookies = []
        for c in self.cookies:
            cookie = {
                "name": c.get("name"),
                "value": c.get("value"),
                "domain": ".x.com",
                "path": "/"
            }
            twitter_cookies.append(cookie)

        await self.context.add_cookies(twitter_cookies)

        # Créer la page
        self.page = await self.context.new_page()

        # Intercepter les réponses réseau
        self.page.on("response", self._handle_response)

        print("[PLAYWRIGHT] Navigateur prêt!")

    async def _handle_response(self, response: Response):
        """Intercepte les réponses GraphQL pour capturer les données utilisateurs."""
        if not self.is_capturing:
            return

        url = response.url

        # Détecter rate limit
        if response.status == 429:
            self.rate_limited = True
            # Extraire le temps d'attente du header si disponible
            retry_after = response.headers.get("retry-after", "60")
            try:
                self.rate_limit_wait = int(retry_after)
            except:
                self.rate_limit_wait = 60
            print(f"[PLAYWRIGHT] Rate limit détecté! Attente de {self.rate_limit_wait}s...")
            return

        # Capturer les réponses GraphQL Followers/Following
        if "/graphql/" in url and ("Followers" in url or "Following" in url):
            try:
                data = await response.json()
                users = self._extract_users_from_response(data)
                if users:
                    print(f"[PLAYWRIGHT] Capturé {len(users)} utilisateurs (total: {len(self.captured_users) + len(users)})")
                    self.captured_users.extend(users)
            except Exception as e:
                print(f"[PLAYWRIGHT] Erreur parsing réponse: {e}")

    def _extract_users_from_response(self, data: dict) -> list:
        """Extrait les utilisateurs d'une réponse GraphQL avec le VRAI can_dm."""
        users = []

        try:
            # Naviguer dans la structure de réponse
            result = data.get("data", {}).get("user", {}).get("result", {})
            timeline = result.get("timeline", {}).get("timeline", {})
            instructions = timeline.get("instructions", [])

            for instruction in instructions:
                if instruction.get("type") != "TimelineAddEntries":
                    continue

                entries = instruction.get("entries", [])

                for entry in entries:
                    entry_id = entry.get("entryId", "")

                    # Skip cursors
                    if "cursor" in entry_id.lower():
                        continue

                    # Extraire les données utilisateur
                    content = entry.get("content", {})
                    item_content = content.get("itemContent", {})

                    if item_content.get("itemType") != "TimelineUser":
                        continue

                    user_result = item_content.get("user_results", {}).get("result", {})

                    if not user_result:
                        continue

                    # Extraire les données - Apify format
                    # Le VRAI can_dm est directement dans user_result
                    can_dm = user_result.get("can_dm", False)
                    can_media_tag = user_result.get("can_media_tag", False)

                    # Fallback sur les sous-objets si nécessaire
                    if not can_dm and "dm_permissions" in user_result:
                        can_dm = user_result.get("dm_permissions", {}).get("can_dm", False)
                    if not can_media_tag and "media_permissions" in user_result:
                        can_media_tag = user_result.get("media_permissions", {}).get("can_media_tag", False)

                    # Données de base
                    user_id = user_result.get("rest_id") or user_result.get("id")

                    # Username peut être à différents endroits
                    username = (
                        user_result.get("screen_name") or
                        user_result.get("core", {}).get("screen_name") or
                        user_result.get("legacy", {}).get("screen_name")
                    )

                    name = (
                        user_result.get("name") or
                        user_result.get("core", {}).get("name") or
                        user_result.get("legacy", {}).get("name", "")
                    )

                    if not username or not user_id:
                        continue

                    # Autres données
                    legacy = user_result.get("legacy", {})
                    privacy = user_result.get("privacy", {})
                    location_obj = user_result.get("location", {})

                    protected = (
                        user_result.get("protected", False) or
                        privacy.get("protected", False) or
                        legacy.get("protected", False)
                    )

                    description = (
                        user_result.get("description", "") or
                        legacy.get("description", "")
                    )

                    profile_image = (
                        user_result.get("profile_image_url_https", "") or
                        legacy.get("profile_image_url_https", "")
                    )
                    if profile_image:
                        profile_image = profile_image.replace("_normal", "_400x400")

                    location = ""
                    if isinstance(location_obj, dict):
                        location = location_obj.get("location", "")
                    elif isinstance(location_obj, str):
                        location = location_obj
                    if not location:
                        location = legacy.get("location", "")

                    followers_count = user_result.get("followers_count", 0) or legacy.get("followers_count", 0)
                    following_count = user_result.get("friends_count", 0) or legacy.get("friends_count", 0)
                    tweets_count = user_result.get("statuses_count", 0) or legacy.get("statuses_count", 0)

                    created_at = user_result.get("created_at", "") or legacy.get("created_at", "")

                    verified = user_result.get("is_blue_verified", False)

                    # Détection du genre
                    gender = detect_gender(name)

                    user_data = {
                        "id": str(user_id),
                        "username": username,
                        "name": name,
                        "bio": description,
                        "followers_count": followers_count,
                        "following_count": following_count,
                        "tweets_count": tweets_count,
                        "verified": verified,
                        "protected": protected,
                        "profile_image": profile_image,
                        "location": location,
                        "created_at": created_at,
                        "can_dm": can_dm,  # VRAI can_dm de Twitter!
                        "can_media_tag": can_media_tag,
                        "gender": gender,
                    }

                    users.append(user_data)

        except Exception as e:
            print(f"[PLAYWRIGHT] Erreur extraction users: {e}")
            import traceback
            traceback.print_exc()

        return users

    async def get_user_info(self, username: str) -> Optional[dict]:
        """Récupère les infos d'un utilisateur en visitant son profil."""
        print(f"[PLAYWRIGHT] Récupération info pour @{username}...")

        await self.page.goto(f"https://x.com/{username}", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)

        try:
            await self.page.wait_for_selector('[data-testid="UserName"]', timeout=10000)

            followers_link = await self.page.query_selector(f'a[href="/{username}/followers"]')
            followers_text = await followers_link.inner_text() if followers_link else "0"

            following_link = await self.page.query_selector(f'a[href="/{username}/following"]')
            following_text = await following_link.inner_text() if following_link else "0"

            def parse_count(text):
                text = text.strip().upper()
                if "K" in text:
                    return int(float(text.replace("K", "").replace(",", ".")) * 1000)
                elif "M" in text:
                    return int(float(text.replace("M", "").replace(",", ".")) * 1000000)
                return int(text.replace(",", "").replace(" ", "") or "0")

            return {
                "username": username,
                "followers_count": parse_count(followers_text.split()[0] if followers_text else "0"),
                "following_count": parse_count(following_text.split()[0] if following_text else "0"),
            }

        except Exception as e:
            print(f"[PLAYWRIGHT] Erreur get_user_info: {e}")
            return None

    async def scrape_followers(
        self,
        username: str,
        list_type: str = "followers",
        max_records: Optional[int] = None,
        on_progress: Optional[callable] = None
    ) -> AsyncGenerator[dict, None]:
        """
        Scrape les followers/following en scrollant la page (méthode Apify).
        Récupère le VRAI can_dm depuis les réponses GraphQL.

        Args:
            username: Le @username du compte cible
            list_type: "followers" ou "following"
            max_records: Nombre max de records à récupérer
            on_progress: Callback appelé avec (count, user) à chaque nouveau user
        """
        print(f"[PLAYWRIGHT] Scraping {list_type} de @{username}...")

        # Réinitialiser la capture
        self.captured_users = []
        self.is_capturing = True
        self.rate_limited = False
        yielded_ids = set()

        # Aller sur la page followers/following
        url = f"https://x.com/{username}/{list_type}"
        await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # Attendre que la liste se charge
        try:
            await self.page.wait_for_selector('[data-testid="cellInnerDiv"]', timeout=15000)
        except:
            print("[PLAYWRIGHT] Timeout en attendant la liste")

        await asyncio.sleep(3)

        last_count = 0
        no_new_users_count = 0
        scroll_attempts = 0
        max_scroll_attempts = 500  # Plus de tentatives

        while scroll_attempts < max_scroll_attempts:
            # Vérifier rate limit
            if self.rate_limited:
                wait_time = self.rate_limit_wait or 390
                print(f"[PLAYWRIGHT] Rate limit! Attente de {wait_time} secondes...")

                if on_progress:
                    on_progress(len(yielded_ids), None, f"Rate limit - attente {wait_time}s")

                await asyncio.sleep(wait_time)
                self.rate_limited = False
                self.rate_limit_wait = 0

                # Recharger la page après rate limit
                await self.page.reload(wait_until="domcontentloaded")
                await asyncio.sleep(3)
                continue

            # Yield les nouveaux utilisateurs capturés
            for user in self.captured_users:
                if user["id"] not in yielded_ids:
                    yielded_ids.add(user["id"])

                    if on_progress:
                        on_progress(len(yielded_ids), user, None)

                    yield user

                    # Vérifier limite
                    if max_records and len(yielded_ids) >= max_records:
                        print(f"[PLAYWRIGHT] Limite atteinte: {max_records}")
                        self.is_capturing = False
                        return

            # Vérifier si on a de nouveaux users
            if len(yielded_ids) == last_count:
                no_new_users_count += 1
                if no_new_users_count >= 20:  # Plus de patience
                    print("[PLAYWRIGHT] Plus de nouveaux utilisateurs, fin du scraping")
                    break
            else:
                no_new_users_count = 0
                last_count = len(yielded_ids)

            scroll_attempts += 1

            # === SCROLL AGRESSIF ===

            # 1. Scroll via JavaScript
            await self.page.evaluate("""
                () => {
                    window.scrollTo(0, document.body.scrollHeight);

                    // Scroll sur différents conteneurs
                    const containers = [
                        document.querySelector('main'),
                        document.querySelector('section[role="region"]'),
                        document.querySelector('[data-testid="primaryColumn"]')
                    ];

                    containers.forEach(c => {
                        if (c) c.scrollTop = c.scrollHeight;
                    });

                    // Scroll le dernier élément visible
                    const cells = document.querySelectorAll('[data-testid="cellInnerDiv"]');
                    if (cells.length > 0) {
                        cells[cells.length - 1].scrollIntoView({ behavior: 'instant', block: 'end' });
                    }
                }
            """)

            # 2. Touches clavier
            for _ in range(3):
                await self.page.keyboard.press("End")
                await asyncio.sleep(0.1)

            for _ in range(2):
                await self.page.keyboard.press("PageDown")
                await asyncio.sleep(0.1)

            # 3. Mouse wheel
            await self.page.mouse.wheel(0, 3000)

            # 4. Attendre le chargement
            wait_time = random.uniform(1.5, 3.0)
            await asyncio.sleep(wait_time)

            if scroll_attempts % 10 == 0:
                print(f"[PLAYWRIGHT] Scroll #{scroll_attempts} - Total: {len(yielded_ids)} users")

        self.is_capturing = False
        print(f"[PLAYWRIGHT] Scraping terminé: {len(yielded_ids)} utilisateurs")

    async def close(self):
        """Ferme le navigateur."""
        if self.browser:
            await self.browser.close()
            print("[PLAYWRIGHT] Navigateur fermé")


# Fonction utilitaire pour scraper de manière synchrone
def scrape_followers_sync(cookies: list, username: str, list_type: str = "followers", max_records: int = None, headless: bool = True):
    """
    Version synchrone du scraper pour utilisation simple.

    Returns:
        Liste de tous les utilisateurs scrapés avec le VRAI can_dm
    """
    async def _scrape():
        scraper = TwitterPlaywrightScraper(cookies=cookies, headless=headless)
        await scraper.start()

        users = []
        async for user in scraper.scrape_followers(username, list_type, max_records):
            users.append(user)
            dm_status = "DM OK" if user['can_dm'] else "DM Fermé"
            print(f"  {len(users)}. @{user['username']} - {dm_status}")

        await scraper.close()
        return users

    return asyncio.run(_scrape())


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python scraper_playwright.py <cookies.json> <username> [max_records]")
        sys.exit(1)

    cookies_file = sys.argv[1]
    username = sys.argv[2]
    max_records = int(sys.argv[3]) if len(sys.argv) > 3 else 100

    with open(cookies_file, "r") as f:
        cookies = json.load(f)

    users = scrape_followers_sync(cookies, username, "followers", max_records, headless=False)

    # Stats
    dm_ok = [u for u in users if u["can_dm"]]
    dm_closed = [u for u in users if not u["can_dm"]]

    print(f"\n=== Résultats ===")
    print(f"Total: {len(users)}")
    print(f"DM OK (vrai): {len(dm_ok)}")
    print(f"DM Fermé: {len(dm_closed)}")

    if users:
        print(f"\nTaux DM OK: {len(dm_ok)/len(users)*100:.1f}%")
