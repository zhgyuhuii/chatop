@echo off
chcp 65001 >nul
setlocal
set C=chatop
set OUT=%USERPROFILE%\chatop-diag.txt

echo chatop diagnostic report> "%OUT%"
echo container=%C%>> "%OUT%"

echo.>> "%OUT%"
echo ===== docker ps (image + ports) =====>> "%OUT%"
docker ps -a --format "{{.Names}} | {{.Image}} | {{.Status}} | {{.Ports}}">> "%OUT%" 2>&1

echo.>> "%OUT%"
echo ===== listeners + gateway processes =====>> "%OUT%"
docker exec %C% sh -c "ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null; echo === PROC ===; ps aux | grep -E 'caddy|app_manager|filebrowser' | grep -v grep">> "%OUT%" 2>&1

echo.>> "%OUT%"
echo ===== shebang CRLF check (^M at line end = CRLF/bad) =====>> "%OUT%"
docker exec %C% sh -c "for f in /usr/local/bin/start-caddy.sh /usr/local/bin/start-app-manager.sh /dockerstartup/custom_startup.sh /etc/caddy/Caddyfile; do echo --- $f ---; head -1 $f | cat -A; done">> "%OUT%" 2>&1

echo.>> "%OUT%"
echo ===== caddy.log =====>> "%OUT%"
docker exec %C% sh -c "cat /tmp/caddy.log">> "%OUT%" 2>&1

echo.>> "%OUT%"
echo ===== app-mgr.log =====>> "%OUT%"
docker exec %C% sh -c "cat /tmp/app-mgr.log">> "%OUT%" 2>&1

echo.>> "%OUT%"
echo ===== filebrowser.log (tail) =====>> "%OUT%"
docker exec %C% sh -c "tail -20 /tmp/filebrowser.log">> "%OUT%" 2>&1

echo.>> "%OUT%"
echo ===== internal curl -^> Caddy 7443 /login =====>> "%OUT%"
docker exec %C% sh -c "curl -sk --max-time 6 -D - -o /dev/null https://127.0.0.1:7443/login 2>&1 | head -12 || echo CURL-FAILED">> "%OUT%" 2>&1

echo.
echo Report written to: %OUT%
echo ------------------------------------------------------------
type "%OUT%"
echo ------------------------------------------------------------
echo Paste the whole file content back.
echo.
pause
