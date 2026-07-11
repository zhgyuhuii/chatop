"""激活闸门：app_manager.py 唯一该 import 的东西。

四态：
    off              无 HMAC 密钥 → 闸门关闭，登录页退回「用户名+密码+验证码」现状。
                     这是为了让不带 --build-arg 的自建/开发镜像不会把自己锁在门外。
    needs_activation 无记录 / 签名不符 / 记录属于别的指纹
    expired          记录有效但已过期，或检测到系统时钟被回拨
    active           放行

activate() 的校验顺序不能调换 —— 每一步对应一个明确的用户可读错误码。

**光验签是不够的**：一张 chat(bit 1) 的序列号在同一把密钥下验签同样返回 valid=True。
必须再查 modules & (1<<9)，否则任何察元桌面版的序列号都能开工舱。
"""
import json
import os

from . import codec, machine, shortcode, store

# 与 website server/data/license-modules.json 的 chatop.bit 必须一致。
# bit 0-8 已被 video/chat/kb/avatar/ocr/asr/note/wps/video_edit 占用。
CHATOP_MODULE_BIT = 9

KEYS_FILE = os.environ.get("CHATOP_LICENSE_KEYS_FILE") or "/opt/chatop/license-keys.json"

# 时钟回拨容差：允许 1 天以内的漂移（时区/NTP 校正），超出即判篡改。
ROLLBACK_TOLERANCE_SEC = 86400

OFF = "off"
NEEDS_ACTIVATION = "needs_activation"
EXPIRED = "expired"
ACTIVE = "active"

ERR_INVALID = 3          # 格式 / 校验位 / 密钥版本不受支持
ERR_FINGERPRINT = 4      # 验签失败 —— 不是为本机签发的
ERR_NO_MODULE = 5        # 不含工舱模块位
ERR_KIND = 6             # 次数型不支持
ERR_SERIAL_EXPIRED = 7   # 序列号本身已过期
ERR_LICENSE_EXPIRED = 8  # 已激活但授权到期
ERR_CLOCK = 9            # 系统时钟回拨

_keys_cache = {"loaded": False, "keys": {}}
_rec_cache = {"stat": None, "rec": None}


def reset_cache():
    """测试用：清掉密钥与记录缓存。"""
    _keys_cache["loaded"] = False
    _keys_cache["keys"] = {}
    _rec_cache["stat"] = None
    _rec_cache["rec"] = None


def _parse_hex_key(text):
    try:
        raw = bytes.fromhex((text or "").strip())
    except ValueError:
        return b""
    return raw if raw else b""


# === 激活闸门总开关 =========================================================
# 2026-07-11：应产品要求暂停「机器指纹 + 序列号激活」功能。置 True 后
# hmac_keys() 恒返回空 dict → 闸门恒为 off → 登录页退回「用户名 + 密码 +
# 验证码」，不再生成指纹、不再要求序列号（不锁死任何用户）。
# 以后要恢复该功能：把此值改回 False 再重新打镜像即可，其它代码一律不用动
# （HMAC 密钥仍会由 .env → build-arg 烤进镜像内 /opt/chatop/license-keys.json）。
GATE_DISABLED = True
# ===========================================================================


def hmac_keys():
    """→ {key_id: bytes}。空 dict 表示未配置 → 闸门关闭。

    优先级：环境变量 CHATOP_LICENSE_HMAC_KEY > /opt/chatop/license-keys.json。
    """
    if GATE_DISABLED:          # 总开关：功能停用中，恒当作「未配置密钥」→ 闸门 off
        return {}
    if _keys_cache["loaded"]:
        return _keys_cache["keys"]

    keys = {}
    env = _parse_hex_key(os.environ.get("CHATOP_LICENSE_HMAC_KEY"))
    if env:
        active = int(os.environ.get("CHATOP_LICENSE_ACTIVE_KEY_ID") or 1)
        keys[active] = env
    else:
        try:
            with open(KEYS_FILE, encoding="utf-8") as f:
                cfg = json.load(f)
            for kid, hexval in (cfg.get("hmac_keys") or {}).items():
                raw = _parse_hex_key(hexval)
                if raw:
                    keys[int(kid)] = raw
        except (OSError, ValueError, TypeError):
            keys = {}

    _keys_cache["keys"] = keys
    _keys_cache["loaded"] = True
    return keys


def _record_path():
    return store.ACTIVATION_FILE


def _load_record():
    """按 (mtime_ns, size) 缓存，避免每个 HTTP 请求都读盘（/auth 是热路径）。"""
    path = _record_path()
    try:
        st = os.stat(path)
    except OSError:
        _rec_cache["stat"] = None
        _rec_cache["rec"] = None
        return None
    sig = (st.st_mtime_ns, st.st_size)
    if _rec_cache["stat"] != sig:
        _rec_cache["stat"] = sig
        _rec_cache["rec"] = store.load(path)
    return _rec_cache["rec"]


def state_detail(now=None):
    """→ (state, err_code)。err_code 仅在 expired 时有意义（8=到期，9=时钟回拨）。"""
    keys = hmac_keys()
    if not keys:
        return (OFF, 0)

    rec = _load_record()
    if not rec:
        return (NEEDS_ACTIVATION, 0)

    key = keys.get(rec.get("key_id"))
    if not key or not store.verify_sig(rec, key):
        return (NEEDS_ACTIVATION, 0)
    if rec.get("mid") != machine.mid():
        return (NEEDS_ACTIVATION, 0)

    now = now or codec.now_utc()
    try:
        seen = codec.from_iso(rec["seen_max"])
        expire = codec.from_iso(rec["expire_at"])
    except (KeyError, ValueError):
        return (NEEDS_ACTIVATION, 0)

    if (seen - now).total_seconds() > ROLLBACK_TOLERANCE_SEC:
        return (EXPIRED, ERR_CLOCK)
    if now >= expire:
        return (EXPIRED, ERR_LICENSE_EXPIRED)
    return (ACTIVE, 0)


def state(now=None):
    return state_detail(now)[0]


def validate(serial, now=None):
    """纯校验，**不落盘** → (ok, err_code, record_or_None)。

    与 commit() 分开，是为了让调用方能在「序列号已验过、密码尚未验」时不写任何东西。
    调用顺序必须是 validate(序列号) → 验密码 → commit()：
      - 反过来先验密码，则 e=1(密码错) 与 e=3(序列号错) 的差异会变成**密码预言机**
        —— 攻击者随便填个序列号，看返回码就能判断密码对不对。
      - 先 validate 则 e=1 只泄漏「序列号有效」，而序列号的 tag 有 64 bit，爆破不可行。
    """
    keys = hmac_keys()
    if not keys:
        return (False, ERR_INVALID, None)

    result = shortcode.verify_shortcode(serial, machine.mid_bytes(), keys)
    if not result["valid"]:
        # signature = 密钥对、码完整，但不是为本机指纹签的 —— 最常见的用户错误，
        # 值得和「码本身无效」分开提示。
        if result["reason"] == "signature":
            return (False, ERR_FINGERPRINT, None)
        return (False, ERR_INVALID, None)

    fields = result["fields"]
    if not fields["modules"] & (1 << CHATOP_MODULE_BIT):
        return (False, ERR_NO_MODULE, None)
    if fields["kind"] != 0:
        return (False, ERR_KIND, None)

    now = now or codec.now_utc()
    if now >= codec.from_iso(result["expireAt"]):
        return (False, ERR_SERIAL_EXPIRED, None)

    stamp = codec.to_iso(now)
    rec = {
        "v": 1,
        "key_id": fields["ver"],
        "mid": machine.mid(),
        "serial": (serial or "").strip().upper(),
        "modules": fields["modules"],
        "kind": "time",
        "expire_at": result["expireAt"],
        "activated_at": stamp,
        "seen_max": stamp,
    }
    return (True, 0, rec)


def commit(rec):
    """把 validate() 产出的记录签名落盘。"""
    keys = hmac_keys()
    key = keys.get(rec["key_id"])
    if not key:
        raise ValueError("unknown key_id: %r" % rec.get("key_id"))
    store.save(rec, key, _record_path())
    _rec_cache["stat"] = None  # 强制下次重读


def activate(serial, now=None):
    """validate + commit 的便捷组合 → (ok, err_code)。"""
    ok, err, rec = validate(serial, now)
    if not ok:
        return (False, err)
    commit(rec)
    return (True, 0)


def touch(now=None):
    """登录成功时推进 seen_max（时钟回拨检测的单调基线）。失败静默 —— 不该挡住登录。"""
    keys = hmac_keys()
    if not keys:
        return
    rec = _load_record()
    if not rec:
        return
    key = keys.get(rec.get("key_id"))
    if not key or not store.verify_sig(rec, key):
        return
    now = now or codec.now_utc()
    try:
        if now <= codec.from_iso(rec["seen_max"]):
            return
    except (KeyError, ValueError):
        return
    rec = dict(rec)
    rec["seen_max"] = codec.to_iso(now)
    try:
        store.save(rec, key, _record_path())
        _rec_cache["stat"] = None
    except OSError:
        pass


def info(now=None):
    """给登录页用的展示信息。"""
    st, err = state_detail(now)
    rec = _load_record() if st in (ACTIVE, EXPIRED) else None
    return {
        "state": st,
        "err": err,
        "mid": machine.mid(),
        "expire_at": (rec or {}).get("expire_at"),
    }
