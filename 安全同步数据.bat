@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 请先完成首次安装。
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\data_repo_sync.py pull --all
pause
