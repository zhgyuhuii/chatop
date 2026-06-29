#!/bin/bash
# 调通端口 1080、4901、5901：确保有进程监听并可选做连通性测试
set -e

PORTS="1080 4901 5901"
PYTHON_LISTENERS="1080 5901"

log() { echo "[$(date +%H:%M:%S)] $*"; }

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
# 保持主线程不退出
import time
while True: time.sleep(3600)
PY
}

# 后台启动 1080、5901 的监听（若尚未监听）
for port in $PYTHON_LISTENERS; do
    if ss -tlnp 2>/dev/null | grep -q ":$port "; then
        log "端口 $port 已被占用且正在监听，跳过"
    else
        ( start_tcp_listener "$port" ) &
        sleep 2
    fi
done

# 确认 4901
check_4901 || true

# 等待一下再检测
sleep 2
log "--- 端口状态 ---"
for port in $PORTS; do
    if ss -tlnp 2>/dev/null | grep -q ":$port "; then
        log "端口 $port: 正在监听"
    else
        log "端口 $port: 未监听"
    fi
done

log "完成。1080/5901 若由本脚本启动，会在当前 shell 后台运行；关闭终端会结束。"
