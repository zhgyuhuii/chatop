#!/usr/bin/env bash
set -e
export STATION_PORT="${STATION_PORT:-8787}"
export APPS_CATALOG="${APPS_CATALOG:-/etc/chatop/apps-catalog.json}"

SVC="${CHATOP_SERVICES_DIR:-$HOME/.chatop/services}"
FAC="${CHATOP_FACTORY_DIR:-/opt/chatop/factory}"

# 服务生效目录：卷内 current 有效则用，否则回退出厂 factory（缺失再退旧 /opt 兼容）
resolve() { # $1=service name  $2=fallback-opt-path
  if [ -d "$SVC/$1/current" ]; then echo "$SVC/$1/current";
  elif [ -d "$FAC/$1" ]; then echo "$FAC/$1";
  else echo "$2"; fi
}

AGENT_CFG_DIR="$(resolve agent-config /opt/agent-config)"
OPENCLAW_DIR="$(resolve openclaw-tool /opt/openclaw-tool)"
STATION_DIR="$(resolve station /opt/station/station)"

# agent-config bundle 内层是 agentconfig/；PYTHONPATH 要指其父，import 名 agentconfig
if [ -d "$AGENT_CFG_DIR/agentconfig" ]; then PYPARENT="$AGENT_CFG_DIR"; else PYPARENT="/opt/agent-config"; fi
export PYTHONPATH="${PYPARENT}${PYTHONPATH:+:$PYTHONPATH}"
export OPENCLAW_TOOL_DIR="$OPENCLAW_DIR"

if [ "${STATION_DRY_RUN:-0}" = "1" ]; then
  echo "PYTHONPATH=$PYTHONPATH"
  echo "OPENCLAW_TOOL_DIR=$OPENCLAW_TOOL_DIR"
  echo "STATION_DIR=$STATION_DIR"
  exit 0
fi

# station 源可能在卷内 current/station（bundle 内层 station/），也可能出厂 /opt/station/station
if [ -d "$STATION_DIR/station" ]; then cd "$STATION_DIR"; else cd /opt/station; fi
exec /opt/station-venv/bin/python -m station
