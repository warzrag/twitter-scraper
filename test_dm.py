#!/usr/bin/env python3
"""Test pour voir les champs disponibles dans l'API"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import json
from scraper import TwitterScraper

cookies = [
    {'name': 'auth_token', 'value': 'aa6926e875a5ccea16a927a310603f1471fa1e5c'},
    {'name': 'ct0', 'value': 'a31d3dd4883c225c2a9240f5fd448f70a5400add641962b1cb5e6786af76be0a7ed627a0f9ff87cfeb76c66a26fdc6760be05479cab72fa1468fc7ddc86c60cc3d12a388d6a6bb8c0db6b23f95e3dc2e'}
]

scraper = TwitterScraper(cookies=cookies, min_wait=1, max_wait=2)
info = scraper.get_user_info('lolaafck')

if info:
    # Faire une requête raw pour voir tous les champs
    import httpx

    url = "https://x.com/i/api/1.1/followers/list.json"
    params = {
        "user_id": info['id'],
        "count": 5,
        "cursor": "-1",
        "skip_status": "false",
        "include_user_entities": "true",
    }

    response = scraper.client.get(url, params=params)
    data = response.json()

    # Sauvegarder pour analyse
    with open("debug_followers_raw.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("Réponse sauvegardée dans debug_followers_raw.json")

    # Afficher les clés disponibles pour le premier user
    if data.get("users"):
        user = data["users"][0]
        print(f"\nClés disponibles pour @{user.get('screen_name')}:")
        for key in sorted(user.keys()):
            val = user[key]
            if isinstance(val, bool) or key in ['can_dm', 'following', 'followed_by', 'can_media_tag']:
                print(f"  {key}: {val}")

scraper.close()
