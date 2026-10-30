param(
    [ValidateSet('start','stop','start-all','stop-all','status','qq-start','qq-stop','autostart-enable','autostart-disable')]
    [string]$Action = 'status',
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot '..\..\.local\gpt_qq')
)
$ErrorActionPreference = 'Stop'
$gqRoot = [IO.Path]::GetFullPath($RuntimeRoot)
$gqReceiptPath = Join-Path $gqRoot 'installation.json'
$gqReceipt = Get-Content -LiteralPath $gqReceiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($gqReceipt.expected_host -ne [Environment]::MachineName) { throw 'This installation belongs to another computer.' }
$gqRunner = Join-Path $PSScriptRoot 'run.py'
$gqPython = Join-Path $gqRoot ('app\AstrBot-' + $gqReceipt.app_version + '\.venv\Scripts\python.exe')
$gqNode = Join-Path $gqRoot 'napcat\node.exe'
$gqEntry = Join-Path $gqRoot 'napcat\index.js'
$gqLog = Join-Path $gqRoot 'logs'
$gqTaskName = 'GPTQQ-' + $gqReceipt.bot_qq
$gqTaskDescription = 'Independent GPT QQ instance: ' + $gqRoot
New-Item -ItemType Directory -Path $gqLog -Force | Out-Null
function Get-GptQQProcess([bool]$QQ = $false) {
    @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='node.exe'" | Where-Object {
        if ($QQ) { $_.ExecutablePath -eq $gqNode }
        else { $_.Name -eq 'python.exe' -and $_.CommandLine -and $_.CommandLine.Contains($gqRunner) -and $_.CommandLine.Contains($gqRoot) }
    })
}
function Assert-GptQQPortFree([int]$Port) {
    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
        throw "Port $Port is already occupied. No existing process was changed."
    }
}
switch ($Action) {
    'start-all' {
        & $PSCommandPath -Action start -RuntimeRoot $gqRoot
        & $PSCommandPath -Action qq-start -RuntimeRoot $gqRoot
    }
    'stop-all' {
        & $PSCommandPath -Action qq-stop -RuntimeRoot $gqRoot
        & $PSCommandPath -Action stop -RuntimeRoot $gqRoot
    }
    'start' {
        if ((Get-GptQQProcess).Count) { Write-Output 'GPT QQ is already running.'; break }
        Assert-GptQQPortFree $gqReceipt.ports.dashboard
        Assert-GptQQPortFree $gqReceipt.ports.onebot
        $env:PYTHONIOENCODING = 'utf-8'
        Start-Process -FilePath $gqPython -ArgumentList @('-B','-u',('"' + $gqRunner + '"'),('"' + $gqRoot + '"')) `
            -WorkingDirectory $gqRoot -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $gqLog 'astrbot.stdout.log') `
            -RedirectStandardError (Join-Path $gqLog 'astrbot.stderr.log') | Out-Null
        Write-Output ('GPT QQ starting: http://127.0.0.1:' + $gqReceipt.ports.dashboard)
    }
    'qq-start' {
        $gqProcesses = @(Get-GptQQProcess $true)
        if ($gqProcesses.Count) {
            if (-not @($gqProcesses | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($gqEntry) }).Count) {
                throw 'A worker remains without its launcher; stop this instance before restarting.'
            }
            Write-Output 'This QQ bridge is already running.'; break
        }
        Assert-GptQQPortFree $gqReceipt.ports.napcat
        $gqPrevious = $env:NAPCAT_QUICK_ACCOUNT
        try {
            $env:NAPCAT_QUICK_ACCOUNT = [string]$gqReceipt.bot_qq
            Start-Process -FilePath $gqNode -ArgumentList ('"' + $gqEntry + '"') `
                -WorkingDirectory (Join-Path $gqRoot 'napcat') -WindowStyle Hidden `
                -RedirectStandardOutput (Join-Path $gqLog 'napcat.stdout.log') `
                -RedirectStandardError (Join-Path $gqLog 'napcat.stderr.log') | Out-Null
        } finally { $env:NAPCAT_QUICK_ACCOUNT = $gqPrevious }
        Write-Output ('QQ login: http://127.0.0.1:' + $gqReceipt.ports.napcat)
    }
    { $_ -in 'stop','qq-stop' } {
        $gqQQ = $Action -eq 'qq-stop'
        foreach ($gqProcess in @(Get-GptQQProcess $gqQQ)) {
            # Re-read the PID and match this installation before stopping anything.
            $gqLive = Get-CimInstance Win32_Process -Filter "ProcessId=$($gqProcess.ProcessId)" -ErrorAction SilentlyContinue
            if ($gqLive -and $gqLive.ExecutablePath -eq $gqProcess.ExecutablePath -and $gqLive.CreationDate -eq $gqProcess.CreationDate) {
                Stop-Process -Id $gqLive.ProcessId -ErrorAction SilentlyContinue
            }
        }
        for ($gqAttempt = 0; $gqAttempt -lt 10 -and (Get-GptQQProcess $gqQQ).Count; $gqAttempt++) { Start-Sleep -Milliseconds 200 }
        if ((Get-GptQQProcess $gqQQ).Count) { throw 'This instance did not fully stop.' }
        Write-Output 'This component stopped.'
    }
    'status' {
        foreach ($gqQQ in @($false,$true)) {
            $gqProcesses = @(Get-GptQQProcess $gqQQ)
            [pscustomobject]@{ Component = $(if($gqQQ){'GPT QQ bridge'}else{'GPT AstrBot'}); Running = [bool]$gqProcesses.Count; ProcessIds = ($gqProcesses.ProcessId -join ',') }
        }
        Get-ScheduledTask -TaskName $gqTaskName -ErrorAction SilentlyContinue | Select-Object TaskName,State
    }
    { $_ -in 'autostart-enable','autostart-disable' } {
        $gqExisting = Get-ScheduledTask -TaskName $gqTaskName -ErrorAction SilentlyContinue
        if ($gqExisting -and $gqExisting.Description -ne $gqTaskDescription) { throw 'An unrelated task already has this name.' }
        if ($Action -eq 'autostart-disable') {
            if ($gqExisting) { Disable-ScheduledTask -TaskName $gqTaskName | Out-Null }
            $gqReceipt.login_autostart_enabled = $false
        } else {
            if (-not $gqReceipt.qq_account_logged_in) { throw 'Verify the intended QQ account before enabling autostart.' }
            $gqUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
            $gqTrigger = New-ScheduledTaskTrigger -AtLogOn -User $gqUser
            $gqTrigger.Delay = 'PT30S'
            $gqArguments = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -Action start-all -RuntimeRoot "' + $gqRoot + '"'
            $gqTaskAction = New-ScheduledTaskAction -Execute (Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe') -Argument $gqArguments -WorkingDirectory $gqRoot
            $gqPrincipal = New-ScheduledTaskPrincipal -UserId $gqUser -LogonType Interactive -RunLevel Limited
            $gqSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
            Register-ScheduledTask -TaskName $gqTaskName -Description $gqTaskDescription -Action $gqTaskAction -Trigger $gqTrigger -Principal $gqPrincipal -Settings $gqSettings -Force | Out-Null
            $gqReceipt.login_autostart_enabled = $true
        }
        $gqReceipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $gqReceiptPath -Encoding UTF8
        Write-Output ('GPT QQ login autostart: ' + $gqReceipt.login_autostart_enabled)
    }
}
