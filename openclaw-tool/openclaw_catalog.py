#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""OpenClaw 配置器 — 目录服务（通道/厂商/搜索三份清单的唯一真源出口）。

设计（对齐 docs/superpowers/specs/2026-07-09-openclaw-catalog-truth-source-design.md）：

  * **id 权威** = `openclaw channels list --all --json`。不在其中的 id 一律不进结果。
    这条硬规则自动挡掉 raft（存在于插件目录但 openclaw 不列为可用通道）、
    qa-channel（在 schema 但 CLI 不列）以及 webchat/voice-call 等根本不存在的通道。
  * **字段来源** = `openclaw config schema` 的 channels.properties。注意「键存在」不等于
    「有字段」（openclaw-weixin / twitch 的 properties 为空）。
  * **中文名 / QR 标记** = openclaw 自带的官方外部插件目录（dist JS，文件名带内容哈希）。
    openclaw 自己就写着 selectionLabel="WeCom（企业微信）"、"WhatsApp (QR link)"。
  * **安装** 用通道 id（`openclaw plugins install wecom` 已实证可用，openclaw 自行解析成
    @wecom/wecom-openclaw-plugin@2026.5.7）。故 npm_spec 仅供展示，目录解析失败不影响安装。

约束：本模块不 import tkinter、import 时不调 CLI（CLI 每次 8-12s 且无热缓存），
可在宿主机 py3.6 直接单测。故用 typing.NamedTuple 而非 dataclasses（py3.7+）。
"""
import glob
import json
import os
import subprocess
from typing import NamedTuple, Optional

import catalog_overrides as _ov


# openclaw 实际不提供的通道 id（配置器 GUI 曾误列）。真源是 `openclaw channels list --all --json`
# 的烤入快照，已核对这四个都不在其中。它们一旦写进 openclaw.json，gateway 会以
# "unknown channel id" 拒绝启动。故 GUI 不展示，且保存时从既有配置里剔除（自愈）。
BOGUS_CHANNEL_IDS = ("bluebubbles", "webchat", "voice-call", "zalo-personal")


def channel_entry_when_disabled(existing):
    """通道未启用时该写入 openclaw.json 的内容；返回 None 表示整条不要写。

    openclaw 有些通道（如 twitch）的 schema 用 anyOf：只要该通道对象存在，就必须带
    username/accounts。写裸的 {"enabled": false} 空桩会让 gateway 启动时校验失败
    （"must have required property 'username'"）。因此：

      * 此前配过实质字段 → 保留字段并置 enabled=false（必填字段仍在，校验能过）
      * 从未配过 → 返回 None，整条不写（openclaw 对缺席的通道不做校验）
    """
    existing = existing or {}
    if not any(k != "enabled" for k in existing):
        return None
    out = dict(existing)
    out["enabled"] = False
    return out


def sanitize_config_for_gateway(config):
    """移除会让 openclaw 网关启动校验失败的「半配置」残留；就地修改并返回 (config, removed)。

    幂等、无副作用、不依赖 openclaw CLI（可在桌面启动器里快速跑，无需 8~12s 调 CLI），
    供 GUI 保存与启动器双方复用——单一真源，判据一致。处理三类（都是「没真正配过」的残留，
    openclaw 会明确拒绝、导致整份配置非法、网关拒启）：

      1) 伪通道 id（BOGUS_CHANNEL_IDS）：openclaw 快照里没有，报 "unknown channel id"。
      2) 空桩通道：channels.<id> 只有 enabled / 无实质字段——anyOf 类(twitch)必然校验失败，
         其余也无从工作。以 channel_entry_when_disabled 判定为 None 即空桩。channels.defaults 例外。
      3) 未配全的 web 搜索：tools.web.search 没同时给 enabled+provider+apiKey——provider 默认
         perplexity，未装插件即报 "web_search provider is not available"。

    只删「从未配过」的残留，绝不动用户已填实质字段的通道/搜索（那些是真配置）。"""
    removed = []
    if not isinstance(config, dict):
        return config, removed
    ch = config.get("channels")
    if isinstance(ch, dict):
        for cid in list(ch.keys()):
            if cid == "defaults":
                continue
            if cid in BOGUS_CHANNEL_IDS:
                del ch[cid]; removed.append("channels." + cid); continue
            entry = ch.get(cid)
            if not isinstance(entry, dict) or channel_entry_when_disabled(entry) is None:
                del ch[cid]; removed.append("channels." + cid)
    tools = config.get("tools")
    if isinstance(tools, dict):
        web = tools.get("web")
        if isinstance(web, dict):
            s = web.get("search")
            if isinstance(s, dict):
                ok = (bool(s.get("enabled"))
                      and str(s.get("provider") or "").strip() != ""
                      and str(s.get("apiKey") or "").strip() != "")
                if not ok:
                    web.pop("search", None); removed.append("tools.web.search")
                    if not web:
                        tools.pop("web", None)
    return config, removed


class ChannelEntry(NamedTuple):
    id: str
    label: str
    origin: str            # "builtin" | "plugin"
    installed: bool
    configured: bool
    accounts: tuple
    npm_spec: Optional[str]
    auth: str              # qr|token|webhook|oauth|builtin
    supports_qr: bool
    has_schema: bool
    apply_url: Optional[str]


class CapabilityEntry(NamedTuple):
    id: str
    label: str
    kind: str              # "provider" | "search"
    origin: str            # "builtin" | "plugin"
    installed: bool
    npm_spec: Optional[str]
    auth: Optional[str]
    env_var: Optional[str]
    apply_url: Optional[str]


# ---------- 官方外部插件目录解析 ----------

def _iter_json_objects(text):
    """扫描文本，产出每个平衡花括号块的 (start, end_exclusive)。字符串/转义感知。

    目录文件是 JS（外层 `{ entries: [...] }` 的 key 未加引号，json.loads 会失败），
    但每个条目对象自身是合法 JSON。故逐块尝试 json.loads，失败即跳过。
    """
    stack = []
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            stack.append(i)
        elif ch == "}":
            if stack:
                yield stack.pop(), i + 1


def parse_plugin_catalog(js_text):
    """解析 official-external-plugin-catalog-<hash>.js。

    返回 {"channels": {id: meta}, "providers": {id: meta}}。
    输入损坏时返回空目录（不抛异常）—— 目录解析是增强，不是命脉：
    通道 id 与安装状态来自 CLI，缺了包名只是退化成「复制安装命令」。
    """
    out = {"channels": {}, "providers": {}}
    if not js_text:
        return out
    for start, end in _iter_json_objects(js_text):
        chunk = js_text[start:end]
        if '"kind"' not in chunk or '"name"' not in chunk:
            continue
        try:
            obj = json.loads(chunk)
        except Exception:
            continue
        if not isinstance(obj, dict) or "kind" not in obj or "name" not in obj:
            continue
        oc = obj.get("openclaw") or {}
        if not isinstance(oc, dict):
            continue
        install = oc.get("install") or {}
        # 只有真有 install 块的才算「可安装插件」。不要拿 obj["name"] 兜底：
        # 那会把 bundled 条目误判成需安装，且包名可能根本不可 npm install。
        npm_spec = install.get("npmSpec")
        if obj["kind"] == "channel":
            chan = oc.get("channel") or {}
            cid = chan.get("id")
            if not cid:
                continue
            label = chan.get("selectionLabel") or chan.get("label") or cid
            out["channels"][cid] = {
                "npm_spec": npm_spec,
                "label": label,
                "supports_qr": "(QR" in label,
                "docs": chan.get("docsPath"),
            }
        elif obj["kind"] == "provider":
            for prov in oc.get("providers") or []:
                if not isinstance(prov, dict):
                    continue
                pid = prov.get("id")
                if not pid:
                    continue
                out["providers"][pid] = {
                    "npm_spec": npm_spec,
                    "label": prov.get("name") or pid,
                    "docs": prov.get("docs"),
                }
    return out


# ---------- CLI 输出解析 ----------

def parse_channels_list(json_text):
    """解析 `openclaw channels list --all --json`。

    顶层键 `chat`，每条 {accounts, installed, origin}。
    注意 origin ∈ {configured, installable, available} —— 它表示**配置状态**
    （available = 已装未配置），不是 builtin/plugin 这条轴（telegram 是内置通道，
    却也报 installable）。故此处只取状态，origin 由 build_catalog 从插件目录推导。
    """
    try:
        data = json.loads(json_text)
    except Exception:
        return {}
    chat = (data or {}).get("chat") or {}
    out = {}
    for cid, meta in chat.items():
        if not isinstance(meta, dict):
            continue
        accounts = tuple(meta.get("accounts") or ())
        out[cid] = {
            "installed": bool(meta.get("installed")),
            "configured": meta.get("origin") == "configured" or bool(accounts),
            "accounts": accounts,
        }
    return out


def parse_schema_channels(json_text):
    """解析 `openclaw config schema`，返回 {通道 id: 是否有可渲染的字段清单}。

    「键存在」不等于「有字段」：openclaw-weixin / twitch 在 schema 里，properties 却是空的；
    装上 wecom 插件后 schema 也只多出一个空壳键（实测）。这两类都必须走自由键值编辑器，
    否则 GUI 会渲染出一个没有任何输入框的表单。
    """
    try:
        data = json.loads(json_text)
    except Exception:
        return {}
    try:
        props = data["properties"]["channels"]["properties"]
    except Exception:
        return {}
    return dict((cid, bool((spec or {}).get("properties")))
                for cid, spec in props.items())


import re as _re_fields

_SECRET_NAME_RE = _re_fields.compile(
    r"(token|secret|key|password|apikey|appsecret|corpsecret)", _re_fields.I)


def _is_secret_name(name):
    return bool(_SECRET_NAME_RE.search(name or ""))


def _schema_kind(name, fspec):
    fspec = fspec or {}
    if fspec.get("enum"):
        return "select"
    if fspec.get("type") == "boolean":
        return "bool"
    if _is_secret_name(name):
        return "secret"
    return "text"


def parse_channel_fields(json_text):
    """解析 `openclaw config schema`，返回 {通道id: [字段dict]}。
    字段dict = {key(点路径), name, label, kind, secret, advanced, help, default, options}。
    advanced 先按 secret 反推（secret=主字段）；策展层可再提升，见 merge_field_overrides。
    空 properties 的通道返回 []（调用方走 free_kv）。"""
    try:
        data = json.loads(json_text)
    except Exception:
        return {}
    try:
        chans = data["properties"]["channels"]["properties"]
    except Exception:
        return {}
    out = {}
    for cid, spec in chans.items():
        props = ((spec or {}).get("properties")) or {}
        fields = []
        for fname, fspec in props.items():
            fspec = fspec or {}
            secret = _is_secret_name(fname)
            fields.append({
                "key": "channels.%s.%s" % (cid, fname),
                "name": fname, "label": fname,
                "kind": _schema_kind(fname, fspec),
                "secret": secret, "advanced": not secret,
                "help": fspec.get("description") or "",
                "default": fspec.get("default"),
                "options": list(fspec.get("enum") or []),
            })
        out[cid] = fields
    return out


def parse_models_providers(json_text):
    """解析 `openclaw models list --all --json`，返回**无需安装即可用**的 provider 前缀集。

    model key 形如 `zai/glm-5`。这些 provider 未装任何插件就能列出模型，故是内置的。
    这是区分「目录里有插件」与「必须装插件」的唯一可靠信号 —— 例如 zai 两者皆是，
    但它内置可用，不该被标成需安装。
    """
    try:
        data = json.loads(json_text)
    except Exception:
        return set()
    out = set()
    for model in (data or {}).get("models") or []:
        key = (model or {}).get("key") or ""
        if "/" in key:
            out.add(key.split("/", 1)[0])
    return out


# ---------- 合并 ----------

def build_catalog(channels_json, schema_json, catalog_js, models_json="",
                  openclaw_version=None):
    """把四份来源合并成规范化目录。

    硬规则：id 权威 = channels_json。不在其中的 id 一律不进结果 —— 这条规则挡掉了
    幻影通道（raft 确实存在于插件目录，但 openclaw 不把它列为可用通道）与内部通道
    （qa-channel 在 schema 里，但 CLI 不列）。
    """
    state = parse_channels_list(channels_json)
    schema_fields = parse_schema_channels(schema_json)
    model_builtin = parse_models_providers(models_json)
    plugin = parse_plugin_catalog(catalog_js)
    pchans = plugin["channels"]
    pprovs = plugin["providers"]

    channels = []
    for cid in sorted(state):
        st = state[cid]
        meta = pchans.get(cid) or {}
        label = meta.get("label") or _ov.CHANNEL_LABELS_ZH.get(cid) or cid
        supports_qr = bool(meta.get("supports_qr")) or cid in _ov.CHANNEL_QR_EXTRA
        npm_spec = meta.get("npm_spec")
        channels.append(ChannelEntry(
            id=cid,
            label=label,
            origin="plugin" if npm_spec else "builtin",
            installed=st["installed"],
            configured=st["configured"],
            accounts=st["accounts"],
            npm_spec=npm_spec,
            auth=_ov.CHANNEL_AUTH.get(cid, "token"),
            supports_qr=supports_qr,
            has_schema=schema_fields.get(cid, False),
            apply_url=_ov.CHANNEL_APPLY_URLS.get(cid),
        ))

    def _prov_origin(pid):
        """有模型即内置（无需装插件）；否则目录里有 install 才算需安装。

        zai/deepseek/cohere 等既在插件目录里、又能免安装列出模型 —— 必须判为 builtin，
        否则会误导用户去装一个根本不需要的插件。
        """
        if pid in model_builtin:
            return "builtin"
        return "plugin" if (pprovs.get(pid) or {}).get("npm_spec") else "builtin"

    providers = []
    seen = set()
    for pid, label, auth, env_var, apply_url in _ov.MODEL_PROVIDERS:
        pm = pprovs.get(pid) or {}
        origin = _prov_origin(pid)
        providers.append(CapabilityEntry(
            id=pid, label=label, kind="provider", origin=origin,
            installed=origin == "builtin",
            npm_spec=pm.get("npm_spec") if origin == "plugin" else None,
            auth=auth, env_var=env_var, apply_url=apply_url,
        ))
        seen.add(pid)
    # 目录里有、策展表没有的 provider 插件（amazon-bedrock / qwen / arcee 等）一并列出。
    # 它们是真实存在的 openclaw provider，不该因为没手抄进表就消失。
    for pid in sorted(pprovs):
        if pid in seen:
            continue
        origin = _prov_origin(pid)
        providers.append(CapabilityEntry(
            id=pid, label=pprovs[pid]["label"], kind="provider", origin=origin,
            installed=origin == "builtin",
            npm_spec=pprovs[pid]["npm_spec"] if origin == "plugin" else None,
            auth="api-key", env_var=None, apply_url=None,
        ))

    search = [
        CapabilityEntry(id=sid, label=sid, kind="search", origin="plugin",
                        installed=False, npm_spec=None, auth="api-key",
                        env_var=None, apply_url=url)
        for sid, url in sorted(_ov.SEARCH_APPLY_URLS.items())
    ]

    return {
        "channels": channels,
        "providers": providers,
        "search": search,
        "meta": {"openclaw_version": openclaw_version, "source": "live"},
    }


# ---------- 持久化与三级降级 ----------

CACHE_PATH = os.path.expanduser("~/.cache/chatop/openclaw-catalog.json")
FACTORY_PATH = "/usr/share/chatop/openclaw-catalog.json"

_ENTRY_TYPES = {"channels": ChannelEntry, "providers": CapabilityEntry,
                "search": CapabilityEntry}


def _to_jsonable(catalog):
    out = {"meta": dict(catalog.get("meta") or {})}
    for key in _ENTRY_TYPES:
        out[key] = [dict(e._asdict()) for e in catalog.get(key) or []]
    return out


def _from_jsonable(data):
    out = {"meta": dict(data.get("meta") or {})}
    for key, typ in _ENTRY_TYPES.items():
        rows = []
        for row in data.get(key) or []:
            kwargs = dict((f, row.get(f)) for f in typ._fields)
            if "accounts" in kwargs:
                kwargs["accounts"] = tuple(kwargs["accounts"] or ())
            rows.append(typ(**kwargs))
        out[key] = rows
    return out


def save_catalog(path, catalog):
    """原子写：先写 .tmp 再 rename，避免半截文件被下次启动读到。"""
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        try:
            os.makedirs(directory)
        except OSError:
            pass
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(_to_jsonable(catalog), fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _static_fallback():
    """③ 末级兜底：只有 overrides 的策展信息，无通道。

    通道 id 只能来自 CLI —— 宁可一个通道都不显示，也不凭空捏造。
    """
    built = build_catalog("", "", "")
    built["meta"] = {"openclaw_version": None, "source": "fallback"}
    return built


def load_catalog(cache_path=CACHE_PATH, factory_path=FACTORY_PATH):
    """三级降级：① 用户刷新缓存 → ② 构建期出厂快照 → ③ 静态兜底。永不抛异常。"""
    for path, source in ((cache_path, "cache"), (factory_path, "factory")):
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            catalog = _from_jsonable(data)
        except Exception:
            continue
        catalog["meta"]["source"] = source
        return catalog
    return _static_fallback()


# ---------- 实时采集（仅供刷新按钮 / 构建期快照调用，绝不在 GUI 启动路径） ----------

def _run(cmd, timeout=60):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = proc.communicate(timeout=timeout)
    if proc.returncode != 0:
        detail = (err or b"").decode("utf-8", "replace").strip()[-300:]
        raise RuntimeError("命令失败 rc=%s: %s\n%s"
                           % (proc.returncode, " ".join(cmd), detail))
    return out.decode("utf-8", "replace")


def parse_version(text):
    """从 `openclaw --version` 抽版本号。

    实际输出是 `OpenClaw 2026.6.10 (aa69b12)` —— 取 split()[-1] 会拿到 commit 哈希，
    不是版本号。取第一个形如数字开头的 token。
    """
    for token in (text or "").split():
        stripped = token.strip("()")
        if stripped and stripped[0].isdigit():
            return stripped
    return (text or "").strip() or None


def _find_catalog_js(openclaw_bin):
    """读 dist 里的官方插件目录。

    文件名带内容哈希（official-external-plugin-catalog-<hash>.js），随版本变，必须 glob。
    dist 里通常有**两份**：一份 external-only（20 通道），一份超集（26 通道，含 bundled）。
    取**最大的那份**，因为超集的中文名/QR 标记覆盖面更广。找不到返回 ""（降级，不致命）。
    """
    real = os.path.realpath(openclaw_bin)
    bin_dir = os.path.dirname(real)
    roots = [os.path.dirname(bin_dir),
             os.path.dirname(os.path.dirname(os.path.dirname(bin_dir)))]
    for root in roots:
        for pattern in (
            os.path.join(root, "lib", "node_modules", "openclaw", "dist",
                         "official-external-plugin-catalog-*.js"),
            os.path.join(root, "dist", "official-external-plugin-catalog-*.js"),
        ):
            hits = glob.glob(pattern)
            if not hits:
                continue
            biggest = max(hits, key=lambda p: os.path.getsize(p))
            try:
                with open(biggest, encoding="utf-8") as fh:
                    return fh.read()
            except Exception:
                return ""
    return ""


def collect(openclaw_bin="openclaw", timeout=60):
    """串行跑 CLI 采集目录（约 53s）。

    命令互不依赖、可并发（约 12s），但本机仅 7.3G 内存且生产容器常驻，
    并发会同起多个 node 进程 → 默认串行。
    """
    version = parse_version(_run([openclaw_bin, "--version"], timeout=15))
    channels_json = _run([openclaw_bin, "channels", "list", "--all", "--json"], timeout)
    schema_json = _run([openclaw_bin, "config", "schema"], timeout)
    models_json = _run([openclaw_bin, "models", "list", "--all", "--json"], timeout)
    catalog_js = _find_catalog_js(openclaw_bin)
    return build_catalog(channels_json, schema_json, catalog_js, models_json,
                         openclaw_version=version)


def main(argv=None):
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--snapshot" not in argv:
        sys.stderr.write("用法: python3.11 -m openclaw_catalog --snapshot [--out PATH] [--bin PATH]\n")
        return 2
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    binary = argv[argv.index("--bin") + 1] if "--bin" in argv else "openclaw"
    catalog = collect(openclaw_bin=binary)
    catalog["meta"]["source"] = "factory"
    if out:
        save_catalog(out, catalog)
        sys.stderr.write("已写入 %s（openclaw %s，%d 通道）\n"
                         % (out, catalog["meta"]["openclaw_version"], len(catalog["channels"])))
    else:
        json.dump(_to_jsonable(catalog), sys.stdout, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
