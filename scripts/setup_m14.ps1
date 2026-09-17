param([string]$Python = 'python', [string]$Codex = 'codex')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskVenv = Join-Path $taskRoot '.venv-m14'
$taskPython = Join-Path $taskVenv 'Scripts\python.exe'
if (!(Test-Path -LiteralPath $taskPython)) {
    & $Python -m venv $taskVenv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the M14 environment.' }
}
& $taskPython -m pip install -r (Join-Path $taskRoot 'integrations\m14\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install M14 dependencies.' }
& $Codex mcp add m14 -- $taskPython (Join-Path $taskRoot 'scripts\m14_mcp.py') --transport stdio --env-file (Join-Path $taskRoot '.env.m14')
if ($LASTEXITCODE -ne 0) { throw 'Could not register M14 with Codex.' }
Write-Host 'M14 registered. Configure GitHub access locally, then start a new Work/Codex chat.'
