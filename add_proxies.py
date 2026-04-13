"""
Associe un proxy a chaque cookie du pool.

Format proxies.txt (1 ligne par proxy) :
    ip:port:user:pass

Le script associe le 1er proxy au 1er cookie, le 2eme au 2eme, etc.
S'il y a moins de proxies que de cookies, rotation cyclique.

Usage:
    python add_proxies.py proxies.txt
"""

import json
import sys
from pathlib import Path

POOL_FILE = "cookies_pool.json"


def main():
    if len(sys.argv) < 2:
        print("Usage: python add_proxies.py proxies.txt")
        return

    proxies_file = sys.argv[1]
    if not Path(proxies_file).exists():
        print(f"[ERREUR] {proxies_file} introuvable")
        return

    pool_path = Path(POOL_FILE)
    if not pool_path.exists():
        print(f"[ERREUR] {POOL_FILE} introuvable. Lance d'abord parse_accounts.py.")
        return

    pool = json.loads(pool_path.read_text(encoding="utf-8"))
    proxies = []
    for ln in Path(proxies_file).read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split(":")
        if len(parts) == 4:
            ip, port, user, pwd = parts
            proxies.append(f"http://{user}:{pwd}@{ip}:{port}")
        elif len(parts) == 2:
            ip, port = parts
            proxies.append(f"http://{ip}:{port}")
        else:
            print(f"[SKIP] format invalide : {ln}")

    if not proxies:
        print("Aucun proxy valide.")
        return

    print(f"Pool : {len(pool)} cookies, Proxies : {len(proxies)}")

    for i, cookie in enumerate(pool):
        cookie["proxy"] = proxies[i % len(proxies)]

    pool_path.write_text(json.dumps(pool, indent=2), encoding="utf-8")
    print(f"[OK] Proxies associes a {len(pool)} cookies dans {POOL_FILE}")
    for c in pool[:3]:
        print(f"  {c['user']:20s} -> {c['proxy'].split('@')[-1]}")


if __name__ == "__main__":
    main()
