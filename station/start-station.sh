#!/usr/bin/env bash
set -e
export STATION_PORT="${STATION_PORT:-8787}"
export APPS_CATALOG="${APPS_CATALOG:-/etc/chatop/apps-catalog.json}"
# 智能体配置中心引擎（纯 stdlib，随镜像 COPY 到 /opt/agent-config）与其复用的
# openclaw-tool 纯模块路径。缺失时 agentcfg 路由自动降级为 503，不影响大屏。
export PYTHONPATH="/opt/agent-config${PYTHONPATH:+:$PYTHONPATH}"
export OPENCLAW_TOOL_DIR="${OPENCLAW_TOOL_DIR:-/opt/openclaw-tool}"
cd /opt/station
exec /opt/station-venv/bin/python -m station
