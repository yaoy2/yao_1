@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo 警告：此步骤会按照已审核清单在115中新建目录、改名和移动；不会删除或覆盖文件。
set /p MANIFEST=请粘贴操作清单 JSON 的完整路径：
if "%MANIFEST%"=="" exit /b 1
set /p CONFIRM=请粘贴清单生成时显示的 APPLY- 确认码：
if "%CONFIRM%"=="" exit /b 1
python -m app execute-open115 --manifest "%MANIFEST%" --confirm "%CONFIRM%"
pause
