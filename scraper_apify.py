#!/usr/bin/env python3
"""
Twitter/X Scraper - Mode Apify
Appels GraphQL directs avec curseur (comme Apify fait)
Récupère le VRAI can_dm - 50 users par requête
"""

import json
import asyncio
import time
import random
import re
from urllib.parse import urlparse, parse_qs, parse_qsl, urlencode
from typing import Optional, AsyncGenerator
from playwright.async_api import async_playwright, Page, Request, Response

from gender_detector import detect_gender


class ApifyStyleScraper:
    """
    Scraper Twitter qui fait des appels GraphQL directs (comme Apify).
    50 users par requête, VRAI can_dm.

    Stratégie:
    1. Capturer la PREMIERE requête GraphQL que Twitter fait (avec tous ses headers)
    2. Extraire le curseur de la réponse
    3. Réutiliser les mêmes headers/features pour faire nos propres requêtes avec curseur
    """

    def __init__(self, cookies: list, headless: bool = True):
        self.cookies = cookies
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None
        self.auth_token = None
        self.csrf_token = None

        # Pour capturer les détails de la requête originale
        self.captured_request_headers = None
        self.captured_features = None
        self.captured_variables_template = None
        self._debug_dm_samples = 0
        self.last_stop_reason = None

    def _extract_timeline_users_and_cursor(self, data: dict) -> tuple[list, Optional[str]]:
        """Extract TimelineUser results and bottom cursor from current X GraphQL shapes."""
        users = []
        cursor = None

        def walk(node):
            nonlocal cursor
            if isinstance(node, dict):
                entry_id = str(node.get("entryId") or node.get("entry_id") or "")
                if "cursor-bottom" in entry_id.lower():
                    value = node.get("content", {}).get("value") if isinstance(node.get("content"), dict) else None
                    if value:
                        cursor = value

                content = node.get("content")
                if isinstance(content, dict):
                    value = content.get("value")
                    cursor_type = content.get("cursorType")
                    if value and str(cursor_type).lower() == "bottom":
                        cursor = value

                item_content = node.get("itemContent")
                if isinstance(item_content, dict) and item_content.get("itemType") == "TimelineUser":
                    result = item_content.get("user_results", {}).get("result", {})
                    if result:
                        users.append(result)

                if "user_results" in node and isinstance(node.get("user_results"), dict):
                    result = node.get("user_results", {}).get("result", {})
                    if isinstance(result, dict) and (result.get("rest_id") or result.get("legacy") or result.get("core")):
                        users.append(result)

                for value in node.values():
                    if isinstance(value, (dict, list)):
                        walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)

        deduped = []
        seen = set()
        for user in users:
            uid = user.get("rest_id") or user.get("id")
            if not uid or uid in seen:
                continue
            seen.add(uid)
            deduped.append(user)

        return deduped, cursor

    async def start(self):
        """Démarre le navigateur et récupère les tokens."""
        print("[APIFY] Démarrage du navigateur...")

        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"]
        )

        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )

        # Ajouter les cookies
        twitter_cookies = []
        for c in self.cookies:
            cookie = {
                "name": c.get("name"),
                "value": c.get("value"),
                "domain": ".x.com",
                "path": "/"
            }
            twitter_cookies.append(cookie)

            # Extraire les tokens
            if c.get("name") == "auth_token":
                self.auth_token = c.get("value")
            elif c.get("name") == "ct0":
                self.csrf_token = c.get("value")

        await self.context.add_cookies(twitter_cookies)
        self.page = await self.context.new_page()

        # IMPORTANT: Naviguer vers Twitter pour activer les cookies
        print("[APIFY] Navigation vers Twitter pour activer la session...")
        await self.page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        print("[APIFY] Navigateur prêt!")
        print(f"[APIFY] CSRF Token: {self.csrf_token[:20]}...")

    async def _dismiss_cookie_banner(self):
        try:
            button = self.page.get_by_role("button", name="Accept all cookies")
            if await button.count():
                await button.first.click(timeout=3000)
                await asyncio.sleep(1)
                print("[APIFY] Cookie banner acceptee")
        except Exception:
            pass

    async def scrape_followers(
        self,
        username: str,
        list_type: str = "followers",
        max_records: Optional[int] = None,
        on_progress = None
    ) -> AsyncGenerator[dict, None]:
        """
        Scrape les followers/following avec appels GraphQL directs.
        50 users par requête, comme Apify.

        Stratégie:
        1. Visiter la page pour déclencher la PREMIÈRE requête
        2. Capturer à la fois la REQUÊTE (headers, features) et la RÉPONSE (users, cursor)
        3. Faire nos propres requêtes avec les MÊMES headers/features + cursor
        """
        print(f"[APIFY] Scraping {list_type} de @{username}...")
        self.last_stop_reason = None

        # Variables pour capturer la requête et réponse
        captured = {
            "query_id": None,
            "operation": None,
            "base_url": None,
            "original_url": None,  # URL complète originale pour debug
            "original_query_string": None,  # Query string originale exacte
            "headers": None,
            "features": None,
            "features_raw": None,  # Features string brute (non parsée)
            "variables": None,
            "variables_raw": None,  # Variables string brute
            "field_toggles": None,  # Paramètre optionnel
            "cursor": None,
            "first_users": [],
            "user_id": None,
        }

        async def capture_request(request: Request):
            """Capture les détails de la requête GraphQL originale."""
            url = request.url
            if "/graphql/" in url and ("Followers" in url or "Following" in url):
                try:
                    # Sauvegarder l'URL originale complète pour debug
                    captured["original_url"] = url

                    # Extraire query_id et operation de l'URL
                    parts = url.split("/graphql/")[1].split("/")
                    if len(parts) >= 2:
                        captured["query_id"] = parts[0]
                        captured["operation"] = parts[1].split("?")[0]
                        captured["base_url"] = url.split("?")[0]

                    # Capturer les headers importants
                    all_headers = request.headers
                    captured["headers"] = {
                        "accept": all_headers.get("accept"),
                        "accept-language": all_headers.get("accept-language"),
                        "authorization": all_headers.get("authorization"),
                        "content-type": all_headers.get("content-type"),
                        "referer": all_headers.get("referer"),  # Important pour Twitter!
                        "x-csrf-token": all_headers.get("x-csrf-token"),
                        "x-twitter-auth-type": all_headers.get("x-twitter-auth-type"),
                        "x-twitter-active-user": all_headers.get("x-twitter-active-user"),
                        "x-twitter-client-language": all_headers.get("x-twitter-client-language"),
                        # Note: x-client-transaction-id change à chaque requête, on ne le réutilise pas
                    }
                    blocked_headers = {"host", "content-length", "x-client-transaction-id"}
                    captured["headers"] = {
                        k: v
                        for k, v in all_headers.items()
                        if v and k.lower() not in blocked_headers
                    }
                    print(f"[APIFY] Referer: {captured['headers'].get('referer')}")

                    # Extraire TOUS les paramètres de l'URL
                    parsed = urlparse(url)
                    captured["original_query_string"] = parsed.query
                    params = parse_qs(parsed.query)

                    print(f"[APIFY] Paramètres URL: {list(params.keys())}")

                    if "features" in params:
                        captured["features_raw"] = params["features"][0]  # Garder la version brute
                        captured["features"] = json.loads(params["features"][0])
                    if "variables" in params:
                        captured["variables_raw"] = params["variables"][0]  # Garder la version brute
                        captured["variables"] = json.loads(params["variables"][0])
                        # Récupérer le userId depuis les variables
                        if "userId" in captured["variables"]:
                            captured["user_id"] = captured["variables"]["userId"]
                    if "fieldToggles" in params:
                        captured["field_toggles"] = json.loads(params["fieldToggles"][0])
                        print(f"[APIFY] fieldToggles trouvé: {captured['field_toggles']}")

                    print(f"[APIFY] Requête capturée: {captured['operation']}")
                    print(f"[APIFY] Query ID: {captured['query_id']}")
                    print(f"[APIFY] User ID: {captured['user_id']}")

                except Exception as e:
                    print(f"[APIFY] Erreur capture requête: {e}")
                    import traceback
                    traceback.print_exc()

        async def capture_response(response: Response):
            """Capture les utilisateurs et le curseur de la réponse."""
            url = response.url
            if "/graphql/" in url and ("Followers" in url or "Following" in url):
                try:
                    data = await response.json()

                    # Vérifier les erreurs
                    if "errors" in data:
                        print(f"[APIFY] Erreur GraphQL: {data['errors']}")
                        self.last_stop_reason = f"graphql_errors:{data['errors']}"
                        return

                    users, cursor = self._extract_timeline_users_and_cursor(data)
                    if cursor:
                        captured["cursor"] = cursor
                    if users:
                        known = {u.get("rest_id") or u.get("id") for u in captured["first_users"]}
                        captured["first_users"].extend([
                            u for u in users
                            if (u.get("rest_id") or u.get("id")) not in known
                        ])

                    print(f"[APIFY] Réponse: {len(captured['first_users'])} users, cursor: {'Oui' if captured['cursor'] else 'Non'}")

                except Exception as e:
                    print(f"[APIFY] Erreur capture réponse: {e}")

        # Attacher les listeners AVANT de naviguer
        self.page.on("request", capture_request)
        self.page.on("response", capture_response)

        # Visiter la page pour déclencher la requête GraphQL
        print(f"[APIFY] Navigation vers https://x.com/{username}/{list_type}...")
        await self.page.goto(f"https://x.com/{username}/{list_type}", wait_until="domcontentloaded", timeout=30000)
        await self._dismiss_cookie_banner()

        # Attendre un peu que les requêtes soient capturées
        await asyncio.sleep(5)

        # Retirer les listeners
        self.page.remove_listener("request", capture_request)
        self.page.remove_listener("response", capture_response)

        # Vérifier qu'on a capturé ce qu'il faut
        if not captured["query_id"] or not captured["headers"]:
            print("[APIFY] Échec de la capture de la requête originale")
            print(f"[APIFY] Query ID: {captured['query_id']}")
            print(f"[APIFY] Headers: {captured['headers']}")
            self.last_stop_reason = "capture_failed"
            return

        if not captured["first_users"]:
            print("[APIFY] Aucun utilisateur dans la première réponse")
            self.last_stop_reason = "first_page_empty"
            return

        total_scraped = 0

        # Yield les premiers utilisateurs
        print(f"[APIFY] Première page: {len(captured['first_users'])} users")

        for user_result in captured["first_users"]:
            user_data = self._format_user(user_result)
            if user_data:
                yield user_data
                total_scraped += 1

                if on_progress:
                    on_progress(total_scraped, user_data, None)

                if max_records and total_scraped >= max_records:
                    print(f"[APIFY] Limite atteinte: {max_records}")
                    self.last_stop_reason = "max_records_reached"
                    return

        print(f"[APIFY] Page 1: {total_scraped} users scrapés")

        if not captured["cursor"]:
            print(f"[APIFY] Pas de curseur, fin: {total_scraped} utilisateurs")
            self.last_stop_reason = f"no_cursor_after_first_page:{total_scraped}"
            return

        # ============================================
        # PAGINATION: Requêtes GraphQL directes
        # ============================================
        page_num = 2
        cursor = captured["cursor"]
        seen_ids = set(u.get("rest_id") for u in captured["first_users"] if u.get("rest_id"))

        while cursor:
            print(f"[APIFY] Page {page_num}: requête avec curseur...")

            # Construire les variables avec le curseur
            variables = captured["variables"].copy()
            variables["cursor"] = cursor

            # IMPORTANT: Utiliser le même format que Twitter
            # Modifier le JSON des variables pour ajouter le cursor
            variables_json = json.dumps(variables, separators=(',', ':'))
            original_params = parse_qsl(captured["original_query_string"], keep_blank_values=True)
            next_params = []
            replaced_variables = False
            for key, value in original_params:
                if key == "variables":
                    next_params.append((key, variables_json))
                    replaced_variables = True
                else:
                    next_params.append((key, value))
            if not replaced_variables:
                next_params.insert(0, ("variables", variables_json))

            request_url = f"{captured['base_url']}?{urlencode(next_params)}"

            print(f"[APIFY] URL originale (début): {captured['original_url'][:150]}...")
            print(f"[APIFY] URL pagination (début): {request_url[:150]}...")

            # Utiliser l'API de requête de Playwright (meilleure gestion des cookies/headers)
            try:
                headers_to_send = {k: v for k, v in captured["headers"].items() if v}
                # S'assurer que le referer est défini
                if "referer" not in headers_to_send or not headers_to_send["referer"]:
                    headers_to_send["referer"] = f"https://x.com/{username}/{list_type}"
                response = await self.context.request.fetch(
                    request_url,
                    method="GET",
                    headers=headers_to_send
                )

                if response.status == 429:
                    result = {"error": "rate_limit", "status": 429}
                elif response.status != 200:
                    body = await response.text()
                    result = {
                        "error": "http_error",
                        "status": response.status,
                        "body": body[:500] if body else ""
                    }
                    print(f"[APIFY] Status: {response.status}, Headers: {dict(response.headers)}")
                    if response.status == 404:
                        print("[APIFY] 404 via context.request, retry depuis la page X.com...", flush=True)
                        browser_result = await self.page.evaluate(
                            """
                            async ({ url, headers }) => {
                                const response = await fetch(url, {
                                    method: 'GET',
                                    credentials: 'include',
                                    headers
                                });
                                const text = await response.text();
                                return {
                                    status: response.status,
                                    ok: response.ok,
                                    text,
                                    headers: Object.fromEntries(response.headers.entries())
                                };
                            }
                            """,
                            {"url": request_url, "headers": headers_to_send}
                        )
                        if browser_result.get("status") == 429:
                            result = {"error": "rate_limit", "status": 429}
                        elif browser_result.get("status") == 200:
                            result = json.loads(browser_result.get("text") or "{}")
                            print("[APIFY] Retry page X.com OK", flush=True)
                        else:
                            result = {
                                "error": "http_error",
                                "status": browser_result.get("status"),
                                "body": (browser_result.get("text") or "")[:500],
                            }
                            print(
                                f"[APIFY] Retry page X.com status: {browser_result.get('status')}, "
                                f"headers: {browser_result.get('headers')}",
                                flush=True,
                            )
                else:
                    result = await response.json()

            except Exception as e:
                print(f"[APIFY] Exception requête: {e}")
                result = {"error": str(e)}

            # Gérer les erreurs
            if not result:
                print("[APIFY] Pas de réponse")
                self.last_stop_reason = f"empty_response_page:{page_num}"
                break

            if result.get("error") == "rate_limit":
                wait_time = 390
                print(f"[APIFY] Rate limit! Attente de {wait_time} secondes...")
                if on_progress:
                    on_progress(total_scraped, None, f"Rate limit - attente {wait_time}s")
                await asyncio.sleep(wait_time)
                continue

            if result.get("error"):
                print(f"[APIFY] Erreur: {result.get('error')} - {result.get('status')} {result.get('statusText', '')}")
                if result.get("body"):
                    print(f"[APIFY] Body erreur: {result.get('body')[:200]}")
                body_hint = (result.get("body") or "").replace("\n", " ")[:120]
                self.last_stop_reason = (
                    f"error_page:{page_num}:{result.get('error')}:{result.get('status')}"
                    + (f":{body_hint}" if body_hint else "")
                )
                break

            # Extraire les utilisateurs et le curseur suivant
            try:
                extracted_users, next_cursor = self._extract_timeline_users_and_cursor(result)
                users_in_page = []
                for user_result in extracted_users:
                    uid = user_result.get("rest_id") or user_result.get("id")
                    if uid and uid not in seen_ids:
                        users_in_page.append(user_result)
                        seen_ids.add(uid)
                print(
                    f"[APIFY] Page {page_num}: parsed users={len(extracted_users)}, "
                    f"new={len(users_in_page)}, cursor={'Oui' if next_cursor else 'Non'}",
                    flush=True,
                )
            except Exception as e:
                print(f"[APIFY] Erreur parsing: {e}")
                self.last_stop_reason = f"parse_error_page:{page_num}:{e}"
                break

            if not users_in_page:
                print("[APIFY] Plus d'utilisateurs")
                self.last_stop_reason = f"no_new_users_page:{page_num}:parsed={len(extracted_users) if 'extracted_users' in locals() else 'unknown'}:cursor={'yes' if next_cursor else 'no'}"
                break

            # Yield les utilisateurs
            for user_result in users_in_page:
                user_data = self._format_user(user_result)
                if user_data:
                    yield user_data
                    total_scraped += 1

                    if on_progress:
                        on_progress(total_scraped, user_data, None)

                    if max_records and total_scraped >= max_records:
                        print(f"[APIFY] Limite atteinte: {max_records}")
                        self.last_stop_reason = "max_records_reached"
                        return

            print(f"[APIFY] Page {page_num}: +{len(users_in_page)} users (total: {total_scraped})")

            # Préparer la page suivante
            if not next_cursor or next_cursor == cursor:
                print("[APIFY] Fin de la pagination")
                self.last_stop_reason = f"pagination_end_page:{page_num}:cursor_repeat={next_cursor == cursor}"
                break

            cursor = next_cursor
            page_num += 1

            # Délai entre requêtes (comme Apify)
            delay = random.uniform(3, 6)
            await asyncio.sleep(delay)

        print(f"[APIFY] Scraping terminé: {total_scraped} utilisateurs")
        if not self.last_stop_reason:
            self.last_stop_reason = f"completed:{total_scraped}"

    def _format_user(self, user_result: dict) -> Optional[dict]:
        """Formate un user_result en données utilisateur."""
        try:
            # L'ID est dans rest_id
            user_id = user_result.get("rest_id")

            # Les données sont dans différents sous-objets
            legacy = user_result.get("legacy", {})
            core = user_result.get("core", {})
            dm_permissions = user_result.get("dm_permissions", {})
            media_permissions = user_result.get("media_permissions", {})
            privacy = user_result.get("privacy", {})

            # can_dm et can_media_tag - vérifier plusieurs emplacements
            can_dm = (
                user_result.get("can_dm") or
                dm_permissions.get("can_dm") or
                legacy.get("can_dm", False)
            )
            can_media_tag = (
                user_result.get("can_media_tag") or
                media_permissions.get("can_media_tag") or
                legacy.get("can_media_tag", False)
            )

            if self._debug_dm_samples < 5:
                self._debug_dm_samples += 1
                print(
                    "[APIFY] DM sample "
                    f"@{core.get('screen_name') or legacy.get('screen_name')}: "
                    f"user.can_dm={user_result.get('can_dm')} "
                    f"dm_permissions.can_dm={dm_permissions.get('can_dm')} "
                    f"legacy.can_dm={legacy.get('can_dm')} "
                    f"can_media_tag={can_media_tag}",
                    flush=True,
                )

            # screen_name - vérifier core d'abord (structure 2026), puis legacy
            username = (
                core.get("screen_name") or
                legacy.get("screen_name") or
                user_result.get("screen_name")
            )

            # name - même chose
            name = (
                core.get("name") or
                legacy.get("name") or
                user_result.get("name", "")
            )

            if not username:
                return None

            return {
                "id": str(user_id) if user_id else "",
                "username": username,
                "name": name,
                "bio": legacy.get("description", "") or user_result.get("description", ""),
                "followers_count": legacy.get("followers_count", 0) or user_result.get("followers_count", 0),
                "following_count": legacy.get("friends_count", 0) or user_result.get("friends_count", 0),
                "tweets_count": legacy.get("statuses_count", 0) or user_result.get("statuses_count", 0),
                "verified": user_result.get("is_blue_verified", False),
                "protected": privacy.get("protected", False) or legacy.get("protected", False),
                "profile_image": (legacy.get("profile_image_url_https", "") or user_result.get("profile_image_url_https", "")).replace("_normal", "_400x400"),
                "location": legacy.get("location", ""),
                "created_at": legacy.get("created_at", "") or user_result.get("created_at", ""),
                "can_dm": can_dm,
                "can_media_tag": can_media_tag,
                "gender": detect_gender(name),
                "raw": user_result,
            }
        except Exception as e:
            print(f"[APIFY] Erreur format user: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def close(self):
        """Ferme le navigateur."""
        if self.browser:
            await self.browser.close()
            print("[APIFY] Navigateur fermé")


# Test
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python scraper_apify.py <cookies.json> <username> [max_records]")
        sys.exit(1)

    async def main():
        with open(sys.argv[1], "r") as f:
            cookies = json.load(f)

        username = sys.argv[2]
        max_records = int(sys.argv[3]) if len(sys.argv) > 3 else 100

        scraper = ApifyStyleScraper(cookies=cookies, headless=False)
        await scraper.start()

        users = []
        async for user in scraper.scrape_followers(username, "followers", max_records):
            users.append(user)
            dm_status = "DM OK" if user['can_dm'] else "DM Fermé"
            print(f"  {len(users)}. @{user['username']} - {dm_status}")

        await scraper.close()

        # Stats
        dm_ok = [u for u in users if u["can_dm"]]
        print(f"\n=== Résultats ===")
        print(f"Total: {len(users)}")
        print(f"DM OK: {len(dm_ok)}")
        print(f"DM Fermé: {len(users) - len(dm_ok)}")

    asyncio.run(main())
