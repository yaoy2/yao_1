# Register the receiver's fixed Explorer link for this Windows user only.
# No URL arguments are passed to Explorer: a page cannot choose another path
# or turn this link into a general command launcher.
$ErrorActionPreference = 'Stop'
$folder = 'E:\GoogleDrive\Ding2026\手机传输'
$protocolKey = 'HKCU:\Software\Classes\yao-suishouchuan'
$commandKey = "$protocolKey\shell\open\command"
$explorer = Join-Path (Split-Path ([Environment]::SystemDirectory) -Parent) 'explorer.exe'

if ([Environment]::MachineName -ne 'NSU-20240627RGY') {
    throw 'This link is only configured for office computer L.'
}
if (-not (Test-Path -LiteralPath $folder -PathType Container)) {
    throw "Receive folder does not exist: $folder"
}
if (-not (Test-Path -LiteralPath $explorer -PathType Leaf)) {
    throw 'Windows Explorer was not found.'
}
$command = '"{0}" "{1}"' -f $explorer, $folder
if (Test-Path -LiteralPath $protocolKey) {
    $existing = if (Test-Path -LiteralPath $commandKey) { (Get-Item -LiteralPath $commandKey).GetValue('') } else { $null }
    if ($existing -ne $command) {
        throw 'The protocol already belongs to another handler; it has not been changed.'
    }
}

New-Item -Path $commandKey -Force | Out-Null
Set-Item -LiteralPath $protocolKey -Value 'URL:Suishouchuan - Open phone transfer folder'
New-ItemProperty -LiteralPath $protocolKey -Name 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null
Set-Item -LiteralPath $commandKey -Value $command
if ((Get-Item -LiteralPath $commandKey).GetValue('') -ne $command) {
    throw 'Protocol registration verification failed.'
}
Write-Output "Registered yao-suishouchuan://open-folder for $folder"
