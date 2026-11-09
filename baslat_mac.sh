#!/bin/zsh
cd "$(dirname "$0")"
echo "[*] GitHub uzerinden en guncel surum cekiliyor..."
git pull --rebase --autostash origin main
adb start-server 2>/dev/null
./venv/bin/python src/gui.py
