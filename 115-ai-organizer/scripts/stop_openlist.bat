@echo off
chcp 65001 >nul
cd /d E:\OpenList
if not exist openlist.exe (
  echo 没有找到 E:\OpenList\openlist.exe
  pause
  exit /b 1
)
openlist.exe stop
echo OpenList 已请求停止。
pause
