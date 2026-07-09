"""Crockford Base32 解码 + mod-37 校验符。

与 website `server/license/base32.js` 及 chayuan-desktop `license/base32.py` 字节兼容。
改这里之前先跑 tests/test_chatop_license.py 的跨语言金标向量。
"""

_ENC = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # 去掉 I L O U
_CHECK = _ENC + "*~$=U"                    # mod-37 校验符表，比 _ENC 多 5 个
_DEC = {c: i for i, c in enumerate(_ENC)}
# 人眼容错：O→0，I/L→1（Crockford 规范要求，不是我们自己加的）
_DEC["O"] = 0
_DEC["I"] = 1
_DEC["L"] = 1


def decode(s):
    """base32 字符串 → bytes。连字符忽略，大小写不敏感。非法符号抛 ValueError。"""
    bits = 0
    value = 0
    out = bytearray()
    for raw in s.upper():
        if raw == "-":
            continue
        v = _DEC.get(raw)
        if v is None:
            raise ValueError("invalid base32 symbol: %s" % raw)
        value = (value << 5) | v
        bits += 5
        if bits >= 8:
            out.append((value >> (bits - 8)) & 0xFF)
            bits -= 8
            value &= (1 << bits) - 1
    return bytes(out)


def check_char(buf):
    """整个 body 当大整数取 mod 37，映射到 _CHECK。序列号的最后一个字符。"""
    n = 0
    for b in buf:
        n = (n * 256 + b) % 37
    return _CHECK[n]
