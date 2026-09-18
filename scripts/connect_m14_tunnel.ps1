param(
    [Parameter(Mandatory = $true)][ValidatePattern('^tunnel_[a-zA-Z0-9]+$')][string]$TunnelId,
    [Parameter(Mandatory = $true)][string]$ClientPath,
    [Parameter(Mandatory = $true)][string]$RuntimeKeyFile,
    [string]$LogFile,
    [switch]$RegisterAutoStart
)
$ErrorActionPreference = 'Stop'
# Windows PowerShell scheduled tasks otherwise decode native UTF-8 JSON as ANSI.
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
if ($LogFile) { Start-Transcript -LiteralPath $LogFile -Append | Out-Null }
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv-m14\Scripts\python.exe'
foreach ($path in @($taskPython, $ClientPath, $RuntimeKeyFile)) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file missing: $path" }
}
$ClientPath = (Resolve-Path -LiteralPath $ClientPath).Path
$RuntimeKeyFile = (Resolve-Path -LiteralPath $RuntimeKeyFile).Path
$taskProfileDir = Join-Path $env:LOCALAPPDATA 'OpenAI\m14-tunnel\profiles'
$taskMcp = '"{0}" "{1}" --transport stdio --env-file "{2}"' -f (
    $taskPython.Replace('\', '/'),
    (Join-Path $taskRoot 'scripts\m14_mcp.py').Replace('\', '/'),
    (Join-Path $taskRoot '.env.m14').Replace('\', '/')
)
# Windows PowerShell uses legacy native argument quoting.
$taskMcpArgument = if ($PSVersionTable.PSVersion.Major -le 5) { $taskMcp.Replace('"', '\"') } else { $taskMcp }
# Pass only a file reference, never a secret value on the command line.
$taskResult = & $ClientPath runtimes connect --json --alias m14 --tunnel-id $TunnelId `
    --profile m14 --profile-dir $taskProfileDir `
    --runtime-api-key ('file:' + $RuntimeKeyFile.Replace('\', '/')) --mcp-command $taskMcpArgument
if ($LASTEXITCODE -ne 0) { throw 'M14 tunnel could not start.' }
$taskStatus = & $ClientPath runtimes status m14 --json
if ($LASTEXITCODE -ne 0) { throw 'M14 tunnel status could not be read.' }
$taskState = $taskStatus | ConvertFrom-Json
$taskState | Select-Object alias, process_running, healthy, ready, runtime_state
if (!$taskState.process_running -or !$taskState.healthy -or !$taskState.ready) {
    throw 'M14 tunnel is not ready. Check the tunnel-client status and network.'
}

if ($RegisterAutoStart) {
    $taskName = 'M14 Todo Tunnel'
    $taskShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $taskArgs = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -TunnelId "{1}" -ClientPath "{2}" -RuntimeKeyFile "{3}" -LogFile "{4}"' -f (
        $PSCommandPath, $TunnelId, $ClientPath, $RuntimeKeyFile,
        (Join-Path (Split-Path -Parent $taskProfileDir) 'startup.log')
    )
    $taskUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $taskAction = New-ScheduledTaskAction -Execute $taskShell -Argument $taskArgs -WorkingDirectory $taskRoot
    $taskTrigger = New-ScheduledTaskTrigger -AtLogOn -User $taskUser
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId $taskUser -LogonType Interactive -RunLevel Limited
    $taskSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
    $taskExisting = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($taskExisting -and @($taskExisting.Actions | Where-Object { $_.Arguments -like '*connect_m14_tunnel.ps1*' }).Count -eq 0) {
        throw 'A different scheduled task already uses this name; it was not replaced.'
    }
    Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $taskTrigger `
        -Principal $taskPrincipal -Settings $taskSettings -Description 'Start the private M14 todo tunnel after Windows sign-in.' -Force | Out-Null
    Write-Host 'M14 tunnel will start after this Windows user signs in.'
}
if ($LogFile) { Stop-Transcript | Out-Null }
