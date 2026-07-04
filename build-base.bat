@echo off
REM Windows build for the fixed base image chatop-base:latest.
REM Run this when base deps change / to update AI tools / on a fresh machine.
REM ASCII-only source (avoid PS/CMD codepage mojibake).
chcp 65001 >nul
cd /d "%~dp0"

echo Building chatop-base:latest ... (first time downloads several GB, only once)
docker build -f Dockerfile.base --build-arg APP_USER=admin --build-arg LOGIN_USER=admin -t chatop-base:latest .
if errorlevel 1 (
  echo [FAIL] chatop-base build failed
  pause
  exit /b 1
)
echo [OK] chatop-base:latest built. Now build-and-run.bat will reuse it.
