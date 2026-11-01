@echo off
setlocal
chcp 65001 >nul
title M20 文件分发
if not exist "%~dp0文件分发.exe" (
  echo 请等待 Drive 同步完成，确认本目录已有 文件分发.exe。
  pause
  exit /b 1
)
start "" "%~dp0文件分发.exe"
exit /b 0
