#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$(mktemp -d)"; INBOX="$(mktemp -d)"
echo "payload" > "$SRC/station-1.7.0.tar.gz"
echo '{"name":"station","version":"1.7.0"}' > "$SRC/station-1.7.0.json"
export CHATOP_UPDATER_INBOX="$INBOX" CHATOP_BUNDLE_BASE="file://$SRC"
bash "$ROOT/app-manager/chatop-fetch-bundle.sh" station 1.7.0
test -f "$INBOX/station-1.7.0.tar.gz" && test -f "$INBOX/station-1.7.0.json" || { echo FAIL; exit 1; }
echo "PASS"
