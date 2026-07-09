"""序列号头部解包。与 website `server/license/codec.js` 一致。

v1: 6 字节头，modules 8bit;  v2: 7 字节头，modules 16bit。
签发端按 `modules > 0xff` 自动选 v1/v2（codec.js: widthsFor），解析端按长度反推。

注意 `ver` 字段**不是编解码版本号，是密钥 id**（issue.js: `ver: activeKeyId`）。

chatop 不支持 8 字节的 seat（席位）短码 —— 它属于网络版部署授权，这里显式拒绝，
避免把一张席位码误当成工舱授权放行。
"""
from datetime import datetime, timedelta, timezone

EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)

_ORDER = ["ver", "kind", "modules", "value", "issueDate", "nonce"]
_WIDTHS_V1 = {"ver": 4, "kind": 1, "modules": 8, "value": 14, "issueDate": 13, "nonce": 8}
_WIDTHS_V2 = {"ver": 4, "kind": 1, "modules": 16, "value": 14, "issueDate": 13, "nonce": 8}


def unpack(buf):
    """6/7 字节头 → dict。其它长度（含 8 字节 seat 头）抛 ValueError。"""
    if len(buf) == 6:
        widths = _WIDTHS_V1
    elif len(buf) == 7:
        widths = _WIDTHS_V2
    else:
        raise ValueError("unsupported header length: %d" % len(buf))
    v = int.from_bytes(buf, "big")
    out = {}
    for k in reversed(_ORDER):
        w = widths[k]
        out[k] = v & ((1 << w) - 1)
        v >>= w
    return out


def issue_to_date(n):
    return EPOCH + timedelta(days=n)


def to_iso(dt):
    """与 JS Date.toISOString() 同形：毫秒 + Z。"""
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (dt.microsecond // 1000)


def from_iso(s):
    """解析 to_iso 产出的字符串（也容忍不带毫秒的 ...Z）。"""
    txt = s.strip()
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    return datetime.fromisoformat(txt)


def now_utc():
    return datetime.now(timezone.utc)
