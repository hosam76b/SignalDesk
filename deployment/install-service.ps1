[CmdletBinding()]
param(
    [string]$NssmPath = "",
    [string]$ServiceName = "SignalDeskServer"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$virtualEnvironment = @(".venv", "venv") |
    ForEach-Object { Join-Path $projectRoot "$_\Scripts\python.exe" } |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1
if (-not $virtualEnvironment) {
    $bootstrapPython = Get-Command py -ErrorAction SilentlyContinue
    if ($bootstrapPython) {
        & py -3 -m venv (Join-Path $projectRoot ".venv")
    } else {
        $bootstrapPython = Get-Command python -ErrorAction SilentlyContinue
        if (-not $bootstrapPython) { throw "Python 3.10 or newer is required. Install Python, then rerun this script." }
        & python -m venv (Join-Path $projectRoot ".venv")
    }
    $virtualEnvironment = Join-Path $projectRoot ".venv\Scripts\python.exe"
}
$python = $virtualEnvironment
$logs = Join-Path $projectRoot "logs"
$frontend = Join-Path $projectRoot "frontend"
$trayLauncher = Join-Path $projectRoot "deployment\start_tray.vbs"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this script from an elevated PowerShell window."
}
if (-not $python) { throw "No virtual environment Python found. Expected .venv\Scripts\python.exe or venv\Scripts\python.exe." }

& $python -m ensurepip --upgrade
& $python -m pip install -r (Join-Path $projectRoot "requirements.txt")
New-Item -ItemType Directory -Force -Path $logs | Out-Null
Push-Location $frontend
try { & npm.cmd run build } finally { Pop-Location }

if (-not $NssmPath) {
    $nssmDirectory = Join-Path $projectRoot "tools\nssm"
    $NssmPath = Get-ChildItem -Path $nssmDirectory -Filter "nssm.exe" -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "win64" } |
        Select-Object -First 1 -ExpandProperty FullName
    if (-not $NssmPath) {
        $archive = Join-Path $env:TEMP "nssm-2.24.zip"
        New-Item -ItemType Directory -Force -Path $nssmDirectory | Out-Null
        Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $archive
        Expand-Archive -Path $archive -DestinationPath $nssmDirectory -Force
        $NssmPath = Get-ChildItem -Path $nssmDirectory -Filter "nssm.exe" -Recurse |
            Where-Object { $_.FullName -match "win64" } |
            Select-Object -First 1 -ExpandProperty FullName
    }
}
if (-not $NssmPath -or -not (Test-Path $NssmPath)) { throw "NSSM executable was not found after download. Check Internet access or rerun with -NssmPath <path-to-nssm.exe>." }

if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
    & $NssmPath stop $ServiceName
    & $NssmPath remove $ServiceName confirm
}
& $NssmPath install $ServiceName $python "-m uvicorn main:app --host 0.0.0.0 --port 8000"
& $NssmPath set $ServiceName AppDirectory $projectRoot
& $NssmPath set $ServiceName Start SERVICE_AUTO_START
& $NssmPath set $ServiceName AppStdout (Join-Path $logs "service_stdout.log")
& $NssmPath set $ServiceName AppStderr (Join-Path $logs "service_stderr.log")
& $NssmPath set $ServiceName AppRotateFiles 1
& $NssmPath set $ServiceName AppExit Default Restart
& $NssmPath set $ServiceName AppRestartDelay 5000
& sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null

Get-NetFirewallRule -DisplayName "SignalDesk Server Access" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "SignalDesk Server Access" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow | Out-Null
& $NssmPath start $ServiceName

$desktop = [Environment]::GetFolderPath("Desktop")
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $desktop "SignalDesk.lnk"))
$shortcut.TargetPath = "msedge.exe"
$shortcut.Arguments = "--app=http://127.0.0.1:8000 --window-size=1440,900"
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Save()

$trayShortcut = $shell.CreateShortcut((Join-Path $desktop "SignalDesk Monitor.lnk"))
$trayShortcut.TargetPath = "wscript.exe"
$trayShortcut.Arguments = "`"$trayLauncher`""
$trayShortcut.WorkingDirectory = $projectRoot
$trayShortcut.Save()

$startup = [Environment]::GetFolderPath("Startup")
$startupTrayShortcut = $shell.CreateShortcut((Join-Path $startup "SignalDesk Monitor.lnk"))
$startupTrayShortcut.TargetPath = "wscript.exe"
$startupTrayShortcut.Arguments = "`"$trayLauncher`""
$startupTrayShortcut.WorkingDirectory = $projectRoot
$startupTrayShortcut.Save()

Write-Host "SignalDeskServer is installed and running. Open http://localhost:8000 or http://<SERVER_IP>:8000"