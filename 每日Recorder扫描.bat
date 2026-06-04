@echo off
cd /d E:\github\yao_1
if not exist logs mkdir logs
echo ===== %date% %time% ===== >> logs\recorder_scan.log

set "current_branch="
for /f "usebackq delims=" %%B in (`git branch --show-current`) do set "current_branch=%%B"
echo current_branch=%current_branch% >> logs\recorder_scan.log
if not "%current_branch%"=="main" (
    echo Recorder scan stopped: current branch is not main. >> logs\recorder_scan.log
    exit /b 3
)

for /f "usebackq delims=" %%K in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY','User')"`) do set "DEEPSEEK_API_KEY=%%K"
"C:\Users\Yao\AppData\Local\Programs\Python\Python314\python.exe" -c "import os, sys; key=os.environ.get('DEEPSEEK_API_KEY',''); print('key_ready=' + str(len(key) > 10)); sys.exit(0 if len(key) > 10 else 2)" >> logs\recorder_scan.log 2>&1
if errorlevel 2 (
    echo DEEPSEEK_API_KEY is missing or too short. >> logs\recorder_scan.log
    exit /b 2
)

git fetch origin >> logs\recorder_scan.log 2>&1
set fetch_exit=%ERRORLEVEL%
echo fetch_exit_code=%fetch_exit% >> logs\recorder_scan.log
if not "%fetch_exit%"=="0" exit /b %fetch_exit%

git pull --rebase origin main >> logs\recorder_scan.log 2>&1
set pull_exit=%ERRORLEVEL%
echo pull_exit_code=%pull_exit% >> logs\recorder_scan.log
if not "%pull_exit%"=="0" exit /b %pull_exit%

"C:\Users\Yao\AppData\Local\Programs\Python\Python314\python.exe" scripts\scan_ding_minutes.py >> logs\recorder_scan.log 2>&1
set scan_exit=%ERRORLEVEL%
echo scan_exit_code=%scan_exit% >> logs\recorder_scan.log

"C:\Users\Yao\AppData\Local\Programs\Python\Python314\python.exe" scripts\sync_recorder_cloud.py >> logs\recorder_scan.log 2>&1
set export_exit=%ERRORLEVEL%
echo export_exit_code=%export_exit% >> logs\recorder_scan.log

git add data\ding_minutes_cloud.json >> logs\recorder_scan.log 2>&1
git diff --cached --quiet -- data\ding_minutes_cloud.json
if errorlevel 1 (
    git commit -m "data: sync recorder notes" -- data\ding_minutes_cloud.json >> logs\recorder_scan.log 2>&1
    git push origin main >> logs\recorder_scan.log 2>&1
) else (
    echo no recorder cloud changes to commit >> logs\recorder_scan.log
)

if not "%scan_exit%"=="0" exit /b %scan_exit%
exit /b %export_exit%
