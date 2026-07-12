@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo 尚未完成首次安装，请先双击“首次安装.bat”。
  pause
  exit /b 1
)

echo 正在检查整个项目，请稍候...
".venv\Scripts\python.exe" -m pytest -q
set TEST_EXIT=%ERRORLEVEL%

echo.
if "%TEST_EXIT%"=="0" (
  echo 全部测试通过。
) else (
  echo 测试未全部通过，请保留上方错误信息交给 Codex 排查。
)
pause
exit /b %TEST_EXIT%
