#!/usr/bin/env python3
"""
Twitter/X Followers Scraper
Clone de l'Actor Apify curious_coder/twitter-scraper
Scrape followers OU following d'un compte Twitter/X.
"""

import json
import time
import csv
import random
import re
from pathlib import Path
from typing import Optional, Generator, Literal
from datetime import datetime

import httpx
import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel

from gender_detector import detect_gender

console = Console()

# Twitter GraphQL endpoints
TWITTER_API_BASE = "https://x.com/i/api/graphql"

# Cache pour les query IDs dynamiques
_DYNAMIC_QUERY_IDS = {}

def fetch_twitter_query_ids() -> dict:
    """
    Récupère dynamiquement les query IDs depuis Twitter (comme Apify).
    Parse le JavaScript de Twitter pour extraire les IDs actuels.
    """
    global _DYNAMIC_QUERY_IDS

    if _DYNAMIC_QUERY_IDS:
        return _DYNAMIC_QUERY_IDS

    print("[DEBUG] Fetching fresh query IDs from Twitter...")

    try:
        # 1. Récupérer la page d'accueil pour trouver les URLs des scripts
        client = httpx.Client(timeout=30.0, follow_redirects=True)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }

        response = client.get("https://x.com/", headers=headers)
        html = response.text

        # 2. Trouver les URLs des scripts JS principaux
        script_pattern = r'src="(https://abs\.twimg\.com/responsive-web/client-web[^"]+\.js)"'
        scripts = re.findall(script_pattern, html)

        print(f"[DEBUG] Found {len(scripts)} scripts to scan")

        # 3. Scanner chaque script pour trouver les query IDs
        query_patterns = {
            "Followers": r'queryId:"([^"]+)"[^}]*operationName:"Followers"',
            "Following": r'queryId:"([^"]+)"[^}]*operationName:"Following"',
            "UserByScreenName": r'queryId:"([^"]+)"[^}]*operationName:"UserByScreenName"',
        }

        # Pattern alternatif (ordre inversé)
        alt_patterns = {
            "Followers": r'operationName:"Followers"[^}]*queryId:"([^"]+)"',
            "Following": r'operationName:"Following"[^}]*queryId:"([^"]+)"',
            "UserByScreenName": r'operationName:"UserByScreenName"[^}]*queryId:"([^"]+)"',
        }

        for script_url in scripts[:5]:  # Scanner les 5 premiers scripts
            try:
                js_response = client.get(script_url, headers=headers)
                js_content = js_response.text

                for operation, pattern in query_patterns.items():
                    if operation not in _DYNAMIC_QUERY_IDS:
                        match = re.search(pattern, js_content)
                        if match:
                            _DYNAMIC_QUERY_IDS[operation] = match.group(1)
                            print(f"[DEBUG] Found {operation}: {match.group(1)}")

                # Essayer les patterns alternatifs
                for operation, pattern in alt_patterns.items():
                    if operation not in _DYNAMIC_QUERY_IDS:
                        match = re.search(pattern, js_content)
                        if match:
                            _DYNAMIC_QUERY_IDS[operation] = match.group(1)
                            print(f"[DEBUG] Found {operation} (alt): {match.group(1)}")

            except Exception as e:
                print(f"[DEBUG] Error scanning {script_url}: {e}")
                continue

        client.close()

    except Exception as e:
        print(f"[DEBUG] Error fetching query IDs: {e}")

    # Fallback si on n'a pas trouvé
    if "Followers" not in _DYNAMIC_QUERY_IDS:
        _DYNAMIC_QUERY_IDS["Followers"] = "pd8Tt1qUz1YWrICegqZ8cw"
    if "Following" not in _DYNAMIC_QUERY_IDS:
        _DYNAMIC_QUERY_IDS["Following"] = "wjvx62Hye2dGVvnvVco0xA"

    print(f"[DEBUG] Final query IDs: {_DYNAMIC_QUERY_IDS}")
    return _DYNAMIC_QUERY_IDS


# Query IDs - récupérés dynamiquement ou fallback
QUERY_IDS = {
    "followers": [
        "pd8Tt1qUz1YWrICegqZ8cw",  # fallback
    ],
    "following": [
        "wjvx62Hye2dGVvnvVco0xA",  # fallback
    ],
}

# Endpoints par défaut
ENDPOINTS = {
    "followers": f"/{QUERY_IDS['followers'][0]}/Followers",
    "following": f"/{QUERY_IDS['following'][0]}/Following",
}

# Features GraphQL - exactement comme twscrape (janvier 2026)
GQL_FEATURES = {
    "articles_preview_enabled": False,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "communities_web_enable_tweet_community_results_fetch": True,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_media_download_video_enabled": False,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_awards_web_tipping_enabled": False,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "tweet_with_visibility_results_prefer_gql_media_interstitial_enabled": False,
    "tweetypie_unmention_optimization_enabled": True,
    "verified_phone_label_enabled": False,
    "view_counts_everywhere_api_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "premium_content_api_read_enabled": False,
    "profile_label_improvements_pcf_label_in_post_enabled": False,
    "responsive_web_grok_share_attachment_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": False,
    "responsive_web_grok_image_annotation_enabled": False,
    "responsive_web_grok_analysis_button_from_backend": False,
    "responsive_web_jetfuel_frame": False,
    "rweb_video_screen_enabled": True,
    "responsive_web_grok_show_grok_translated_post": True,
}

# Alternative: Twitter API 1.1
TWITTER_API_V1 = "https://x.com/i/api/1.1"

# Headers nécessaires pour simuler le navigateur
DEFAULT_HEADERS = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
    "content-type": "application/json",
    "origin": "https://x.com",
    "referer": "https://x.com/",
    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "x-twitter-active-user": "yes",
    "x-twitter-auth-type": "OAuth2Session",
    "x-twitter-client-language": "fr",
}


def extract_username(url_or_username: str) -> str:
    """Extraire le username d'une URL Twitter ou retourner le username tel quel."""
    # Si c'est une URL
    patterns = [
        r'(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/(@?\w+)/?',
        r'^@?(\w+)$'
    ]

    for pattern in patterns:
        match = re.match(pattern, url_or_username.strip())
        if match:
            return match.group(1).lstrip('@')

    return url_or_username.strip().lstrip('@')


def parse_cookies(cookies_input) -> dict:
    """
    Parser les cookies depuis différents formats:
    - Liste de dicts (format Apify/EditThisCookie)
    - Dict simple {name: value}
    """
    if isinstance(cookies_input, list):
        # Format Apify/EditThisCookie: liste de dicts avec "name" et "value"
        result = {}
        for c in cookies_input:
            name = c.get("name")
            value = c.get("value")
            if name and value:
                # Nettoyer les valeurs (enlever les guillemets en trop)
                if isinstance(value, str):
                    value = value.strip('"')
                result[name] = value
        print(f"[DEBUG] Cookies parsés: {list(result.keys())}")
        return result
    elif isinstance(cookies_input, dict):
        return cookies_input
    return {}


class TwitterScraper:
    """Scraper pour récupérer les followers/following d'un compte Twitter/X."""

    def __init__(
        self,
        cookies: dict,
        proxy: Optional[str] = None,
        min_wait: float = 3,
        max_wait: float = 15
    ):
        self.cookies = parse_cookies(cookies)
        self.proxy = proxy
        self.min_wait = min_wait
        self.max_wait = max_wait
        self.client = self._create_client()
        self.request_count = 0
        self.last_cursor = None

    def _get_csrf_token(self) -> str:
        """Récupérer le token CSRF depuis les cookies."""
        return self.cookies.get("ct0", "")

    def _create_client(self) -> httpx.Client:
        """Créer le client HTTP avec les bons cookies et headers."""
        headers = DEFAULT_HEADERS.copy()
        headers["x-csrf-token"] = self._get_csrf_token()

        return httpx.Client(
            headers=headers,
            cookies=self.cookies,
            proxy=self.proxy,
            timeout=30.0,
            follow_redirects=True,
        )

    def _random_delay(self):
        """Attendre un délai aléatoire entre min_wait et max_wait."""
        delay = random.uniform(self.min_wait, self.max_wait)
        time.sleep(delay)
        return delay

    def get_user_info(self, username: str) -> Optional[dict]:
        """Récupérer les infos complètes d'un utilisateur."""
        url = "https://x.com/i/api/graphql/Yka-W8dz7RaEuQNkroPkYw/UserByScreenName"

        variables = {
            "screen_name": username,
            "withSafetyModeUserFields": True,
        }

        features = {
            "hidden_profile_subscriptions_enabled": True,
            "rweb_tipjar_consumption_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "subscriptions_verification_info_is_identity_verified_enabled": True,
            "subscriptions_verification_info_verified_since_enabled": True,
            "highlights_tweets_tab_ui_enabled": True,
            "responsive_web_twitter_article_notes_tab_enabled": True,
            "subscriptions_feature_can_gift_premium": True,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True,
        }

        params = {
            "variables": json.dumps(variables),
            "features": json.dumps(features),
        }

        try:
            response = self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            user_result = data.get("data", {}).get("user", {}).get("result", {})
            legacy = user_result.get("legacy", {})

            # Nouvelle structure Twitter 2025
            core = user_result.get("core", {})
            dm_permissions = user_result.get("dm_permissions", {})
            media_permissions = user_result.get("media_permissions", {})
            privacy = user_result.get("privacy", {})

            if not user_result.get("rest_id"):
                return None

            # Priorité: nouvelle structure (2025) puis fallback sur legacy
            username = core.get("screen_name") or legacy.get("screen_name")
            name = core.get("name") or legacy.get("name")

            # VRAI can_dm depuis dm_permissions (structure 2025) sinon fallback legacy
            can_dm = dm_permissions.get("can_dm", legacy.get("can_dm", False))
            can_media_tag = media_permissions.get("can_media_tag", legacy.get("can_media_tag", False))
            protected = privacy.get("protected", legacy.get("protected", False))

            return {
                "id": user_result.get("rest_id"),
                "username": username,
                "name": name,
                "followers_count": legacy.get("followers_count", 0),
                "following_count": legacy.get("friends_count", 0),
                "tweets_count": legacy.get("statuses_count", 0),
                "bio": legacy.get("description", ""),
                "verified": user_result.get("is_blue_verified", False),
                "protected": protected,
                "location": legacy.get("location", ""),
                "website": legacy.get("url", ""),
                "created_at": legacy.get("created_at", ""),
                "profile_image": legacy.get("profile_image_url_https", "").replace("_normal", "_400x400"),
                "profile_banner": legacy.get("profile_banner_url", ""),
                "can_dm": can_dm,  # VRAI can_dm de Twitter (2025)
                "can_media_tag": can_media_tag,
            }

        except httpx.HTTPStatusError as e:
            console.print(f"[red]Erreur HTTP {e.response.status_code}[/red]")
            if e.response.status_code == 401:
                console.print("[yellow]Cookies invalides ou expirés![/yellow]")
            return None
        except Exception as e:
            console.print(f"[red]Erreur: {e}[/red]")
            return None

    def check_can_dm(self, target_user_id: str) -> bool:
        """
        Vérifie si on peut envoyer un DM à un utilisateur via friendships/show.
        Retourne True si can_dm, False sinon.
        """
        url = f"{TWITTER_API_V1}/friendships/show.json"
        params = {
            "target_id": target_user_id,
        }

        try:
            response = self.client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                # can_dm est dans relationship.source.can_dm
                relationship = data.get("relationship", {})
                source = relationship.get("source", {})
                return source.get("can_dm", False)
        except Exception as e:
            print(f"[DEBUG] check_can_dm error: {e}")

        return False

    def check_can_dm_bulk(self, user_ids: list) -> dict:
        """
        Vérifie can_dm pour plusieurs utilisateurs via friendships/show.
        Rate limit: 15 req / 15 min, donc on vérifie max 15 users par appel.

        Pour vérifier plus, on utilise un délai de 1 min entre chaque batch de 15.

        Returns:
            dict: {user_id: can_dm (bool)}
        """
        results = {}

        # Process in batches of 15 (rate limit)
        batch_size = 15
        total_batches = (len(user_ids) + batch_size - 1) // batch_size

        for batch_num, i in enumerate(range(0, len(user_ids), batch_size)):
            batch = user_ids[i:i+batch_size]
            print(f"[DEBUG] Vérification batch {batch_num + 1}/{total_batches} ({len(batch)} users)")

            for user_id in batch:
                can_dm = self.check_can_dm(str(user_id))
                results[str(user_id)] = can_dm
                time.sleep(0.5)  # Petit délai entre chaque requête

            # Si on a encore des batches, attendre pour respecter le rate limit
            if i + batch_size < len(user_ids):
                wait_time = 60  # 1 minute entre batches
                print(f"[DEBUG] Attente de {wait_time}s avant le prochain batch (rate limit)...")
                time.sleep(wait_time)

        return results

    def scrape_list_v1(
        self,
        user_id: str,
        list_type: Literal["followers", "following"] = "followers",
        max_records: Optional[int] = None,
        start_cursor: Optional[str] = None,
        on_progress: Optional[callable] = None,
        check_dm: bool = True,  # Vérifier can_dm pour chaque user
    ) -> Generator[dict, None, None]:
        """
        Scraper avec l'API v1.1 (plus stable).
        """
        cursor = start_cursor or "-1"
        total_scraped = 0
        endpoint = "followers" if list_type == "followers" else "friends"

        while cursor != "0":
            url = f"{TWITTER_API_V1}/{endpoint}/list.json"
            params = {
                "user_id": user_id,
                "count": 200,  # Max pour v1.1
                "cursor": cursor,
                "skip_status": "true",
                "include_user_entities": "false",
            }

            try:
                self.request_count += 1
                response = self.client.get(url, params=params)
                print(f"[DEBUG v1.1] Status: {response.status_code}")

                if response.status_code != 200:
                    print(f"[DEBUG v1.1] Response: {response.text[:300]}")
                    break

                data = response.json()

                users = data.get("users", [])
                for user in users:
                    # Indicateurs de qualité du profil
                    can_media_tag = user.get("can_media_tag", False)  # Souvent = DMs ouverts
                    is_protected = user.get("protected", False)
                    has_profile_pic = not user.get("default_profile_image", True)
                    has_bio = bool(user.get("description", "").strip())
                    following_me = user.get("followed_by", False)  # Il me follow
                    i_follow = user.get("following", False)  # Je le follow

                    # Score de "contactabilité" (plus c'est haut, mieux c'est)
                    dm_score = 0
                    if can_media_tag: dm_score += 3
                    if not is_protected: dm_score += 2
                    if has_profile_pic: dm_score += 1
                    if has_bio: dm_score += 1
                    if following_me: dm_score += 5  # Gros bonus si il te follow

                    # On considère DM possible si score >= 3 et pas protégé
                    can_dm = (dm_score >= 3) and not is_protected

                    # Détection du genre
                    name = user.get("name", "")
                    gender = detect_gender(name)

                    user_data = {
                        "id": str(user.get("id")),
                        "username": user.get("screen_name"),
                        "name": name,
                        "bio": user.get("description", ""),
                        "followers_count": user.get("followers_count", 0),
                        "following_count": user.get("friends_count", 0),
                        "tweets_count": user.get("statuses_count", 0),
                        "verified": user.get("verified", False),
                        "protected": is_protected,
                        "profile_image": user.get("profile_image_url_https", "").replace("_normal", "_400x400"),
                        "location": user.get("location", ""),
                        "created_at": user.get("created_at", ""),
                        "can_dm": can_dm,
                        "can_media_tag": can_media_tag,
                        "has_profile_pic": has_profile_pic,
                        "has_bio": has_bio,
                        "following_me": following_me,
                        "i_follow": i_follow,
                        "is_mutual": following_me and i_follow,
                        "dm_score": dm_score,
                        "gender": gender,
                    }

                    yield user_data
                    total_scraped += 1

                    if max_records and total_scraped >= max_records:
                        return

                cursor = str(data.get("next_cursor", "0"))
                self.last_cursor = cursor

                if on_progress:
                    on_progress(cursor, total_scraped)

                if cursor != "0":
                    self._random_delay()

            except Exception as e:
                print(f"[DEBUG v1.1] Error: {e}")
                break

    def scrape_list(
        self,
        user_id: str,
        list_type: Literal["followers", "following"] = "followers",
        max_records: Optional[int] = None,
        start_cursor: Optional[str] = None,
        on_progress: Optional[callable] = None,
    ) -> Generator[dict, None, None]:
        """
        Scraper les followers ou following avec pagination.

        Args:
            user_id: ID Twitter du compte cible
            list_type: "followers" ou "following"
            max_records: Nombre max de records à récupérer (None = tous)
            start_cursor: Curseur pour reprendre un scraping interrompu
            on_progress: Callback appelé à chaque page (cursor, count)

        Yields:
            Dict avec les infos de chaque utilisateur
        """
        cursor = start_cursor
        total_scraped = 0

        # D'abord essayer de récupérer les query IDs dynamiques (comme Apify)
        dynamic_ids = fetch_twitter_query_ids()
        endpoint_name = "Followers" if list_type == "followers" else "Following"

        # Construire la liste des IDs à essayer (dynamique en premier, puis fallback)
        query_ids = []
        if endpoint_name in dynamic_ids:
            query_ids.append(dynamic_ids[endpoint_name])
        query_ids.extend(QUERY_IDS.get(list_type, []))

        working_query_id = None  # On mémorise le query ID qui fonctionne

        while True:
            variables = {
                "userId": user_id,
                "count": 20,
                "includePromotedContent": False,
            }

            if cursor:
                variables["cursor"] = cursor

            # Utiliser les features de twscrape avec l'override pour followers
            features = GQL_FEATURES.copy()
            if list_type == "followers":
                features["responsive_web_twitter_article_notes_tab_enabled"] = False

            params = {
                "variables": json.dumps(variables),
                "features": json.dumps(features),
            }

            # Essayer plusieurs query IDs si nécessaire (fallback)
            data = None
            ids_to_try = [working_query_id] if working_query_id else query_ids

            for query_id in ids_to_try:
                if query_id is None:
                    continue

                endpoint_name = "Followers" if list_type == "followers" else "Following"
                url = f"{TWITTER_API_BASE}/{query_id}/{endpoint_name}"

                print(f"[DEBUG] Trying query ID: {query_id}")
                print(f"[DEBUG] URL: {url}")

                try:
                    self.request_count += 1
                    response = self.client.get(url, params=params)
                    print(f"[DEBUG] Status code: {response.status_code}")

                    if response.status_code in [403, 404]:
                        print(f"[DEBUG] Query ID {query_id} failed, trying next...")
                        continue

                    # Sauvegarder la réponse pour debug
                    try:
                        data = response.json()
                        with open("debug_response.json", "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                    except:
                        with open("debug_response.txt", "w", encoding="utf-8") as f:
                            f.write(response.text)
                        continue

                    response.raise_for_status()

                    # Ce query ID fonctionne, on le mémorise
                    working_query_id = query_id
                    print(f"[DEBUG] Query ID {query_id} works!")
                    break

                except httpx.HTTPStatusError as e:
                    if e.response.status_code in [403, 404]:
                        print(f"[DEBUG] Query ID {query_id} returned {e.response.status_code}, trying next...")
                        continue
                    raise
                except Exception as e:
                    print(f"[DEBUG] Error with query ID {query_id}: {e}")
                    continue

            if data is None:
                console.print("[red]Tous les query IDs ont échoué! Twitter a peut-être changé l'API.[/red]")
                break

            print(f"[DEBUG] Response keys: {list(data.keys())}")

            # Parser la réponse - essayer plusieurs chemins possibles
            result = data.get("data", {}).get("user", {}).get("result", {})

            # Chemin 1: timeline.timeline
            timeline = result.get("timeline", {}).get("timeline", {})
            instructions = timeline.get("instructions", [])

            # Chemin 2: si pas d'instructions, essayer directement
            if not instructions:
                timeline = result.get("timeline", {})
                instructions = timeline.get("instructions", [])

            entries = []
            next_cursor = None

            print(f"[DEBUG] Instructions count: {len(instructions)}")
            for instruction in instructions:
                print(f"[DEBUG] Instruction type: {instruction.get('type')}")
                if instruction.get("type") == "TimelineAddEntries":
                    entries = instruction.get("entries", [])
                    print(f"[DEBUG] Entries found: {len(entries)}")
                elif instruction.get("type") == "TimelineAddToModule":
                    entries.extend(instruction.get("moduleItems", []))

            users_in_page = 0

            for entry in entries:
                entry_id = entry.get("entryId", "")

                # Récupérer le curseur pour la pagination
                if "cursor-bottom" in entry_id:
                    next_cursor = entry.get("content", {}).get("value")
                    continue

                if "cursor-top" in entry_id:
                    continue

                # Parser les données utilisateur
                content = entry.get("content", {})
                item_content = content.get("itemContent", {})

                if item_content.get("itemType") != "TimelineUser":
                    continue

                user_results = item_content.get("user_results", {}).get("result", {})
                legacy = user_results.get("legacy", {})

                if not legacy:
                    continue

                # Extraire le VRAI can_dm depuis legacy (comme Apify)
                can_dm = legacy.get("can_dm", False)
                can_media_tag = legacy.get("can_media_tag", False)
                is_protected = legacy.get("protected", False)
                has_profile_pic = not legacy.get("default_profile_image", True)
                has_bio = bool(legacy.get("description", "").strip())

                # Détection du genre
                name = legacy.get("name", "")
                gender = detect_gender(name)

                user_data = {
                    "id": user_results.get("rest_id"),
                    "username": legacy.get("screen_name"),
                    "name": name,
                    "bio": legacy.get("description", ""),
                    "followers_count": legacy.get("followers_count", 0),
                    "following_count": legacy.get("friends_count", 0),
                    "tweets_count": legacy.get("statuses_count", 0),
                    "verified": user_results.get("is_blue_verified", False),
                    "protected": is_protected,
                    "profile_image": legacy.get("profile_image_url_https", "").replace("_normal", "_400x400"),
                    "location": legacy.get("location", ""),
                    "website": legacy.get("url", ""),
                    "created_at": legacy.get("created_at", ""),
                    "default_profile": legacy.get("default_profile", False),
                    "default_profile_image": legacy.get("default_profile_image", False),
                    # Champs DM (comme Apify)
                    "can_dm": can_dm,  # LE VRAI CHAMP !
                    "can_media_tag": can_media_tag,
                    "has_profile_pic": has_profile_pic,
                    "has_bio": has_bio,
                    "gender": gender,
                }

                yield user_data
                total_scraped += 1
                users_in_page += 1

                if max_records and total_scraped >= max_records:
                    self.last_cursor = next_cursor
                    return

            # Sauvegarder le curseur actuel
            self.last_cursor = next_cursor

            # Callback de progression
            if on_progress:
                on_progress(next_cursor, total_scraped)

            # Vérifier s'il y a encore des pages
            if not next_cursor or next_cursor == cursor or users_in_page == 0:
                break

            cursor = next_cursor

            # Délai aléatoire pour éviter le rate limiting
            self._random_delay()

    def close(self):
        """Fermer le client HTTP."""
        self.client.close()


def load_config(config_path: str) -> dict:
    """Charger la configuration depuis un fichier JSON."""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_to_csv(users: list, output_path: str):
    """Sauvegarder les utilisateurs dans un fichier CSV."""
    if not users:
        return

    fieldnames = users[0].keys()

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(users)


def save_to_json(users: list, output_path: str):
    """Sauvegarder les utilisateurs dans un fichier JSON."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def save_state(state: dict, state_path: str):
    """Sauvegarder l'état du scraping pour pouvoir reprendre."""
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


@click.command()
@click.argument("target")
@click.option("--config", "-c", default="config.json", help="Chemin vers le fichier de config")
@click.option("--output", "-o", default=None, help="Fichier de sortie")
@click.option("--max", "-m", "max_records", default=None, type=int, help="Nombre max de records")
@click.option("--type", "-t", "list_type", default="followers", type=click.Choice(["followers", "following"]), help="Type de liste")
@click.option("--format", "-f", "output_format", default="csv", type=click.Choice(["csv", "json"]), help="Format de sortie")
@click.option("--cursor", default=None, help="Curseur pour reprendre un scraping")
@click.option("--min-wait", default=3, type=float, help="Délai minimum entre requêtes (secondes)")
@click.option("--max-wait", default=15, type=float, help="Délai maximum entre requêtes (secondes)")
@click.option("--proxy", "-p", default=None, help="URL du proxy (http://user:pass@host:port)")
def main(
    target: str,
    config: str,
    output: str,
    max_records: int,
    list_type: str,
    output_format: str,
    cursor: str,
    min_wait: float,
    max_wait: float,
    proxy: str
):
    """
    Twitter/X Scraper - Clone Apify curious_coder/twitter-scraper

    TARGET: URL Twitter (https://x.com/username) ou @username

    Exemples:
        python scraper.py https://x.com/elonmusk -m 1000
        python scraper.py @elonmusk -t following -m 500
        python scraper.py elonmusk --cursor "xxx" (reprendre)
    """
    console.print(Panel.fit(
        "[bold blue]Twitter/X Scraper[/bold blue]\n"
        "[dim]Clone de l'Actor Apify curious_coder/twitter-scraper[/dim]",
        border_style="blue"
    ))

    # Extraire le username
    username = extract_username(target)
    console.print(f"\n[cyan]Cible:[/cyan] @{username}")
    console.print(f"[cyan]Type:[/cyan] {list_type}")

    # Charger la config
    config_path = Path(config)
    if not config_path.exists():
        console.print(f"\n[red]Fichier de config '{config}' non trouvé![/red]")
        console.print("[yellow]Crée un fichier config.json avec tes cookies.[/yellow]")
        console.print("\nExemple de config.json:")
        console.print('''[dim]{
  "cookies": [
    {"name": "auth_token", "value": "xxx"},
    {"name": "ct0", "value": "xxx"}
  ]
}[/dim]''')
        return

    cfg = load_config(config)
    cookies = cfg.get("cookies", {})

    # Utiliser le proxy de la config si pas spécifié en CLI
    if not proxy:
        proxy = cfg.get("proxy")

    # Créer le scraper
    scraper = TwitterScraper(
        cookies=cookies,
        proxy=proxy,
        min_wait=min_wait,
        max_wait=max_wait,
    )

    try:
        # Récupérer les infos du compte cible
        console.print(f"\n[cyan]Récupération des infos de @{username}...[/cyan]")
        user_info = scraper.get_user_info(username)

        if not user_info:
            console.print(f"[red]Compte @{username} non trouvé ou inaccessible![/red]")
            return

        # Afficher les infos
        table = Table(title=f"@{username}", show_header=False, box=None)
        table.add_column("", style="cyan", width=15)
        table.add_column("", style="white")
        table.add_row("Nom", user_info["name"])
        table.add_row("Bio", (user_info["bio"][:50] + "...") if len(user_info["bio"]) > 50 else user_info["bio"])
        table.add_row("Followers", f"{user_info['followers_count']:,}")
        table.add_row("Following", f"{user_info['following_count']:,}")
        table.add_row("Tweets", f"{user_info['tweets_count']:,}")
        table.add_row("Vérifié", "Yes" if user_info["verified"] else "No")
        table.add_row("Privé", "Yes" if user_info["protected"] else "No")
        console.print(table)

        if user_info["protected"]:
            console.print("\n[red]Ce compte est privé! Impossible de scraper.[/red]")
            return

        # Déterminer le nombre à scraper
        total_available = user_info["followers_count"] if list_type == "followers" else user_info["following_count"]
        target_count = min(max_records, total_available) if max_records else total_available

        console.print(f"\n[cyan]Scraping {target_count:,} {list_type}...[/cyan]")
        if cursor:
            console.print(f"[dim]Reprise depuis le curseur: {cursor[:30]}...[/dim]")
        console.print(f"[dim]Délai entre requêtes: {min_wait}-{max_wait}s[/dim]")
        if proxy:
            console.print(f"[dim]Proxy: {proxy[:30]}...[/dim]")
        console.print()

        # Scraper
        users = []
        state_file = f"{username}_{list_type}_state.json"

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
            refresh_per_second=2,
        ) as progress:
            task = progress.add_task(f"Scraping {list_type}", total=target_count)

            def on_progress(cur, count):
                # Sauvegarder l'état périodiquement
                if count % 100 == 0:
                    save_state({
                        "username": username,
                        "list_type": list_type,
                        "cursor": cur,
                        "count": count,
                        "timestamp": datetime.now().isoformat(),
                    }, state_file)

            for user in scraper.scrape_list(
                user_info["id"],
                list_type=list_type,
                max_records=max_records,
                start_cursor=cursor,
                on_progress=on_progress,
            ):
                users.append(user)
                progress.update(
                    task,
                    advance=1,
                    description=f"@{user['username'][:15]}"
                )

        console.print(f"\n[green]✓ {len(users)} {list_type} récupérés![/green]")
        console.print(f"[dim]Requêtes effectuées: {scraper.request_count}[/dim]")

        if scraper.last_cursor and len(users) < total_available:
            console.print(f"\n[yellow]Pour continuer plus tard, utilise:[/yellow]")
            console.print(f"[dim]--cursor \"{scraper.last_cursor}\"[/dim]")

        # Sauvegarder
        if users:
            if output is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output = f"{username}_{list_type}_{timestamp}.{output_format}"

            if output_format == "csv":
                save_to_csv(users, output)
            else:
                save_to_json(users, output)

            console.print(f"[green]✓ Sauvegardé dans {output}[/green]")

            # Stats finales
            avg_followers = sum(u["followers_count"] for u in users) / len(users)
            verified_count = sum(1 for u in users if u["verified"])
            with_bio = sum(1 for u in users if u["bio"])

            console.print(f"\n[bold]Stats:[/bold]")
            console.print(f"  • Followers moyen: {avg_followers:,.0f}")
            console.print(f"  • Comptes vérifiés: {verified_count} ({verified_count/len(users)*100:.1f}%)")
            console.print(f"  • Avec bio: {with_bio} ({with_bio/len(users)*100:.1f}%)")

        # Nettoyer le fichier d'état si terminé
        state_path = Path(state_file)
        if state_path.exists() and (not max_records or len(users) >= max_records):
            state_path.unlink()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interruption! Sauvegarde de l'état...[/yellow]")
        if scraper.last_cursor:
            save_state({
                "username": username,
                "list_type": list_type,
                "cursor": scraper.last_cursor,
                "count": len(users) if 'users' in dir() else 0,
                "timestamp": datetime.now().isoformat(),
            }, f"{username}_{list_type}_state.json")
            console.print(f"[green]État sauvegardé. Reprends avec --cursor[/green]")

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
