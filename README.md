# Twitter/X Followers Scraper 🐦

Scrape tous les followers d'un compte Twitter/X sans limites et sans payer 30€/mois pour Apify.

## Installation

```bash
cd twitter-followers-scraper
pip install -r requirements.txt
```

## Configuration

1. Copie le fichier de config exemple:
```bash
cp config_example.json config.json
```

2. Récupère tes cookies Twitter:
   - Va sur https://x.com et connecte-toi
   - Ouvre les DevTools (F12) → Application → Cookies → https://x.com
   - Copie les valeurs de `auth_token` et `ct0`

3. Remplis `config.json`:
```json
{
  "cookies": {
    "auth_token": "ton_auth_token_ici",
    "ct0": "ton_ct0_ici"
  },
  "proxy": null
}
```

## Utilisation

### Scraper tous les followers d'un compte:
```bash
python scraper.py elonmusk
```

### Limiter à 1000 followers:
```bash
python scraper.py elonmusk -m 1000
```

### Exporter en JSON:
```bash
python scraper.py elonmusk -f json -o followers.json
```

### Toutes les options:
```bash
python scraper.py --help
```

## Output

Le scraper génère un fichier CSV/JSON avec ces infos pour chaque follower:

| Champ | Description |
|-------|-------------|
| id | ID Twitter unique |
| username | @handle |
| name | Nom affiché |
| bio | Description du profil |
| followers_count | Nombre de followers |
| following_count | Nombre de following |
| tweets_count | Nombre de tweets |
| verified | Badge vérifié (bleu) |
| protected | Compte privé |
| profile_image | URL de la photo de profil |
| location | Localisation |
| website | Site web |
| created_at | Date de création |

## Notes

- **Rate Limiting**: Le scraper gère automatiquement les limites de Twitter avec des délais entre requêtes
- **Gros comptes**: Pour les comptes avec +100k followers, ça peut prendre du temps
- **Compte banni**: Utilise un compte secondaire pour éviter de risquer ton compte principal

## Proxy (optionnel)

Pour éviter les bans, tu peux utiliser un proxy:
```json
{
  "cookies": {...},
  "proxy": "http://user:pass@proxy.example.com:8080"
}
```
