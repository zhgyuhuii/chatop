"""本机指纹。

mid = sha256(machine_id)[:16]，16 位小写 hex —— 与 website 的 /^[0-9a-fA-F]{16}$/ 一致。
喂给 HMAC 的是 bytes.fromhex(mid)，8 个原始字节。

machine_id 优先级：
  1. 环境变量 CHATOP_MACHINE_ID —— 运维逃生口：换卷也不换号
  2. ~/.local/share/chatop/node-id —— station 心跳的匿名工位 UUID，卷内持久，容器重建不变
  3. 不存在则 O_CREAT|O_EXCL 原子创建

为什么不用 /etc/machine-id：它在镜像层里，同一镜像跑出来的所有容器完全相同。
为什么不用 container id / MAC：`compose down/up` 后就变。
唯一跨容器重建存活的是 chatop-home 卷，所以指纹只能锚在卷里。

代价：`docker compose down -v` 删卷后指纹改变，需重新领序列号。CHATOP_MACHINE_ID 是出口。

并发：app-manager 与 station 由 custom_startup.sh 并行拉起，两边都会碰 node-id。
必须 O_EXCL 创建 + 失败回读，否则首启双写会让指纹翻一次，把刚激活的记录作废。
station/station/heartbeat.py::_hid() 已同步改成同样的写法。
"""
import hashlib
import os
import uuid

DATA_DIR = os.path.expanduser(
    os.environ.get("CHATOP_DATA_DIR") or "~/.local/share/chatop")
NODE_ID_FILE = os.path.join(DATA_DIR, "node-id")

_VALID_CHARS = set("0123456789abcdef-")


def _looks_like_id(v):
    return 8 <= len(v) <= 64 and all(c in _VALID_CHARS for c in v.lower())


def _read_node_id(path):
    try:
        with open(path) as f:
            v = f.read().strip()
    except OSError:
        return ""
    return v if _looks_like_id(v) else ""


def _create_node_id(path):
    """先写满 tmp，再 os.link 原子地「创建即完整」，最后一律回读。

    不能用裸 O_EXCL：它只保证「谁创建」是原子的，不保证内容已写入。竞态输的一方
    拿到 FileExistsError 后去读，会读到赢家尚未写完的**空文件**，于是退回自己的 UUID
    —— 指纹照样会翻。os.link 在目标已存在时失败，且链接出现时源内容已完整。
    """
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        pass
    v = str(uuid.uuid4())
    tmp = "%s.%s.tmp" % (path, v)  # 名字含自身 UUID，同进程多线程也不互踩
    try:
        with open(tmp, "w") as f:
            f.write(v)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        try:
            os.link(tmp, path)
        except FileExistsError:
            pass  # 别人先建好了，下面回读他的
    except OSError:
        return v  # 卷只读之类：退化成进程内临时 id，不落盘
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return _read_node_id(path) or v


def machine_id():
    env = (os.environ.get("CHATOP_MACHINE_ID") or "").strip()
    if env:
        return env
    return _read_node_id(NODE_ID_FILE) or _create_node_id(NODE_ID_FILE)


def mid():
    return hashlib.sha256(machine_id().encode()).hexdigest()[:16]


def mid_bytes():
    return bytes.fromhex(mid())
