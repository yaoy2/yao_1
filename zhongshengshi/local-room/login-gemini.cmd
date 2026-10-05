@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Google Antigravity Login - Gemini
python -X utf8 login_cli.py gemini
pause
