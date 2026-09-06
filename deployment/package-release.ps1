[CmdletBinding()]
param(
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $projectRoot "releases" }

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is required to create a release package. Install Git for Windows and retry."
}

$changes = git -C $projectRoot status --porcelain
if ($LASTEXITCODE -ne 0) { throw "Unable to read the Git repository status." }
if ($changes) {
    throw "Commit or stash all changes before packaging. The package contains committed source only."
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$version = git -C $projectRoot rev-parse --short HEAD
if ($LASTEXITCODE -ne 0) { throw "Unable to determine the current Git revision." }
$packagePath = Join-Path $OutputDirectory "SignalDesk-$version.zip"
git -C $projectRoot archive --format=zip --output=$packagePath HEAD
if ($LASTEXITCODE -ne 0) { throw "Git could not create the release archive." }

Write-Host "Release package created: $packagePath"
Write-Host "This package excludes .env, databases, virtual environments, logs, and uploaded media."