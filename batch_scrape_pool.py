"""
Scrape parallele de plusieurs comptes cibles avec rotation du pool de cookies.
Mode Playwright (100% can_dm fiable).

Usage:
    python batch_scrape_pool.py targets.txt
    (targets.txt = 1 username par ligne, sans @)

Sortie:
    output_can_dm_YYYYMMDD_HHMMSS.csv  (uniquement les can_dm=True)

Config:
    PARALLEL_WORKERS: nombre de scrapes en parallele (defaut 3)
    MAX_PER_TARGET: max followers par cible (None = tout)
"""

import asyncio
import csv
import sys
from datetime import datetime
from pathlib import Path

from cookie_pool import CookiePool
from scraper_playwright import TwitterPlaywrightScraper

PARALLEL_WORKERS = 3       # 3 navigateurs en parallele (ajuste selon ta RAM)
MAX_PER_TARGET = 200       # None = tout, sinon ex: 5000 (200 = test rapide)
OUTPUT_PREFIX = "output_can_dm"


def cookies_to_playwright_format(cookies_dict: dict) -> list:
    """Convertit {auth_token, ct0} en format playwright [{name, value}, ...]"""
    return [{"name": k, "value": v} for k, v in cookies_dict.items()]


async def scrape_one_target(target: str, cookie_entry: dict, pool: CookiePool, results: list, lock: asyncio.Lock):
    """Scrape un compte cible avec un cookie donne."""
    user = cookie_entry.get("user", "?")
    print(f"[{user}] Demarrage scrape de @{target}...")

    cookies_dict = pool.to_dict(cookie_entry)
    pl_cookies = cookies_to_playwright_format(cookies_dict)
    proxy_url = pool.get_proxy(cookie_entry)
    if proxy_url:
        print(f"[{user}] Proxy: {proxy_url.split('@')[-1]}")

    scraper = TwitterPlaywrightScraper(cookies=pl_cookies, headless=True, proxy=proxy_url)
    count = 0
    can_dm_count = 0
    try:
        await scraper.start()
        async for user_data in scraper.scrape_followers(
            username=target,
            list_type="followers",
            max_records=MAX_PER_TARGET,
        ):
            count += 1
            if user_data.get("can_dm"):
                can_dm_count += 1
                async with lock:
                    user_data["_source_target"] = target
                    results.append(user_data)
            if count % 100 == 0:
                print(f"[{user}] @{target}: {count} scrapes, {can_dm_count} can_dm")
        pool.report_success(cookie_entry)
    except Exception as e:
        print(f"[{user}] Erreur sur @{target}: {e}")
        pool.report_error(cookie_entry, 500)
    finally:
        try:
            await scraper.close()
        except Exception:
            pass
    print(f"[{user}] FIN @{target}: {count} scrapes, {can_dm_count} can_dm garde")


async def worker(queue: asyncio.Queue, pool: CookiePool, results: list, lock: asyncio.Lock):
    """Worker qui consomme la queue de targets en piochant un cookie a chaque tour."""
    while True:
        target = await queue.get()
        if target is None:
            queue.task_done()
            break
        cookie = pool.get_next()
        if not cookie:
            print(f"[QUEUE] Aucun cookie dispo, attente 60s avant @{target}")
            await asyncio.sleep(60)
            await queue.put(target)
            queue.task_done()
            continue
        try:
            await scrape_one_target(target, cookie, pool, results, lock)
        except Exception as e:
            print(f"[QUEUE] Erreur worker: {e}")
        queue.task_done()


def save_csv(results: list, path: str):
    if not results:
        print("Aucun resultat a sauvegarder.")
        return
    keys = list(results[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(results)
    print(f"[SAVED] {len(results)} can_dm dans {path}")


def dedup(results: list) -> list:
    """Supprime les doublons par user_id."""
    seen = set()
    out = []
    for r in results:
        uid = r.get("id") or r.get("user_id") or r.get("username")
        if uid and uid not in seen:
            seen.add(uid)
            out.append(r)
    return out


async def main():
    if len(sys.argv) < 2:
        print("Usage: python batch_scrape_pool.py targets.txt")
        return

    targets_file = sys.argv[1]
    if not Path(targets_file).exists():
        print(f"[ERREUR] {targets_file} introuvable")
        return

    targets = [
        ln.strip().lstrip("@")
        for ln in Path(targets_file).read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    if not targets:
        print("Aucune cible dans le fichier.")
        return

    pool = CookiePool()
    print(f"Pool : {len(pool.cookies)} cookies")
    print(f"Cibles : {len(targets)}")
    print(f"Workers paralleles : {PARALLEL_WORKERS}")
    print()

    results = []
    lock = asyncio.Lock()
    queue: asyncio.Queue = asyncio.Queue()
    for t in targets:
        await queue.put(t)
    for _ in range(PARALLEL_WORKERS):
        await queue.put(None)  # sentinelles

    workers = [asyncio.create_task(worker(queue, pool, results, lock)) for _ in range(PARALLEL_WORKERS)]
    await queue.join()
    for w in workers:
        await w

    results = dedup(results)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = f"{OUTPUT_PREFIX}_{timestamp}.csv"
    save_csv(results, output)


if __name__ == "__main__":
    asyncio.run(main())
