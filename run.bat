@echo off
cd /d "%~dp0"
set FILESENSE_DB_USER=root
set /p FILESENSE_DB_PASSWORD=Enter MySQL root password: 
if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe main.py
) else (
    python main.py
)
pause