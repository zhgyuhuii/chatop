#!/bin/bash
# OpenClaw 网关开机自启脚本（可选）
# 从 ~/.openclaw/openclaw.json 读取端口，先加载 nvm 再启动 openclaw gateway

CONFIG="${HOME}/.openclaw/openclaw.json"
LOG="${LOG:-/tmp/openclaw-gateway.log}"
PORT=18789

if [ -r "$CONFIG" ]; then
    PORT=$(python3 -c "
import json
try:
    with open('$CONFIG') as f:
        p = json.load(f).get('gateway') or {}
    print(int(p.get('port', 18789)))
except Exception:
    print(18789)
" 2>/dev/null || echo 18789)
fi

# 若在图形会话中由 autostart 启动，稍等再启动，避免与桌面竞争
[ -n "${XDG_CURRENT_DESKTOP:-}" ] && sleep 5

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

# 若已在监听，说明网关已运行
if ss -tlnp 2>/dev/null | grep -q ":$PORT "; then
    log "端口 $PORT 已在监听，OpenClaw 网关可能已运行，跳过"
    exit 0
fi

NVM_SH="${NVM_DIR:-$HOME/.nvm}/nvm.sh"
if [ -s "$NVM_SH" ]; then
    . "$NVM_SH"
fi

log "启动 OpenClaw 网关 (port=$PORT)..."
exec openclaw gateway --port "$PORT" >>"$LOG" 2>&1
