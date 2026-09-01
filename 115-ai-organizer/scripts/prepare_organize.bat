@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo 此步骤只生成操作清单，不会修改115。请先在网页中审核并批准计划。
set /p ROOT_ID=请粘贴本次扫描文件夹的 cid：
if "%ROOT_ID%"=="" exit /b 1
python -m app prepare-execution --scan-root-id "%ROOT_ID%" --scan-root-path "/云下载" --organize-dir "已整理"
pause
