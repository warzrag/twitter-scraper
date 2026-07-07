# Contexte du bot Twitter/X scraper

## Dossier et repo

- Dossier local principal : `E:\twitter-scraper`
- Repo GitHub : `https://github.com/warzrag/twitter-scraper`
- Branche : `main`
- Dernier commit important : `4c7a624` (`Fix queue scraper can_dm detection and progress`)

## Lancement

Depuis `E:\twitter-scraper` :

```powershell
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Interface :

- `http://localhost:8000/queue`
- Auth basique vue pendant les tests : `admin / changeme`

## Fonctionnement attendu

La page `/queue` sert a ajouter une ou plusieurs cibles Twitter/X, scraper leurs followers, lire le vrai champ `can_dm` depuis les reponses GraphQL Twitter, puis sortir uniquement les nouveaux profils DM ouverts.

Les compteurs importants :

- `Total scrapés` : nombre de profils followers recuperes.
- `DM trouvés` : nombre de profils avec `can_dm=true` detectes dans Twitter.
- `nouveaux` : profils `can_dm=true` qui ne sont pas deja dans `scraped_history.txt`.
- `deja vus DM` : profils `can_dm=true` ignores car deja presents dans l'historique.
- `fermes` : profils avec `can_dm=false`.
- `doublons total` : profils ignores car deja dans l'historique.

Exemple :

```text
DM 24 | nouveaux 4 | DM trouves 24 | deja vus DM 20 | fermes 19 | doublons total 20
```

Cela signifie que le bot a bien trouve 24 DM ouverts, mais seulement 4 sont nouveaux/exportables.

## Corrections faites

1. Le bot affichait parfois `0 validé` alors que Twitter renvoyait bien des `can_dm=true`.
   Cause : les profils etaient filtres par `scraped_history.txt` avant que l'interface montre clairement les DM trouves.

2. L'interface a ete corrigee pour separer :
   - DM trouves
   - nouveaux exportables
   - deja vus dans l'historique
   - fermes

3. Le scraping `/queue` utilise maintenant le flux GraphQL/Apify direct pour lire `dm_permissions.can_dm`, avec fallback Playwright.

4. Ajout de logs console/backend :
   - `[QUEUE UI] ...`
   - `[QUEUE <id>] ...`
   - `[APIFY] DM sample ...`
   - `[PLAYWRIGHT] DM sample ...`

5. Pagination :
   - Le bot capturait la premiere page correctement.
   - Sur certains comptes, la page 2 GraphQL renvoyait `404`.
   - Ajout d'un retry depuis la page X.com ouverte dans Playwright :

```text
[APIFY] 404 via context.request, retry depuis la page X.com...
[APIFY] Retry page X.com OK
```

Si `Retry page X.com OK` apparait, le bot devrait depasser la premiere page.

## Tests utiles

Test simple :

1. Ouvrir `/queue`.
2. Coller les cookies Twitter en JSON array.
3. Mettre une cible, par exemple `BenG92` ou `elihet`.
4. Mettre `Max par cible = 500`.
5. Lancer.
6. Verifier dans les logs si la pagination depasse environ 40-50 profils.

Si le bot reste bloque a environ 49 :

- regarder `server.log`
- chercher `404`, `Retry page X.com`, `APIFY`, `PLAYWRIGHT`
- le probleme est la pagination Twitter/X, pas le `can_dm`

## Historique

Le fichier `scraped_history.txt` evite de ressortir les memes profils.

Pour un test propre, cliquer sur `Reset` dans l'interface ou vider `scraped_history.txt`.

Attention : si l'historique contient deja des DM ouverts, le bot peut afficher beaucoup de `deja vus DM` et peu de `nouveaux`.

