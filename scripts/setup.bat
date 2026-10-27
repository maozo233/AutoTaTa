@echo off
cd /d "%~dp0.."
py -3.12 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Ready. Run scripts\start.bat.
pause
exit /b 0
:failed
echo Setup failed. Python 3.12 x64 is required.
pause
exit /b 1
