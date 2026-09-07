[CmdletBinding()]
param(
    [string]$Repository = "https://github.com/hosam76b/SignalDesk.git",
    [string]$Branch = "main",
    [string]$ServiceName = "SignalDeskServer"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is required to update SignalDesk."
}

$status = git status --porcelain
if ($LASTEXITCODE -ne 0) { throw "Unable to read the Git repository status." }
if ($status) {
    throw "Local changes detected. Commit or stash them before updating from GitHub."
}

$currentRemote = git remote get-url origin 2>$null
if (-not $currentRemote) {
    git remote add origin $Repository
} elseif ($currentRemote -ne $Repository) {
    throw "The origin remote is '$currentRemote', not '$Repository'."
}

git fetch origin $Branch --prune
if ($LASTEXITCODE -ne 0) { throw "Unable to fetch updates from GitHub." }
git merge --ff-only "origin/$Branch"
if ($LASTEXITCODE -ne 0) { throw "The local branch cannot be fast-forwarded safely." }

$python = @(".venv", "venv") |
    ForEach-Object { Join-Path $projectRoot "$_\Scripts\python.exe" } |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1
if (-not $python) { throw "No virtual environment Python was found." }

& $python -m pip install -r (Join-Path $projectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed. The service was not restarted." }

Push-Location (Join-Path $projectRoot "frontend")
try {
    npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
} finally {
    Pop-Location
}

& (Join-Path $PSScriptRoot "restart-service.ps1") -ServiceName $ServiceName
Write-Host "SignalDesk updated to $(git rev-parse --short HEAD) from origin/$Branch."