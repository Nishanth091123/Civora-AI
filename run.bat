@echo off
REM Civora AI v2.4 launcher
cd /d "%~dp0"
if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" set "PATH=C:\Program Files\Tesseract-OCR;%PATH%"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment .venv not found in %CD%
  pause
  exit /b 1
)
echo Starting Civora AI at http://127.0.0.1:8000  (Ctrl+C to stop)
".venv\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 8000
pause
