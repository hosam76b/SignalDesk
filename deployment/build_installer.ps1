[CmdletBinding()]
param(
    [string] = ""
)

\Continue = "Stop"
\ = Split-Path -Parent \
\ = Join-Path \ "releases"
\ = Join-Path \ "SignalDesk.iss"

New-Item -ItemType Directory -Force -Path \ | Out-Null

if (-not \) {
    \ = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
        "C:\Program Files\Inno Setup 5\ISCC.exe"
    )
    \ = \ | Where-Object { Test-Path \ } | Select-Object -First 1
}

if (-not \) {
    throw "Inno Setup not found. Install Inno Setup 6 (https://jrsoftware.org/isinfo.php) or pass -InnoPath to the path of ISCC.exe."
}

& "\" "\"
if (\ -ne 0) { throw "Inno Setup compilation failed with exit code \" }

\ = Get-ChildItem -Path \ -Filter "SignalDesk_Setup*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (\) {
    Write-Host "Installer created successfully:" -ForegroundColor Green
    Write-Host \.FullName
} else {
    throw "Installer executable not found in \"
}
