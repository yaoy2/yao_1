@echo off
cd /d "%~dp0"

echo [1/4] Current folder:
cd

echo.
echo [2/4] Creating virtual environment...
python -m venv .venv

echo.
echo [3/4] Installing pip tools...
".venv\Scripts\python.exe" -m pip install --upgrade pip

echo.
echo [4/4] Installing requirements...
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo.
echo Done.
echo You can now double click: start_wechat_archiver.bat
pause