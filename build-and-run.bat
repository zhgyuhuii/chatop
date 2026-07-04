@echo off
REM Windows build + run for the product image chatop-ai. Bootstraps base if missing.
REM Daily iteration: just run this. It only rebuilds the fast product layers (no download).
REM ASCII-only source (avoid PS/CMD codepage mojibake).
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".env" (
  echo Please run first:  copy .env.example .env   then set PASSWORD in .env
  pause
  exit /b 1
)

REM VERSION file (single line) -> env var so compose resolves chatop-ai:<VERSION>
set /p VERSION=<VERSION

REM Bootstrap: build base once if it is not present locally
docker image inspect chatop-base:latest >nul 2>&1
if errorlevel 1 (
  echo chatop-base:latest not found, building base first ...
  call "%~dp0build-base.bat"
  if errorlevel 1 exit /b 1
)

docker compose up -d --build
if errorlevel 1 (
  echo [FAIL] docker compose up failed
  pause
  exit /b 1
)
echo [OK] started. Open https://localhost:6901  (or your PORT from .env)
pause
