[CmdletBinding()]
param(
    [string]$ServiceName = "SignalDeskServer",
    [int]$Port = 8000,
    # 0.0.0.0 keeps LAN access working (the install script opens a firewall
    # rule and prints http://<SERVER_IP>:8000). Use 127.0.0.1 for a
    # loopback-only service reachable from this machine alone.
    [string]$HostAddress = "0.0.0.0",
    [string]$NssmPath = ""
)

# Point the service at one port and prove the self-check agrees with it.
#
# Why this script exists: uvicorn's --port and the socket self-check used to be
# configured independently. When they disagreed (probe 8010, listener 8000) the
# self-check saw no listener, declared a dead accept loop and exited the process
# of a perfectly healthy server, which NSSM then restarted in a loop. The port
# now lives in exactly one place -- SIGNALDESK_PORT in the service environment --
# and main.py hands that same value to the self-check.

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this script from an elevated PowerShell window."
}

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $service) {
    throw "Windows service '$ServiceName' was not found. Run deployment\install-service.ps1 first."
}

$python = @(".venv", "venv") |
    ForEach-Object { Join-Path $projectRoot "$_\Scripts\python.exe" } |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1
if (-not $python) {
    throw "No virtual environment Python found. Expected .venv\Scripts\python.exe or venv\Scripts\python.exe."
}

if (-not $NssmPath) {
    $NssmPath = Get-ChildItem -Path (Join-Path $projectRoot "tools\nssm") -Filter "nssm.exe" -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "win64" } |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $NssmPath -or -not (Test-Path $NssmPath)) { throw "NSSM executable was not found. Pass -NssmPath <path-to-nssm.exe>." }

# --- pre-flight: the port the app will actually use -------------------------
$resolvedPort = & $python -c "from config import settings; print(settings.port)" 2>&1
if ($LASTEXITCODE -ne 0) { throw "The application failed to load its configuration: $resolvedPort" }
if ([int]$resolvedPort -ne $Port) {
    throw "SIGNALDESK_PORT resolves to $resolvedPort, not $Port. Fix the value in $projectRoot\.env (or drop it there and pass -Port to this script)."
}
Write-Host "Config check: settings.port = $resolvedPort"

# --- apply -----------------------------------------------------------------
& $NssmPath set $ServiceName AppEnvironmentExtra "SIGNALDESK_PORT=$Port"
& $NssmPath set $ServiceName AppParameters "-m uvicorn main:app --host $HostAddress --port $Port"
& $NssmPath set $ServiceName AppDirectory $projectRoot
& $NssmPath set $ServiceName AppExit Default Restart
& $NssmPath set $ServiceName AppRestartDelay 5000
& sc.exe config $ServiceName start= auto | Out-Null

& $NssmPath restart $ServiceName

# --- verify ----------------------------------------------------------------
$status = Get-Service -Name $ServiceName
$healthUrl = "http://127.0.0.1:$Port/health"
$health = $null
for ($attempt = 1; $attempt -le 15; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 5
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}

$stderr = Join-Path $projectRoot "logs\service_stderr.log"
$probe = if (Test-Path $stderr) {
    (Select-String -Path $stderr -Pattern "Socket self-check started: (\S+)" | Select-Object -Last 1).Matches.Groups[1].Value
} else { $null }
$probeFailures = if (Test-Path $stderr) {
    (Select-String -Path $stderr -Pattern "self-check (failed|gave up)" | Measure-Object).Count
} else { 0 }

Write-Host "Service status  : $($status.Status)"
Write-Host "AppParameters   : $HostAddress : $Port"
Write-Host "Self-check probe: $probe"
if ($health) {
    Write-Host "Health          : $($health | ConvertTo-Json -Compress)"
} else {
    Write-Warning "Health check failed at ${healthUrl}. Inspect $stderr."
}

# The probe must have started on the bound port; anything else means the fix is
# not in force and the next false verdict will kill the service again.
if ($probe -ne "127.0.0.1:$Port" -and $probe -ne "$HostAddress`:$Port") {
    Write-Warning "Self-check probed '$probe' but the service binds $HostAddress`:$Port. Check SIGNALDESK_PORT in the service environment and SELF_CHECK_PORT in .env."
}
Write-Host "Self-check failures in the current log: $probeFailures"
Write-Host "SignalDeskServer is now bound to $HostAddress`:$Port"
