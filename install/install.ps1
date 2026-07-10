# chatop one-click installer (Windows / PowerShell)
#
#   irm https://<your-domain>/install.ps1 | iex
#   # or non-interactive with env vars:
#   $env:CHATOP_IMAGE="youruser/chatop-ai:latest"; $env:CHATOP_USER="admin"; $env:CHATOP_PASSWORD="xxxx"
#   irm https://<your-domain>/install.ps1 | iex
#
# Steps: check/install Docker Desktop -> set username/password -> generate compose -> pull image -> up -> open browser.
# Source is 100% ASCII on purpose (PS 5.1 mis-decodes non-ASCII .ps1 under a CJK codepage).

chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$ErrorActionPreference = "Stop"

# ---- config (override via env) ----
$IMAGE = if ($env:CHATOP_IMAGE) { $env:CHATOP_IMAGE } else { "chatopai/chatop-ai:latest" }  # TODO: your Docker Hub / GHCR image
$PORT  = if ($env:CHATOP_PORT)  { $env:CHATOP_PORT }  else { "6901" }
$DIR   = if ($env:CHATOP_DIR)   { $env:CHATOP_DIR }   else { Join-Path $env:USERPROFILE ".chatop" }
$USER  = $env:CHATOP_USER
$PW    = $env:CHATOP_PASSWORD

function Info($m){ Write-Host "[chatop] $m" -ForegroundColor Cyan }
function Ok($m){   Write-Host "[OK] $m"     -ForegroundColor Green }
function Warn($m){ Write-Host "[!] $m"      -ForegroundColor Yellow }
function Die($m){  Write-Host "[ERR] $m"    -ForegroundColor Red; exit 1 }

function Test-Cmd($name){ return [bool](Get-Command $name -ErrorAction SilentlyContinue) }

# ---- 1) Docker ----
function Ensure-Docker {
  if (Test-Cmd docker) { Ok ("docker found: " + (docker --version)); return }
  Warn "Docker Desktop not found."
  if (Test-Cmd winget) {
    Info "Installing Docker Desktop via winget (may require reboot for WSL2)..."
    try {
      winget install -e --id Docker.DockerDesktop --accept-source-agreements --accept-package-agreements
    } catch { Warn "winget install returned an error; continuing to check for docker." }
  } elseif (Test-Cmd choco) {
    Info "Installing Docker Desktop via Chocolatey..."
    try { choco install docker-desktop -y } catch { Warn "choco install failed; continuing." }
  } else {
    Info "Opening the Docker Desktop download page..."
    Start-Process "https://www.docker.com/products/docker-desktop"
    Die "Please install Docker Desktop (needs WSL2), start it, then re-run this script."
  }
  if (-not (Test-Cmd docker)) {
    Start-Process "https://www.docker.com/products/docker-desktop"
    Die "Docker Desktop installed but 'docker' is not on PATH yet. A sign-out/reboot may be needed. Re-run after Docker Desktop is running."
  }
}

function Ensure-Daemon {
  # Docker Desktop app path (best-effort launch)
  $dd = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
  for ($i=0; $i -lt 60; $i++) {
    try { docker info *> $null; if ($LASTEXITCODE -eq 0) { Ok "docker daemon is ready"; return } } catch {}
    if ($i -eq 0) { Info "Waiting for Docker Desktop to start (first run can take 1-2 min)..."; if (Test-Path $dd) { Start-Process $dd } }
    Start-Sleep -Seconds 3
  }
  Die "Docker daemon not ready. Make sure Docker Desktop is running (WSL2 backend), then re-run."
}

function Ensure-Compose {
  try { docker compose version *> $null; if ($LASTEXITCODE -eq 0) { Ok "docker compose ready"; return } } catch {}
  Die "docker compose (v2) plugin missing. Update Docker Desktop."
}

# ---- 2) credentials ----
function New-Password {
  -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 16 | ForEach-Object { [char]$_ })
}

function Collect-Credentials {
  if (-not $script:USER -and -not $script:PW -and (Test-Path (Join-Path $DIR ".env"))) {
    Info "Reusing existing config at $DIR\.env"; $script:REUSE = $true; return
  }
  if (-not $script:USER) {
    $u = Read-Host "Set login username [admin]"
    $script:USER = if ([string]::IsNullOrWhiteSpace($u)) { "admin" } else { $u }
  }
  if (-not $script:PW) {
    $sec = Read-Host "Set login password (empty = auto-generate)" -AsSecureString
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
    if ([string]::IsNullOrEmpty($plain)) { $script:PW = New-Password; Info "Generated password: $script:PW" }
    else { $script:PW = $plain }
  }
}

# ---- 3) config files ----
function Write-Config {
  if ($script:REUSE) { return }
  New-Item -ItemType Directory -Force -Path $DIR | Out-Null
  # compose interpolates .env values: a '$' in the password would eat the next token.
  # Escape '$' -> '$$'; compose restores the literal '$'.
  $pwEsc = $PW -replace '\$', '$$$$'
  @"
LOGIN_USER=$USER
PASSWORD=$pwEsc
PORT=$PORT
CHATOP_IMAGE=$IMAGE
"@ | Set-Content -Path (Join-Path $DIR ".env") -Encoding utf8
  @'
name: chatop-ai
services:
  chatop-ai:
    image: ${CHATOP_IMAGE}
    container_name: chatop-ai
    pull_policy: always
    environment:
      - VNC_PW=${PASSWORD:?}
      - LOGIN_USER=${LOGIN_USER:-admin}
      - FILES_PW=${PASSWORD:?}
    ports:
      - "${PORT:-6901}:7443"
    shm_size: "1gb"
    volumes:
      - chatop-home:/home/${LOGIN_USER:-admin}
    restart: unless-stopped
volumes:
  chatop-home:
'@ | Set-Content -Path (Join-Path $DIR "docker-compose.yml") -Encoding utf8
  Ok "Config written to $DIR"
}

# ---- 4) pull + up ----
function Start-Chatop {
  Info "Pulling image $IMAGE (first pull is large)..."
  Push-Location $DIR
  try {
    docker compose pull
    if ($LASTEXITCODE -ne 0) { Die "Image pull failed. Check CHATOP_IMAGE=$IMAGE is reachable." }
    Info "Starting chatop..."
    docker compose up -d
    if ($LASTEXITCODE -ne 0) { Die "Start failed." }
  } finally { Pop-Location }
  Ok "Container started"
}

# ---- 5) wait + open browser ----
function Open-Browser {
  $url = "https://localhost:$PORT"
  Info "Waiting for the service to be ready..."
  for ($i=0; $i -lt 40; $i++) {
    try { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 -SkipCertificateCheck *> $null; break } catch { Start-Sleep -Seconds 2 }
  }
  Ok "chatop is ready: $url"
  Start-Process $url
}

Info "chatop one-click installer (Windows)"
Ensure-Docker
Ensure-Daemon
Ensure-Compose
Collect-Credentials
Write-Config
Start-Chatop
Open-Browser
Write-Host ""
Ok "Done!"
Write-Host "  URL:      https://localhost:$PORT  (self-signed cert; accept the browser warning)"
Write-Host "  Username: $USER"
Write-Host "  Password: $PW"
Write-Host "  Config:   $DIR  (docker compose down to stop, up -d to restart)"
