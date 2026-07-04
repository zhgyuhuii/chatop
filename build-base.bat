@echo off
REM Windows build for the fixed base image chatop-base:latest.
REM Run when base deps change / to update AI tools / on a fresh machine.
REM Optional proxy for blocked downloads (GitHub/Google/nodesource):
REM   build-base.bat                          (direct)
REM   build-base.bat http://127.0.0.1:7890    (through local proxy; Docker Desktop: http://host.docker.internal:7890)
REM ASCII-only source (avoid CMD codepage mojibake).
chcp 65001 >nul
cd /d "%~dp0"

set "PROXY=%~1"
set "PROXY_ARGS="
if not "%PROXY%"=="" (
  set "PROXY_ARGS=--build-arg HTTPS_PROXY=%PROXY% --build-arg HTTP_PROXY=%PROXY% --build-arg NO_PROXY=localhost,127.0.0.1"
  echo Using build proxy: %PROXY%
)

echo Building chatop-base:latest ... (first time downloads several GB, only once)
docker build -f Dockerfile.base --build-arg APP_USER=admin --build-arg LOGIN_USER=admin %PROXY_ARGS% -t chatop-base:latest .
if errorlevel 1 (
  echo [FAIL] chatop-base build failed
  pause
  exit /b 1
)
echo [OK] chatop-base:latest built. Now build-and-run.bat will reuse it.
