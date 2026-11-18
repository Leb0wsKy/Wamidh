@echo off
rem Wamidh: start everything with one double-click.
rem   Docker Desktop (if not running) -> database + MQTT broker -> backend -> 200 virtual sensors
rem   -> web app -> station dashboard in the browser.
rem   start.bat          opens the dashboard in your default browser
rem   start.bat kiosk    opens it as a full-screen station screen that can sound the siren (Edge)
setlocal
cd /d "%~dp0"
title Wamidh launcher

set "URL=http://127.0.0.1:5173/station"

rem Already running? Then only open the dashboard (avoids a second backend on the same port).
curl.exe -s -o nul -m 3 http://127.0.0.1:8000/api/v1/nodes && (
  echo Wamidh is already running.
  goto open
)

rem 1. Docker Desktop: needed for the database and the MQTT broker.
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready
echo Starting Docker Desktop...
start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
set /a tries=0
:wait_docker
ping -n 4 127.0.0.1 >nul
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready
set /a tries+=1
if %tries% lss 60 goto wait_docker
echo Docker Desktop did not start within 3 minutes. Start it by hand, then run start.bat again.
pause
exit /b 1
:docker_ready
echo Docker is ready.

rem 2. The whole stack, each part in its own window (scripts\dev.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\dev.ps1"
if errorlevel 1 (
  echo Startup failed: see the messages above.
  pause
  exit /b 1
)

rem 3. Wait for the web app to answer.
echo Waiting for the web app...
set /a tries=0
:wait_web
curl.exe -s -o nul -m 3 http://127.0.0.1:5173/ && goto open
ping -n 3 127.0.0.1 >nul
set /a tries+=1
if %tries% lss 60 goto wait_web
echo The web app did not answer within 2 minutes: check the "Wamidh web" window.
pause
exit /b 1

:open
if /i "%~1"=="kiosk" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\station-kiosk.ps1" -Url "%URL%"
) else (
  start "" "%URL%"
)
echo.
echo Station dashboard: %URL%
echo Crew app:          http://127.0.0.1:5173/crew
echo Residents:         http://127.0.0.1:5173/residents
echo To stop: close the Wamidh windows, then run  docker compose stop
ping -n 9 127.0.0.1 >nul
