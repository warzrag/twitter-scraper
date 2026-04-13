"""
Parse un fichier de comptes au format shop standard et genere cookies_pool.json.

Format attendu (1 ligne par compte) :
    user:password:email:email_password:ct0:auth_token:totp_secret

Le script tolere des variantes :
- Avec/sans email_password
- Avec/sans totp_secret
- Auto-detection ct0 (long) vs auth_token (40 chars hex)

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
    password = parts[1]
    email = None
    email_pwd = None
    ct0 = None
    auth_token = None
    totp = None

    # On scanne les autres colonnes et on devine
    for p in parts[2:]:
        if not p:
            continue
        if "@" in p and not email:
            email = p
        elif HEX40.match(p) and not auth_token:
            auth_token = p
        elif HEX_LONG.match(p) and not ct0:
            ct0 = p
        elif TOTP.match(p) and not totp:
            totp = p
        elif not email_pwd and not (HEX40.match(p) or HEX_LONG.match(p) or TOTP.match(p)):
            email_pwd = p

    if not auth_token or not ct0:
        return None  # cookies indispensables

    entry = {
        "user": user,
        "password": password,
        "auth_token": auth_token,
        "ct0": ct0,
    }
    if email:
        entry["email"] = email
    if email_pwd:
        entry["email_password"] = email_pwd
    if totp:
        entry["totp"] = totp
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
        print(f"  {c['user']:20s}  ct0={c['ct0'][:12]}...  auth={c['auth_token'][:12]}...  2fa={'oui' if c.get('totp') else 'non'}")
    if len(pool) > 3:
        print(f"  ... et {len(pool) - 3} autres")


if __name__ == "__main__":
    main()
