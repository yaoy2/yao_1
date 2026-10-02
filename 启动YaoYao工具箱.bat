@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo 尚未完成首次安装，请先双击“首次安装.bat”。
  pause
  exit /b 1
)

".venv\Scripts\python.exe" scripts\data_repo_sync.py pull --all
if errorlevel 1 (
  echo 数据核对未通过，已保留本机与云端记录。请查看上方原因后再启动。
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\local_password_setup.py
if errorlevel 1 (
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m streamlit run hello.py
if errorlevel 1 (
  echo.
  echo 启动失败，请查看上方错误信息。
  pause
)
