@echo off
REM Civora AI - restore a database backup. Stop the Civora server first.
cd /d "%~dp0"
echo Available backups (newest first):
".venv\Scripts\python.exe" data_safety.py list
echo.
set "N="
set /p N=Type the backup NUMBER to restore, or press Enter to cancel: 
if "%N%"=="" (
  echo Cancelled. Nothing changed.
  pause
  exit /b 0
)
".venv\Scripts\python.exe" data_safety.py restore %N%
pause
