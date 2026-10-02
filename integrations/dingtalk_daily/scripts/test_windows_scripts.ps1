[CmdletBinding()]
param([string]$PythonExecutable = 'python.exe')

# No task is registered, no dependency is installed, and no real chat is read.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot
$testDirectory = Join-Path ([IO.Path]::GetTempPath()) ('dingtalk-daily-script-tests-' + [guid]::NewGuid().ToString('N'))
$passed = 0

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
    $script:passed += 1
}

function Assert-Rejected {
    param([scriptblock]$Action, [string]$Message)
    $rejected = $false
    try { & $Action } catch { $rejected = $true }
    Assert-True -Condition $rejected -Message $Message
}

function New-TestTask {
    param([string]$OwnerSid, [string]$Directory, [string]$Executable, [string]$Arguments)
    $action = New-ScheduledTaskAction -Execute $Executable -Argument $Arguments -WorkingDirectory $Directory
    $trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours(22))
    $principal = New-ScheduledTaskPrincipal -UserId $OwnerSid -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 45) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $settings.StartWhenAvailable = $false
    $settings.WakeToRun = $false
    $settings.RestartCount = 0
    return New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description ((Get-DingTalkTaskMarker -OwnerSid $OwnerSid) + ' test definition')
}

try {
    [IO.Directory]::CreateDirectory($testDirectory) | Out-Null
    foreach ($fileName in @('setup.ps1', 'register_task.ps1', 'run_daily.ps1')) {
        $tokens = $null
        $parseErrors = $null
        [Management.Automation.Language.Parser]::ParseFile((Join-Path $projectDirectory $fileName), [ref]$tokens, [ref]$parseErrors) | Out-Null
        Assert-True -Condition (@($parseErrors).Count -eq 0) -Message ("Parse failed: $fileName")
    }
    . (Join-Path $projectDirectory 'register_task.ps1')

    $chinaZone = [TimeZoneInfo]::FindSystemTimeZoneById('China Standard Time')
    Assert-ChinaTimeZone -TimeZone $chinaZone -Now ([datetime]::new(2026, 10, 2, 22, 0, 0))
    $passed += 1
    Assert-Rejected -Action { Assert-ChinaTimeZone -TimeZone ([TimeZoneInfo]::Utc) } -Message 'UTC was accepted as China time.'
    $wrongOffset = [TimeZoneInfo]::CreateCustomTimeZone('China Standard Time', [TimeSpan]::FromHours(7), 'test', 'test')
    Assert-Rejected -Action { Assert-ChinaTimeZone -TimeZone $wrongOffset } -Message 'A non-eight-hour offset was accepted.'

    $configPath = Join-Path $testDirectory 'config.local.json'
    Assert-Rejected -Action { Assert-LocalCalibration -ConfigPath $configPath } -Message 'Missing calibration was accepted.'
    foreach ($invalid in @('{}', 'null', '{"calibration_ok":false}', '{"calibration_ok":"true"}', '{"calibration_ok":1}', '{broken')) {
        [IO.File]::WriteAllText($configPath, $invalid, [Text.UTF8Encoding]::new($false))
        Assert-Rejected -Action { Assert-LocalCalibration -ConfigPath $configPath } -Message ("Invalid calibration was accepted: $invalid")
    }
    [IO.File]::WriteAllText($configPath, '{"calibration_ok":true}', [Text.UTF8Encoding]::new($false))
    Assert-LocalCalibration -ConfigPath $configPath
    $passed += 1

    $ownerSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    Assert-OwnedDingTalkTask -ExistingTask $null -OwnerSid $ownerSid
    Assert-OwnedDingTalkTask -ExistingTask ([pscustomobject]@{Description = (Get-DingTalkTaskMarker -OwnerSid $ownerSid) + ' test'}) -OwnerSid $ownerSid
    $passed += 2
    Assert-Rejected -Action { Assert-OwnedDingTalkTask -ExistingTask ([pscustomobject]@{Description = 'unrelated task'}) -OwnerSid $ownerSid } -Message 'An unrelated task was accepted.'
    Assert-Rejected -Action { Assert-OwnedDingTalkTask -ExistingTask ([pscustomobject]@{Description = (Get-DingTalkTaskMarker -OwnerSid 'S-1-5-21-9999')}) -OwnerSid $ownerSid } -Message 'Another user task was accepted.'

    Import-Module ScheduledTasks -ErrorAction Stop
    $powershellExecutable = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -File "C:\test path\run_daily.ps1"'
    $definition = New-TestTask -OwnerSid $ownerSid -Directory $testDirectory -Executable $powershellExecutable -Arguments $arguments
    $verify = @{ Task = $definition; OwnerSid = $ownerSid; Executable = $powershellExecutable; Arguments = $arguments; Directory = $testDirectory }
    Assert-RegisteredDingTalkTask @verify
    $passed += 1
    $definition.Settings.StartWhenAvailable = $true
    Assert-Rejected -Action { Assert-RegisteredDingTalkTask @verify } -Message 'Missed-run catch-up was accepted.'
    $definition.Settings.StartWhenAvailable = $false
    $definition.Settings.WakeToRun = $true
    Assert-Rejected -Action { Assert-RegisteredDingTalkTask @verify } -Message 'Wake-to-run was accepted.'
    $definition.Settings.WakeToRun = $false
    $definition.Triggers[0].StartBoundary = [datetime]::Today.AddHours(21).ToString('s')
    Assert-Rejected -Action { Assert-RegisteredDingTalkTask @verify } -Message 'A non-22:00 trigger was accepted.'

    # Exercise the real runner only in a temporary project containing a synthetic main.py.
    # The throwaway environment has no pip and cannot run the actual application.
    if ([TimeZoneInfo]::Local.Id -eq 'China Standard Time') {
        $testVenv = Join-Path $testDirectory '.venv'
        & $PythonExecutable -m venv --without-pip $testVenv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the isolated runner smoke-test environment.' }
        $testRunner = Join-Path $testDirectory 'run_daily.ps1'
        Copy-Item -LiteralPath (Join-Path $projectDirectory 'run_daily.ps1') -Destination $testRunner
        $stub = 'import sys; print("stdout \\u6d4b\\u8bd5".encode().decode("unicode_escape")); print("stderr \\u6d4b\\u8bd5".encode().decode("unicode_escape"), file=sys.stderr); raise SystemExit(37 if sys.argv[1:] == ["run", "--scheduled"] else 91)'
        [IO.File]::WriteAllText((Join-Path $testDirectory 'main.py'), $stub, [Text.UTF8Encoding]::new($false))
        $previousLocalAppData = $env:LOCALAPPDATA
        try {
            $env:LOCALAPPDATA = Join-Path $testDirectory 'localdata'
            & $powershellExecutable -NoProfile -NonInteractive -File $testRunner
            Assert-True -Condition ($LASTEXITCODE -eq 37) -Message 'The runner did not preserve the Python exit code or scheduled arguments.'
            $logPath = Join-Path $env:LOCALAPPDATA ('YaoTools\DingTalkDaily\logs\runner-{0:yyyyMMdd}.log' -f [datetime]::Now)
            $logText = [IO.File]::ReadAllText($logPath, [Text.Encoding]::UTF8)
            $expectedUnicode = [string][char]0x6d4b + [char]0x8bd5
            Assert-True -Condition ($logText.Contains('stdout ' + $expectedUnicode)) -Message 'UTF-8 stdout was not retained in the private runner log.'
            Assert-True -Condition ($logText.Contains('stderr ' + $expectedUnicode)) -Message 'UTF-8 stderr was not retained in the private runner log.'
            Assert-True -Condition ($logText.Contains('exit=37')) -Message 'The runner log did not preserve the failing exit code.'
        } finally {
            $env:LOCALAPPDATA = $previousLocalAppData
        }
    } else {
        Write-Host 'Runner smoke test skipped: this machine is not in China Standard Time.'
    }
    Write-Host ("PASS: {0} Windows script checks. No scheduled task was registered." -f $passed)
} finally {
    if (Test-Path -LiteralPath $testDirectory) {
        $resolvedTestDirectory = (Resolve-Path -LiteralPath $testDirectory).Path
        $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
        if (-not $resolvedTestDirectory.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -or
            (Split-Path -Leaf $resolvedTestDirectory) -notlike 'dingtalk-daily-script-tests-*') {
            throw 'Refusing cleanup outside the verified test directory.'
        }
        Remove-Item -LiteralPath $resolvedTestDirectory -Recurse -Force
    }
}
