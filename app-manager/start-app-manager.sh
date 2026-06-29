#!/usr/bin/env bash
set -e
export APPS_CATALOG="${APPS_CATALOG:-/etc/chatop/apps-catalog.json}"
export APPS_PORT="${APPS_PORT:-8686}"
exec python3 /usr/local/lib/chatop/app_manager.py
