#!/bin/bash
# chatop-preinstall.sh —— 构建期以 admin 身份把核心工具装进 /home/admin。
# 装完后 Dockerfile 会把整棵 home 迁到 /opt/chatop-seed-home，运行时由 chatop-seed-home.sh
# 播种回卷。构建路径=运行路径(/home/admin)，保证工具内任何硬编码绝对路径运行时仍有效。
set -e
export HOME="${HOME:-/home/admin}"
export NPM_CONFIG_PREFIX="$HOME/.npm-global"
export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
mkdir -p "$HOME/.npm-global" "$HOME/.local/bin" "$HOME/Applications" "$HOME/Desktop"

echo "==== [preinstall] npm CLI: openclaw / codex / claude-code / tokscale ===="
npm i -g openclaw@latest @openai/codex @anthropic-ai/claude-code tokscale

echo "==== [preinstall] RTK (静态 musl 二进制) ===="
RTK_TAG="$(curl -fsSL https://api.github.com/repos/rtk-ai/rtk/releases/latest | awk -F'"' '/tag_name/{print $4; exit}')"
[ -n "$RTK_TAG" ] || { echo "RTK tag 解析失败"; exit 1; }
curl -fsSL "https://github.com/rtk-ai/rtk/releases/download/${RTK_TAG}/rtk-x86_64-unknown-linux-musl.tar.gz" -o /tmp/rtk.tgz
tar -xzf /tmp/rtk.tgz -C /tmp
install -m755 "$(find /tmp -maxdepth 3 -name rtk -type f | head -1)" "$HOME/.local/bin/rtk"
rm -rf /tmp/rtk.tgz
"$HOME/.local/bin/rtk" --version || true

echo "==== [preinstall] openclaw-agent-builder (单文件 HTML 配置器) ===="
mkdir -p "$HOME/Applications/agent-builder"
curl -fsSL -o "$HOME/Applications/agent-builder/index.html" \
  https://raw.githubusercontent.com/nathancarlton/openclaw-agent-builder/main/index.html
test -s "$HOME/Applications/agent-builder/index.html"

# 桌面图标：agent-builder(Chrome 打开本地 HTML) + tokscale(终端 TUI 监控)
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/chatop-agent-builder.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=OpenClaw 配置器
Comment=openclaw-agent-builder 可视化配置
Exec=/usr/local/bin/google-chrome --app=file://$HOME/Applications/agent-builder/index.html
Icon=preferences-system
Categories=Development;
Terminal=false
EOF
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
cp -f "$HOME/.local/share/applications/chatop-agent-builder.desktop" \
      "$HOME/.local/share/applications/chatop-tokscale.desktop" "$HOME/Desktop/" 2>/dev/null || true

# 注：Hermes(uv+py3.11+自带 Node，重量级) 与 OpenHuman(AppImage) 暂不预装进镜像——
# 宿主磁盘紧张(其它项目卷占满 /var/lib/docker)，烤进去需数 GB 瞬时空间。两者已在应用市场
# 作一键安装(catalog 的 hermes / openhuman，安装命令均已核实可用)。待磁盘释放后可加回本脚本。

echo "==== [preinstall] 已装命令自检 ===="
ls -l "$HOME/.npm-global/bin/" | grep -E 'openclaw|codex|claude|tokscale' || true
ls -l "$HOME/.local/bin/rtk" 2>/dev/null || echo "rtk MISSING"
echo "==== [preinstall] 完成 ===="
