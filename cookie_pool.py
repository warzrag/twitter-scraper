"""
Pool de cookies avec rotation et gestion des cooldowns.

Format attendu pour cookies_pool.json :
[
  {"user": "alice", "auth_token": "...", "ct0": "...", "cookie": "..."},
  {"user": "bob",   "auth_token": "...", "ct0": "..."}
]

Etat persiste dans cookies_pool_state.json (cooldowns, compteurs).
"""

import json
import time
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

POOL_FILE = "cookies_pool.json"
STATE_FILE = "cookies_pool_state.json"

# Cooldowns en secondes par type d'erreur
COOLDOWN_429 = 15 * 60        # rate limit X
COOLDOWN_401 = 24 * 60 * 60   # cookie invalide / banni
COOLDOWN_403 = 60 * 60        # action bloquee

# Quota par defaut par compte (par jour)
MAX_REQUESTS_PER_DAY = 10000


class CookiePool:
    def __init__(self, pool_path: str = POOL_FILE, state_path: str = STATE_FILE):
        self.pool_path = Path(pool_path)
        self.state_path = Path(state_path)
        self.cookies = self._load_pool()
        self.state = self._load_state()
        if not self.cookies:
            raise ValueError(f"Pool vide. Place {pool_path} avec au moins un compte.")

    def _load_pool(self) -> list:
        if not self.pool_path.exists():
            return []
        return json.loads(self.pool_path.read_text(encoding="utf-8"))

    def _load_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self):
        self.state_path.write_text(json.dumps(self.state, indent=2, default=str), encoding="utf-8")

    def _entry_state(self, user: str) -> dict:
        if user not in self.state:
            self.state[user] = {
                "cooldown_until": None,
                "requests_today": 0,
                "day": datetime.utcnow().date().isoformat(),
                "last_used": None,
                "last_error": None,
                "first_seen": datetime.utcnow().isoformat(),
                "total_requests": 0,
            }
        # reset compteur quotidien
        today = datetime.utcnow().date().isoformat()
        if self.state[user].get("day") != today:
            self.state[user]["requests_today"] = 0
            self.state[user]["day"] = today
        return self.state[user]

    def _is_available(self, cookie: dict) -> bool:
        user = cookie.get("user", cookie.get("auth_token", "")[:8])
        st = self._entry_state(user)
        if st["requests_today"] >= MAX_REQUESTS_PER_DAY:
            return False
        cd = st.get("cooldown_until")
        if cd:
            try:
                if datetime.fromisoformat(cd) > datetime.utcnow():
                    return False
            except Exception:
                pass
        return True

    def get_next(self) -> Optional[dict]:
        """Retourne le prochain cookie utilisable (LRU parmi les disponibles)."""
        candidates = [c for c in self.cookies if self._is_available(c)]
        if not candidates:
            return None
        # tri par derniere utilisation (jamais utilise = priorite max)
        def last_used_key(c):
            user = c.get("user", c.get("auth_token", "")[:8])
            lu = self.state.get(user, {}).get("last_used")
            return lu or ""
        candidates.sort(key=last_used_key)
        choice = candidates[0]
        user = choice.get("user", choice.get("auth_token", "")[:8])
        st = self._entry_state(user)
        st["last_used"] = datetime.utcnow().isoformat()
        st["requests_today"] += 1
        st["total_requests"] = st.get("total_requests", 0) + 1
        if "first_seen" not in st:
            st["first_seen"] = datetime.utcnow().isoformat()
        self._save_state()
        return choice

    def to_dict(self, cookie: dict) -> dict:
        """Convertit l'entree pool en dict compatible scraper (auth_token, ct0)."""
        result = {"auth_token": cookie["auth_token"], "ct0": cookie["ct0"]}
        # parser cookie complet si fourni (format "k=v; k=v;")
        raw = cookie.get("cookie")
        if raw:
            for part in raw.split(";"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    k = k.strip()
                    if k and k not in result:
                        result[k] = v.strip()
        return result

    def get_proxy(self, cookie: dict) -> str | None:
        """Retourne l'URL proxy associee au cookie (ou None)."""
        return cookie.get("proxy")

    def report_error(self, cookie: dict, status: int):
        """Met le cookie en cooldown selon le code HTTP."""
        user = cookie.get("user", cookie.get("auth_token", "")[:8])
        st = self._entry_state(user)
        st["last_error"] = f"{status} @ {datetime.utcnow().isoformat()}"
        if status == 429:
            seconds = COOLDOWN_429
        elif status in (401, 403) and status == 401:
            seconds = COOLDOWN_401
        elif status == 403:
            seconds = COOLDOWN_403
        else:
            seconds = 5 * 60
        until = datetime.utcnow() + timedelta(seconds=seconds)
        st["cooldown_until"] = until.isoformat()
        self._save_state()
        print(f"[POOL] {user} en cooldown {seconds}s (HTTP {status})")

    def report_success(self, cookie: dict):
        user = cookie.get("user", cookie.get("auth_token", "")[:8])
        st = self._entry_state(user)
        st["cooldown_until"] = None
        self._save_state()

    def status(self) -> list:
        """Renvoie un snapshot de l'etat de chaque compte (pour debug/UI)."""
        out = []
        for c in self.cookies:
            user = c.get("user", c.get("auth_token", "")[:8])
            st = self._entry_state(user)
            out.append({
                "user": user,
                "available": self._is_available(c),
                "requests_today": st["requests_today"],
                "cooldown_until": st.get("cooldown_until"),
                "last_error": st.get("last_error"),
                "last_used": st.get("last_used"),
                "first_seen": st.get("first_seen"),
                "total_requests": st.get("total_requests", 0),
            })
        return out


if __name__ == "__main__":
    # Test rapide : affiche l'etat du pool
    pool = CookiePool()
    print(f"Pool chargee : {len(pool.cookies)} comptes")
    for s in pool.status():
        flag = "OK" if s["available"] else "COOLDOWN"
        print(f"  [{flag}] {s['user']:20s} reqs={s['requests_today']:4d}  cd={s['cooldown_until']}")
