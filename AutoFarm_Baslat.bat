@echo off
cd /d "%~dp0"
echo [*] GitHub uzerinden en guncel surum kontrol ediliyor ve cekiliyor...
git fetch origin main
git pull --rebase --autostash origin main
adb start-server
adb reconnect offline
start "" ".\venv\Scripts\python.exe" "src\gui.py"
