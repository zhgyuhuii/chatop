"""运行状态同步 —— station 后台静默上报本工位实例的存活心跳。

对齐 chayuan-wps 的 runtimeSync：每隔一段时间 POST 一次匿名存活心跳到官网，
用于官网后台统计"在线工位数 / 版本分布"。任何失败(断网/DNS/超时)全部静默吞掉，
绝不影响 station 主服务。

合规提示：会上报 IP(网络请求自动携带)与操作系统信息，属个人信息，须在隐私政策告知。
"""
from __future__ import annotations

import base64
import json
import os
import platform
import threading
import time
import urllib.request
import uuid

from . import config

# website 白名单当前为 {wps, desktop}；chatop 是云桌面工位 → 归 desktop
_PRODUCT = "desktop"
_VERSION = os.environ.get("CHATOP_VERSION", "0.0.0")
_FIRST_DELAY_S = 30
# 默认 30 分钟一次(官网侧同 hid 5 分钟去重；别低于此)。可用 env 调。
_INTERVAL_S = max(300, int(os.environ.get("CHATOP_HEARTBEAT_INTERVAL", str(30 * 60))))
_HID_FILE = config.DATA_DIR / "node-id"

# 上报域名：base64 + XOR 0x5a 混淆(与 chayuan-wps runtimeSync 同法)。
# 说明：客户端运行时必须连该域名，无法真正"加密"，此处仅源码混淆防直接 grep；抓包仍可见。
_H = "OzM+NTU1dDk1Nw=="


def _endpoint() -> str:
    raw = base64.b64decode(_H)
    host = "".join(chr(b ^ 0x5A) for b in raw)
    return "https://" + host + "/api/node-sync"


def _valid_hid(v: str) -> bool:
    return 8 <= len(v) <= 64 and all(c in "0123456789abcdef-" for c in v.lower())


def _read_hid() -> str:
    try:
        v = _HID_FILE.read_text().strip()
    except OSError:
        return ""
    return v if _valid_hid(v) else ""


def _hid() -> str:
    """匿名工位标识：首次生成 UUID 持久化到卷内，跨重启稳定，与个人身份无关。

    这个文件同时是 app-manager 序列号激活的**指纹锚点**（chatop_license/machine.py），
    而 custom_startup.sh 并行拉起 station 与 app-manager。所以创建必须是
    「出现即完整」的：先写满 tmp，再 os.link 原子占位，最后一律回读。

    别改回 read→write：那样两边首启会各写一个 UUID，指纹翻一次，把刚激活的授权作废。
    裸 O_EXCL 也不行 —— 它只保证谁创建原子，输的一方会读到尚未写完的空文件。
    """
    v = _read_hid()
    if v:
        return v
    v = str(uuid.uuid4())
    tmp = _HID_FILE.with_name(f"{_HID_FILE.name}.{v}.tmp")
    try:
        _HID_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(v)
        try:
            os.link(tmp, _HID_FILE)
        except FileExistsError:
            pass
    except OSError:
        return v
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    return _read_hid() or v


def _brand_intact() -> bool:
    """品牌完整性：登录页(app-manager)标题应含品牌名；探测本身失败时不误判为被改。"""
    try:
        with urllib.request.urlopen("http://127.0.0.1:8686/login", timeout=3) as r:
            return "察元AI工舱" in r.read(4096).decode("utf-8", "ignore")
    except Exception:
        return True


def _payload() -> bytes:
    return json.dumps({
        "hid": _hid(),
        "product": _PRODUCT,
        "ver": _VERSION,
        "os": platform.system().lower() or "linux",
        "osVer": platform.release(),
        "arch": (platform.machine() or "").lower(),
        "brand": _brand_intact(),
        "t": int(time.time() * 1000),
    }).encode()


def _report() -> None:
    try:
        req = urllib.request.Request(
            _endpoint(), data=_payload(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=8).close()
    except Exception:
        pass  # 静默：遥测绝不影响主程序


def _loop() -> None:
    time.sleep(_FIRST_DELAY_S)
    while True:
        _report()
        time.sleep(_INTERVAL_S)


_started = False


def start_heartbeat() -> None:
    """启动后台心跳线程(daemon)。重复调用无副作用。"""
    global _started
    if _started:
        return
    _started = True
    try:
        threading.Thread(target=_loop, name="chatop-heartbeat", daemon=True).start()
    except Exception:
        pass
