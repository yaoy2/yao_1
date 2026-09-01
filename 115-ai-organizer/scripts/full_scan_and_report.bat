@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo 此操作只读取115，并在本地生成HTML、Excel和JSON报告。
set /p ROOT_ID=请粘贴要扫描文件夹链接中 cid= 后面的数字：
if "%ROOT_ID%"=="" exit /b 1
python -m app full-workflow --root-folder-id "%ROOT_ID%" --dir "/云下载" --depth 8 --max-files 0 --output-dir "reports"
pause
