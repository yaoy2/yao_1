# Compatibility entry; implementation belongs to the Cyber QQ project.
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot '..\cyber_qq\gpt_qq\manage.ps1') @args
