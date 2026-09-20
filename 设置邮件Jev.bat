@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Please run the project installer first.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "scripts\mail_jev_setup.py"
