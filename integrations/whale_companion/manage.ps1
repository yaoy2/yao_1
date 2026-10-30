# Compatibility entry keeps existing launchers and the disabled login task usable.
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot '..\cyber_qq\whale_companion\manage.ps1') @args
