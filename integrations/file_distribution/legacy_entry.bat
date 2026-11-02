@echo off
setlocal
chcp 65001 >nul
title M20 文件分发
rem Build template: the builder fills the exact versioned executable name.
set "M20_ENTRY=__M20_ENTRY_FILENAME__"
if not exist "%~dp0%M20_ENTRY%" (
  echo 请等待 Drive 同步完成，确认本目录已有 %M20_ENTRY%。
  pause
  exit /b 1
)
start "" "%~dp0%M20_ENTRY%"
exit /b 0
