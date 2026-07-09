"""截断 HMAC 短码验签。与 website `server/license/shortcode.js` 的 verify() 字节兼容。

serial = group5( base32( header ‖ HMAC-SHA256(header ‖ machine_fp, key)[:8] ) + check_char )

v1: 24 字符（6 字节头 + 8 字节 tag）
v2: 25 字符（7 字节头 + 8 字节 tag）

`machine_fp` 是 **8 个原始字节**（bytes.fromhex(mid)），不是 16 个 ASCII 字符 ——
website 的 license-routes.js 里就是 `Buffer.from(mid, 'hex')`。搞错这个，验签永远失败。

密钥按 `fields["ver"]` 取（ver == activeKeyId）。
"""
import hashlib
import hmac
from datetime import timedelta

from .base32 import check_char, decode
from .codec import issue_to_date, to_iso, unpack


def verify_shortcode(serial, machine_fp, hmac_keys):
    """→ {"valid": bool, "reason": str} 或 {"valid": True, "fields": dict, "expireAt": iso}

    reason: length | decode | checksum | unknown-key | signature
    """
    norm = (serial or "").replace("-", "").replace(" ", "").upper()
    if len(norm) == 24:
        header_len = 6
    elif len(norm) == 25:
        header_len = 7
    else:
        # 27 字符的 seat（席位）短码走这里被拒 —— chatop 不认席位授权。
        return {"valid": False, "reason": "length"}

    body_len = header_len + 8
    try:
        body = decode(norm[:-1])
    except ValueError:
        return {"valid": False, "reason": "decode"}
    if len(body) != body_len:
        return {"valid": False, "reason": "decode"}
    if check_char(body) != norm[-1]:
        return {"valid": False, "reason": "checksum"}

    header = body[:header_len]
    given_tag = body[header_len:body_len]
    fields = unpack(header)

    key = hmac_keys.get(fields["ver"])
    if not key:
        return {"valid": False, "reason": "unknown-key"}

    tag = hmac.new(key, header + machine_fp, hashlib.sha256).digest()[:8]
    if not hmac.compare_digest(tag, given_tag):
        return {"valid": False, "reason": "signature"}

    if fields["kind"] == 0:
        expire = issue_to_date(fields["issueDate"]) + timedelta(days=fields["value"])
    else:
        # kind=1 次数型：签发日 + 30 天（三端一致的 COUNT_VALID_DAYS）。
        # chatop 最终会在 gate 层拒掉它，这里仍算出 expireAt 以便诊断。
        expire = issue_to_date(fields["issueDate"]) + timedelta(days=30)
    return {"valid": True, "fields": fields, "expireAt": to_iso(expire)}
