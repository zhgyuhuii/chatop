@echo off
REM Windows build + run (single Dockerfile, no base split).
REM Version auto-bumps last digit each run; old image removed to save disk.
REM Daily iteration: just run this (same-machine layer cache avoids re-download).
REM Optional proxy forwarded to build:
REM   build-and-run.bat http://127.0.0.1:7890   (Docker Desktop: http://host.docker.internal:7890)
REM ASCII-only source (avoid CMD codepage mojibake).
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist ".env" (
  echo Please run first:  copy .env.example .env   then set PASSWORD in .env
  pause
  exit /b 1
)
set "PROXY=%~1"

REM Version bump: last digit +1
set /p OLD=<VERSION
for /f "tokens=1,2,3 delims=." %%a in ("%OLD%") do set "MA=%%a"& set "MI=%%b"& set "PA=%%c"
set /a PA=PA+1
set "NEW=%MA%.%MI%.%PA%"
echo Version %OLD% -^> %NEW%

set "VERSION=%NEW%"
if "%PROXY%"=="" (
  docker compose up -d --build
) else (
  docker compose build --build-arg HTTPS_PROXY=%PROXY% --build-arg HTTP_PROXY=%PROXY% --build-arg NO_PROXY=localhost,127.0.0.1
  docker compose up -d
)
if errorlevel 1 (
  echo [FAIL] docker compose up failed
  pause
  exit /b 1
)

REM Persist new version; remove old image + dangling layers to save disk
>VERSION echo %NEW%
docker image rm chatop-ai:%OLD% >nul 2>&1
docker image prune -f >nul 2>&1

echo [OK] started chatop-ai:%NEW%. Open https://localhost:6901  (or your PORT in .env)
pause
