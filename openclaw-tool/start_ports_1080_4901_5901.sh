#!/bin/bash
# 调通端口 1080、4901、5901：开机或手动运行时确保有进程监听
# 位置：/openclaw-tool/start_ports_1080_4901_5901.sh
# 注意：5901 为 VNC 端口，不在此脚本中占位；若需传统 VNC 客户端连接，请安装 x11vnc 或使用浏览器连接 6901 (noVNC)
set -e

# 若从图形会话自启，稍等再检测端口，避免与系统服务竞争
[ -n "$XDG_CURRENT_DESKTOP" ] && sleep 3

PORTS="1080 4901 5901"
PYTHON_LISTENERS="1080"
LOG="${LOG:-/tmp/ports-1080-4901-5901.log}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

# 检查 4901 是否已在监听（kasm_audio_out）
check_4901() {
    if ss -tlnp 2>/dev/null | grep -q ':4901 '; then
        log "4901 已在监听 (kasm_audio_out)，无需启动"
        return 0
    fi
    log "4901 未监听，请检查 Kasm 音频服务是否正常"
    return 1
}

# 用 Python 在指定端口启动简单 TCP 监听（仅接受连接，便于“调通”端口）
start_tcp_listener() {
    local port=$1
    if ss -tlnp 2>/dev/null | grep -q ":$port "; then
        log "端口 $port 已在监听，跳过"
        return 0
    fi
    log "在端口 $port 启动 TCP 监听..."
    python3 - <<PY
import socket
import threading
import sys
def serve(sock):
    while True:
        try:
            c, _ = sock.accept()
            c.close()
        except Exception:
            break
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('0.0.0.0', $port))
s.listen(5)
t = threading.Thread(target=serve, args=(s,), daemon=True)
t.start()
print("Listening on 0.0.0.0:$port", flush=True)
sys.stdout.flush()
import time
while True: time.sleep(3600)
PY
}

for port in $PYTHON_LISTENERS; do
    if ss -tlnp 2>/dev/null | grep -q ":$port "; then
        log "端口 $port 已被占用且正在监听，跳过"
    else
        ( start_tcp_listener "$port" ) &
        sleep 2
    fi
done

# 5901：若已安装 x11vnc 且 5901 未被占用，则启动 x11vnc 供传统 VNC 客户端连接
if command -v x11vnc >/dev/null 2>&1; then
    if ! ss -tlnp 2>/dev/null | grep -q ':5901 '; then
        log "在 5901 启动 x11vnc（共享当前桌面）..."
        x11vnc -display :1 -rfbport 5901 -forever -shared -bg -o /tmp/x11vnc-5901.log 2>/dev/null || true
        sleep 1
    else
        log "5901 已在监听，跳过 x11vnc"
    fi
else
    log "5901 未监听（未安装 x11vnc）。请用浏览器连接端口 6901 使用 noVNC，或安装: sudo apt-get install x11vnc"
fi

check_4901 || true
sleep 2
log "--- 端口状态 ---"
for port in $PORTS; do
    if ss -tlnp 2>/dev/null | grep -q ":$port "; then
        log "端口 $port: 正在监听"
    else
        log "端口 $port: 未监听"
    fi
done
log "完成。1080 监听进程已在后台运行；5901 为 VNC（x11vnc 或 noVNC:6901）。"
# 保持脚本不退出，避免子进程收到 SIGHUP
wait
