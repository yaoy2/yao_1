@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo 尚未完成首次安装，请先双击“首次安装.bat”。
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m streamlit run hello.py
if errorlevel 1 (
  echo.
  echo 启动失败，请查看上方错误信息。
  pause
)
