@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo [mp_watch] 工作目录: %CD%
echo [mp_watch] 配置: config\mp_watch_sources.json
echo [mp_watch] 状态: data\mp_watch_state.json
echo [mp_watch] 日志: logs\mp_watch_YYYY-MM-DD.log
echo.

python -m mp_watch %*
set EXITCODE=%ERRORLEVEL%

echo.
echo [mp_watch] 退出码: %EXITCODE%
exit /b %EXITCODE%
