@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Chua cai dat. Hay chay setup-windows.bat truoc.
  pause
  exit /b 1
)
if not exist ".env" (
  echo Chua co tep .env. Hay chay setup-windows.bat truoc.
  pause
  exit /b 1
)

call .venv\Scripts\activate.bat
start "" http://127.0.0.1:8765
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
pause

