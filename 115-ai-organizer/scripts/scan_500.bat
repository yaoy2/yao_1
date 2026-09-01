@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo 即将扫描「云下载」下最多 500 个文件。只读，不会移动或改名。
echo 请确认 50 个文件的扫描已经成功，再继续。
pause
python -m app scan --dir "/云下载" --depth 12 --max-files 500
pause
