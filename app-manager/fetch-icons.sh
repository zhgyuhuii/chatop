#!/usr/bin/env bash
# 网络放开 / URL 核实后，用各应用官方 logo 覆盖占位图标（icons/<name>）。
# 仅作应用商店式标识展示用途。下载失败则保留 make_icons 生成的占位，不影响 UI。
# 注意：下列 URL 需按各项目官方页面核实；部分域名在当前构建环境 DNS 受限。
set -u
cd "$(dirname "$0")/icons"
declare -A SRC=(
  [continue.png]="https://raw.githubusercontent.com/continuedev/continue/main/media/icon.png"
  [cline.png]="https://raw.githubusercontent.com/cline/cline/main/assets/icons/icon.png"
  [claude-code.png]="https://www.anthropic.com/favicon.ico"
  [codex.png]="https://openai.com/favicon.ico"
  [opencode.png]="https://raw.githubusercontent.com/sst/opencode/dev/packages/web/src/assets/logo-ornate-dark.svg"
  [qwen.png]="https://raw.githubusercontent.com/QwenLM/Qwen/main/assets/logo.png"
  [aider.png]="https://aider.chat/assets/icons/favicon-32x32.png"
  [hermes.png]="https://avatars.githubusercontent.com/NousResearch"
)
for f in "${!SRC[@]}"; do
  echo -n "fetch $f ... "
  if curl -fsSL --max-time 15 -o "${f}.tmp" "${SRC[$f]}" && [ -s "${f}.tmp" ]; then
    mv "${f}.tmp" "$f"; echo "OK（已覆盖占位）"
  else
    rm -f "${f}.tmp"; echo "FAIL（保留占位）"
  fi
done
echo "完成。未列出的（openclaw/reasonix/mimo/nanobot 等）暂无稳定官方 logo 源，保留占位。"
