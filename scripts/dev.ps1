# Start the whole Wamidh stack locally, each part in its own window:
#   MQTT broker + PostgreSQL/PostGIS (Docker) -> schema migration -> backend -> virtual nodes -> web app.
# Usage (from the repo root):  powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
# Then open http://127.0.0.1:5173/station  (or run scripts\station-kiosk.ps1)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$py = Join-Path $repo ".venv\Scripts\python.exe"
Set-Location $repo

Write-Host "1/4 MQTT broker and database (Docker)..."
docker compose up -d mqtt db | Out-Null
# Wait for PostgreSQL to accept connections (first start initialises PostGIS: a few seconds).
$db = docker compose ps -q db  # container id, independent of the folder name
$deadline = (Get-Date).AddSeconds(60)
while ((docker inspect --format '{{.State.Health.Status}}' $db 2>$null) -ne 'healthy') {
    if ((Get-Date) -gt $deadline) {
        throw "The database container did not become healthy in 60 s. Check: docker compose logs db"
    }
    Start-Sleep -Seconds 2
}
Write-Host "    database ready; applying the schema migrations..."
& $py -m wamidh_backend.db upgrade
if ($LASTEXITCODE -ne 0) { throw "Schema migration failed (see the message above)." }
if (Test-Path "data\processed\zones.geojson") {
    Write-Host "    loading the population alert zones (zones\README.md)..."
    & $py -m wamidh_backend.load_zones
} else {
    Write-Host "    no alert zones yet: run 'python -m zones.pipeline --download' for the Residents tab"
}

# All 200 optimised sites; sensors already provisioned keep their keys.
Write-Host "    provisioning the 200 placement sites (keys in config\dev\registry.json)..."
& $py -m wamidh_sim.provision --count 200
New-Item -ItemType Directory -Force "data\dev" | Out-Null

function Start-Window($title, $command, $dir) {
    Start-Process powershell -WorkingDirectory $dir -ArgumentList @(
        "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle = '$title'; $command"
    )
}

Write-Host "2/4 backend on http://127.0.0.1:8000 ..."
Start-Window "Wamidh backend" "& '$py' -m wamidh_backend" $repo
Start-Sleep -Seconds 3

Write-Host "3/4 five virtual nodes ..."
Start-Window "Wamidh sensors" "& '$py' -m wamidh_sim.run" $repo

Write-Host "4/4 web app on http://127.0.0.1:5173 ..."
Start-Window "Wamidh web" "npx vite --host 127.0.0.1 --port 5173" (Join-Path $repo "web")

Write-Host ""
Write-Host "Station dashboard: http://127.0.0.1:5173/station"
Write-Host "Light a fire next to a node:   .venv\Scripts\python -m wamidh_sim.ignite 3"
Write-Host "Put it out:                    .venv\Scripts\python -m wamidh_sim.ignite 3 --out"
Write-Host "Cut a node's power:            .venv\Scripts\python -m wamidh_sim.ignite 5 --power off"
