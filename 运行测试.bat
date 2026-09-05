@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo 尚未完成首次安装，请先双击“首次安装.bat”。
  pause
  exit /b 1
)

echo 正在检查主工具箱，请稍候（独立子项目请使用各自的测试入口）...
".venv\Scripts\python.exe" -m pytest -q tests
set TEST_EXIT=%ERRORLEVEL%

echo.
if "%TEST_EXIT%"=="0" (
  echo 全部测试通过。
) else (
  echo 测试未全部通过，请保留上方错误信息交给 Codex 排查。
)
pause
exit /b %TEST_EXIT%
