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
echo [4/4] Installing runtime and test requirements...
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 (
  echo.
  echo Installation failed. Check the network connection and the error message above.
  pause
  exit /b 1
)

echo.
echo Done.
echo You can now double click:
echo   启动YaoYao工具箱.bat
echo   运行测试.bat
pause
