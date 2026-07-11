#!/bin/bash
# chatop-agent-launch <agent-id>
# 内置智能体桌面图标的双击入口：探测「是否已配置」→ 未配置先跑配置动作，已配置直接运行。
# 「已配置」判据与 station/probe/agent_probes.py 的 AGENT_SPECS.config_candidates 保持一致
# （单一真源两处实现，改判据时两边同步）。CLI 型统一走 chatop-run-cli（自带终端 + 退出留 shell）。
set -u
export DISPLAY="${DISPLAY:-:1}"
HOME="${HOME:-/home/$(id -un)}"
ID="${1:?usage: chatop-agent-launch <agent-id>}"

RUN=/usr/local/bin/chatop-run-cli
# OpenClaw 可视化配置器（tkinter，本项目 openclaw-tool）；取代原 agent-builder(HTML)
# 走 launch-config-gui.sh：它负责钉死解释器(python3.11，与 station venv / app-manager 一致)。
# 段错误根因已由 gdb 定案(9460e9d)：Tk 输入法 XIM 在无 IME 的 zh_CN 下调 XCreateIC 必崩，
# 属确定性而非偶发；修法是 GUI 内 `tk useinputmethods 0`。脚本里的重试循环只是兜底，不是防线。
OPENCLAW_CFG="bash /opt/openclaw-tool/launch-config-gui.sh"

# 已配置 = 任一候选存在（目录，或非空文件）
configured() {
  local rel p
  for rel in "$@"; do
    p="$HOME/$rel"
    if [ -d "$p" ] || { [ -f "$p" ] && [ -s "$p" ]; }; then return 0; fi
  done
  return 1
}

# 轻提示（有 zenity 才弹，4s 自动消失；无则静默，紧随其后的终端/窗口自身会说明）
notify() {
  command -v zenity >/dev/null 2>&1 && \
    ( zenity --info --timeout=4 --title="察元AI工舱" --text="$1" >/dev/null 2>&1 & )
}

# openclaw.json 存在但缺 gateway.mode（配置被写残 / onboard 未完成）会让 `openclaw gateway`
# 启动被拦(exit 78)，图标表现为"打不开"。启动前幂等补一个默认 local 模式（已有 mode 则不动）。
ensure_openclaw_gateway_mode() {
  local f="$HOME/.openclaw/openclaw.json"
  [ -f "$f" ] || return 0
  command -v python3.11 >/dev/null 2>&1 || return 0
  python3.11 - "$f" <<'PY' 2>/dev/null || true
import json,sys
p=sys.argv[1]
try:
    d=json.load(open(p,encoding="utf-8"))
except Exception:
    sys.exit(0)                       # 读不了就别动，交给配置器处理
if not isinstance(d,dict): sys.exit(0)
g=d.get("gateway")
if not isinstance(g,dict): g={}; d["gateway"]=g
if not g.get("mode"):
    g["mode"]="local"
    json.dump(d,open(p,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    print("[openclaw] 补齐 gateway.mode=local")
PY
}

case "$ID" in
  openclaw)
    if configured ".openclaw/openclaw.json" ".config/openclaw/config.json"; then
      ensure_openclaw_gateway_mode
      exec "$RUN" openclaw gateway
    else
      notify "OpenClaw 尚未配置，先打开可视化配置器（配置后再双击即启动网关）"
      exec $OPENCLAW_CFG
    fi ;;
  codex)
    if configured ".codex/auth.json" ".codex/config.toml"; then
      exec "$RUN" codex
    else
      notify "Codex 尚未登录，先执行 codex login"
      exec "$RUN" codex login
    fi ;;
  hermes)
    if configured ".hermes/config.yaml" ".hermes/config.json" ".hermes/.env"; then
      exec "$RUN" hermes
    else
      notify "Hermes 尚未配置，先执行 hermes setup"
      exec "$RUN" hermes setup
    fi ;;
  claude-code)
    # claude CLI 首启自带登录引导；配置与否命令一致，无需分支
    configured ".claude.json" ".claude/settings.json" || notify "Claude Code 首次启动将引导登录"
    exec "$RUN" claude ;;
  rtk)      exec "$RUN" rtk --help ;; # 命令包装器(rtk git/ls/read...)，无默认动作：先列命令(exit 0)再留 shell 供 rtk <cmd>
  tokscale) exec "$RUN" tokscale ;;   # 交互 TUI，直接跑
  openclaw-config)
    exec $OPENCLAW_CFG ;;   # 直接打开 OpenClaw 可视化配置器
  openhuman)
    exec "$HOME/Applications/openhuman/squashfs-root/AppRun" ;;
  *)
    echo "chatop-agent-launch: 未知智能体 '$ID'" >&2; exit 2 ;;
esac
