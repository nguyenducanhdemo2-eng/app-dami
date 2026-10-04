@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Khong tim thay Python. Hay cai Python 3.11 hoac 3.12 va chon Add Python to PATH.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv 2>nul || py -3.11 -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if not exist ".env" python scripts\generate_secrets.py

echo.
echo Cai dat xong. Hay mo tep .env de dien thong tin Meta App.
pause

