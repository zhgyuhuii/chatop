#!/usr/bin/env bash
# 后台启动 Ollama 服务；若已在运行则仅提示
if command -v ollama >/dev/null 2>&1; then
  if pgrep -x ollama >/dev/null 2>&1; then
    notify-send "Ollama" "Ollama 已在运行。" 2>/dev/null || true
    exit 0
  fi
  nohup ollama serve >/dev/null 2>&1 &
  sleep 1
  if pgrep -x ollama >/dev/null 2>&1; then
    notify-send "Ollama" "Ollama 已启动。" 2>/dev/null || true
  else
    notify-send "Ollama" "启动失败，请检查终端。" 2>/dev/null || true
  fi
else
  notify-send "Ollama" "未找到 ollama 命令，请先安装 Ollama。" 2>/dev/null || true
  exit 1
fi
