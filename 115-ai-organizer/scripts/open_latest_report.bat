@echo off
chcp 65001 >nul
cd /d "%~dp0.."
for /f "delims=" %%F in ('dir /b /a-d /o-d "reports\115_整理报告_*.html" 2^>nul') do (
  start "" "reports\%%F"
  exit /b 0
)
echo 尚未找到报告，请先运行 full_scan_and_report.bat。
pause
