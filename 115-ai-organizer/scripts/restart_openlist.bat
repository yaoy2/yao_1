@echo off
chcp 65001 >nul
cd /d E:\OpenList
openlist.exe restart
echo OpenList 已请求重启。请打开：http://127.0.0.1:5244
pause
