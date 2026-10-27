param(
    [ValidateSet('start','stop','start-all','stop-all','status','open','qq-start','qq-stop','backup','autostart-enable','autostart-disable')]
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
$wcTaskName = 'WhaleCompanion-L'
$wcTaskDescription = 'Whale companion launcher managed by integrations/whale_companion/manage.ps1'
New-Item -ItemType Directory -Path $wcLog -Force | Out-Null
function Get-WhaleProcess([bool]$QQ = $false) {
    @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'node.exe'" |
        Where-Object {
            if ($QQ) {
                # The portable bridge also owns a Node worker in this exact runtime.
                $_.ExecutablePath -eq $wcNode
            } else {
                $_.Name -eq 'python.exe' -and $_.CommandLine -and
                    $_.CommandLine.Contains($wcRunner) -and $_.CommandLine.Contains($wcRoot)
            }
        })
}
switch ($Action) {
    { $_ -in 'autostart-enable','autostart-disable' } {
        $wcExistingTask = Get-ScheduledTask -TaskName $wcTaskName -ErrorAction SilentlyContinue
        if ($wcExistingTask -and $wcExistingTask.Description -ne $wcTaskDescription) {
            throw 'An unrelated scheduled task has this name. No task was changed.'
        }
        if ($Action -eq 'autostart-disable') {
            if ($wcExistingTask) { Disable-ScheduledTask -TaskName $wcTaskName | Out-Null }
            Write-Output 'Login autostart disabled. Running processes were preserved.'
            break
        }
        $wcUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $wcTrigger = New-ScheduledTaskTrigger -AtLogOn -User $wcUser
        $wcTrigger.Delay = 'PT30S'
        $wcArguments = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' +
            $PSCommandPath + '" -Action start-all -RuntimeRoot "' + $wcRoot + '"'
        $wcTaskAction = New-ScheduledTaskAction -Execute (Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe') `
            -Argument $wcArguments -WorkingDirectory $wcRoot
        $wcPrincipal = New-ScheduledTaskPrincipal -UserId $wcUser -LogonType Interactive -RunLevel Limited
        $wcSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
        Register-ScheduledTask -TaskName $wcTaskName -Description $wcTaskDescription -Action $wcTaskAction `
            -Trigger $wcTrigger -Principal $wcPrincipal -Settings $wcSettings -Force | Out-Null
        Write-Output 'Login autostart enabled for this Windows user, with a 30-second delay.'
    }
    'start-all' {
        & $PSCommandPath -Action start -RuntimeRoot $wcRoot
        & $PSCommandPath -Action qq-start -RuntimeRoot $wcRoot
    }
    'stop-all' {
        & $PSCommandPath -Action qq-stop -RuntimeRoot $wcRoot
        & $PSCommandPath -Action stop -RuntimeRoot $wcRoot
    }
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
    'stop' {
        Get-WhaleProcess | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
        if ((Get-WhaleProcess).Count) { throw 'AstrBot did not fully stop.' }
        Write-Output 'AstrBot stopped.'
    }
    'qq-start' {
        $wcQQProcesses = @(Get-WhaleProcess $true)
        if ($wcQQProcesses.Count) {
            if (-not @($wcQQProcesses | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($wcQQEntry) }).Count) {
                throw 'A QQ bridge worker remains without its launcher. Run qq-stop before starting again.'
            }
            Write-Output 'QQ bridge is already running.'
            break
        }
        if (Get-NetTCPConnection -State Listen -LocalPort 6099 -ErrorAction SilentlyContinue) { throw 'Port 6099 is in use.' }
        $wcPreviousQuickAccount = $env:NAPCAT_QUICK_ACCOUNT
        try {
            # Only reuse the dedicated account already verified for this instance.
            $env:NAPCAT_QUICK_ACCOUNT = if ($wcReceipt.qq_account_logged_in -and
                [string]$wcReceipt.bot_qq -match '^\d{5,12}$') { [string]$wcReceipt.bot_qq } else { $null }
            Start-Process -FilePath $wcNode -ArgumentList ('"' + $wcQQEntry + '"') `
                -WorkingDirectory (Join-Path $wcRoot 'napcat') -WindowStyle Hidden `
                -RedirectStandardOutput (Join-Path $wcLog 'napcat.stdout.log') `
                -RedirectStandardError (Join-Path $wcLog 'napcat.stderr.log') | Out-Null
        } finally {
            $env:NAPCAT_QUICK_ACCOUNT = $wcPreviousQuickAccount
        }
        Write-Output 'QQ login page: http://127.0.0.1:6099'
    }
    'qq-stop' {
        Get-WhaleProcess $true | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
        if ((Get-WhaleProcess $true).Count) { throw 'QQ bridge did not fully stop.' }
        Write-Output 'QQ bridge stopped.'
    }
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
