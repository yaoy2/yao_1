@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo 即将扫描「云下载」下最多 5000 个文件。只读，不会移动或改名。
echo 这一步会比 50/500 更久，但仍不会下载视频，也不会改 115 文件。
pause
python -m app scan --dir "/云下载" --depth 20 --max-files 5000
pause
