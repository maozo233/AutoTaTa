@echo off
cd /d "%~dp0.."
.venv\Scripts\python.exe -m pip install -r requirements\build.txt
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe tools\build.py %*
set "AUTOTATA_BUILD_EXIT=%ERRORLEVEL%"
pause
exit /b %AUTOTATA_BUILD_EXIT%
