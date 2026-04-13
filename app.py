#!/usr/bin/env python3
"""
Twitter/X Scraper - Interface Web
Backend FastAPI avec WebSocket pour le scraping en temps réel
"""

import json
import asyncio
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional
import csv
import io

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from pydantic import BaseModel
import httpx

# Import des scrapers
from scraper import TwitterScraper, extract_username, parse_cookies
from scraper_playwright import TwitterPlaywrightScraper
from scraper_apify import ApifyStyleScraper
from cookie_pool import CookiePool

app = FastAPI(title="Twitter/X Scraper", version="1.0.0")

# Stockage des jobs en cours
active_jobs = {}
completed_jobs = {}

# Modèles Pydantic
class ScrapeRequest(BaseModel):
    target: str
    list_type: str = "followers"
    max_records: Optional[int] = None
    min_wait: float = 3
    max_wait: float = 15
    cookies: list
    proxy: Optional[str] = None
    mode: str = "api"  # "api" (rapide, ~85% can_dm) ou "playwright" (lent, 100% can_dm)


class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    total: int
    current_user: Optional[str]
    users_scraped: int
    error: Optional[str]


# API Endpoints
from fastapi.responses import RedirectResponse


@app.get("/")
async def index():
    return RedirectResponse(url="/queue")


@app.get("/scraper", response_class=HTMLResponse)
async def scraper_page():
    """Ancienne page scraper (accessible via /scraper si besoin)"""
    return FileResponse("static/index.html")


@app.get("/dm-checker", response_class=HTMLResponse)
async def dm_checker():
    """Servir le DM Checker"""
    return FileResponse("static/dm-checker.html")


@app.get("/extractor", response_class=HTMLResponse)
async def extractor():
    """Servir l'Extracteur de usernames"""
    return FileResponse("static/extractor.html")


@app.post("/api/scrape")
async def start_scrape(request: ScrapeRequest):
    """Démarrer un nouveau job de scraping"""
    job_id = str(uuid.uuid4())[:8]

    active_jobs[job_id] = {
        "status": "pending",
        "progress": 0,
        "total": 0,
        "current_user": None,
        "users": [],
        "error": None,
        "request": request.dict(),
        "started_at": datetime.now().isoformat(),
    }

    return {"job_id": job_id, "message": "Job créé, connectez-vous au WebSocket pour suivre la progression"}


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Récupérer le statut d'un job"""
    if job_id in active_jobs:
        job = active_jobs[job_id]
        return JobStatus(
            job_id=job_id,
            status=job["status"],
            progress=job["progress"],
            total=job["total"],
            current_user=job["current_user"],
            users_scraped=len(job["users"]),
            error=job["error"],
        )
    elif job_id in completed_jobs:
        job = completed_jobs[job_id]
        return JobStatus(
            job_id=job_id,
            status="completed",
            progress=job["total"],
            total=job["total"],
            current_user=None,
            users_scraped=len(job["users"]),
            error=job.get("error"),
        )
    raise HTTPException(status_code=404, detail="Job non trouvé")


@app.get("/api/jobs/{job_id}/download")
async def download_results(job_id: str, format: str = "csv"):
    """Télécharger les résultats d'un job"""
    job = completed_jobs.get(job_id) or active_jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")

    users = job.get("users", [])
    if not users:
        raise HTTPException(status_code=400, detail="Pas de données à télécharger")

    username = job.get("username", "export")
    list_type = job.get("list_type", "followers")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if format == "json":
        content = json.dumps(users, ensure_ascii=False, indent=2)
        filename = f"{username}_{list_type}_{timestamp}.json"
        media_type = "application/json"
    else:
        output = io.StringIO()
        if users:
            writer = csv.DictWriter(output, fieldnames=users[0].keys())
            writer.writeheader()
            writer.writerows(users)
        content = output.getvalue()
        filename = f"{username}_{list_type}_{timestamp}.csv"
        media_type = "text/csv"

    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


validate_jobs = {}


@app.post("/api/jobs/{job_id}/auto-validate")
async def auto_validate(job_id: str):
    """Lance l'auto-validation d'un scrape avec le compte clean configure."""
    job = completed_jobs.get(job_id) or active_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")

    # Utilise le pool de 13 cookies en rotation (rapide)
    try:
        pool = CookiePool()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Pool indispo: {e}")

    candidates = [u for u in job.get("users", []) if u.get("can_dm") in (True, "true", "True")]
    pairs = [(u.get("id") or u.get("user_id"), u.get("username", "")) for u in candidates]
    pairs = [(uid, uname) for uid, uname in pairs if uid and uname]
    if not pairs:
        raise HTTPException(status_code=400, detail="Aucun candidat can_dm a valider")

    vid = str(uuid.uuid4())[:8]
    validate_jobs[vid] = {
        "status": "running",
        "total": len(pairs),
        "done": 0,
        "validated": [],
        "scrape_job": job_id,
        "started_at": datetime.now().isoformat(),
    }

    async def worker():
        try:
            GLOBAL_DELAY = 0.5  # 13 cookies LRU * 0.5s = ~6.5s par cookie (safe)
            for uid, uname in pairs:
                cookie = pool.get_next()
                if not cookie:
                    await asyncio.sleep(60)
                    continue
                cookies_dict = pool.to_dict(cookie)
                proxy = pool.get_proxy(cookie)
                try:
                    scraper = TwitterScraper(cookies=cookies_dict, proxy=proxy, min_wait=0.1, max_wait=0.3)
                    can_dm = scraper.check_can_dm(str(uid))
                    scraper.close()
                    pool.report_success(cookie)
                    if can_dm:
                        validate_jobs[vid]["validated"].append(uname)
                except httpx.HTTPStatusError as he:
                    pool.report_error(cookie, he.response.status_code)
                except Exception:
                    pool.report_error(cookie, 500)
                validate_jobs[vid]["done"] += 1
                await asyncio.sleep(GLOBAL_DELAY)
            validate_jobs[vid]["status"] = "completed"
        except Exception as e:
            validate_jobs[vid]["status"] = "error"
            validate_jobs[vid]["error"] = str(e)

    asyncio.create_task(worker())
    return {"validate_id": vid, "total": len(pairs)}


@app.get("/api/validate/{vid}")
async def validate_status(vid: str):
    j = validate_jobs.get(vid)
    if not j:
        raise HTTPException(status_code=404)
    return {
        "status": j["status"],
        "total": j["total"],
        "done": j["done"],
        "validated_count": len(j["validated"]),
        "validated": j["validated"] if j["status"] == "completed" else [],
    }


# ========== QUEUE MULTI-CIBLES ==========

queue_jobs = {}

HISTORY_FILE = Path("scraped_history.txt")


def load_history() -> set:
    if not HISTORY_FILE.exists():
        return set()
    return {ln.strip().lower() for ln in HISTORY_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()}


def append_history(usernames: list):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        for u in usernames:
            f.write(u + "\n")


@app.get("/api/history/stats")
async def history_stats():
    h = load_history()
    return {"total": len(h)}


@app.post("/api/history/clear")
async def history_clear():
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()
    return {"cleared": True}


class QueueStartRequest(BaseModel):
    targets: list  # liste de usernames cibles
    max_per_target: Optional[int] = None  # None = tout
    cookies: list  # cookies pour scraper (1 compte shop)
    parallel: int = 3  # nombre de scrapes en parallele


@app.post("/api/queue/start")
async def queue_start(request: QueueStartRequest):
    """Lance une queue multi-cibles : scrape + auto-valide chaque cible."""
    try:
        pool = CookiePool()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Pool indispo: {e}")

    targets = [t.strip().lstrip("@").replace("https://x.com/", "").replace("https://twitter.com/", "") for t in request.targets if t.strip()]
    if not targets:
        raise HTTPException(status_code=400, detail="Aucune cible")

    qid = str(uuid.uuid4())[:8]
    queue_jobs[qid] = {
        "status": "running",
        "targets": {t: {"status": "pending", "scraped": 0, "validated": 0, "candidates": 0, "checked": 0} for t in targets},
        "total_validated": 0,
        "all_validated": [],
        "started_at": datetime.now().isoformat(),
        "parallel": request.parallel,
    }

    scrape_cookies = parse_cookies(request.cookies)

    async def process_target(target: str):
        try:
            queue_jobs[qid]["targets"][target]["status"] = "scraping"
            scraper = TwitterScraper(cookies=scrape_cookies, min_wait=1.0, max_wait=3.0)
            info = scraper.get_user_info(target)
            if not info or not info.get("id"):
                queue_jobs[qid]["targets"][target]["status"] = "error_not_found"
                scraper.close()
                return

            user_id = str(info["id"])
            history = load_history()
            candidates = []  # (user_id, username)
            skipped_dup = 0
            count = 0
            try:
                for u in scraper.scrape_list_v1(user_id, list_type="followers", max_records=request.max_per_target, check_dm=False):
                    count += 1
                    uname = (u.get("username") or "").strip()
                    if u.get("can_dm") in (True, "true", "True"):
                        if uname.lower() in history:
                            skipped_dup += 1
                        else:
                            candidates.append((str(u.get("id") or u.get("user_id") or ""), uname))
                    queue_jobs[qid]["targets"][target]["scraped"] = count
            except Exception as e:
                print(f"[QUEUE] Scrape error {target}: {e}")
            scraper.close()
            queue_jobs[qid]["targets"][target]["skipped_dup"] = skipped_dup

            queue_jobs[qid]["targets"][target]["status"] = "validating"
            queue_jobs[qid]["targets"][target]["candidates"] = len(candidates)
            # Valide via pool
            validated_here = []
            for uid, uname in candidates:
                if not uid or not uname:
                    continue
                cookie = pool.get_next()
                if not cookie:
                    await asyncio.sleep(30)
                    continue
                cd = pool.to_dict(cookie)
                px = pool.get_proxy(cookie)
                try:
                    s = TwitterScraper(cookies=cd, proxy=px, min_wait=0.1, max_wait=0.3)
                    can_dm = s.check_can_dm(uid)
                    s.close()
                    pool.report_success(cookie)
                    if can_dm:
                        validated_here.append(uname)
                        queue_jobs[qid]["targets"][target]["validated"] += 1
                        queue_jobs[qid]["total_validated"] += 1
                        queue_jobs[qid]["all_validated"].append(uname)
                except httpx.HTTPStatusError as he:
                    pool.report_error(cookie, he.response.status_code)
                except Exception:
                    pool.report_error(cookie, 500)
                queue_jobs[qid]["targets"][target]["checked"] += 1
                await asyncio.sleep(0.4)

            queue_jobs[qid]["targets"][target]["status"] = "done"
        except Exception as e:
            queue_jobs[qid]["targets"][target]["status"] = "error"
            queue_jobs[qid]["targets"][target]["error"] = str(e)

    async def orchestrator():
        sem = asyncio.Semaphore(request.parallel)
        async def run(t):
            async with sem:
                await process_target(t)
        await asyncio.gather(*[run(t) for t in targets])
        # dedup final
        queue_jobs[qid]["all_validated"] = list(dict.fromkeys(queue_jobs[qid]["all_validated"]))
        queue_jobs[qid]["total_validated"] = len(queue_jobs[qid]["all_validated"])
        # Sauvegarde dans l'historique pour eviter de les ressortir au prochain run
        append_history(queue_jobs[qid]["all_validated"])
        queue_jobs[qid]["status"] = "completed"

    asyncio.create_task(orchestrator())
    return {"queue_id": qid, "targets_count": len(targets)}


@app.get("/api/queue/{qid}")
async def queue_status(qid: str):
    j = queue_jobs.get(qid)
    if not j:
        raise HTTPException(status_code=404)
    return {
        "status": j["status"],
        "targets": j["targets"],
        "total_validated": j["total_validated"],
        "parallel": j.get("parallel", 3),
        "all_validated": j["all_validated"] if j["status"] == "completed" else [],
    }


@app.get("/api/queue/{qid}/download")
async def queue_download(qid: str):
    j = queue_jobs.get(qid)
    if not j:
        raise HTTPException(status_code=404)
    content = "\n".join(j["all_validated"])
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=queue_validated_{qid}.txt"}
    )


@app.get("/queue", response_class=HTMLResponse)
async def queue_page():
    return FileResponse("static/queue.html")


# ========== /QUEUE ==========


@app.get("/api/validate/{vid}/download")
async def validate_download(vid: str):
    j = validate_jobs.get(vid)
    if not j:
        raise HTTPException(status_code=404)
    content = "\n".join(j["validated"])
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=validated_clean_{vid}.txt"}
    )


@app.get("/api/jobs/{job_id}/download-can-dm")
async def download_can_dm_only(job_id: str):
    """Telecharge un .txt avec uniquement les usernames can_dm=True (1 par ligne)."""
    job = completed_jobs.get(job_id) or active_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trouvé")

    users = job.get("users", [])
    can_dm_users = [u.get("username", "") for u in users if u.get("can_dm") in (True, "true", "True")]
    can_dm_users = [u for u in can_dm_users if u]

    username = job.get("username", "export")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{username}_can_dm_only_{timestamp}.txt"
    content = "\n".join(can_dm_users)

    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


class UserInfoRequest(BaseModel):
    username: str
    cookies: list


@app.post("/api/user-info")
async def get_user_info(request: UserInfoRequest):
    """
    Récupère les infos d'un utilisateur Twitter par son username.
    Retourne le vrai can_dm depuis l'API GraphQL (100% fiable).
    """
    try:
        cookies = parse_cookies(request.cookies)
        scraper = TwitterScraper(cookies=cookies, min_wait=0.5, max_wait=1)

        # Nettoyer le username (enlever @)
        username = request.username.strip().lstrip('@')

        user_info = scraper.get_user_info(username)
        scraper.close()

        if not user_info:
            return None

        return {
            "id": user_info.get("id"),
            "username": user_info.get("username"),
            "name": user_info.get("name"),
            "followers_count": user_info.get("followers_count", 0),
            "can_dm": user_info.get("can_dm", False),
            "protected": user_info.get("protected", False),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class VerifyDMRequest(BaseModel):
    user_id: str
    cookies: list


@app.post("/api/verify-dm")
async def verify_dm(request: VerifyDMRequest):
    """
    Vérifie si on peut envoyer un DM à un utilisateur via friendships/show.
    Retourne le VRAI statut can_dm (100% fiable).
    Rate limit: 15 requêtes / 15 minutes.
    """
    try:
        cookies = parse_cookies(request.cookies)
        scraper = TwitterScraper(cookies=cookies)
        can_dm = scraper.check_can_dm(request.user_id)
        scraper.close()
        return {"user_id": request.user_id, "can_dm": can_dm}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class VerifyDMBatchRequest(BaseModel):
    user_ids: list
    cookies: list


@app.post("/api/verify-dm-batch")
async def verify_dm_batch(request: VerifyDMBatchRequest):
    """
    Vérifie can_dm pour plusieurs utilisateurs via friendships/lookup.
    Peut vérifier jusqu'à 100 users par requête (1500 users / 15 min).
    """
    try:
        cookies = parse_cookies(request.cookies)
        scraper = TwitterScraper(cookies=cookies, min_wait=1, max_wait=2)

        # Use bulk method - 100 users per request, max 1500 total (15 requests)
        user_ids = request.user_ids[:1500]
        dm_results = scraper.check_can_dm_bulk(user_ids)

        results = [{"user_id": uid, "can_dm": dm_results.get(uid, False)} for uid in user_ids if uid in dm_results]

        scraper.close()
        return {"results": results, "checked": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== POOL ROTATION ENDPOINTS ==========

pool_jobs = {}  # job_id -> {status, total, done, results, error}


@app.get("/accounts", response_class=HTMLResponse)
async def accounts_page():
    return FileResponse("static/accounts.html")


@app.post("/api/pool/remove")
async def pool_remove(user: str):
    pool_path = Path("cookies_pool.json")
    if not pool_path.exists():
        raise HTTPException(status_code=404)
    pool = json.loads(pool_path.read_text(encoding="utf-8"))
    before = len(pool)
    pool = [c for c in pool if c.get("user", "").lower() != user.lower()]
    pool_path.write_text(json.dumps(pool, indent=2), encoding="utf-8")
    return {"removed": before - len(pool), "total": len(pool)}


class PoolAddRequest(BaseModel):
    raw: str  # texte colle : lignes user:pass:email:mdp_email:ct0:auth_token:totp


@app.post("/api/pool/add")
async def pool_add(request: PoolAddRequest):
    """Ajoute des comptes au cookies_pool.json via texte colle depuis l'UI."""
    from parse_accounts import parse_line

    pool_path = Path("cookies_pool.json")
    pool = json.loads(pool_path.read_text(encoding="utf-8")) if pool_path.exists() else []
    existing_users = {p.get("user", "").lower() for p in pool}
    existing_tokens = {p.get("auth_token", "") for p in pool}

    added = 0
    dup = 0
    bad = 0
    for ln in request.raw.splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        entry = parse_line(ln)
        if not entry:
            bad += 1
            continue
        if entry["user"].lower() in existing_users or entry["auth_token"] in existing_tokens:
            dup += 1
            continue
        pool.append(entry)
        existing_users.add(entry["user"].lower())
        existing_tokens.add(entry["auth_token"])
        added += 1

    pool_path.write_text(json.dumps(pool, indent=2), encoding="utf-8")
    return {"added": added, "duplicates": dup, "invalid": bad, "total": len(pool)}


@app.get("/api/pool/status")
async def pool_status():
    """Etat du pool de cookies."""
    try:
        pool = CookiePool()
        return {"total": len(pool.cookies), "accounts": pool.status()}
    except Exception as e:
        return {"error": str(e), "total": 0, "accounts": []}


class PoolVerifyRequest(BaseModel):
    user_ids: list = []  # liste de user_id a verifier (ou usernames, auto-resolu)


@app.post("/api/pool/verify-dm")
async def pool_verify_dm(request: PoolVerifyRequest):
    """
    Verifie can_dm en 100% fiable, avec rotation automatique du pool.
    Renvoie un job_id. Consulte /api/pool/job/{job_id} pour le suivi.
    """
    try:
        pool = CookiePool()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Pool invalide: {e}")

    job_id = str(uuid.uuid4())[:8]
    pool_jobs[job_id] = {
        "status": "running",
        "total": len(request.user_ids),
        "done": 0,
        "results": [],
        "error": None,
        "started_at": datetime.now().isoformat(),
    }

    async def worker():
        try:
            # Avec 13 cookies a 720/h chacun, on peut faire 13/5s = 2.6/s global
            # Avec marge: 0.5s entre chaque requete (= ~5/s par cookie max si LRU)
            GLOBAL_DELAY = 0.5
            for item in request.user_ids:
                item = str(item).strip().lstrip("@")
                if not item:
                    pool_jobs[job_id]["done"] += 1
                    continue

                cookie = pool.get_next()
                if not cookie:
                    await asyncio.sleep(60)
                    continue
                cookies_dict = pool.to_dict(cookie)
                proxy = pool.get_proxy(cookie)
                try:
                    scraper = TwitterScraper(cookies=cookies_dict, proxy=proxy, min_wait=0.1, max_wait=0.3)
                    if item.isdigit():
                        uid = item
                        display = item
                    else:
                        info = scraper.get_user_info(item)
                        if not info or not info.get("id"):
                            scraper.close()
                            pool_jobs[job_id]["results"].append({"user_id": item, "username": item, "can_dm": False, "error": "not_found"})
                            pool_jobs[job_id]["done"] += 1
                            await asyncio.sleep(GLOBAL_DELAY)
                            continue
                        uid = str(info["id"])
                        display = item
                    can_dm = scraper.check_can_dm(uid)
                    scraper.close()
                    pool.report_success(cookie)
                    pool_jobs[job_id]["results"].append({"user_id": uid, "username": display, "can_dm": can_dm})
                except httpx.HTTPStatusError as he:
                    pool.report_error(cookie, he.response.status_code)
                except Exception:
                    pool.report_error(cookie, 500)
                pool_jobs[job_id]["done"] += 1
                await asyncio.sleep(GLOBAL_DELAY)
            pool_jobs[job_id]["status"] = "completed"
        except Exception as e:
            pool_jobs[job_id]["status"] = "error"
            pool_jobs[job_id]["error"] = str(e)

    asyncio.create_task(worker())
    return {"job_id": job_id, "total": len(request.user_ids)}


@app.get("/api/pool/job/{job_id}")
async def pool_job_status(job_id: str):
    job = pool_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job inconnu")
    return {
        "status": job["status"],
        "total": job["total"],
        "done": job["done"],
        "can_dm_count": sum(1 for r in job["results"] if r["can_dm"]),
        "error": job.get("error"),
    }


@app.get("/api/pool/job/{job_id}/download")
async def pool_job_download(job_id: str):
    job = pool_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job inconnu")
    can_dm_ids = [r["user_id"] for r in job["results"] if r["can_dm"]]
    content = "\n".join(can_dm_ids)
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=can_dm_validated_{job_id}.txt"}
    )


# ========== /POOL ==========


class VerifyDMPlaywrightRequest(BaseModel):
    usernames: list
    cookies: list


@app.post("/api/verify-dm-playwright")
async def verify_dm_playwright(request: VerifyDMPlaywrightRequest):
    """
    Vérifie can_dm pour une liste d'usernames en utilisant Playwright.
    Visite le profil de chaque user et intercepte le GraphQL pour le vrai can_dm.
    Plus lent mais 100% fiable.
    """
    try:
        scraper = TwitterPlaywrightScraper(
            cookies=request.cookies,
            headless=True
        )
        await scraper.start()

        results = []
        for username in request.usernames[:50]:  # Max 50 pour éviter timeout
            try:
                # Visiter le profil pour déclencher une requête GraphQL
                await scraper.page.goto(f"https://x.com/{username}", wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)

                # Chercher le can_dm dans les réponses capturées
                can_dm = False
                for user in scraper.captured_users:
                    if user.get("username", "").lower() == username.lower():
                        can_dm = user.get("can_dm", False)
                        break

                results.append({"username": username, "can_dm": can_dm})
            except Exception as e:
                results.append({"username": username, "can_dm": False, "error": str(e)})

        await scraper.close()
        return {"results": results, "checked": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """WebSocket pour le scraping en temps réel avec API v1.1 (rapide et fiable)"""
    await websocket.accept()

    if job_id not in active_jobs:
        await websocket.send_json({"type": "error", "message": "Job non trouvé"})
        await websocket.close()
        return

    job = active_jobs[job_id]
    request = job["request"]
    scraper = None

    try:
        # Parser les paramètres
        username = extract_username(request["target"])
        cookies = parse_cookies(request["cookies"])

        await websocket.send_json({
            "type": "status",
            "message": f"Connexion à Twitter pour @{username}..."
        })

        # Utiliser le scraper API v1.1 (rapide, récupère tous les followers)
        scraper = TwitterScraper(
            cookies=cookies,
            min_wait=request.get("min_wait", 2),
            max_wait=request.get("max_wait", 5),
        )

        # Récupérer les infos du compte
        user_info = scraper.get_user_info(username)

        if not user_info:
            await websocket.send_json({
                "type": "error",
                "message": "Compte non trouvé ou cookies invalides"
            })
            job["status"] = "error"
            job["error"] = "Compte non trouvé ou cookies invalides"
            return

        job["username"] = username
        job["list_type"] = request["list_type"]
        job["user_info"] = user_info

        # Envoyer les infos du compte
        await websocket.send_json({
            "type": "user_info",
            "data": user_info
        })

        # Calculer le total
        total = user_info.get("followers_count", 0) if request["list_type"] == "followers" else user_info.get("following_count", 0)
        if request["max_records"]:
            total = min(total, request["max_records"])

        job["total"] = total
        job["status"] = "running"

        await websocket.send_json({
            "type": "start",
            "total": total,
            "list_type": request["list_type"]
        })

        # Scraper avec API v1.1 (200 users par requête, très rapide)
        # can_dm est basé sur can_media_tag (~85% fiable)
        count = 0
        for user in scraper.scrape_list_v1(
            user_info["id"],
            list_type=request["list_type"],
            max_records=request["max_records"],
        ):
            job["users"].append(user)
            count += 1
            job["progress"] = count
            job["current_user"] = user["username"]

            # Envoyer la mise à jour
            await websocket.send_json({
                "type": "progress",
                "count": count,
                "total": total,
                "user": user
            })

            # Petit délai pour ne pas surcharger le WebSocket
            await asyncio.sleep(0.01)

        # Terminé
        job["status"] = "completed"
        completed_jobs[job_id] = job

        await websocket.send_json({
            "type": "complete",
            "total_scraped": len(job["users"]),
            "message": f"Scraping terminé! {len(job['users'])} {request['list_type']} récupérés."
        })

    except WebSocketDisconnect:
        job["status"] = "cancelled"
        print(f"Job {job_id} annulé par le client")
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })
    finally:
        if scraper:
            scraper.close()
        if job_id in active_jobs and job["status"] in ["completed", "error"]:
            completed_jobs[job_id] = active_jobs.pop(job_id)


@app.websocket("/ws-playwright/{job_id}")
async def websocket_playwright_endpoint(websocket: WebSocket, job_id: str):
    """
    WebSocket pour le scraping avec GraphQL direct (comme Apify) - VRAI can_dm 100%
    50 users par requête, pagination par curseur.
    """
    await websocket.accept()

    if job_id not in active_jobs:
        await websocket.send_json({"type": "error", "message": "Job non trouvé"})
        await websocket.close()
        return

    job = active_jobs[job_id]
    request = job["request"]
    scraper = None

    try:
        # Parser les paramètres
        username = extract_username(request["target"])

        await websocket.send_json({
            "type": "status",
            "message": f"[Mode Apify] Démarrage du navigateur pour @{username}..."
        })

        # Utiliser le scraper Apify (GraphQL direct, 50 users par batch)
        scraper = ApifyStyleScraper(
            cookies=request["cookies"],
            headless=True
        )
        await scraper.start()

        job["username"] = username
        job["list_type"] = request["list_type"]

        # Calculer le total estimé (sera mis à jour après la première requête)
        total = request.get("max_records") or 10000  # Estimation par défaut
        job["total"] = total
        job["status"] = "running"

        await websocket.send_json({
            "type": "start",
            "total": total,
            "list_type": request["list_type"],
            "mode": "apify"
        })

        # Callback pour les mises à jour de progression
        async def on_progress(cnt, user, rate_limit_msg):
            if rate_limit_msg:
                await websocket.send_json({
                    "type": "rate_limit",
                    "message": rate_limit_msg,
                    "count": cnt
                })

        # Scraper avec GraphQL direct (VRAI can_dm! 50 users par batch)
        count = 0

        async for user in scraper.scrape_followers(
            username,
            list_type=request["list_type"],
            max_records=request["max_records"],
            on_progress=lambda cnt, user, msg: asyncio.create_task(
                websocket.send_json({
                    "type": "rate_limit" if msg else "batch_info",
                    "message": msg or f"Batch complété: {cnt} users",
                    "count": cnt
                })
            ) if msg else None
        ):
            job["users"].append(user)
            count += 1
            job["progress"] = count
            job["current_user"] = user["username"]

            # Envoyer la mise à jour
            await websocket.send_json({
                "type": "progress",
                "count": count,
                "total": total,
                "user": user
            })

            # Petit délai pour ne pas surcharger le WebSocket
            await asyncio.sleep(0.005)

        # Terminé
        job["status"] = "completed"
        completed_jobs[job_id] = job

        # Stats finales
        dm_ok = sum(1 for u in job["users"] if u.get("can_dm"))
        dm_closed = len(job["users"]) - dm_ok

        await websocket.send_json({
            "type": "complete",
            "total_scraped": len(job["users"]),
            "dm_ok": dm_ok,
            "dm_closed": dm_closed,
            "message": f"Scraping terminé! {len(job['users'])} {request['list_type']} récupérés. DM OK: {dm_ok}, DM Fermé: {dm_closed}"
        })

    except WebSocketDisconnect:
        job["status"] = "cancelled"
        print(f"Job {job_id} annulé par le client")
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        import traceback
        traceback.print_exc()
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })
    finally:
        if scraper:
            await scraper.close()
        if job_id in active_jobs and job["status"] in ["completed", "error"]:
            completed_jobs[job_id] = active_jobs.pop(job_id)


# Servir les fichiers statiques
app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
