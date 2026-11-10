@echo off
cd /d "%~dp0"
set AUTOFARM_SKIP_AUTO_UPDATE=1
if not exist "venv\Scripts\python.exe" (
    echo Python ortami bulunamadi. Bu dosyayi mevcut autofarm-core klasorune koyun.
    pause
    exit /b 1
)
"venv\Scripts\python.exe" -c "import customtkinter; import PIL" 2>nul
if errorlevel 1 (
    echo Gerekli kutuphaneler eksik. Kurulum kilavuzundaki komutu uygulayin.
    pause
    exit /b 1
)
adb start-server
"venv\Scripts\python.exe" "src\gui.py"
if errorlevel 1 pause
