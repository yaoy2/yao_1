param(
    [Parameter(Mandatory = $true)][string]$PythonPath,
    [Parameter(Mandatory = $true)][string]$UvPath,
    [string]$RuntimeRoot = (Join-Path $PSScriptRoot '..\..\.local\whale_companion')
)
$ErrorActionPreference = 'Stop'
$wcRoot = [IO.Path]::GetFullPath($RuntimeRoot)
$wcCache = Join-Path $PSScriptRoot '..\..\.tmp\whale-install-可删'
$wcVersions = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'versions.lock.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not (Test-Path -LiteralPath $PythonPath) -or -not (Test-Path -LiteralPath $UvPath)) { throw 'Provide existing Python 3.12 and uv executables.' }
$wcVersion = & $PythonPath -c 'import sys; print("%d.%d" % sys.version_info[:2])'
if ($wcVersion -ne '3.12') { throw 'Use Python 3.12 for this verified dependency set.' }
$wcActive = @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='node.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains($wcRoot) })
if ($wcActive.Count) { throw 'Stop this installation before installing dependencies.' }
New-Item -ItemType Directory -Path $wcCache,$wcRoot -Force | Out-Null
foreach ($wcSource in $wcVersions.sources) {
    $wcDestination = [IO.Path]::GetFullPath((Join-Path $wcRoot $wcSource.destination))
    if (-not $wcDestination.StartsWith($wcRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Destination outside runtime.' }
    if (Test-Path -LiteralPath $wcDestination) { continue }
    $wcArchive = Join-Path $wcCache ($wcSource.id + '.zip')
    if (-not (Test-Path -LiteralPath $wcArchive)) {
        & curl.exe --fail --silent --show-error --location --retry 3 --retry-all-errors --output $wcArchive $wcSource.url
        if ($LASTEXITCODE -ne 0) { throw "Download failed: $($wcSource.id). Retain the partial file for inspection." }
    }
    if ((Get-FileHash -LiteralPath $wcArchive -Algorithm SHA256).Hash -ne $wcSource.sha256) { throw "Archive checksum mismatch: $($wcSource.id). No unverified archive was installed." }
    $wcUnpack = Join-Path $wcCache ($wcSource.id + '-' + [guid]::NewGuid().ToString('N'))
    Expand-Archive -LiteralPath $wcArchive -DestinationPath $wcUnpack
    $wcCopySource = $wcUnpack
    if ($wcSource.strip_root) {
        $wcEntries = @(Get-ChildItem -LiteralPath $wcUnpack)
        if ($wcEntries.Count -ne 1 -or -not $wcEntries[0].PSIsContainer) { throw 'Unexpected archive layout.' }
        $wcCopySource = $wcEntries[0].FullName
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $wcDestination) -Force | Out-Null
    Copy-Item -LiteralPath $wcCopySource -Destination $wcDestination -Recurse
}
$wcVenv = Join-Path $wcRoot 'app\AstrBot-4.29.3\.venv'
if (-not (Test-Path -LiteralPath $wcVenv)) {
    & $UvPath venv --python $PythonPath $wcVenv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create isolated Python environment.' }
}
$wcPython = Join-Path $wcVenv 'Scripts\python.exe'
& $UvPath pip sync --python $wcPython (Join-Path $PSScriptRoot 'requirements.lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $UvPath pip check --python $wcPython
if ($LASTEXITCODE -ne 0) { throw 'Dependency verification failed.' }
$env:PYTHONIOENCODING = 'utf-8'
& $wcPython (Join-Path $PSScriptRoot 'prepare.py') --root $wcRoot
if ($LASTEXITCODE -ne 0) { throw 'Initial configuration failed.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'versions.lock.json') -Destination (Join-Path $wcRoot 'installed-versions.json')
Write-Output 'Installed. Credentials and account setup remain local to this installation.'
