"""功能：序列号连错 3 次后放行（软激活），但不落盘激活 → 下次登录仍要输序列号。

只测纯逻辑单元：宽限令牌(签名+TTL) 与 每-IP 序列号失败计数器。
HTTP 装配在容器内实测验证（见提交说明）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import app_manager as am


def setup_function(_):
    am._SERIAL_FAILS.clear()


# ---- 宽限令牌 ----

def test_grace_token_roundtrips_and_verifies():
    tok = am._grace_new(now=1000)
    assert am._grace_ok(tok, now=1000) is True
    assert am._grace_ok(tok, now=1000 + am.GRACE_TTL - 1) is True


def test_grace_token_expires():
    tok = am._grace_new(now=1000)
    assert am._grace_ok(tok, now=1000 + am.GRACE_TTL + 1) is False


def test_grace_token_rejects_tampering():
    tok = am._grace_new(now=1000)
    b64, _, sig = tok.partition(".")
    forged = b64 + "." + ("0" * len(sig))
    assert am._grace_ok(forged, now=1000) is False


def test_grace_token_rejects_garbage():
    for bad in ("", None, "nodot", "a.b", "....", "x" * 50):
        assert am._grace_ok(bad, now=1000) is False


def test_grace_token_rejects_non_grace_payload():
    # 用 captcha 的签名格式（同一把 AUTH_TOKEN）也不能冒充 grace：tag 必须是 "grace"
    _, cap_cookie = am._captcha_new()
    assert am._grace_ok(cap_cookie, now=1000) is False


# ---- 每-IP 序列号失败计数 ----

def test_serial_fail_counter_increments():
    ip = "10.0.0.1"
    assert am._serial_fails(ip, now=0) == 0
    am._serial_record_fail(ip, now=0)
    am._serial_record_fail(ip, now=1)
    assert am._serial_fails(ip, now=2) == 2


def test_serial_bypass_threshold_is_three():
    ip = "10.0.0.2"
    for i in range(am.SERIAL_BYPASS_MAX):
        assert am._serial_fails(ip, now=i) < am.SERIAL_BYPASS_MAX
        am._serial_record_fail(ip, now=i)
    assert am._serial_fails(ip, now=99) >= am.SERIAL_BYPASS_MAX


def test_serial_fail_counter_windows_out():
    ip = "10.0.0.3"
    am._serial_record_fail(ip, now=0)
    am._serial_record_fail(ip, now=1)
    assert am._serial_fails(ip, now=am.SERIAL_WINDOW + 2) == 0


def test_serial_reset_clears_counter():
    ip = "10.0.0.4"
    am._serial_record_fail(ip, now=0)
    am._serial_reset(ip)
    assert am._serial_fails(ip, now=1) == 0


def test_serial_counter_is_per_ip():
    am._serial_record_fail("a", now=0)
    am._serial_record_fail("a", now=0)
    am._serial_record_fail("b", now=0)
    assert am._serial_fails("a", now=0) == 2
    assert am._serial_fails("b", now=0) == 1
