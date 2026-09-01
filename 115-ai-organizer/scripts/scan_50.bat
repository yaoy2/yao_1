@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo 即将扫描「云下载」下最多 50 个文件。只读，不会移动或改名。
python -m app scan --dir "/云下载" --depth 8 --max-files 50
pause
