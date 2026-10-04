[CmdletBinding()]
param(
    [string]$InnoPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$releaseDir = Join-Path $projectRoot "releases"
$issFile = Join-Path $PSScriptRoot "SignalDesk.iss"

New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

if ($InnoPath -and -not (Test-Path -LiteralPath $InnoPath)) {
    throw "The -InnoPath '$InnoPath' does not exist."
}

if (-not $InnoPath) {
    $candidates = New-Object System.Collections.Generic.List[string]

    $onPath = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($onPath) { $candidates.Add($onPath.Source) }

    $uninstallKeys = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
    )
    foreach ($uninstallKey in $uninstallKeys) {
        foreach ($key in Get-ChildItem -Path $uninstallKey -ErrorAction SilentlyContinue) {
            $entry = Get-ItemProperty -Path $key.PSPath -ErrorAction SilentlyContinue
            if ($entry.DisplayName -like "Inno Setup*" -and $entry.InstallLocation) {
                $candidates.Add((Join-Path $entry.InstallLocation.TrimEnd("\") "ISCC.exe"))
            }
        }
    }

    foreach ($version in @("6", "7", "5")) {
        foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
            if (-not $root) { continue }
            $candidates.Add((Join-Path $root "Inno Setup $version\ISCC.exe"))
        }
    }

    $InnoPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

if (-not $InnoPath) {
    throw "Inno Setup not found. Install Inno Setup 6 (https://jrsoftware.org/isinfo.php) or pass -InnoPath to the path of ISCC.exe."
}

& $InnoPath $issFile
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed with exit code $LASTEXITCODE" }

$installer = Get-ChildItem -Path $releaseDir -Filter "SignalDesk_Setup*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($installer) {
    Write-Host "Installer created successfully:" -ForegroundColor Green
    Write-Host $installer.FullName
} else {
    throw "Installer executable not found in $releaseDir"
}