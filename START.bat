@echo off
title Twitter/X Scraper (Playwright)
echo.
echo  ============================================
echo    Twitter/X Scraper - Mode Apify
echo    Utilise Playwright pour can_dm reel
echo  ============================================
echo.
echo  Installation des dependances...
pip install -r requirements.txt -q

echo.
echo  Installation du navigateur Playwright...
playwright install chromium

echo.
echo  Demarrage du serveur...
echo.
echo  Ouvre ton navigateur sur: http://localhost:8000
echo.
echo  Pour arreter: Ferme cette fenetre ou Ctrl+C
echo.
echo  ============================================
echo.

cd /d "%~dp0"
start http://localhost:8000
python app.py

pause
