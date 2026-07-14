#!/usr/bin/env bash
# 用法: build-bundle.sh <name> <version> <hmac_key_hex> <out_dir>
# 从仓库源打一个服务 bundle(.tar.gz) + manifest(.json)，不走 Docker。
set -euo pipefail
NAME="$1"; VER="$2"; KEY_HEX="$3"; OUT="$4"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$OUT"

# 各服务的源目录 → bundle 内布局
case "$NAME" in
  station)       SRC="$ROOT/station/station"; ARC="station" ;;
  agent-config)  SRC="$ROOT/agent-config/agentconfig"; ARC="agentconfig" ;;
  openclaw-tool) SRC="$ROOT/openclaw-tool"; ARC="." ;;
  dashboard-web) SRC="$ROOT/dashboard-web/dist"; ARC="dist" ;;
  *) echo "unknown service: $NAME" >&2; exit 2 ;;
esac
[ -d "$SRC" ] || { echo "source not found: $SRC" >&2; exit 2; }

TAR="$OUT/${NAME}-${VER}.tar.gz"
if [ "$ARC" = "." ]; then
  tar -C "$SRC" -czf "$TAR" .
else
  tar -C "$(dirname "$SRC")" -czf "$TAR" "$(basename "$SRC")"
fi

SHA="$(sha256sum "$TAR" | cut -d' ' -f1)"
SIG="$(python3.11 -c "import hmac,hashlib,sys;print(hmac.new(bytes.fromhex(sys.argv[1]),sys.argv[2].encode(),hashlib.sha256).hexdigest())" "$KEY_HEX" "$SHA")"
cat > "$OUT/${NAME}-${VER}.json" <<EOF
{"name":"$NAME","version":"$VER","sha256":"$SHA","sig":"$SIG","min_base":"1.5.0","needs_venv":false}
EOF
echo "built $TAR"
