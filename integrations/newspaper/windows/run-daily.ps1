[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Preflight,
    [string]$PythonPath,
    [string]$ExpectedComputerName
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Get-NewspaperPython {
    param([string]$RepositoryRoot, [string]$ExplicitPath)

    $candidates = New-Object System.Collections.Generic.List[object]
    if ($ExplicitPath) {
        if (-not (Test-Path -LiteralPath $ExplicitPath -PathType Leaf)) {
            throw "Python does not exist: $ExplicitPath"
        }
        $candidates.Add(@{ Path = (Resolve-Path -LiteralPath $ExplicitPath).Path; Prefix = @() })
    }
    else {
        $venvPython = Join-Path $RepositoryRoot '.venv\Scripts\python.exe'
        if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
            $candidates.Add(@{ Path = $venvPython; Prefix = @() })
        }
        foreach ($name in @('python.exe', 'python', 'py.exe')) {
            $commands = @(Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue)
            foreach ($command in $commands) {
                $prefix = @()
                if ($name -eq 'py.exe') { $prefix = @('-3') }
                $candidates.Add(@{ Path = $command.Source; Prefix = $prefix })
            }
        }
    }

    $probe = 'import json,sys; print(json.dumps({''executable'':sys.executable,''version'':list(sys.version_info[:3])}))'
    $checked = @{}
    foreach ($candidate in $candidates) {
        $candidatePath = [string]$candidate.Path
        # Windows App Execution Aliases can open the Store instead of Python.
        if ($candidatePath -match '(?i)[\\/]Microsoft[\\/]WindowsApps[\\/]') { continue }
        if ($checked.ContainsKey($candidatePath)) { continue }
        $checked[$candidatePath] = $true
        try {
            $arguments = @($candidate.Prefix) + @('-c', $probe)
            $output = & $candidatePath @arguments 2>$null
            if ($LASTEXITCODE -ne 0) { continue }
            $runtime = ($output -join "`n") | ConvertFrom-Json
            if ($runtime.version[0] -ne 3 -or $runtime.version[1] -lt 10) { continue }
            if (-not (Test-Path -LiteralPath $runtime.executable -PathType Leaf)) { continue }
            if ($runtime.executable -match '(?i)[\\/]Microsoft[\\/]WindowsApps[\\/]') { continue }
            return [pscustomobject]@{
                Path = (Resolve-Path -LiteralPath $runtime.executable).Path
                Version = ($runtime.version -join '.')
            }
        }
        catch {
            if ($ExplicitPath) { throw "Cannot use the selected Python: $ExplicitPath" }
        }
    }
    throw 'Python 3.10+ was not found. Use an existing environment via -PythonPath; no dependencies were installed.'
}

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
$dailyScript = Join-Path $repositoryRoot 'scripts\newspaper_daily.py'
if (-not (Test-Path -LiteralPath $dailyScript -PathType Leaf)) {
    throw "The daily entry point is missing. Pull the complete repository first: $dailyScript"
}
$actualComputer = [Environment]::MachineName
if ($ExpectedComputerName -and $ExpectedComputerName -ine $actualComputer) {
    throw "Computer mismatch. Expected '$ExpectedComputerName'; this computer is '$actualComputer'."
}

$runtime = Get-NewspaperPython -RepositoryRoot $repositoryRoot -ExplicitPath $PythonPath
$dependencyProbe = 'import importlib; [importlib.import_module(name) for name in (''requests'',''bs4'')]; print(''newspaper-dependencies-ok'')'
$probeErrorPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = 'Continue'
    $dependencyResult = & $runtime.Path -c $dependencyProbe 2>&1
}
finally { $ErrorActionPreference = $probeErrorPreference }
if ($LASTEXITCODE -ne 0 -or ($dependencyResult -join "`n") -notmatch 'newspaper-dependencies-ok') {
    throw "The selected Python needs the repository dependencies requests and beautifulsoup4. No install was attempted. Python: $($runtime.Path)"
}

$logDirectory = Join-Path $repositoryRoot '.local\newspaper'
$manifestPath = Join-Path $logDirectory 'task-install.json'
if ($Preflight) {
    # This mode performs imports only: no network requests, log files or tasks.
    [pscustomobject]@{
        RepositoryRoot = $repositoryRoot
        ComputerName = $actualComputer
        PythonPath = $runtime.Path
        PythonVersion = $runtime.Version
        Dependencies = @('requests', 'beautifulsoup4')
        DailyScript = $dailyScript
        LogDirectory = $logDirectory
        ManifestPath = $manifestPath
    }
    return
}

if (-not $DryRun) {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw 'Publishing requires the local Computer L installation receipt. Run the installer on the confirmed L computer first, or use -DryRun.'
    }
    $receipt = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($receipt.MachineRole -ne 'L' -or $receipt.ComputerName -ine $actualComputer -or
        $receipt.RepositoryRoot -ine $repositoryRoot -or $receipt.TaskName -ne 'Yao-Newspaper-Daily-0900') {
        throw 'The installation receipt does not identify this repository and computer as Computer L. Publishing was not started.'
    }
}

if (-not (Test-Path -LiteralPath $logDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
}
$lockPath = Join-Path $logDirectory 'task-run.lock'
try {
    $runLock = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
}
catch [System.IO.IOException] {
    Write-Output 'Another newspaper run holds the local lock. This overlapping invocation was skipped.'
    exit 0
}

$mode = '--publish'
if ($DryRun) { $mode = '--dry-run' }
$logName = 'daily-{0}-{1}.log' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), $PID
$logPath = Join-Path $logDirectory $logName
$previousEncoding = [Console]::OutputEncoding
$previousPythonUtf8 = $env:PYTHONUTF8
$exitCode = 1
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $env:PYTHONUTF8 = '1'
    Push-Location -LiteralPath $repositoryRoot
    try {
        @(
            'StartedAt={0}' -f [DateTimeOffset]::Now.ToString('o')
            'Computer={0}' -f $actualComputer
            'Python={0}' -f $runtime.Path
            'Mode={0}' -f $mode
        ) | Out-File -LiteralPath $logPath -Encoding UTF8
        $savedErrorPreference = $ErrorActionPreference
        try {
            # Native stderr is diagnostic output, not a PowerShell terminating
            # error. Preserve the Python exit code for Task Scheduler retries.
            $ErrorActionPreference = 'Continue'
            $LASTEXITCODE = 1
            & $runtime.Path -u $dailyScript $mode 2>&1 |
                Out-File -LiteralPath $logPath -Append -Encoding UTF8 -ErrorAction Stop
            $exitCode = $LASTEXITCODE
            if ($null -eq $exitCode) { $exitCode = 1 }
        }
        finally { $ErrorActionPreference = $savedErrorPreference }
        ('FinishedAt={0}; ExitCode={1}' -f [DateTimeOffset]::Now.ToString('o'), $exitCode) |
            Out-File -LiteralPath $logPath -Append -Encoding UTF8
    }
    finally { Pop-Location }
}
finally {
    $runLock.Dispose()
    [Console]::OutputEncoding = $previousEncoding
    if ($null -eq $previousPythonUtf8) { Remove-Item Env:\PYTHONUTF8 -ErrorAction SilentlyContinue }
    else { $env:PYTHONUTF8 = $previousPythonUtf8 }
}
Write-Output ("Daily newspaper exit code: {0}. Log: {1}" -f $exitCode, $logPath)
exit $exitCode
