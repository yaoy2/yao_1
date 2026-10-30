param(
    [ValidateSet('all','whale','gpt')][string]$Instance = 'all',
    [ValidateSet('status','start','stop','start-all','stop-all','qq-start','qq-stop','open','backup','autostart-enable','autostart-disable')]
    [string]$Action = 'status',
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$cqRepo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$cqProject = [IO.Path]::GetFullPath($PSScriptRoot)
$cqManifest = Get-Content -LiteralPath (Join-Path $cqProject 'instances.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Instance -eq 'all' -and $Action -notin @('status','stop-all','autostart-disable')) {
    throw 'Choose -Instance whale or -Instance gpt for this action. Bulk startup is not supported.'
}
$cqTargets = @($cqManifest.instances | Where-Object { $Instance -eq 'all' -or $_.id -eq $Instance })
if (-not $cqTargets.Count) { throw 'No matching Cyber QQ instance.' }
$cqPlans = @()
foreach ($cqTarget in $cqTargets) {
    if ($Action -notin $cqTarget.actions) { throw "Action '$Action' is not supported by '$($cqTarget.id)'." }
    $cqEntry = [IO.Path]::GetFullPath((Join-Path $cqProject $cqTarget.entry))
    $cqRuntime = [IO.Path]::GetFullPath((Join-Path $cqRepo $cqTarget.runtime))
    if (-not $cqEntry.StartsWith($cqProject + '\', [StringComparison]::OrdinalIgnoreCase) -or
        -not $cqRuntime.StartsWith((Join-Path $cqRepo '.local') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Instance paths must remain inside this project and its local runtime directory.'
    }
    if (-not (Test-Path -LiteralPath $cqEntry -PathType Leaf)) { throw "Missing instance entry: $cqEntry" }
    $cqPlans += [pscustomobject]@{ Instance = $cqTarget.id; Name = $cqTarget.name;
        Action = $Action; Entry = $cqEntry; RuntimeRoot = $cqRuntime }
}
if ($DryRun) {
    ConvertTo-Json -InputObject $cqPlans -Depth 5
    return
}
foreach ($cqPlan in $cqPlans) {
    Write-Host ("[{0}] {1}" -f $cqPlan.Name, $cqPlan.Action)
    if (-not (Test-Path -LiteralPath (Join-Path $cqPlan.RuntimeRoot 'installation.json'))) {
        if ($Action -eq 'status') {
            [pscustomobject]@{ Instance = $cqPlan.Instance; Installed = $false; Running = $false }
            continue
        }
        throw "Instance '$($cqPlan.Instance)' is not installed on this computer."
    }
    if ($Action -eq 'status') {
        & $cqPlan.Entry -Action $cqPlan.Action -RuntimeRoot $cqPlan.RuntimeRoot | Format-Table -AutoSize
    } else {
        & $cqPlan.Entry -Action $cqPlan.Action -RuntimeRoot $cqPlan.RuntimeRoot
    }
}
