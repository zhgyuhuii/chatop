"""激活记录的原子读写与签名校验。

~/.local/share/chatop/activation.json（卷内持久）：

    {"v":1, "key_id":1, "mid":"a1b2…", "serial":"20803-…", "modules":512,
     "kind":"time", "expire_at":"…Z", "activated_at":"…Z", "seen_max":"…Z", "sig":"…"}

sig = HMAC-SHA256(record_key, canonical_json_without_sig)
record_key = HMAC(license_hmac_key, "chatop-activation-v1")   —— 不引入新密钥。

它挡住：手改到期日、把 A 机的记录拷到 B 机（mid 不符）、把系统时钟拨回去续命（seen_max）。
它挡不住拥有宿主 root 的人 —— 那个人可以 docker exec 改任何东西。这是业务闸门，不是 DRM。
"""
import hashlib
import hmac
import json
import os

from . import machine

ACTIVATION_FILE = os.path.join(machine.DATA_DIR, "activation.json")


def record_key(license_key):
    return hmac.new(license_key, b"chatop-activation-v1", hashlib.sha256).digest()


def _canonical(rec):
    body = {k: v for k, v in rec.items() if k != "sig"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sign(rec, license_key):
    return hmac.new(record_key(license_key), _canonical(rec), hashlib.sha256).hexdigest()


def verify_sig(rec, license_key):
    given = rec.get("sig") or ""
    return hmac.compare_digest(given, sign(rec, license_key))


def load(path=None):
    """→ dict 或 None（不存在 / 不是合法 JSON 对象）。不做签名校验，那是 gate 的事。"""
    try:
        with open(path or ACTIVATION_FILE, encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return None
    return rec if isinstance(rec, dict) else None


def save(rec, license_key, path=None):
    """签名后原子落盘（tmp + os.replace），避免断电/并发读到半截 JSON。"""
    path = path or ACTIVATION_FILE
    rec = dict(rec)
    rec["sig"] = sign(rec, license_key)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        pass
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return rec
