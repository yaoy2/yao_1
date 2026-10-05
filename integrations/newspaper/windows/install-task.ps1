[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$ComputerName,
    [switch]$ConfirmComputerL,
    [switch]$Preview,
    [string]$PythonPath
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function ConvertTo-NewspaperXmlText {
    param([string]$Value)
    return [System.Security.SecurityElement]::Escape($Value)
}


function Get-NewspaperFileSha256 {
    param([string]$Path)
    $stream = [System.IO.File]::OpenRead($Path)
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-', '') }
    finally { $hasher.Dispose(); $stream.Dispose() }
}

function Get-NewspaperXmlValue {
    param([xml]$Document, [string]$XPath)
    $namespaces = New-Object System.Xml.XmlNamespaceManager($Document.NameTable)
    $namespaces.AddNamespace('t', 'http://schemas.microsoft.com/windows/2004/02/mit/task')
    $node = $Document.SelectSingleNode($XPath, $namespaces)
    if ($null -eq $node) { return '' }
    return $node.InnerText
}

function Assert-NewspaperTaskOwner {
    param([xml]$Document, [string]$RunnerPath, [string]$RepositoryRoot,
          [string]$PowerShellPath, [string]$AccountSid, [string]$AccountName,
          [string]$ComputerName)
    $namespaces = New-Object System.Xml.XmlNamespaceManager($Document.NameTable)
    $namespaces.AddNamespace('t', 'http://schemas.microsoft.com/windows/2004/02/mit/task')
    if ($Document.SelectNodes('/t:Task/t:Actions/*', $namespaces).Count -ne 1) {
        throw 'The existing task has different actions. It will not be replaced.'
    }
    $command = Get-NewspaperXmlValue $Document '/t:Task/t:Actions/t:Exec/t:Command'
    $workingDirectory = Get-NewspaperXmlValue $Document '/t:Task/t:Actions/t:Exec/t:WorkingDirectory'
    $arguments = Get-NewspaperXmlValue $Document '/t:Task/t:Actions/t:Exec/t:Arguments'
    $owner = Get-NewspaperXmlValue $Document '/t:Task/t:Principals/t:Principal/t:UserId'
    $argumentPrefix = '-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File "{0}" -ExpectedComputerName "{1}" -PythonPath ' -f $RunnerPath, $ComputerName
    $argumentPattern = '^' + [regex]::Escape($argumentPrefix) + '"[^"\r\n]+"$'
    if ($command -ine $PowerShellPath -or $workingDirectory -ine $RepositoryRoot -or
        $arguments -inotmatch $argumentPattern -or ($owner -ine $AccountSid -and $owner -ine $AccountName)) {
        throw 'An unrelated same-name task exists. Its action, directory or account does not match this repository; nothing was replaced.'
    }
}

function Assert-NewspaperTaskDefinition {
    param([xml]$Actual, [xml]$Planned)
    $namespaces = New-Object System.Xml.XmlNamespaceManager($Actual.NameTable)
    $namespaces.AddNamespace('t', 'http://schemas.microsoft.com/windows/2004/02/mit/task')
    if ($Actual.SelectNodes('/t:Task/t:Triggers/*', $namespaces).Count -ne 1 -or
        $Actual.SelectNodes('/t:Task/t:Principals/t:Principal', $namespaces).Count -ne 1) {
        throw 'The registered task has unexpected triggers or principals.'
    }
    $paths = @(
        '/t:Task/t:Actions/t:Exec/t:Command',
        '/t:Task/t:Actions/t:Exec/t:Arguments',
        '/t:Task/t:Actions/t:Exec/t:WorkingDirectory',
        '/t:Task/t:Principals/t:Principal/t:LogonType',
        '/t:Task/t:Principals/t:Principal/t:RunLevel',
        '/t:Task/t:Triggers/t:CalendarTrigger/t:ScheduleByDay/t:DaysInterval',
        '/t:Task/t:Settings/t:MultipleInstancesPolicy',
        '/t:Task/t:Settings/t:DisallowStartIfOnBatteries',
        '/t:Task/t:Settings/t:StopIfGoingOnBatteries',
        '/t:Task/t:Settings/t:AllowHardTerminate',
        '/t:Task/t:Settings/t:StartWhenAvailable',
        '/t:Task/t:Settings/t:RunOnlyIfNetworkAvailable',
        '/t:Task/t:Settings/t:AllowStartOnDemand',
        '/t:Task/t:Settings/t:Enabled',
        '/t:Task/t:Settings/t:RunOnlyIfIdle',
        '/t:Task/t:Settings/t:ExecutionTimeLimit',
        '/t:Task/t:Settings/t:Hidden',
        '/t:Task/t:Settings/t:WakeToRun',
        '/t:Task/t:Settings/t:RestartOnFailure/t:Interval',
        '/t:Task/t:Settings/t:RestartOnFailure/t:Count'
    )
    foreach ($path in $paths) {
        if ((Get-NewspaperXmlValue $Actual $path) -cne (Get-NewspaperXmlValue $Planned $path)) {
            throw "The registered task failed configuration verification: $path"
        }
    }
    $startPath = '/t:Task/t:Triggers/t:CalendarTrigger/t:StartBoundary'
    $actualBoundary = [DateTimeOffset]::Parse((Get-NewspaperXmlValue $Actual $startPath))
    $plannedBoundary = [DateTimeOffset]::Parse((Get-NewspaperXmlValue $Planned $startPath))
    if ($actualBoundary -ne $plannedBoundary) {
        throw 'The registered task has an unexpected start time.'
    }
}

$actualComputer = [Environment]::MachineName
if ($ComputerName -ine $actualComputer) {
    throw "Computer mismatch. Explicitly pass this computer's actual name '$actualComputer'; received '$ComputerName'."
}
if (-not $Preview -and -not $ConfirmComputerL) {
    throw 'Registration requires -ConfirmComputerL after confirming that this physical computer is L. Use -Preview for a read-only plan.'
}

$runnerPath = Join-Path $PSScriptRoot 'run-daily.ps1'
$preflightParameters = @{ Preflight = $true; ExpectedComputerName = $actualComputer }
if ($PythonPath) { $preflightParameters.PythonPath = $PythonPath }
$environment = & $runnerPath @preflightParameters
$repositoryRoot = $environment.RepositoryRoot
$taskName = 'Yao-Newspaper-Daily-0900'
$taskPath = '\'
$powerShellPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (-not (Test-Path -LiteralPath $powerShellPath -PathType Leaf)) {
    throw 'Windows PowerShell 5.1 was not found at the expected system path.'
}
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$accountName = $identity.Name
$accountSid = $identity.User.Value
$beijingOffset = [TimeSpan]::FromHours(8)
$beijingNow = [DateTimeOffset]::UtcNow.ToOffset($beijingOffset)
$nextStart = [DateTimeOffset]::ParseExact(
    $beijingNow.ToString('yyyy-MM-dd') + 'T09:00:00+08:00',
    'yyyy-MM-ddTHH:mm:sszzz', [Globalization.CultureInfo]::InvariantCulture)
if ($nextStart -le $beijingNow) { $nextStart = $nextStart.AddDays(1) }
$startBoundary = $nextStart.ToString('yyyy-MM-ddTHH:mm:sszzz')
$actionArguments = '-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File "{0}" -ExpectedComputerName "{1}" -PythonPath "{2}"' -f $runnerPath, $actualComputer, $environment.PythonPath
$description = 'Yao newspaper daily collection on explicitly confirmed Computer L. 09:00 Beijing time; interactive current user; no saved password.'
$taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>$(ConvertTo-NewspaperXmlText $accountName)</Author>
    <Description>$(ConvertTo-NewspaperXmlText $description)</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>$startBoundary</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="CurrentUser">
      <UserId>$(ConvertTo-NewspaperXmlText $accountSid)</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>false</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT15M</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure><Interval>PT10M</Interval><Count>3</Count></RestartOnFailure>
  </Settings>
  <Actions Context="CurrentUser">
    <Exec>
      <Command>$(ConvertTo-NewspaperXmlText $powerShellPath)</Command>
      <Arguments>$(ConvertTo-NewspaperXmlText $actionArguments)</Arguments>
      <WorkingDirectory>$(ConvertTo-NewspaperXmlText $repositoryRoot)</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@
[xml]$planned = $taskXml
$limitations = 'Runs while the current user is signed in, including a locked session. It cannot run after sign-out, while powered off, or wake a sleeping computer. Missed runs may start when the user, computer and network are available. No account password is stored.'
$previewResult = [ordered]@{
    Mode = 'Preview'
    ComputerName = $actualComputer
    MachineRole = 'L requires explicit human confirmation'
    TaskName = $taskName
    TaskPath = $taskPath
    RepositoryRoot = $repositoryRoot
    RunnerPath = $runnerPath
    PythonPath = $environment.PythonPath
    PythonVersion = $environment.PythonVersion
    RunAs = $accountName
    Schedule = 'Daily 09:00 Asia/Shanghai (UTC+08:00)'
    FirstStartBoundary = $startBoundary
    LogDirectory = $environment.LogDirectory
    ManifestPath = $environment.ManifestPath
    Limitations = $limitations
    TaskXml = $taskXml
}
if ($Preview) {
    # Return before querying/registering tasks or writing the local receipt.
    [pscustomobject]$previewResult | ConvertTo-Json -Depth 5
    return
}

Import-Module ScheduledTasks -ErrorAction Stop
if (Test-Path -LiteralPath $environment.ManifestPath -PathType Leaf) {
    $oldReceipt = Get-Content -LiteralPath $environment.ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($oldReceipt.MachineRole -ne 'L' -or $oldReceipt.ComputerName -ine $actualComputer -or
        $oldReceipt.RepositoryRoot -ine $repositoryRoot -or $oldReceipt.TaskName -ne $taskName) {
        throw 'The existing local installation receipt belongs to a different role, computer or repository. Nothing was replaced.'
    }
}

$existing = @(Get-ScheduledTask -TaskPath $taskPath -ErrorAction Stop | Where-Object { $_.TaskName -eq $taskName })
$registerParameters = @{ TaskName = $taskName; TaskPath = $taskPath; Xml = $taskXml; ErrorAction = 'Stop' }
$needsRegistration = $true
if ($existing.Count -gt 0) {
    [xml]$existingXml = Export-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction Stop
    Assert-NewspaperTaskOwner -Document $existingXml -RunnerPath $runnerPath -RepositoryRoot $repositoryRoot `
        -PowerShellPath $powerShellPath -AccountSid $accountSid -AccountName $accountName -ComputerName $actualComputer
    # Keep an established 09:00 boundary, including a past boundary, so an
    # idempotent update does not discard a pending missed-run catch-up.
    $existingStartText = Get-NewspaperXmlValue $existingXml '/t:Task/t:Triggers/t:CalendarTrigger/t:StartBoundary'
    $existingStart = [DateTimeOffset]::MinValue
    if ([DateTimeOffset]::TryParse($existingStartText, [ref]$existingStart)) {
        $existingBeijingStart = $existingStart.ToOffset($beijingOffset)
        if ($existingBeijingStart.Hour -eq 9 -and $existingBeijingStart.Minute -eq 0 -and
            $existingBeijingStart.Second -eq 0 -and $existingStartText -match '(?:\+08:00|Z)$') {
            $planned.Task.Triggers.CalendarTrigger.StartBoundary = $existingStartText
            $registerParameters.Xml = $planned.OuterXml
        }
    }
    try {
        Assert-NewspaperTaskDefinition -Actual $existingXml -Planned $planned
        $needsRegistration = $false
    }
    catch { $needsRegistration = $true }
    $registerParameters.Force = $true
}
if ($needsRegistration) { Register-ScheduledTask @registerParameters | Out-Null }
[xml]$registered = Export-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction Stop
Assert-NewspaperTaskOwner -Document $registered -RunnerPath $runnerPath -RepositoryRoot $repositoryRoot `
    -PowerShellPath $powerShellPath -AccountSid $accountSid -AccountName $accountName -ComputerName $actualComputer
Assert-NewspaperTaskDefinition -Actual $registered -Planned $planned
$taskInfo = Get-ScheduledTaskInfo -TaskName $taskName -TaskPath $taskPath -ErrorAction Stop

$receipt = [ordered]@{
    SchemaVersion = 1
    MachineRole = 'L'
    ComputerName = $actualComputer
    TaskName = $taskName
    TaskPath = $taskPath
    RepositoryRoot = $repositoryRoot
    RunnerPath = $runnerPath
    PythonPath = $environment.PythonPath
    AccountSid = $accountSid
    AccountName = $accountName
    Schedule = '09:00 Asia/Shanghai'
    InstallerSha256 = Get-NewspaperFileSha256 $PSCommandPath
    RunnerSha256 = Get-NewspaperFileSha256 $runnerPath
    DailyScriptSha256 = Get-NewspaperFileSha256 $environment.DailyScript
    DefinitionUpdated = $needsRegistration
    ConfigurationVerifiedAt = [DateTimeOffset]::Now.ToString('o')
    NextRunTimeLocal = $taskInfo.NextRunTime.ToString('o')
    NextRunTimeBeijing = ([DateTimeOffset]$taskInfo.NextRunTime).ToOffset($beijingOffset).ToString('o')
    LastRunTimeLocal = $taskInfo.LastRunTime.ToString('o')
    LastTaskResult = $taskInfo.LastTaskResult
    RunValidation = 'Not performed by installer; validate a manual run on Computer L.'
    Limitations = $limitations
}
if (-not (Test-Path -LiteralPath $environment.LogDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $environment.LogDirectory -Force | Out-Null
}
$temporaryReceipt = Join-Path $environment.LogDirectory ('task-install-{0}.tmp' -f $PID)
$receipt | ConvertTo-Json -Depth 4 | Out-File -LiteralPath $temporaryReceipt -Encoding UTF8
Move-Item -LiteralPath $temporaryReceipt -Destination $environment.ManifestPath -Force
[pscustomobject]$receipt | ConvertTo-Json -Depth 4
