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
    # Wheels for the transitive scientific stack (numpy via opencv/easyocr and
    # friends) are not published for 3.13 yet, so pinning the newest interpreter
    # turns `pip install` into a source build that needs a C compiler. Pick the
    # newest version that actually has wheels.
    $venvPath = Join-Path $projectRoot ".venv"
    $created = $false
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($version in @("3.12", "3.11", "3.10")) {
            & py "-$version" -m venv $venvPath
            if (Test-Path (Join-Path $venvPath "Scripts\python.exe")) { $created = $true; break }
        }
    }
    if (-not $created) {
        $bootstrapPython = Get-Command python -ErrorAction SilentlyContinue
        if (-not $bootstrapPython) { throw "Python 3.10, 3.11 or 3.12 is required. Install Python, then rerun this script." }
        & python -m venv $venvPath
    }
    $virtualEnvironment = Join-Path $venvPath "Scripts\python.exe"
}
$python = $virtualEnvironment
$logs = Join-Path $projectRoot "logs"
$frontend = Join-Path $projectRoot "frontend"
$trayLauncher = Join-Path $projectRoot "deployment\start_tray.vbs"
$trayIcon = Join-Path $projectRoot "assets\signaldesk-monitor.ico"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this script from an elevated PowerShell window."
}
if (-not $python) { throw "No virtual environment Python found. Expected .venv\Scripts\python.exe or venv\Scripts\python.exe." }

& $python -m ensurepip --upgrade
& $python -m pip install --upgrade pip
& $python -m pip install -r (Join-Path $projectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed with exit code $LASTEXITCODE. Check Internet access and rerun this script." }
& $python -c "import uvicorn, fastapi"
if ($LASTEXITCODE -ne 0) { throw "The virtual environment at $python is missing uvicorn/fastapi. Delete it and rerun this script to rebuild it." }
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

# One port, defined once. It reaches the process as SIGNALDESK_PORT, reaches
# uvicorn as --port, and main.py hands that same value to the socket self-check
# so the probe can never target a port the service is not serving.
$port = 8000

if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
    & $NssmPath stop $ServiceName
    & $NssmPath remove $ServiceName confirm
}
& $NssmPath install $ServiceName $python "-m uvicorn main:app --host 0.0.0.0 --port $port"
& $NssmPath set $ServiceName AppDirectory $projectRoot
& $NssmPath set $ServiceName AppEnvironmentExtra "SIGNALDESK_PORT=$port"
& $NssmPath set $ServiceName Start SERVICE_AUTO_START
& $NssmPath set $ServiceName AppStdout (Join-Path $logs "service_stdout.log")
& $NssmPath set $ServiceName AppStderr (Join-Path $logs "service_stderr.log")
& $NssmPath set $ServiceName AppRotateFiles 1
& $NssmPath set $ServiceName AppExit Default Restart
& $NssmPath set $ServiceName AppRestartDelay 5000
& sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null

Get-NetFirewallRule -DisplayName "SignalDesk Server Access" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "SignalDesk Server Access" -Direction Inbound -LocalPort $port -Protocol TCP -Action Allow | Out-Null
& $NssmPath start $ServiceName

# The desktop and Start Menu shortcuts are owned by the Inno Setup [Icons]
# section, so they are not recreated here. Only the tray monitor is started
# with the user session, because it is a per-user convenience and not part of
# the installation itself.
if (Test-Path $trayLauncher) {
    $shell = New-Object -ComObject WScript.Shell
    $startup = [Environment]::GetFolderPath("Startup")
    $trayShortcut = $shell.CreateShortcut((Join-Path $startup "SignalDesk Monitor.lnk"))
    $trayShortcut.TargetPath = "$env:SystemRoot\System32\wscript.exe"
    $trayShortcut.Arguments = "`"$trayLauncher`""
    $trayShortcut.WorkingDirectory = $projectRoot
    $trayShortcut.IconLocation = "$trayIcon,0"
    $trayShortcut.Save()
    Write-Host "Tray monitor registered in the Startup folder."
}

Write-Host "SignalDeskServer is installed and running. Open http://localhost:8000 or http://<SERVER_IP>:8000"