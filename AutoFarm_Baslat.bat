@echo off
title AutoFarm-30 // Enterprise Command Center Launcher
color 0B
cd /d "%~dp0"
echo ===================================================
echo [1/3] GitHub uzerinden son guncellemeler cekiliyor...
echo ===================================================
git fetch origin main
git reset --hard origin/main
echo.
echo ===================================================
echo [2/3] Sanal ortam ve kutuphaneler senkronize ediliyor...
echo ===================================================
call venv\Scripts\activate
python -m pip install -r requirements.txt --quiet
echo.
echo ===================================================
echo [3/3] AutoFarm-30 Komuta Merkezi baslatiliyor...
echo ===================================================
python src/gui.py
pause
