@echo off
chcp 65001 >nul
cd /d E:\OpenList
if not exist openlist.exe (
  echo 没有找到 E:\OpenList\openlist.exe
  echo 请先按 README 安装 OpenList。
  pause
  exit /b 1
)
openlist.exe start
echo OpenList 已请求启动。请打开浏览器访问：
echo http://127.0.0.1:5244
pause
