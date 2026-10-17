@echo off
REM Civora AI - one-time setup on a Windows PC: creates .venv, installs packages, runs the tests.
cd /d "%~dp0"
where python >nul 2>nul || (echo Python not found. Install it with:  winget install -e --id Python.Python.3.12 & echo Then close and reopen CMD and run setup.bat again. & exit /b 1)
if not exist .venv\Scripts\python.exe (
  echo Creating .venv ...
  python -m venv .venv || exit /b 1
)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-app.txt || exit /b 1
.venv\Scripts\python.exe run_tests.py
echo.
echo Setup finished. Start Civora with:  run.bat   then open http://127.0.0.1:8000
