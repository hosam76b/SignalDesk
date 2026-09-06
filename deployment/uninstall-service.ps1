[CmdletBinding()]
param(
    [string]$NssmPath = "",
    [string]$ServiceName = "SignalDeskServer"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this script from an elevated PowerShell window."
}
if (-not $NssmPath) { $NssmPath = Join-Path $projectRoot "tools\nssm\win64\nssm.exe" }
if (Test-Path $NssmPath) {
    & $NssmPath stop $ServiceName 2>$null
    & $NssmPath remove $ServiceName confirm 2>$null
} elseif (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
    Stop-Service -Name $ServiceName -Force
    sc.exe delete $ServiceName | Out-Null
}
Get-NetFirewallRule -DisplayName "SignalDesk Server Access" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Write-Host "SignalDeskServer and its firewall rule were removed."