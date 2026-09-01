@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo 即将打开 115 整理系统网页。
echo 这只会读取本地索引，不会修改 115 文件。
python -m streamlit run app/web.py --server.headless false --server.port 8502
pause
