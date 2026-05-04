@echo off
cd /d "%~dp0"

echo Starting WeChat Archiver GUI...
echo.
".venv\Scripts\python.exe" -m streamlit run wechat_app.py

pause