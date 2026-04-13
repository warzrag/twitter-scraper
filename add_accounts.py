"""
Ajoute des comptes au cookies_pool.json existant SANS casser l'etat
(les cooldowns et compteurs des comptes deja presents sont conserves).

Usage:
    python add_accounts.py nouveaux.txt

Format de nouveaux.txt : idem accounts.txt
    user:password:email:mdp_email:ct0:auth_token:totp_secret
"""

import json
import sys
from pathlib import Path
from parse_accounts import parse_line

POOL_FILE = "cookies_pool.json"


def main():
    if len(sys.argv) < 2:
        print("Usage: python add_accounts.py <fichier_nouveaux_comptes.txt>")
        return

    input_file = sys.argv[1]
    if not Path(input_file).exists():
        print(f"[ERREUR] {input_file} introuvable")
        return

    # Charger le pool existant
    pool_path = Path(POOL_FILE)
    if pool_path.exists():
        pool = json.loads(pool_path.read_text(encoding="utf-8"))
    else:
        pool = []

    existing_users = {p["user"].lower() for p in pool if p.get("user")}
    existing_tokens = {p["auth_token"] for p in pool if p.get("auth_token")}

    added = 0
    skipped_dup = 0
    skipped_bad = 0

    for ln in Path(input_file).read_text(encoding="utf-8").splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        entry = parse_line(ln)
        if not entry:
            skipped_bad += 1
            continue
        # Dedup par user ou auth_token
        if entry["user"].lower() in existing_users or entry["auth_token"] in existing_tokens:
            skipped_dup += 1
            continue
        pool.append(entry)
        existing_users.add(entry["user"].lower())
        existing_tokens.add(entry["auth_token"])
        added += 1

    pool_path.write_text(json.dumps(pool, indent=2), encoding="utf-8")

    print(f"[OK] {added} nouveaux comptes ajoutes")
    print(f"     {skipped_dup} doublons ignores")
    print(f"     {skipped_bad} lignes invalides")
    print(f"Pool total : {len(pool)} comptes dans {POOL_FILE}")


if __name__ == "__main__":
    main()
