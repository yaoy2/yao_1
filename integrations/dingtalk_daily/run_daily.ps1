[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-DingTalkRunnerLogDirectory {
    $localData = $env:LOCALAPPDATA
    if (-not $localData) {
        $localData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
    }
    if (-not $localData -or -not [IO.Path]::IsPathRooted($localData)) {
        throw '当前用户的 LocalAppData 路径不可用。'
    }
    $directory = Join-Path $localData 'YaoTools\DingTalkDaily\logs'
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    return $directory
}

function Invoke-DingTalkDaily {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw '每日采集仅支持 Windows。' }
    $timeZone = [TimeZoneInfo]::Local
    $now = [datetime]::Now
    if ($timeZone.Id -ne 'China Standard Time' -or $timeZone.SupportsDaylightSavingTime) {
        throw '本机时区已经不是中国标准时间，已停止每日采集；请核对电脑 L 的时区。'
    }
    foreach ($date in @($now, [datetime]::new($now.Year, 1, 15, 12, 0, 0), [datetime]::new($now.Year, 7, 15, 12, 0, 0))) {
        if ($timeZone.GetUtcOffset($date) -ne [TimeSpan]::FromHours(8)) {
            throw '本机时区并非全年 UTC+08:00，已停止每日采集。'
        }
    }
    $pythonExecutable = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    $entryPoint = Join-Path $PSScriptRoot 'main.py'
    foreach ($requiredFile in @($pythonExecutable, $entryPoint)) {
        if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
            throw "缺少运行文件：$requiredFile。请在电脑 L 重新运行 setup.ps1。"
        }
    }
    # Capture launcher/configuration errors even before main.py can create its own log.
    $logPath = Join-Path (Get-DingTalkRunnerLogDirectory) ('runner-{0:yyyyMMdd}.log' -f $now)
    $utf8 = [Text.UTF8Encoding]::new($false)
    [IO.File]::AppendAllText($logPath, (("{0:yyyy-MM-dd HH:mm:ss zzz} start" -f [datetimeoffset]::Now) + [Environment]::NewLine), $utf8)
    $process = [Diagnostics.Process]::new()
    try {
        $process.StartInfo.FileName = $pythonExecutable
        $process.StartInfo.Arguments = '-X utf8 -u "{0}" run --scheduled' -f $entryPoint
        $process.StartInfo.WorkingDirectory = $PSScriptRoot
        $process.StartInfo.UseShellExecute = $false
        $process.StartInfo.CreateNoWindow = $true
        $process.StartInfo.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
        $process.StartInfo.RedirectStandardOutput = $true
        $process.StartInfo.RedirectStandardError = $true
        $process.StartInfo.StandardOutputEncoding = $utf8
        $process.StartInfo.StandardErrorEncoding = $utf8
        if (-not $process.Start()) { throw '无法启动项目 Python。' }
        # Drain both streams concurrently so large stderr output cannot deadlock the run.
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $stdout = $stdoutTask.Result
        $stderr = $stderrTask.Result
        $script:dailyExitCode = $process.ExitCode
        if ($stdout) { [IO.File]::AppendAllText($logPath, ("[stdout]" + [Environment]::NewLine + $stdout + [Environment]::NewLine), $utf8) }
        if ($stderr) { [IO.File]::AppendAllText($logPath, ("[stderr]" + [Environment]::NewLine + $stderr + [Environment]::NewLine), $utf8) }
        [IO.File]::AppendAllText($logPath, (("{0:yyyy-MM-dd HH:mm:ss zzz} exit={1}" -f [datetimeoffset]::Now, $script:dailyExitCode) + [Environment]::NewLine), $utf8)
    } finally {
        $process.Dispose()
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        Invoke-DingTalkDaily
        exit $script:dailyExitCode
    } catch {
        $failure = '{0:yyyy-MM-dd HH:mm:ss zzz} bootstrap failure: {1}' -f [datetimeoffset]::Now, $_.Exception.Message
        try {
            $logDirectory = Get-DingTalkRunnerLogDirectory
            $logPath = Join-Path $logDirectory 'runner-bootstrap.log'
            [IO.File]::AppendAllText($logPath, ($failure + [Environment]::NewLine), [Text.UTF8Encoding]::new($false))
        } catch {
            Write-Error -Message ("无法保存启动失败日志：{0}" -f $_.Exception.Message) -ErrorAction Continue
        }
        Write-Error -Message $failure -ErrorAction Continue
        exit 1
    }
}
