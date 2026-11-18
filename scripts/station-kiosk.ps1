# Open the station dashboard as a fire-station screen: full screen, and allowed to play the
# alarm siren without anyone clicking first (browsers block page audio otherwise).
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\station-kiosk.ps1 [-Url http://...]

param([string]$Url = "http://127.0.0.1:5173/station")

$edge = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $edge) { throw "Microsoft Edge not found" }

# A separate profile, so the flags apply even when Edge is already open for normal browsing.
$profileDir = Join-Path $env:LOCALAPPDATA "Wamidh\station-profile"
Start-Process $edge -ArgumentList @(
    "--user-data-dir=$profileDir",
    "--autoplay-policy=no-user-gesture-required",
    "--kiosk", $Url,
    "--no-first-run"
)
Write-Host "Station screen opened on $Url (Alt+F4 to close)."
