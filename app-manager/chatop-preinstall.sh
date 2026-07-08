#!/bin/bash
# chatop-preinstall.sh —— 构建期以 admin 身份把核心工具装进 /home/admin。
# 装完后 Dockerfile 会把整棵 home 迁到 /opt/chatop-seed-home，运行时由 chatop-seed-home.sh
# 播种回卷。构建路径=运行路径(/home/admin)，保证工具内任何硬编码绝对路径运行时仍有效。
set -e
export HOME="${HOME:-/home/admin}"
export NPM_CONFIG_PREFIX="$HOME/.npm-global"
export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
mkdir -p "$HOME/.npm-global" "$HOME/.local/bin" "$HOME/Applications" "$HOME/Desktop"

# GitHub 下载：直连被墙时依次回退加速镜像（GH_MIRRORS 置空可禁用，走代理时无需镜像）。
GH_MIRRORS="${GH_MIRRORS-https://ghfast.top/ https://gh-proxy.com/}"
gh_fetch() { # gh_fetch <url> <output>
  local url="$1" out="$2" prefix
  for prefix in "" $GH_MIRRORS; do
    if curl -fL --retry 2 --retry-delay 3 --retry-all-errors --connect-timeout 20 -sS -o "$out" "${prefix}${url}"; then
      return 0
    fi
    echo "[WARN] gh_fetch via [${prefix:-direct}] failed: $url"
  done
  return 1
}

echo "==== [preinstall] npm CLI: openclaw / codex / claude-code / tokscale ===="
# 国内直连 registry.npmjs.org 常超时：直连失败自动回退 npmmirror
npm i -g openclaw@latest @openai/codex @anthropic-ai/claude-code tokscale || \
  npm i -g --registry=https://registry.npmmirror.com \
    openclaw@latest @openai/codex @anthropic-ai/claude-code tokscale

echo "==== [preinstall] RTK (静态 musl 二进制) ===="
# latest/download 直链：免 api.github.com 查 tag（匿名限流 60/h + 被墙双雷），已实测有效
gh_fetch "https://github.com/rtk-ai/rtk/releases/latest/download/rtk-x86_64-unknown-linux-musl.tar.gz" /tmp/rtk.tgz \
  || { echo "RTK 下载失败(直连+全部镜像)"; exit 1; }
tar -xzf /tmp/rtk.tgz -C /tmp
install -m755 "$(find /tmp -maxdepth 3 -name rtk -type f | head -1)" "$HOME/.local/bin/rtk"
rm -rf /tmp/rtk.tgz
"$HOME/.local/bin/rtk" --version || true

# OpenClaw 配置改用本项目 openclaw-tool（tkinter 可视化配置器，镜像内 /opt/openclaw-tool，
# 桌面图标与智能启动在 Dockerfile 产品层生成）；原 agent-builder(HTML) 已移除。

# 桌面图标：tokscale(终端 TUI 监控)
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/chatop-tokscale.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Token 监控 (tokscale)
Comment=跨 AI 编码工具的 token / 成本监控
Exec=/usr/local/bin/chatop-run-cli tokscale
Icon=utilities-system-monitor
Categories=Development;System;
Terminal=false
EOF
cp -f "$HOME/.local/share/applications/chatop-tokscale.desktop" "$HOME/Desktop/" 2>/dev/null || true

# === Hermes 预装（uv+py3.11，--skip-setup），PREINSTALL_HEAVY=0 可跳过（磁盘/网络受限时） ===
if [ "${PREINSTALL_HEAVY:-1}" = "1" ]; then
  echo "==== [preinstall] Hermes Agent (uv+py3.11 安装器, --skip-setup) ===="
  ok=""
  for i in 1 2 3; do
    if curl -fsSL --connect-timeout 20 https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-setup; then
      ok=1; break
    fi
    echo "[WARN] hermes install attempt $i failed"; sleep 3
  done
  [ -n "$ok" ] || { echo "Hermes 预装失败(3 次)。网络受限可 PREINSTALL_HEAVY=0 跳过后走应用市场安装"; exit 1; }
  command -v hermes >/dev/null || export PATH="$HOME/.local/bin:$PATH"
else
  echo "==== [preinstall] PREINSTALL_HEAVY=0：跳过 Hermes（可从应用市场一键安装） ===="
fi

# === OpenHuman 独立门控，默认不预装（解包后 ~1.3GB；PREINSTALL_OPENHUMAN=1 才烤进镜像） ===
# WPS 从不预装（proot-apps 市场应用）；OpenHuman 默认也改为市场按需装，控制镜像体积。
if [ "${PREINSTALL_OPENHUMAN:-0}" = "1" ]; then
  echo "==== [preinstall] OpenHuman (AppImage 解包到 ~/Applications) ===="
  OH_URL="https://github.com/tinyhumansai/openhuman/releases/download/v0.58.0/OpenHuman_0.58.0_amd64.AppImage"
  oh_ok=""
  for prefix in "" $GH_MIRRORS; do
    if bash /usr/local/lib/chatop/gui-install.sh openhuman "${prefix}${OH_URL}" 'OpenHuman'; then
      oh_ok=1; break
    fi
    echo "[WARN] openhuman install via [${prefix:-direct}] failed"
  done
  [ -n "$oh_ok" ] || { echo "OpenHuman 预装失败(直连+镜像)。可 PREINSTALL_OPENHUMAN=0 跳过后走应用市场安装"; exit 1; }
else
  echo "==== [preinstall] PREINSTALL_OPENHUMAN=0：跳过 OpenHuman（可从应用市场一键安装） ===="
fi

echo "==== [preinstall] 清理构建缓存(只删下载/构建/浏览器缓存，不动任何工具本体) ===="
# 这些都是可再生的下载/构建缓存，跟着 home 迁进镜像会白白撑大预装层。工具二进制/venv 不受影响。
# 实测大头：.cache/ms-playwright(~646MB，某 npm 包 postinstall 拉的 Playwright 浏览器) + node-gyp。
npm cache clean --force >/dev/null 2>&1 || true
rm -rf "$HOME/.npm/_cacache" "$HOME/.npm/_logs" \
       "$HOME/.cache/uv" "$HOME/.cache/pip" "$HOME/.cache/node" \
       "$HOME/.cache/ms-playwright" "$HOME/.cache/node-gyp" \
       "$HOME/.cache/yarn" "$HOME/.cache/Cypress" 2>/dev/null || true

echo "==== [preinstall] 已装命令自检 ===="
ls -l "$HOME/.npm-global/bin/" | grep -E 'openclaw|codex|claude|tokscale' || true
ls -l "$HOME/.local/bin/rtk" 2>/dev/null || echo "rtk MISSING"
if [ "${PREINSTALL_HEAVY:-1}" = "1" ]; then
  command -v hermes >/dev/null && echo "hermes OK" || echo "hermes MISSING"
fi
[ "${PREINSTALL_OPENHUMAN:-0}" = "1" ] && { test -d "$HOME/Applications/openhuman/squashfs-root" && echo "openhuman OK" || echo "openhuman MISSING"; }
echo "==== [preinstall] 完成 ===="
