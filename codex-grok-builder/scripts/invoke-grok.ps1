[CmdletBinding(DefaultParameterSetName = 'New')]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectPath,

    [Parameter(Mandatory = $true)]
    [string]$TaskFile,

    [Parameter(ParameterSetName = 'New')]
    [guid]$SessionId = [guid]::NewGuid(),

    [Parameter(Mandatory = $true, ParameterSetName = 'Resume')]
    [string]$ResumeSessionId,

    [string[]]$AllowRule = @(),

    [string[]]$DenyRule = @(),

    [ValidateRange(1, 200)]
    [int]$MaxTurns = 60,

    [string]$Model,

    [string]$OutputDirectory,

    [switch]$EnableWebSearch,

    [switch]$AllowSubagents,

    [switch]$AlwaysApprove,

    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$projectItem = Get-Item -LiteralPath $ProjectPath -Force
if (-not $projectItem.PSIsContainer) {
    throw "ProjectPath must be a directory: $ProjectPath"
}

$taskItem = Get-Item -LiteralPath $TaskFile -Force
if ($taskItem.PSIsContainer) {
    throw "TaskFile must be a file: $TaskFile"
}

$grokCommand = Get-Command grok -ErrorAction Stop
$projectFullPath = $projectItem.FullName
$taskFullPath = $taskItem.FullName

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $tempRoot = [System.IO.Path]::GetTempPath()
    $OutputDirectory = Join-Path $tempRoot 'codex-grok-builder'
}

if (-not (Test-Path -LiteralPath $OutputDirectory)) {
    New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
}

$outputItem = Get-Item -LiteralPath $OutputDirectory -Force
if (-not $outputItem.PSIsContainer) {
    throw "OutputDirectory must be a directory: $OutputDirectory"
}

$timestamp = Get-Date -Format 'yyyyMMddTHHmmss'
$effectiveSessionId = if ($PSCmdlet.ParameterSetName -eq 'Resume') {
    $ResumeSessionId
} else {
    $SessionId.ToString()
}
$logPath = Join-Path $outputItem.FullName "$timestamp-$effectiveSessionId.jsonl"

$defaultAllowRules = @(
    'Read',
    'Grep',
    'Edit',
    'Bash(git status*)',
    'Bash(git diff*)'
)
$defaultDenyRules = @(
    'Bash(git push*)',
    'Bash(git reset --hard*)',
    'Bash(git clean*)',
    'Bash(rm -rf*)',
    'Bash(*Remove-Item*-Recurse*)',
    'Bash(del /s*)',
    'Bash(rmdir /s*)'
)

$effectiveAllowRules = @($defaultAllowRules + $AllowRule | Select-Object -Unique)
$effectiveDenyRules = @($defaultDenyRules + $DenyRule | Select-Object -Unique)

$workerRules = @'
You are the implementation worker. Treat the approved task packet as canonical. Implement only the approved scope, do not redesign the task, do not commit or push, and do not modify governance or documentation files unless the packet explicitly includes them. If a required change exceeds scope or permission, stop and report it. Finish with changed files, commands run, results, and deviations.
'@

$grokArgs = @(
    '--no-auto-update',
    '--cwd', $projectFullPath,
    '--prompt-file', $taskFullPath,
    '--output-format', 'streaming-json',
    '--max-turns', $MaxTurns.ToString(),
    '--no-plan',
    '--permission-mode', 'dontAsk',
    '--rules', $workerRules
)

if ($PSCmdlet.ParameterSetName -eq 'Resume') {
    $grokArgs += @('--resume', $ResumeSessionId)
} else {
    $grokArgs += @('--session-id', $SessionId.ToString())
}

if (-not [string]::IsNullOrWhiteSpace($Model)) {
    $grokArgs += @('--model', $Model)
}
if (-not $EnableWebSearch) {
    $grokArgs += '--disable-web-search'
}
if (-not $AllowSubagents) {
    $grokArgs += '--no-subagents'
}
if ($AlwaysApprove) {
    $permissionIndex = [Array]::IndexOf($grokArgs, '--permission-mode')
    if ($permissionIndex -ge 0) {
        $grokArgs = @($grokArgs[0..($permissionIndex - 1)] + $grokArgs[($permissionIndex + 2)..($grokArgs.Count - 1)])
    }
    $grokArgs += '--always-approve'
}

foreach ($rule in $effectiveAllowRules) {
    $grokArgs += @('--allow', $rule)
}
foreach ($rule in $effectiveDenyRules) {
    $grokArgs += @('--deny', $rule)
}

Write-Host "CODEX_GROK_SESSION_ID=$effectiveSessionId"
Write-Host "CODEX_GROK_OUTPUT=$logPath"

if ($DryRun) {
    [pscustomobject]@{
        Executable = $grokCommand.Source
        ProjectPath = $projectFullPath
        TaskFile = $taskFullPath
        SessionId = $effectiveSessionId
        OutputPath = $logPath
        Arguments = $grokArgs
    } | ConvertTo-Json -Depth 4
    exit 0
}

& $grokCommand.Source @grokArgs 2>&1 | Tee-Object -FilePath $logPath
$grokExitCode = $LASTEXITCODE

if ($grokExitCode -ne 0) {
    Write-Error "Grok Build exited with code $grokExitCode. Log: $logPath"
    exit $grokExitCode
}

Write-Host "CODEX_GROK_EXIT_CODE=0"
exit 0
