[CmdletBinding()]
param(
    [ValidatePattern('^[^\\/\[\]*?:<>|"]+$')]
    [string]$TaskName = 'YaoTools.DingTalkDaily'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-ChinaTimeZone {
    param([TimeZoneInfo]$TimeZone = [TimeZoneInfo]::Local, [datetime]$Now = [datetime]::Now)
    if ($TimeZone.Id -ne 'China Standard Time' -or $TimeZone.SupportsDaylightSavingTime) {
        throw '本机时区必须是中国标准时间（UTC+08:00，无夏令时）。请核对电脑 L 的时区；脚本不会修改系统设置。'
    }
    foreach ($date in @($Now, [datetime]::new($Now.Year, 1, 15, 12, 0, 0), [datetime]::new($Now.Year, 7, 15, 12, 0, 0))) {
        if ($TimeZone.GetUtcOffset($date) -ne [TimeSpan]::FromHours(8)) {
            throw '检测到本机时区并非全年 UTC+08:00，已停止注册，避免错时或跨日采集。'
        }
    }
}

function Assert-LocalCalibration {
    param([string]$ConfigPath)
    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        throw '缺少 config.local.json。请先运行 setup.ps1 并完成本机桌面校准。'
    }
    $config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $config -or $null -eq $config.PSObject.Properties['calibration_ok'] -or
        $config.calibration_ok -isnot [bool] -or -not $config.calibration_ok) {
        throw '本机桌面校准尚未通过（calibration_ok 必须为 true），不启用自动采集。'
    }
}

function Get-DingTalkTaskMarker {
    param([string]$OwnerSid)
    return "Managed by yao_1/integrations/dingtalk_daily v1; owner_sid=$OwnerSid;"
}

function Assert-OwnedDingTalkTask {
    param($ExistingTask, [string]$OwnerSid)
    if ($null -eq $ExistingTask) { return }
    $marker = Get-DingTalkTaskMarker -OwnerSid $OwnerSid
    if (-not ([string]$ExistingTask.Description).StartsWith($marker, [StringComparison]::Ordinal)) {
        throw '同名定时任务已经存在，且不能确认属于本项目和当前用户。脚本没有覆盖它；请检查任务名称。'
    }
}

function Get-TaskOwnerSid {
    param([string]$UserId)
    if ($UserId -match '^S-1-') { return $UserId }
    return ([Security.Principal.NTAccount]::new($UserId)).Translate([Security.Principal.SecurityIdentifier]).Value
}

function Assert-RegisteredDingTalkTask {
    param($Task, [string]$OwnerSid, [string]$Executable, [string]$Arguments, [string]$Directory)
    Assert-OwnedDingTalkTask -ExistingTask $Task -OwnerSid $OwnerSid
    if ($null -eq $Task -or @($Task.Actions).Count -ne 1 -or @($Task.Triggers).Count -ne 1) {
        throw '任务注册后的动作或触发器数量不符，请检查 Windows 任务计划程序。'
    }
    $action = @($Task.Actions)[0]
    $trigger = @($Task.Triggers)[0]
    $time = [datetime]::Parse($trigger.StartBoundary, [Globalization.CultureInfo]::InvariantCulture)
    if ($action.Execute -ne $Executable -or $action.Arguments -cne $Arguments -or
        $action.WorkingDirectory -ne $Directory -or
        (Get-TaskOwnerSid -UserId $Task.Principal.UserId) -ne $OwnerSid -or
        [string]$Task.Principal.LogonType -ne 'Interactive' -or [string]$Task.Principal.RunLevel -ne 'Limited' -or
        [string]$Task.Settings.MultipleInstances -ne 'IgnoreNew' -or
        $Task.Settings.StartWhenAvailable -or $Task.Settings.WakeToRun -or $Task.Settings.RestartCount -ne 0 -or
        [Xml.XmlConvert]::ToTimeSpan($Task.Settings.ExecutionTimeLimit) -ne [TimeSpan]::FromMinutes(45) -or
        -not $Task.Settings.Enabled -or -not $trigger.Enabled -or $trigger.DaysInterval -ne 1 -or
        $time.Hour -ne 22 -or $time.Minute -ne 0 -or $time.Second -ne 0) {
        throw '任务注册后的配置核验未通过，请检查 Windows 任务计划程序；不能确认自动运行已正确启用。'
    }
}

function Register-DingTalkDailyTask {
    param([string]$Name)
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw '定时任务仅支持 Windows。' }
    Assert-ChinaTimeZone
    $projectDirectory = $PSScriptRoot
    $pythonExecutable = Join-Path $projectDirectory '.venv\Scripts\python.exe'
    $entryPoint = Join-Path $projectDirectory 'main.py'
    $runner = Join-Path $projectDirectory 'run_daily.ps1'
    foreach ($requiredFile in @($pythonExecutable, $entryPoint, $runner)) {
        if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
            throw "缺少文件：$requiredFile。请先运行 setup.ps1。"
        }
    }
    Assert-LocalCalibration -ConfigPath (Join-Path $projectDirectory 'config.local.json')
    & $pythonExecutable -X utf8 $entryPoint doctor
    if ($LASTEXITCODE -ne 0) { throw '桌面诊断未通过，没有注册或更新任务。请按诊断提示处理后重试。' }

    Import-Module ScheduledTasks -ErrorAction Stop
    $ownerSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $existing = @(Get-ScheduledTask -TaskPath '\' -ErrorAction Stop | Where-Object { $_.TaskName -eq $Name })
    if ($existing.Count -gt 1) { throw '发现多个同名任务，已停止注册。' }
    if ($existing.Count -eq 1) { Assert-OwnedDingTalkTask -ExistingTask $existing[0] -OwnerSid $ownerSid }

    $powershellExecutable = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -File "{0}"' -f $runner
    $action = New-ScheduledTaskAction -Execute $powershellExecutable -Argument $arguments -WorkingDirectory $projectDirectory
    $trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours(22))
    $principal = New-ScheduledTaskPrincipal -UserId $ownerSid -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 45) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $settings.StartWhenAvailable = $false
    $settings.WakeToRun = $false
    $settings.RestartCount = 0
    $description = '{0} root={1}; daily 22:00 China Standard Time; interactive desktop only.' -f (Get-DingTalkTaskMarker -OwnerSid $ownerSid), $projectDirectory
    $definition = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description $description
    $registration = @{ TaskName = $Name; TaskPath = '\'; InputObject = $definition; ErrorAction = 'Stop' }
    if ($existing.Count -eq 1) { $registration.Force = $true }
    Register-ScheduledTask @registration | Out-Null

    $registered = Get-ScheduledTask -TaskName $Name -TaskPath '\' -ErrorAction Stop
    Assert-RegisteredDingTalkTask -Task $registered -OwnerSid $ownerSid -Executable $powershellExecutable -Arguments $arguments -Directory $projectDirectory
    $info = Get-ScheduledTaskInfo -TaskName $Name -TaskPath '\' -ErrorAction Stop
    if ($info.NextRunTime -le [datetime]::Now -or $info.NextRunTime.Hour -ne 22 -or $info.NextRunTime.Minute -ne 0) {
        throw '任务已写入，但下一次运行时间核验未通过。请检查任务计划程序；尚不能确认每日计划正常。'
    }
    Write-Host ("已核验定时任务：{0}。下次运行：{1:yyyy-MM-dd HH:mm:ss}（北京时间）。" -f $Name, $info.NextRunTime)
    Write-Host '运行时电脑 L 需要保持开机、当前用户已登录并解锁，且钉钉已登录。任务不会唤醒电脑、补跑错过的日期或自动重试。'
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        Register-DingTalkDailyTask -Name $TaskName
    } catch {
        Write-Error -Message $_.Exception.Message -ErrorAction Continue
        exit 1
    }
}
