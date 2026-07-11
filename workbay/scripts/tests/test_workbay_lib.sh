#!/usr/bin/env bash
# 纯逻辑单测：不依赖真 docker / 真 ss，用函数覆盖注入假端口数据。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
source "$ROOT/scripts/_workbay-lib.sh"

fail=0
assert_eq() { if [ "$2" = "$3" ]; then echo "ok   - $1"; else echo "FAIL - $1: expected [$2] got [$3]"; fail=1; fi; }
assert_ok() { if "${@:2}"; then echo "ok   - $1"; else echo "FAIL - $1 (expected success)"; fail=1; fi; }
assert_no() { if "${@:2}"; then echo "FAIL - $1 (expected failure)"; fail=1; else echo "ok   - $1"; fi; }

# 用户名校验
assert_ok "valid: alice"        wb_valid_username alice
assert_ok "valid: a-b_1"        wb_valid_username a-b_1
assert_no "invalid: empty"      wb_valid_username ""
assert_no "invalid: UpperCase"  wb_valid_username Alice
assert_no "invalid: has space"  wb_valid_username "a b"
assert_no "invalid: slash"      wb_valid_username "a/b"
assert_no "invalid: leading -"  wb_valid_username "-a"

# docker 端口解析：只取宿主发布端口，不误提取 IP 里的 0
_docker_ps_ports_raw() { printf '0.0.0.0:6901->7443/tcp, :::6901->7443/tcp\n'; }
assert_eq  "docker parse: only 6901"  6901 "$(_docker_published_ports)"
_docker_parse_no_zero() { ! _docker_published_ports | grep -qx 0; }
assert_ok  "docker parse: no port 0"  _docker_parse_no_zero

# 端口探测：6901,6902 被占，期望从 6901 起找到 6903
_host_listen_ports() { printf '6901\n'; }
_docker_published_ports() { printf '6902\n'; }
assert_ok  "6901 in use" wb_port_in_use 6901
assert_ok  "6902 in use" wb_port_in_use 6902
assert_no  "6903 free"   wb_port_in_use 6903
assert_eq  "find_free_port from 6901 -> 6903" 6903 "$(wb_find_free_port 6901)"

# 回归：set -o pipefail 下端口探测必须仍正确（历史 bug：grep -q 早退 SIGPIPE 被 pipefail 误判失败）
( set -o pipefail
  wb_port_in_use 6901 ) && echo "ok   - pipefail: 6901 still in use" || { echo "FAIL - pipefail: 6901 漏判为空闲"; fail=1; }
assert_eq  "pipefail: find_free_port -> 6903" 6903 "$( set -o pipefail; wb_find_free_port 6901 )"

# compose 渲染：__USER__/__HOME__ 被替换、无残留占位；镜像/端口留给 .env 插值（模板里是 ${...}）
tmpl="$(mktemp)"; out="$(mktemp)"
cat > "$tmpl" <<'EOF'
name: chatop-__USER__
services:
  workbay:
    image: ${CHATOP_IMAGE:?}
    container_name: chatop-__USER__
    ports: ["${PORT:?}:7443"]
    volumes: ["__HOME__:/home/admin"]
EOF
wb_render_compose "$tmpl" alice /data/workbays/alice/home "$out"
assert_ok "render: has project name"   grep -q "name: chatop-alice" "$out"
assert_ok "render: has container name"  grep -q "container_name: chatop-alice" "$out"
assert_ok "render: home mount fixed"    grep -q "/data/workbays/alice/home:/home/admin" "$out"
assert_no "render: no leftover __X__"   grep -q "__" "$out"
assert_ok "render: keeps env interp"    grep -q 'image: ${CHATOP_IMAGE' "$out"
rm -f "$tmpl" "$out"

# 密码转义/还原往返：含 $ 空格 反引号 单双引号的密码必须逐字保住
PW_HARD='p@ss$word 123`x"y'"'"'z'
esc="$(wb_esc_pw "$PW_HARD")"
assert_ok  "esc: \$ -> \$\$"          grep -q 'p@ss[$][$]word' <<<"$esc"
assert_eq  "esc/unesc roundtrip"      "$PW_HARD" "$(wb_unesc_pw "$esc")"

# wb_write_env + wb_env_get：写含特殊字符密码，安全读回并还原
envf="$(mktemp)"
wb_write_env "$envf" cmdbird/chatop:latest 6905 bob "$PW_HARD"
assert_eq  "env_get CHATOP_IMAGE"     cmdbird/chatop:latest "$(wb_env_get CHATOP_IMAGE "$envf")"
assert_eq  "env_get PORT"             6905  "$(wb_env_get PORT "$envf")"
assert_eq  "env_get LOGIN_USER"       bob   "$(wb_env_get LOGIN_USER "$envf")"
assert_eq  "env PASSWORD stored esc"  "$(wb_esc_pw "$PW_HARD")" "$(wb_env_get PASSWORD "$envf")"
assert_eq  "env PASSWORD recovered"   "$PW_HARD" "$(wb_unesc_pw "$(wb_env_get PASSWORD "$envf")")"
assert_no  "env: no bare \$ in pw"    grep -qE 'PASSWORD=.*[^$][$][^$]' "$envf"
rm -f "$envf"

exit $fail
