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

    [switch]$Quiet,

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

$outputFullPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory)
if (Test-Path -LiteralPath $outputFullPath) {
    $outputItem = Get-Item -LiteralPath $outputFullPath -Force
    if (-not $outputItem.PSIsContainer) {
        throw "OutputDirectory must be a directory: $OutputDirectory"
    }
}

$timestamp = Get-Date -Format 'yyyyMMddTHHmmss'
$runId = [guid]::NewGuid().ToString('N')
$effectiveSessionId = if ($PSCmdlet.ParameterSetName -eq 'Resume') {
    $ResumeSessionId
} else {
    $SessionId.ToString()
}
# Session references can be titles containing filename characters or NTFS stream
# separators. Each invocation uses an independent, filename-safe run identifier.
$logBasePath = Join-Path $outputFullPath "$timestamp-$runId"
$logPath = "$logBasePath.jsonl"
$stderrPath = "$logBasePath.stderr.log"
$summaryPath = "$logBasePath.run.json"

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
Write-Host "CODEX_GROK_RUN_ID=$runId"
Write-Host "CODEX_GROK_OUTPUT=$logPath"
Write-Host "CODEX_GROK_STDERR=$stderrPath"
Write-Host "CODEX_GROK_SUMMARY=$summaryPath"

if ($DryRun) {
    [pscustomobject]@{
        Executable = $grokCommand.Source
        ProjectPath = $projectFullPath
        TaskFile = $taskFullPath
        SessionId = $effectiveSessionId
        RunId = $runId
        OutputPath = $logPath
        StderrPath = $stderrPath
        SummaryPath = $summaryPath
        Arguments = $grokArgs
    } | ConvertTo-Json -Depth 4
    exit 0
}

if (-not (Test-Path -LiteralPath $outputFullPath)) {
    New-Item -ItemType Directory -Path $outputFullPath | Out-Null
}

function Get-CliUsageNumber($Value) {
    if (($Value -is [int] -or $Value -is [long] -or $Value -is [double] -or $Value -is [decimal]) -and
        $Value -ge 0 -and -not [double]::IsNaN([double]$Value) -and -not [double]::IsInfinity([double]$Value)) {
        return $Value
    }
    return $null
}

function Select-CliUsageCounters($Value) {
    # Copy only known numeric counters, never transcript text or signatures.
    $counterNames = @(
        'input_tokens', 'output_tokens', 'total_tokens', 'prompt_tokens', 'completion_tokens',
        'cache_creation_input_tokens', 'cache_read_input_tokens', 'cached_tokens', 'reasoning_tokens',
        'inputTokens', 'outputTokens', 'totalTokens', 'cacheCreationInputTokens', 'cacheReadInputTokens',
        'modelCalls', 'webSearchRequests', 'costUSD', 'contextWindow', 'maxOutputTokens'
    )
    $counters = [ordered]@{}
    if ($null -ne $Value) {
        foreach ($property in $Value.PSObject.Properties) {
            if ($counterNames -ccontains $property.Name) {
                $number = Get-CliUsageNumber $property.Value
                if ($null -ne $number) { $counters[$property.Name] = $number }
            }
        }
    }
    if ($counters.Count -gt 0) { return [pscustomobject]$counters }
    return $null
}

function Read-CliCompletionUsage([string]$Path) {
    $usageResult = [ordered]@{
        UsageSource = $null
        UsageStatus = 'completion-event-not-obtained'
        CompletionEventObtained = $false
        MalformedJsonLines = 0
        TokenUsage = $null
        NumTurns = $null
        CliReportedCostUsd = $null
        ModelUsage = $null
        ResolvedModels = $null
    }
    try {
        $lastEnd = $null
        foreach ($line in [System.IO.File]::ReadLines($Path)) {
            if ([string]::IsNullOrWhiteSpace($line)) { continue }
            try {
                $event = $line | ConvertFrom-Json -ErrorAction Stop
                if ($event -is [pscustomobject] -and $event.type -ceq 'end') { $lastEnd = $event }
            } catch {
                # Do not expose parse errors: they can contain the raw line.
                $usageResult.MalformedJsonLines++
            }
        }
        if ($usageResult.MalformedJsonLines -gt 0) {
            # A corrupt later line might be the final end; do not reuse an
            # earlier total or silently report a partial stream as complete.
            $usageResult.UsageStatus = 'completion-event-not-obtained: malformed-json'
        } elseif ($null -ne $lastEnd) {
            $usageResult.UsageSource = 'cli.end'
            $usageResult.UsageStatus = 'completion-event-obtained'
            $usageResult.CompletionEventObtained = $true
            $usageResult.TokenUsage = Select-CliUsageCounters $lastEnd.usage
            $usageResult.NumTurns = Get-CliUsageNumber $lastEnd.num_turns
            $usageResult.CliReportedCostUsd = Get-CliUsageNumber $lastEnd.total_cost_usd
            $modelUsage = [ordered]@{}
            if ($null -ne $lastEnd.modelUsage) {
                foreach ($modelEntry in $lastEnd.modelUsage.PSObject.Properties) {
                    $modelCounters = Select-CliUsageCounters $modelEntry.Value
                    if ($null -ne $modelCounters) { $modelUsage[$modelEntry.Name] = $modelCounters }
                }
            }
            if ($modelUsage.Count -gt 0) {
                $usageResult.ModelUsage = [pscustomobject]$modelUsage
                # RequestedModel is the input option; only the completion
                # event's modelUsage keys identify models reported as used.
                $usageResult.ResolvedModels = @($modelUsage.Keys)
            }
        }
    } catch {
        $usageResult.UsageSource = $null
        $usageResult.UsageStatus = 'completion-event-not-obtained: log-unreadable'
        $usageResult.CompletionEventObtained = $false
        $usageResult.TokenUsage = $null
        $usageResult.NumTurns = $null
        $usageResult.CliReportedCostUsd = $null
        $usageResult.ModelUsage = $null
        $usageResult.ResolvedModels = $null
    }
    return [pscustomobject]$usageResult
}

$startedAt = [DateTimeOffset]::UtcNow
$runTimer = [System.Diagnostics.Stopwatch]::StartNew()
$grokExitCode = $null
$wrapperError = $null
$exitCode = 1
# Preserve native exit codes even when a caller enables PowerShell's opt-in
# conversion of native failures into terminating PowerShell errors.
$PSNativeCommandUseErrorActionPreference = $false
try {
    if ($Quiet) {
        # Suppress console streaming only after the complete stdout stream has
        # been written through the same logging path used by normal mode.
        & $grokCommand.Source @grokArgs 2> $stderrPath | Tee-Object -FilePath $logPath | Out-Null
    } else {
        & $grokCommand.Source @grokArgs 2> $stderrPath | Tee-Object -FilePath $logPath
    }
    $grokExitCode = $LASTEXITCODE
    if ($null -eq $grokExitCode) {
        throw 'Grok did not return a native process exit code.'
    }
    $exitCode = $grokExitCode
} catch {
    $wrapperError = $_.Exception.Message
} finally {
    $runTimer.Stop()
    $completionUsage = Read-CliCompletionUsage $logPath
    [pscustomobject]@{
        RunId = $runId
        SessionReference = $effectiveSessionId
        IsResume = ($PSCmdlet.ParameterSetName -eq 'Resume')
        RequestedModel = $(if ([string]::IsNullOrWhiteSpace($Model)) { $null } else { $Model })
        MaxTurns = $MaxTurns
        StartedAtUtc = $startedAt.ToString('o')
        FinishedAtUtc = [DateTimeOffset]::UtcNow.ToString('o')
        DurationSeconds = [Math]::Round($runTimer.Elapsed.TotalSeconds, 3)
        NativeExitCode = $grokExitCode
        ExitCode = $exitCode
        WrapperError = $wrapperError
        OutputPath = $logPath
        StderrPath = $stderrPath
        UsageSource = $completionUsage.UsageSource
        UsageStatus = $completionUsage.UsageStatus
        CompletionEventObtained = $completionUsage.CompletionEventObtained
        MalformedJsonLines = $completionUsage.MalformedJsonLines
        TokenUsage = $completionUsage.TokenUsage
        NumTurns = $completionUsage.NumTurns
        ModelUsage = $completionUsage.ModelUsage
        ResolvedModels = $completionUsage.ResolvedModels
        CliReportedCostUsd = $completionUsage.CliReportedCostUsd
        # A CLI USD estimate is not evidence of actual subscription charges.
        ActualSubscriptionCharge = 'unknown'
        Cost = $null
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $summaryPath -Encoding utf8
}

Write-Host "CODEX_GROK_DURATION_SECONDS=$([Math]::Round($runTimer.Elapsed.TotalSeconds, 3))"
Write-Host "CODEX_GROK_EXIT_CODE=$exitCode"
if ($exitCode -ne 0 -and -not $Quiet) {
    # Write-Error under ErrorActionPreference=Stop would replace the real code
    # with PowerShell's generic exit 1 before the explicit exit is reached.
    [Console]::Error.WriteLine("Grok Build exited with code $exitCode. Log: $logPath; stderr: $stderrPath; wrapper error: $wrapperError")
}
exit $exitCode
