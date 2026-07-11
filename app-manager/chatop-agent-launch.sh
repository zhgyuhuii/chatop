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

# openclaw.json 配置不全/写坏会让 `openclaw gateway` 启动被拦(exit 78 或 config invalid)，
# 图标表现为"打不开"。启动前幂等自愈三类坑（生产 2026-07-11 逐个踩过）：
#  1) 缺 gateway.mode → openclaw 强制要求 gateway.mode=local 才放行。
#  2) 缺 gateway.bind → 容器里 openclaw 默认 bind=auto(0.0.0.0)，绑 0.0.0.0 又没设 token/password
#     → 拒启("Refusing to bind gateway to auto without auth")。单用户云桌面 gateway 只被容器内
#     本地访问，绑 loopback 最安全、回环免 auth。
#  3) 配置里混入伪通道(bluebubbles 等)/空桩通道(twitch={})/未配全的 web 搜索(provider=perplexity
#     未装插件) → openclaw 校验失败、整份配置非法、网关拒启。复用 openclaw-tool 的 catalog 消毒器
#     （单一真源，与配置器保存路径同一判据），把这些「从未配过」的残留删掉；绝不动用户已填实质字段的。
# 已有值则不动，尊重用户/配置器已写的真配置。这是防线：不管配置被谁写坏，双击图标即自愈能启。
ensure_openclaw_gateway_config() {
  local f="$HOME/.openclaw/openclaw.json"
  [ -f "$f" ] || return 0
  command -v python3.11 >/dev/null 2>&1 || return 0
  python3.11 - "$f" <<'PY' 2>/dev/null || true
import json,sys
sys.path.insert(0, "/opt/openclaw-tool")
p=sys.argv[1]
try:
    d=json.load(open(p,encoding="utf-8"))
except Exception:
    sys.exit(0)                       # 读不了就别动，交给配置器处理
if not isinstance(d,dict): sys.exit(0)
changed=[]
g=d.get("gateway")
if not isinstance(g,dict): g={}; d["gateway"]=g
if not g.get("mode"): g["mode"]="local"; changed.append("gateway.mode=local")
if not g.get("bind"): g["bind"]="loopback"; changed.append("gateway.bind=loopback")
try:                                  # 综合消毒（伪通道/空桩/未配全 web 搜索）
    from openclaw_catalog import sanitize_config_for_gateway
    d, removed = sanitize_config_for_gateway(d)
    changed += ["删 "+r for r in removed]
except Exception:
    pass                              # 消毒器不可用就只做上面的 gateway 兜底，不阻断启动
if changed:
    json.dump(d,open(p,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    print("[openclaw] 配置自愈: "+", ".join(changed))
PY
}

case "$ID" in
  openclaw)
    if configured ".openclaw/openclaw.json" ".config/openclaw/config.json"; then
      ensure_openclaw_gateway_config
      # --bind loopback 双保险：即便配置补齐失败/被用户改乱，也不让它在容器里退回 auth-less 的 auto
      exec "$RUN" openclaw gateway --bind loopback
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
