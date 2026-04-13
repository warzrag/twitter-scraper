#!/usr/bin/env python3
"""Test script pour debugger le scraper"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
from scraper import TwitterScraper, extract_username

cookies = [
    {'name': 'auth_token', 'value': 'aa6926e875a5ccea16a927a310603f1471fa1e5c'},
    {'name': 'ct0', 'value': 'a31d3dd4883c225c2a9240f5fd448f70a5400add641962b1cb5e6786af76be0a7ed627a0f9ff87cfeb76c66a26fdc6760be05479cab72fa1468fc7ddc86c60cc3d12a388d6a6bb8c0db6b23f95e3dc2e'}
]

print("=" * 50)
print("TEST DU SCRAPER TWITTER")
print("=" * 50)

scraper = TwitterScraper(cookies=cookies, min_wait=1, max_wait=2)

print("\n[1] Test récupération info utilisateur...")
info = scraper.get_user_info('lolaafck')

if info:
    print(f"    OK - User ID: {info['id']}")
    print(f"    Nom: {info['name']}")
    print(f"    Followers: {info['followers_count']}")

    print("\n[2] Test scraping followers API v1.1 (5 max)...")
    count = 0
    try:
        for user in scraper.scrape_list_v1(info['id'], max_records=5):
            print(f"    Found: @{user['username']} ({user['followers_count']} followers)")
            count += 1
    except Exception as e:
        print(f"    ERREUR v1.1: {e}")

    if count == 0:
        print("\n[3] Test scraping followers GraphQL (5 max)...")
        try:
            for user in scraper.scrape_list(info['id'], max_records=5):
                print(f"    Found: @{user['username']} ({user['followers_count']} followers)")
                count += 1
        except Exception as e:
            print(f"    ERREUR GraphQL: {e}")

    print(f"\n    Total récupérés: {count}")
else:
    print("    ERREUR - Impossible de récupérer les infos utilisateur")

scraper.close()
print("\n" + "=" * 50)
input("Appuie sur Entrée pour fermer...")
