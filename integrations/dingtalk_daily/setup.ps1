[CmdletBinding()]
param(
    [string]$PythonExecutable
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-PythonVersion {
    param([string]$Executable, [string[]]$PrefixArguments = @())
    & $Executable @PrefixArguments -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Invoke-DingTalkSetup {
    param([string]$RequestedPython)

    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw '此项目需要 Windows 桌面。'
    }
    $projectDirectory = $PSScriptRoot
    $environmentDirectory = Join-Path $projectDirectory '.venv'
    $environmentPython = Join-Path $environmentDirectory 'Scripts\python.exe'
    $entryPoint = Join-Path $projectDirectory 'main.py'
    $requirementsFile = Join-Path $projectDirectory 'requirements.txt'
    foreach ($requiredFile in @($entryPoint, $requirementsFile)) {
        if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
            throw "缺少项目文件：$requiredFile。请先完整拉取项目。"
        }
    }

    if (-not (Test-Path -LiteralPath $environmentPython -PathType Leaf)) {
        if (Test-Path -LiteralPath $environmentDirectory) {
            throw '.venv 已存在，但没有可用的 Python。请检查该目录；脚本不会删除或覆盖已有环境。'
        }
        $launcher = $null
        $launcherArguments = @()
        if ($RequestedPython) {
            $candidate = Get-Command -Name $RequestedPython -CommandType Application -ErrorAction Stop
            if (-not (Test-PythonVersion -Executable $candidate.Source)) {
                throw '指定的 Python 不满足 Python 3.11 或更高版本要求。'
            }
            $launcher = $candidate.Source
        } else {
            foreach ($candidateName in @('py.exe', 'python.exe')) {
                $candidate = Get-Command -Name $candidateName -CommandType Application -ErrorAction SilentlyContinue
                if ($null -eq $candidate) { continue }
                $candidateArguments = @()
                if ($candidateName -eq 'py.exe') { $candidateArguments = @('-3') }
                if (Test-PythonVersion -Executable $candidate.Source -PrefixArguments $candidateArguments) {
                    $launcher = $candidate.Source
                    $launcherArguments = $candidateArguments
                    break
                }
            }
        }
        if (-not $launcher) {
            throw '没有找到 Python 3.11 或更高版本。安装后重试，或通过 -PythonExecutable 指定 python.exe 的完整路径。'
        }
        & $launcher @launcherArguments -m venv $environmentDirectory
        if ($LASTEXITCODE -ne 0) { throw '创建项目独立 Python 环境失败。' }
    }

    & $environmentPython -c 'import pathlib,sys; raise SystemExit(0 if sys.version_info >= (3,11) and sys.prefix != sys.base_prefix and pathlib.Path(sys.prefix).resolve() == pathlib.Path(sys.argv[1]).resolve() else 1)' $environmentDirectory
    if ($LASTEXITCODE -ne 0) {
        throw '现有 .venv 无效或 Python 版本不足；脚本不会自动重建它。'
    }
    & $environmentPython -m pip --require-virtualenv --disable-pip-version-check install --requirement $requirementsFile
    if ($LASTEXITCODE -ne 0) { throw '安装项目依赖失败；尚未配置或启用定时任务。' }
    & $environmentPython -X utf8 $entryPoint configure
    if ($LASTEXITCODE -ne 0) { throw '本机配置未完成；尚未启用定时任务。' }

    Write-Host '环境和本机配置已准备。完成桌面校准后，在电脑 L 运行 .\register_task.ps1 启用每晚 22:00 的任务。'
    Write-Host '本脚本没有注册定时任务。Windows 脚本策略如阻止执行，请采用你所在单位允许的方式处理；脚本不会修改策略。'
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        Invoke-DingTalkSetup -RequestedPython $PythonExecutable
    } catch {
        Write-Error -Message $_.Exception.Message -ErrorAction Continue
        exit 1
    }
}
