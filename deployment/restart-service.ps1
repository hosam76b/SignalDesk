[CmdletBinding()]
param(
    [string]$ServiceName = "SignalDeskServer"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this script from an elevated PowerShell window."
}

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $service) {
    throw "Windows service '$ServiceName' was not found. Run deployment\install-service.ps1 first."
}

Restart-Service -Name $ServiceName -Force

$status = Get-Service -Name $ServiceName
$healthUrl = "http://127.0.0.1:8000/health"
$health = $null
$healthError = $null
for ($attempt = 1; $attempt -le 10; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 5
        break
    } catch {
        $healthError = $_.Exception.Message
        Start-Sleep -Seconds 2
    }
}

try {
    if (-not $health) { throw $healthError }
    Write-Host "$ServiceName restarted from $projectRoot"
    Write-Host "Service status: $($status.Status)"
    Write-Host "Health: $($health | ConvertTo-Json -Compress)"
} catch {
    Write-Host "$ServiceName restarted from $projectRoot"
    Write-Host "Service status: $($status.Status)"
    Write-Warning "Health check failed at ${healthUrl}: $($_.Exception.Message)"
}