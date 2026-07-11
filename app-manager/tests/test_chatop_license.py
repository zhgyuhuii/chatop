"""序列号激活的测试。

金标向量由 website 的真实 JS（server/license/shortcode.js）签出，再由本文件的
Python 实现验证 —— 跨语言字节兼容是这套东西的唯一正确性锚点。

测试密钥不是生产密钥。生产密钥只在构建时以 --build-arg 注入，不入库。
"""
import hashlib
import hmac
import json
import os
import sys
import threading
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chatop_license import base32, codec, gate, machine, shortcode, store

# ── 跨语言金标（website JS 签，见 spec §2.3）────────────────────────────────
KEY_HEX = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
KEY = bytes.fromhex(KEY_HEX)
MID = "a1b2c3d4e5f60718"
FP = bytes.fromhex(MID)

F_CHATOP = {"ver": 1, "kind": 0, "modules": 512, "value": 3650, "issueDate": 190, "nonce": 7}
F_CHAT = {"ver": 1, "kind": 0, "modules": 2, "value": 30, "issueDate": 190, "nonce": 7}
F_COUNT = {"ver": 1, "kind": 1, "modules": 512, "value": 50, "issueDate": 190, "nonce": 7}

S_CHATOP = "20803-J20QR-3VNWP-KW28Y-4KXPC"   # 25 字符 v2，bit9
S_CHAT = "20807-G5Y0Y-8AMVS-ZGZYH-G2R4"      # 24 字符 v1，bit1（察元桌面版的码）
S_COUNT = "30800-1J0QR-3JS5A-B682F-T824X"    # 次数型


# ── 测试用签发端：镜像 website 的 codec.js pack + shortcode.js sign ─────────
_ENC = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ORDER = ["ver", "kind", "modules", "value", "issueDate", "nonce"]
_W1 = {"ver": 4, "kind": 1, "modules": 8, "value": 14, "issueDate": 13, "nonce": 8}
_W2 = {"ver": 4, "kind": 1, "modules": 16, "value": 14, "issueDate": 13, "nonce": 8}


def _pack(fields):
    widths = _W2 if fields["modules"] > 0xFF else _W1
    v = 0
    for k in _ORDER:
        v = (v << widths[k]) | fields[k]
    return v.to_bytes(7 if widths is _W2 else 6, "big")


def _b32encode(buf):
    bits = 0
    value = 0
    out = []
    for b in buf:
        value = (value << 8) | b
        bits += 8
        while bits >= 5:
            out.append(_ENC[(value >> (bits - 5)) & 31])
            bits -= 5
    if bits:
        out.append(_ENC[(value << (5 - bits)) & 31])
    return "".join(out)


def _group5(s):
    return "-".join(s[i:i + 5] for i in range(0, len(s), 5))


def sign(fields, fp=FP, key=KEY):
    header = _pack(fields)
    body = header + hmac.new(key, header + fp, hashlib.sha256).digest()[:8]
    return _group5(_b32encode(body) + base32.check_char(body))


def test_test_helper_reproduces_website_golden_serials():
    """先证明测试 helper 与 website JS 一致，后面才敢用它造边界样本。"""
    assert sign(F_CHATOP) == S_CHATOP
    assert sign(F_CHAT) == S_CHAT
    assert sign(F_COUNT) == S_COUNT


# ── base32 ────────────────────────────────────────────────────────────────
def test_base32_ignores_dashes_and_is_case_insensitive():
    assert base32.decode("20803-J20QR") == base32.decode("20803j20qr")


def test_base32_crockford_confusable_chars():
    assert base32.decode("O") == base32.decode("0")
    assert base32.decode("I") == base32.decode("1") == base32.decode("L")


def test_base32_rejects_invalid_symbol():
    with pytest.raises(ValueError):
        base32.decode("U")  # U 不在编码表里（只在校验符表里）


def test_check_char_is_last_serial_char():
    body = base32.decode(S_CHATOP.replace("-", "")[:-1])
    assert base32.check_char(body) == S_CHATOP[-1]


# ── codec ─────────────────────────────────────────────────────────────────
def test_codec_unpack_v1_and_v2():
    assert codec.unpack(_pack(F_CHAT)) == F_CHAT
    assert codec.unpack(_pack(F_CHATOP)) == F_CHATOP


def test_codec_v2_selected_when_module_bit_above_7():
    assert len(_pack(F_CHAT)) == 6      # modules=2   → v1
    assert len(_pack(F_CHATOP)) == 7    # modules=512 → v2


def test_codec_rejects_seat_header():
    """8 字节 seat（席位）头必须拒绝：chatop 不认网络版部署授权。"""
    with pytest.raises(ValueError):
        codec.unpack(b"\x00" * 8)


def test_codec_iso_roundtrip():
    dt = datetime(2026, 7, 9, 12, 34, 56, 789000, tzinfo=timezone.utc)
    assert codec.to_iso(dt) == "2026-07-09T12:34:56.789Z"
    assert codec.from_iso(codec.to_iso(dt)) == dt


# ── shortcode 验签 ─────────────────────────────────────────────────────────
def test_verify_golden_chatop_serial():
    r = shortcode.verify_shortcode(S_CHATOP, FP, {1: KEY})
    assert r["valid"] and r["fields"] == F_CHATOP
    assert r["expireAt"] == "2036-07-07T00:00:00.000Z"


def test_verify_accepts_lowercase_and_undashed():
    assert shortcode.verify_shortcode(S_CHATOP.replace("-", "").lower(), FP, {1: KEY})["valid"]


def test_chat_serial_verifies_but_is_not_a_chatop_license():
    """血泪点：验签通过 != 有工舱授权。察元桌面版的码在同一把密钥下也是 valid。"""
    r = shortcode.verify_shortcode(S_CHAT, FP, {1: KEY})
    assert r["valid"] is True
    assert not r["fields"]["modules"] & (1 << gate.CHATOP_MODULE_BIT)


def test_verify_wrong_fingerprint_is_signature_failure():
    r = shortcode.verify_shortcode(S_CHATOP, bytes.fromhex("0000000000000000"), {1: KEY})
    assert r == {"valid": False, "reason": "signature"}


def test_verify_tampered_char_is_checksum_failure():
    r = shortcode.verify_shortcode("20803-J20QR-3VNWP-KW28Y-4KXPD", FP, {1: KEY})
    assert r == {"valid": False, "reason": "checksum"}


def test_verify_unknown_key_id():
    r = shortcode.verify_shortcode(S_CHATOP, FP, {2: KEY})
    assert r == {"valid": False, "reason": "unknown-key"}


def test_verify_rejects_27_char_seat_code():
    seat = _group5("A" * 27)
    assert shortcode.verify_shortcode(seat, FP, {1: KEY}) == {"valid": False, "reason": "length"}


def test_verify_rejects_empty_and_garbage():
    assert shortcode.verify_shortcode("", FP, {1: KEY})["reason"] == "length"
    assert shortcode.verify_shortcode("hello", FP, {1: KEY})["reason"] == "length"


# ── machine 指纹 ──────────────────────────────────────────────────────────
@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.delenv("CHATOP_MACHINE_ID", raising=False)
    monkeypatch.delenv("CHATOP_LICENSE_HMAC_KEY", raising=False)
    monkeypatch.setattr(machine, "NODE_ID_FILE", str(tmp_path / "node-id"))
    monkeypatch.setattr(store, "ACTIVATION_FILE", str(tmp_path / "activation.json"))
    monkeypatch.setattr(gate, "KEYS_FILE", str(tmp_path / "license-keys.json"))
    # 生产已用 gate.GATE_DISABLED=True 停用闸门；这些测试验证「闸门开启时」的机制，
    # 故在隔离环境里强制打开（monkeypatch 用例结束自动还原）。
    monkeypatch.setattr(gate, "GATE_DISABLED", False)
    gate.reset_cache()
    yield tmp_path
    gate.reset_cache()


def test_gate_disabled_by_default_in_production(monkeypatch):
    """出厂默认：闸门总开关关闭 → 指纹 + 序列号功能停用。

    2026-07-11 应产品要求停用。即便运行时给了 HMAC 密钥，总开关也压过它 →
    hmac_keys() 恒空、state 恒 off，登录退回用户名+密码+验证码。恢复见 gate.GATE_DISABLED。
    """
    assert gate.GATE_DISABLED is True
    monkeypatch.setenv("CHATOP_LICENSE_HMAC_KEY", "aa" * 32)
    gate.reset_cache()
    assert gate.hmac_keys() == {}
    assert gate.state() == "off"
    gate.reset_cache()


def test_machine_id_env_override_wins(isolated_home, monkeypatch):
    monkeypatch.setenv("CHATOP_MACHINE_ID", "fixed-operator-id")
    assert machine.machine_id() == "fixed-operator-id"
    assert not os.path.exists(machine.NODE_ID_FILE)  # env 生效时不该建 node-id


def test_mid_is_sha256_prefix_of_machine_id(isolated_home, monkeypatch):
    monkeypatch.setenv("CHATOP_MACHINE_ID", "abc")
    expect = hashlib.sha256(b"abc").hexdigest()[:16]
    assert machine.mid() == expect
    assert len(machine.mid()) == 16 and machine.mid() == machine.mid().lower()
    assert machine.mid_bytes() == bytes.fromhex(expect)
    assert len(machine.mid_bytes()) == 8  # 喂给 HMAC 的是 8 个原始字节


def test_node_id_created_once_and_is_stable(isolated_home):
    first = machine.machine_id()
    assert os.path.exists(machine.NODE_ID_FILE)
    assert machine.machine_id() == first


def test_node_id_reused_from_existing_file(isolated_home):
    with open(machine.NODE_ID_FILE, "w") as f:
        f.write("deadbeef-0000-1111-2222-333344445555\n")
    assert machine.machine_id() == "deadbeef-0000-1111-2222-333344445555"


def test_concurrent_machine_id_converges_to_one_uuid(isolated_home):
    """app-manager 与 station 由 custom_startup.sh 并行拉起，双写会让指纹翻一次。"""
    seen = []
    barrier = threading.Barrier(16)

    def worker():
        barrier.wait()
        seen.append(machine.machine_id())

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(seen)) == 1
    with open(machine.NODE_ID_FILE) as f:
        assert f.read().strip() == seen[0]


# ── store 激活记录 ────────────────────────────────────────────────────────
def _record(**over):
    rec = {"v": 1, "key_id": 1, "mid": MID, "serial": S_CHATOP, "modules": 512,
           "kind": "time", "expire_at": "2036-07-07T00:00:00.000Z",
           "activated_at": "2026-07-09T00:00:00.000Z",
           "seen_max": "2026-07-09T00:00:00.000Z"}
    rec.update(over)
    return rec


def test_store_sign_verify_roundtrip(isolated_home):
    saved = store.save(_record(), KEY, store.ACTIVATION_FILE)
    loaded = store.load(store.ACTIVATION_FILE)
    assert loaded == saved and store.verify_sig(loaded, KEY)


@pytest.mark.parametrize("field,value", [
    ("expire_at", "2099-01-01T00:00:00.000Z"),
    ("mid", "ffffffffffffffff"),
    ("modules", 1023),
    ("seen_max", "2000-01-01T00:00:00.000Z"),
])
def test_store_any_mutation_breaks_signature(isolated_home, field, value):
    store.save(_record(), KEY, store.ACTIVATION_FILE)
    rec = store.load(store.ACTIVATION_FILE)
    rec[field] = value
    assert not store.verify_sig(rec, KEY)


def test_store_save_is_atomic_and_leaves_no_tmp(isolated_home):
    store.save(_record(), KEY, store.ACTIVATION_FILE)
    assert not os.path.exists(store.ACTIVATION_FILE + ".tmp")


def test_store_load_missing_or_garbage_returns_none(isolated_home):
    assert store.load(store.ACTIVATION_FILE) is None
    with open(store.ACTIVATION_FILE, "w") as f:
        f.write("not json")
    assert store.load(store.ACTIVATION_FILE) is None


# ── gate 状态机 ───────────────────────────────────────────────────────────
@pytest.fixture
def gated(isolated_home, monkeypatch):
    """密钥就位 + 指纹钉死成金标 MID。"""
    monkeypatch.setattr(machine, "mid", lambda: MID)
    monkeypatch.setattr(machine, "mid_bytes", lambda: FP)
    with open(gate.KEYS_FILE, "w") as f:
        json.dump({"active_key_id": 1, "hmac_keys": {"1": KEY_HEX}}, f)
    gate.reset_cache()
    return isolated_home


NOW = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)


def test_gate_off_when_no_key_configured(isolated_home):
    """自建/开发镜像不注入密钥 → 闸门关闭，行为与今天一致，不会把自己锁在门外。"""
    assert gate.state() == gate.OFF
    assert gate.hmac_keys() == {}


def test_gate_reads_key_from_env(isolated_home, monkeypatch):
    monkeypatch.setenv("CHATOP_LICENSE_HMAC_KEY", KEY_HEX)
    gate.reset_cache()
    assert gate.hmac_keys() == {1: KEY}


def test_gate_ignores_malformed_key_file(isolated_home):
    with open(gate.KEYS_FILE, "w") as f:
        f.write("{oops")
    gate.reset_cache()
    assert gate.state() == gate.OFF


def test_gate_needs_activation_when_no_record(gated):
    assert gate.state(NOW) == gate.NEEDS_ACTIVATION


def test_gate_activate_happy_path(gated):
    assert gate.activate(S_CHATOP, NOW) == (True, 0)
    assert gate.state(NOW) == gate.ACTIVE
    rec = store.load(store.ACTIVATION_FILE)
    assert rec["mid"] == MID and rec["modules"] == 512 and rec["kind"] == "time"
    assert rec["expire_at"] == "2036-07-07T00:00:00.000Z"


def test_gate_rejects_chat_serial_without_chatop_bit(gated):
    """一张察元桌面版的序列号不能开工舱 —— 这是验签之外必须补的一刀。"""
    assert gate.activate(S_CHAT, NOW) == (False, gate.ERR_NO_MODULE)
    assert gate.state(NOW) == gate.NEEDS_ACTIVATION


def test_gate_rejects_count_kind_serial(gated):
    assert gate.activate(S_COUNT, NOW) == (False, gate.ERR_KIND)


def test_gate_rejects_serial_for_another_machine(gated, monkeypatch):
    monkeypatch.setattr(machine, "mid_bytes", lambda: bytes.fromhex("0000000000000000"))
    assert gate.activate(S_CHATOP, NOW) == (False, gate.ERR_FINGERPRINT)


def test_gate_rejects_garbage_serial(gated):
    assert gate.activate("not-a-serial", NOW) == (False, gate.ERR_INVALID)
    assert gate.activate("20803-J20QR-3VNWP-KW28Y-4KXPD", NOW) == (False, gate.ERR_INVALID)


def test_gate_rejects_already_expired_serial(gated):
    """issueDate=190 (2026-07-10) + 1 天 → 2026-07-11 到期；用 2026-08 的 now 去激活。"""
    expired = sign({**F_CHATOP, "value": 1})
    late = datetime(2026, 8, 1, tzinfo=timezone.utc)
    assert gate.activate(expired, late) == (False, gate.ERR_SERIAL_EXPIRED)


def test_gate_expired_license_after_expire_date(gated):
    short = sign({**F_CHATOP, "value": 2})   # 2026-07-12 到期
    assert gate.activate(short, NOW)[0] is True
    later = datetime(2026, 7, 20, tzinfo=timezone.utc)
    assert gate.state_detail(later) == (gate.EXPIRED, gate.ERR_LICENSE_EXPIRED)


def test_gate_detects_clock_rollback(gated):
    assert gate.activate(S_CHATOP, NOW)[0] is True
    back = NOW - timedelta(days=3)
    assert gate.state_detail(back) == (gate.EXPIRED, gate.ERR_CLOCK)


def test_gate_tolerates_small_clock_drift(gated):
    assert gate.activate(S_CHATOP, NOW)[0] is True
    drift = NOW - timedelta(hours=6)
    assert gate.state(drift) == gate.ACTIVE


def test_gate_record_from_another_machine_is_rejected(gated, monkeypatch):
    assert gate.activate(S_CHATOP, NOW)[0] is True
    monkeypatch.setattr(machine, "mid", lambda: "ffffffffffffffff")
    gate.reset_cache()
    assert gate.state(NOW) == gate.NEEDS_ACTIVATION


def test_gate_tampered_record_is_rejected(gated):
    assert gate.activate(S_CHATOP, NOW)[0] is True
    rec = store.load(store.ACTIVATION_FILE)
    rec["expire_at"] = "2099-01-01T00:00:00.000Z"
    with open(store.ACTIVATION_FILE, "w") as f:
        json.dump(rec, f)
    gate.reset_cache()
    assert gate.state(NOW) == gate.NEEDS_ACTIVATION


def test_gate_record_with_unknown_key_id_is_rejected(gated):
    assert gate.activate(S_CHATOP, NOW)[0] is True
    rec = store.load(store.ACTIVATION_FILE)
    rec["key_id"] = 7
    with open(store.ACTIVATION_FILE, "w") as f:
        json.dump(rec, f)
    gate.reset_cache()
    assert gate.state(NOW) == gate.NEEDS_ACTIVATION


def test_gate_touch_advances_seen_max(gated):
    assert gate.activate(S_CHATOP, NOW)[0] is True
    later = NOW + timedelta(days=5)
    gate.touch(later)
    rec = store.load(store.ACTIVATION_FILE)
    assert rec["seen_max"] == codec.to_iso(later)
    assert store.verify_sig(rec, KEY)
    # 推进后再回拨 3 天仍在容差外 → 判篡改
    assert gate.state_detail(NOW)[1] == gate.ERR_CLOCK


def test_gate_touch_never_moves_seen_max_backwards(gated):
    assert gate.activate(S_CHATOP, NOW)[0] is True
    gate.touch(NOW - timedelta(days=10))
    rec = store.load(store.ACTIVATION_FILE)
    assert rec["seen_max"] == codec.to_iso(NOW)


def test_gate_info_exposes_mid_and_expiry(gated):
    assert gate.info(NOW)["state"] == gate.NEEDS_ACTIVATION
    assert gate.info(NOW)["mid"] == MID
    gate.activate(S_CHATOP, NOW)
    got = gate.info(NOW)
    assert got["state"] == gate.ACTIVE and got["expire_at"] == "2036-07-07T00:00:00.000Z"


def test_gate_record_cache_invalidated_on_file_change(gated):
    assert gate.state(NOW) == gate.NEEDS_ACTIVATION   # 建立缓存（无文件）
    gate.activate(S_CHATOP, NOW)
    assert gate.state(NOW) == gate.ACTIVE             # 必须看见新文件


# ── gate.validate / commit 分离 ───────────────────────────────────────────
def test_validate_does_not_write_record(gated):
    ok, err, rec = gate.validate(S_CHATOP, NOW)
    assert ok and err == 0 and rec["mid"] == MID
    assert not os.path.exists(store.ACTIVATION_FILE)   # 密码没验，绝不能落盘
    assert gate.state(NOW) == gate.NEEDS_ACTIVATION


def test_commit_persists_validated_record(gated):
    _, _, rec = gate.validate(S_CHATOP, NOW)
    gate.commit(rec)
    assert gate.state(NOW) == gate.ACTIVE


def test_commit_rejects_unknown_key_id(gated):
    _, _, rec = gate.validate(S_CHATOP, NOW)
    rec["key_id"] = 7
    with pytest.raises(ValueError):
        gate.commit(rec)


# ── app_manager 接线 ──────────────────────────────────────────────────────
@pytest.fixture
def am(gated, monkeypatch):
    monkeypatch.setenv("FILES_PW", "s3cret")
    monkeypatch.setenv("LOGIN_USER", "admin")
    for mod in [m for m in list(sys.modules) if m == "app_manager"]:
        del sys.modules[mod]
    import app_manager
    monkeypatch.setattr(app_manager, "_gate", gate)
    return app_manager


def test_login_page_shows_serial_field_when_not_activated(am):
    html = am._login_html("", gate.state(NOW), MID)
    assert 'name="serial"' in html and "请关注下方公众号获取序列号" in html
    assert MID in html
    assert 'name="captcha"' not in html
    assert "激活并登录" in html


def test_login_page_shows_captcha_when_activated(am):
    html = am._login_html("", gate.ACTIVE, "", "2036-07-07T00:00:00.000Z")
    assert 'name="captcha"' in html and 'name="serial"' not in html
    assert "授权有效期至 2036-07-07" in html


def test_login_page_shows_captcha_when_gate_off(am):
    html = am._login_html("", gate.OFF)
    assert 'name="captcha"' in html and 'name="serial"' not in html


def test_login_page_keeps_brand_string_for_heartbeat_probe(am):
    """station 的 _brand_intact() 靠登录页含「察元AI工舱」判断品牌完整性。"""
    for st in (gate.OFF, gate.ACTIVE, gate.NEEDS_ACTIVATION):
        assert "察元AI工舱" in am._login_html("", st, MID)


@pytest.mark.parametrize("code", ["1", "2", "3", "4", "5", "6", "7", "8", "9"])
def test_every_error_code_renders_a_message(am, code):
    # LOGIN_ERRORS 的值是英文原文（同时也是词典 key），所以只有 lang="en" 时
    # 渲染结果才等于它本身。各语言的译文是否齐全由 test_chatop_i18n.py 保证。
    html = am._login_html(code, gate.NEEDS_ACTIVATION, MID, lang="en")
    assert am.LOGIN_ERRORS[code] in html


def test_gate_passable_semantics(am):
    assert am.gate_passable(gate.OFF) and am.gate_passable(gate.ACTIVE)
    assert not am.gate_passable(gate.NEEDS_ACTIVATION)
    assert not am.gate_passable(gate.EXPIRED)


def test_forged_cookie_cannot_bypass_activation(am):
    """chatop_auth 的值是常量 AUTH_TOKEN，知道密码就能自己算出来。
    所以 /auth 必须同时看激活状态，否则激活闸门形同虚设。"""
    cookie = "%s=%s" % (am.AUTH_COOKIE, am.AUTH_TOKEN)
    assert am._cookie_ok(cookie) is True                 # cookie 本身有效
    assert not am.gate_passable(gate.state(NOW))         # 但未激活
    gate.activate(S_CHATOP, NOW)
    assert am.gate_passable(gate.state(NOW))             # 激活后才放行


def test_gate_state_degrades_to_off_when_package_broken(am, monkeypatch):
    monkeypatch.setattr(am, "_gate", None)
    assert am.gate_state() == ("off", 0)
    assert am.gate_mid() == ""


def test_gate_state_degrades_to_off_when_gate_raises(am, monkeypatch):
    class Boom:
        @staticmethod
        def state_detail():
            raise RuntimeError("disk on fire")
    monkeypatch.setattr(am, "_gate", Boom)
    assert am.gate_state() == ("off", 0)   # 宁可放行也不把用户锁在门外
