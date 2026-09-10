[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [string]$RepositoryUrl = "https://github.com/hosam76b/SignalDesk.git"
)

$ErrorActionPreference = "Stop"

function Select-Folder([string]$Description, [string]$InitialPath) {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = $Description
    $dialog.ShowNewFolderButton = $true
    if (Test-Path $InitialPath) { $dialog.SelectedPath = $InitialPath }
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        throw "No project folder was selected. Setup cancelled."
    }
    return $dialog.SelectedPath
}

function Test-ProjectRoot([string]$Path) {
    return (Test-Path (Join-Path $Path "requirements.txt")) -and (Test-Path (Join-Path $Path "frontend\package.json"))
}

if (-not $ProjectRoot) {
    $suggestedPath = Split-Path -Parent $PSScriptRoot
    $ProjectRoot = Select-Folder "Choose the SignalDesk project folder or an empty folder for download" $suggestedPath
}

$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
if (-not (Test-Path $ProjectRoot)) { New-Item -ItemType Directory -Force -Path $ProjectRoot | Out-Null }

if (-not (Test-ProjectRoot $ProjectRoot)) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "The selected folder does not contain SignalDesk and Git was not found. Install Git or select the downloaded project folder."
    }
    $items = Get-ChildItem -Force -Path $ProjectRoot
    if ($items.Count -gt 0) {
        throw "The selected folder is not an empty SignalDesk folder. Select the downloaded project folder or an empty folder."
    }
    Write-Host "Downloading SignalDesk into $ProjectRoot" -ForegroundColor Cyan
    & git clone $RepositoryUrl $ProjectRoot
    if ($LASTEXITCODE -ne 0) { throw "SignalDesk download failed." }
}

$ProjectRoot = (Resolve-Path $ProjectRoot).Path

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Require-Command([string]$Name, [string]$InstallHint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name was not found. Install it first: $InstallHint"
    }
    Write-Host "Found $Name" -ForegroundColor DarkGray
}

function Set-EnvValue([string]$Path, [string]$Key, [string]$Value) {
    $escapedKey = [regex]::Escape($Key)
    $content = if (Test-Path $Path) { Get-Content $Path -Raw } else { "" }
    $line = "$Key=$Value"
    if ($content -match "(?m)^$escapedKey=") {
        $content = [regex]::Replace($content, "(?m)^$escapedKey=.*$", [System.Text.RegularExpressions.MatchEvaluator]{ param($match) $line })
    } else {
        $content = ($content.TrimEnd() + "`r`n" + $line + "`r`n")
    }
    [System.IO.File]::WriteAllText($Path, $content, [System.Text.UTF8Encoding]::new($false))
}

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this wizard from PowerShell as Administrator."
}

Set-Location $ProjectRoot
Write-Host "SignalDesk Windows Setup Wizard" -ForegroundColor Green
Write-Host "Project: $ProjectRoot"

Write-Step "Checking required programs"
Require-Command "python" "Python 3.10, 3.11, or 3.12 from https://www.python.org/"
Require-Command "node" "Node.js 20 LTS from https://nodejs.org/"
Require-Command "npm" "Node.js 20 LTS from https://nodejs.org/"

Write-Step "Preparing environment file"
$envPath = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $envPath)) {
    Copy-Item (Join-Path $ProjectRoot ".env.example") $envPath
    Write-Host "Created .env from .env.example"
} else {
    Write-Host ".env already exists; existing values will be preserved where possible."
}
$secret = python -c "import secrets; print(secrets.token_urlsafe(48))"
$envContent = Get-Content $envPath -Raw
if ($envContent -match "(?m)^DB_URL=postgresql://user:password@localhost:5432/media_monitor\s*$") {
    Set-EnvValue $envPath "DB_URL" "sqlite:///./media_monitor.db"
}
if ($envContent -match "(?m)^SECRET_KEY=replace-this-in-production\s*$") {
    Set-EnvValue $envPath "SECRET_KEY" $secret.Trim()
}

Write-Step "Creating Python environment"
$pythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonPath)) {
    python -m venv (Join-Path $ProjectRoot ".venv")
}
& $pythonPath -m pip install --upgrade pip
& $pythonPath -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
& $pythonPath -m playwright install chromium

Write-Step "Installing and building the frontend"
Push-Location (Join-Path $ProjectRoot "frontend")
try {
    & npm.cmd install
    & npm.cmd run build
} finally {
    Pop-Location
}

Write-Step "Installing the Windows service"
& (Join-Path $ProjectRoot "deployment\install-service.ps1")

Write-Step "Checking the running service"
$healthUrl = "http://127.0.0.1:8000/health"
$health = $null
for ($attempt = 1; $attempt -le 15; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $health -or $health.status -ne "healthy") {
    throw "SignalDesk did not pass the health check. Review logs\service_stderr.log."
}

Write-Host ""
Write-Host "Setup completed successfully." -ForegroundColor Green
Write-Host "The first-run setup page will now open in your browser."
Start-Process "http://127.0.0.1:8000"