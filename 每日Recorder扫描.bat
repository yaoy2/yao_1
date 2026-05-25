@echo off
cd /d E:\github\yao_1
if not exist logs mkdir logs
echo ===== %date% %time% ===== >> logs\recorder_scan.log
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
    git push >> logs\recorder_scan.log 2>&1
) else (
    echo no recorder cloud changes to commit >> logs\recorder_scan.log
)

if not "%scan_exit%"=="0" exit /b %scan_exit%
exit /b %export_exit%
