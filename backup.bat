@echo off
REM Civora AI - make a database backup now (safe while the app is running)
cd /d "%~dp0"
".venv\Scripts\python.exe" data_safety.py backup
".venv\Scripts\python.exe" data_safety.py check
pause
