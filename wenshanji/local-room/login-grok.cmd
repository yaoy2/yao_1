@echo off
setlocal
cd /d "%~dp0"
python -X utf8 login_cli.py grok
pause
