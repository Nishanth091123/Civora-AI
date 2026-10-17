@echo off
REM Civora AI - remove unwanted files from this folder (v3.7.0)
REM Nothing is erased: everything is MOVED into _to_delete\ so you can check it first,
REM then delete that one folder yourself.  Your data\ folder (users, projects, drawings) is kept.
REM   cleanup.bat         remove junk + old duplicate drawings
REM   cleanup.bat reset   ALSO move data\ and backups\ (fresh start: all users/projects/uploaded drawings)
cd /d "%~dp0"
set T=_to_delete
if not exist "%T%" mkdir "%T%"
echo Moving unwanted files to %T% ...
for %%F in (sample.dxf Civora_Complete_Test_Plan.dxf Civora_Complete_Test_Plan.jpg Civora_Complete_Test_Plan.pdf Civora_Complete_Test_Plan.png Drawing_Input_Reference.csv) do if exist "%%F" move /y "%%F" "%T%\" >nul && echo   %%F
for %%F in (*.zip *.bak *.tmp *.log *.orig *.rej) do if exist "%%F" move /y "%%F" "%T%\" >nul && echo   %%F
if exist _archive move /y _archive "%T%\_archive" >nul && echo   _archive\
if exist .pytest_cache move /y .pytest_cache "%T%\.pytest_cache" >nul && echo   .pytest_cache\
for /d /r %%D in (__pycache__) do if exist "%%D" rd /s /q "%%D"
echo   (Python cache folders removed)
if /i "%1"=="reset" (
  echo.
  echo RESET: this moves data\ and backups\ - ALL users, logins, projects and uploaded drawings on this PC.
  set /p OK=Type YES to continue: 
  call :reset
)
echo.
echo Done. Check the %T% folder, then delete it. Keep: data\, .venv\, sample_drawings\, all .py files.
goto :eof
:reset
if /i not "%OK%"=="YES" (echo Reset cancelled.& goto :eof)
if exist data move /y data "%T%\data" >nul && echo   data\
if exist backups move /y backups "%T%\backups" >nul && echo   backups\
goto :eof
