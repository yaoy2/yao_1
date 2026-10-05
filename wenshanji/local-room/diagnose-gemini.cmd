@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "outputs\" mkdir "outputs"
python -X utf8 gemini_bridge.py --diagnose > "outputs\gemini-diagnostic.txt" 2>&1
set "GEMINI_DIAGNOSTIC_EXIT=%errorlevel%"
type "outputs\gemini-diagnostic.txt"
echo.
echo Report: %~dp0outputs\gemini-diagnostic.txt
echo This check does not sign in or call Google.
pause
exit /b %GEMINI_DIAGNOSTIC_EXIT%
