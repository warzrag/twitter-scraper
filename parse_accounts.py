"""
Parse un fichier de comptes au format shop standard et genere cookies_pool.json.

Format accepte (1 ligne par compte) :
    user:password:email:email_password:totp_secret:auth_token
    user:password:email:email_password:ct0:auth_token:totp_secret

Le script tolere des variantes :
- Avec/sans email_password
- Avec/sans totp_secret
- Auto-detection ct0 (long) vs auth_token (40 chars hex)
- Si ct0 manque, l'API web tentera de le recuperer avec auth_token

Usage:
    python parse_accounts.py accounts.txt
    (sortie : cookies_pool.json)
"""

import json
import re
import sys
from pathlib import Path

INPUT_FILE = sys.argv[1] if len(sys.argv) > 1 else "accounts.txt"
OUTPUT_FILE = "cookies_pool.json"

HEX40 = re.compile(r"^[a-f0-9]{40}$", re.IGNORECASE)
HEX_LONG = re.compile(r"^[a-f0-9]{60,}$", re.IGNORECASE)
TOTP = re.compile(r"^[A-Z2-7]{16,}$")


def parse_line(line: str) -> dict | None:
    parts = [p.strip() for p in line.strip().split(":")]
    if len(parts) < 2:
        return None

    user = parts[0]
    # Les champs sensibles de login ne sont pas conserves. Seuls les cookies
    # utiles au scraper sont ecrits dans cookies_pool.json.
    ct0 = None
    auth_token = None

    # On scanne les autres colonnes et on devine
    for p in parts[2:]:
        if not p:
            continue
        if HEX40.match(p) and not auth_token:
            auth_token = p
        elif HEX_LONG.match(p) and not ct0:
            ct0 = p

    if not auth_token:
        return None  # cookies indispensables

    entry = {
        "user": user,
        "auth_token": auth_token,
    }
    if ct0:
        entry["ct0"] = ct0
    return entry


def main():
    p = Path(INPUT_FILE)
    if not p.exists():
        print(f"[ERREUR] Fichier {INPUT_FILE} introuvable")
        return

    pool = []
    skipped = []
    for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not ln.strip() or ln.startswith("#"):
            continue
        entry = parse_line(ln)
        if entry:
            pool.append(entry)
        else:
            skipped.append(i)

    Path(OUTPUT_FILE).write_text(json.dumps(pool, indent=2), encoding="utf-8")
    print(f"[OK] {len(pool)} comptes ecrits dans {OUTPUT_FILE}")
    if skipped:
        print(f"[WARN] Lignes ignorees (cookies manquants) : {skipped}")
    print()
    print("Apercu :")
    for c in pool[:3]:
        ct0 = c.get("ct0", "")
        print(f"  {c['user']:20s}  ct0={(ct0[:12] + '...') if ct0 else 'manquant'}  auth={c['auth_token'][:12]}...")
    if len(pool) > 3:
        print(f"  ... et {len(pool) - 3} autres")


if __name__ == "__main__":
    main()
