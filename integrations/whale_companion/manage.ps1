param(
    [ValidateSet('start','stop','status','open','qq-start','qq-stop','backup')]
    [string]$Action = 'status',
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot '..\..\.local\whale_companion')
)
$ErrorActionPreference = 'Stop'
$wcRoot = [IO.Path]::GetFullPath($RuntimeRoot)
$wcReceipt = Get-Content -LiteralPath (Join-Path $wcRoot 'installation.json') -Raw | ConvertFrom-Json
if ($wcReceipt.expected_host -ne [Environment]::MachineName) { throw 'This installation belongs to a different computer. Inspect before starting it.' }
$wcRunner = Join-Path $PSScriptRoot 'run.py'
$wcPython = Join-Path $wcRoot 'app\AstrBot-4.29.3\.venv\Scripts\python.exe'
$wcNode = Join-Path $wcRoot 'napcat\node.exe'
$wcQQEntry = Join-Path $wcRoot 'napcat\index.js'
$wcLog = Join-Path $wcRoot 'logs'
New-Item -ItemType Directory -Path $wcLog -Force | Out-Null
function Get-WhaleProcess([bool]$QQ = $false) {
    $wcExecutable = if ($QQ) { $wcNode } else { $wcPython }
    $wcEntry = if ($QQ) { $wcQQEntry } else { $wcRunner }
    @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'node.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine.Contains($wcEntry) -and
            $(if ($QQ) { $_.ExecutablePath -eq $wcExecutable } else { $_.Name -eq 'python.exe' -and $_.CommandLine.Contains($wcRoot) }) })
}
switch ($Action) {
    'start' {
        if ((Get-WhaleProcess).Count) { Write-Output 'AstrBot is already running.'; break }
        $wcListener = Get-NetTCPConnection -State Listen -LocalPort 6188 -ErrorAction SilentlyContinue
        if ($wcListener) { throw 'Port 6188 is in use. No process was changed.' }
        $env:PYTHONIOENCODING = 'utf-8'
        Start-Process -FilePath $wcPython -ArgumentList @('-u',('"' + $wcRunner + '"'),('"' + $wcRoot + '"')) `
            -WorkingDirectory $wcRoot -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $wcLog 'astrbot.stdout.log') `
            -RedirectStandardError (Join-Path $wcLog 'astrbot.stderr.log') | Out-Null
        Write-Output 'AstrBot starting. Dashboard: http://127.0.0.1:6188'
    }
    'stop' { Get-WhaleProcess | ForEach-Object { Stop-Process -Id $_.ProcessId }; Write-Output 'AstrBot stopped.' }
    'qq-start' {
        if ((Get-WhaleProcess $true).Count) { Write-Output 'QQ bridge is already running.'; break }
        if (Get-NetTCPConnection -State Listen -LocalPort 6099 -ErrorAction SilentlyContinue) { throw 'Port 6099 is in use.' }
        Start-Process -FilePath $wcNode -ArgumentList ('"' + $wcQQEntry + '"') `
            -WorkingDirectory (Join-Path $wcRoot 'napcat') -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $wcLog 'napcat.stdout.log') `
            -RedirectStandardError (Join-Path $wcLog 'napcat.stderr.log') | Out-Null
        Write-Output 'QQ login page: http://127.0.0.1:6099'
    }
    'qq-stop' { Get-WhaleProcess $true | ForEach-Object { Stop-Process -Id $_.ProcessId }; Write-Output 'QQ bridge stopped.' }
    'open' { Start-Process 'http://127.0.0.1:6188' }
    'status' {
        foreach ($wcQQ in @($false, $true)) {
            $wcProcesses = @(Get-WhaleProcess $wcQQ)
            $wcWorkingSet = 0
            foreach ($wcProcess in $wcProcesses) {
                $wcWorkingSet += (Get-Process -Id $wcProcess.ProcessId -ErrorAction SilentlyContinue).WorkingSet64
            }
            [pscustomobject]@{ Component = $(if($wcQQ){'QQ bridge'}else{'AstrBot'}); Running = [bool]$wcProcesses.Count;
                ProcessIds = ($wcProcesses.ProcessId -join ','); WorkingSetMB = [math]::Round($wcWorkingSet / 1MB, 1) }
        }
    }
    'backup' {
        if ((Get-WhaleProcess).Count -or (Get-WhaleProcess $true).Count) { throw 'Stop AstrBot and the QQ bridge before a consistent full backup.' }
        $wcBackupDir = Join-Path $wcRoot 'backups'
        New-Item -ItemType Directory -Path $wcBackupDir -Force | Out-Null
        $wcBackup = Join-Path $wcBackupDir ('whale-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.zip')
        Compress-Archive -LiteralPath @((Join-Path $wcRoot 'state'),(Join-Path $wcRoot 'local-access.json'),
            (Join-Path $wcRoot 'installation.json'),(Join-Path $wcRoot 'napcat\napcat\config')) -DestinationPath $wcBackup
        Write-Output $wcBackup
    }
}
