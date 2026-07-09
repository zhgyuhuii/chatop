# OpenClaw 配置器 P1+P2+P3 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 openclaw-tool 配置器的通道/厂商/搜索三份清单由 openclaw 自身驱动（P1），为支持二维码的通道提供 GUI 内扫码登录（P2），并在配置后自动校验+起网关+探活形成闭环（P3）。

**Architecture:** 新增 `openclaw_catalog.py` 纯数据目录服务作为唯一真源出口，以 `channels list --all --json` 为 id 权威、`config schema` 为字段来源、openclaw 自带的官方外部插件目录为包名/中文名/QR 标记来源。CLI 每调 8–12s 且无热缓存，故构建期烤快照、运行期可刷新、三级降级，GUI 启动路径永不调 CLI。P2 复用既有 `openclaw_qr.py`（已完成）与 `openclaw_orchestrator.py` 的交接文件机制。P3 用 `config validate` / `doctor --json` / `gateway probe`。

**Tech Stack:** Python 3.6 兼容（宿主机 py3.6.8，容器 py3.10；`typing.NamedTuple` 而非 `dataclasses`）、tkinter、openclaw CLI 2026.6.10、手写测试 runner（非 pytest）。

---

## 关键实测事实（实现时不要重新推测，直接用）

| 事实 | 值 |
|---|---|
| CLI 耗时 | `channels list --all` 12.3s / `models list --all --json` 10.3s / `plugins list` 10.5s / `config schema` 8.2s；**无热缓存**；`--version` 0.18s |
| 通道 id 全集 | 27（`channels list --all --json` → 顶层键 `chat`，每条 `{accounts, installed, origin}`） |
| `origin` 取值 | 仅 `configured` / `installable` —— **是配置状态，不是 builtin/plugin 轴** |
| schema 通道键 | 25（含 `qa-channel`，它**不在** CLI 27 里） |
| 目录 channel 条目 | 20（`openclaw.channel.id` + `openclaw.install.npmSpec`） |
| 纯内置（无插件包） | `clickclack, imessage, irc, mattermost, signal, sms, telegram`（7） |
| 插件通道 | 20，其中 **17 个 schema 里已有字段**；**只有 `wecom` / `yuanbao` / `openclaw-zaloclawbot` 无 schema** |
| 四个非 `@openclaw/*` 包 | `wecom`→`@wecom/wecom-openclaw-plugin`；`openclaw-weixin`→`@tencent-weixin/openclaw-weixin`；`yuanbao`→`openclaw-plugin-yuanbao`；`openclaw-zaloclawbot`→`@zalo-platforms/openclaw-zaloclawbot` |
| provider 条目形状 | `openclaw.providers[] = {id, name, docs}` + `openclaw.install.npmSpec` |
| `models.providers` schema | 无 `properties`，`propertyNames = {"type":"string"}` → **provider id 是开放集** |
| 目录文件 | `<npm-global>/lib/node_modules/openclaw/dist/official-external-plugin-catalog-<hash>.js`（哈希随版本变，需 glob） |
| 容器内 openclaw | `/home/admin/.npm-global/bin/openclaw`；`docker` 需 `sudo` |

**幻影通道**（当前 GUI 有、openclaw 没有）：`webchat`、`voice-call`、`raft`。**误写 id**：`zalo-personal`（应 `zalouser`）、provider `glm`（应 `zai`）、`bedrock`（应 `amazon-bedrock`）。

---

## 文件结构

```
openclaw-tool/
├─ openclaw_catalog.py       # 新增：目录服务（纯数据，无 tkinter，py3.6 兼容）
├─ catalog_overrides.py      # 新增：本地补充元数据（纯增强，删掉不影响功能）
├─ testdata/                 # 新增：真实 CLI 产物 fixture
│   ├─ channels-list.json
│   ├─ config-schema-channels.json
│   └─ plugin-catalog-snippet.js
├─ openclaw_config_gui.py    # 改：渲染 catalog；删 CHANNEL_PLUGINS；扫码按钮；自检面板
├─ openclaw_orchestrator.py  # 改：auth 来自 catalog；QR 流程；run_all 闭环
├─ openclaw_diagnostics.py   # 改：加 config validate / doctor / gateway probe
├─ openclaw_qr.py            # 不改（已完成）
└─ test_openclaw_modules.py  # 改：新增 catalog 与 diagnostics 测试
Dockerfile                   # 改：构建期烤快照
```

**职责边界**：`openclaw_catalog.py` 只做「拿到文本 → 产出规范化条目」，不碰 tkinter、不在 import 时调 CLI。`catalog_overrides.py` 只有常量，无逻辑。GUI 只通过 `catalog.channels()/providers()/search()` 三个访问器取数。

---

## Task 1: 抓取真实 fixture

**Files:**
- Create: `openclaw-tool/testdata/channels-list.json`
- Create: `openclaw-tool/testdata/config-schema-channels.json`
- Create: `openclaw-tool/testdata/plugin-catalog-snippet.js`

- [ ] **Step 1: 从运行中的容器抓 CLI 产物**

```bash
cd /work/chatop/openclaw-tool && mkdir -p testdata
OC=/home/admin/.npm-global/bin/openclaw
sudo docker exec -u 1000 chatop-ai $OC channels list --all --json > testdata/channels-list.json
sudo docker exec -u 1000 chatop-ai $OC config schema > /tmp/oc-schema-full.json
sudo docker exec chatop-ai bash -c 'cat /home/admin/.npm-global/lib/node_modules/openclaw/dist/official-external-plugin-catalog-*.js' > testdata/plugin-catalog-snippet.js
```

- [ ] **Step 2: 裁剪 schema（全量 2.5MB，只留 channels 键与 models.providers 约束）**

```bash
python3 - <<'PY'
import json
d = json.load(open('/tmp/oc-schema-full.json'))
out = {
    "properties": {
        "channels": {"properties": {k: {"type": "object"} for k in d["properties"]["channels"]["properties"]}},
        "models": {"properties": {"providers": d["properties"]["models"]["properties"]["providers"]}},
    }
}
json.dump(out, open('testdata/config-schema-channels.json', 'w'), ensure_ascii=False, indent=1)
PY
```

- [ ] **Step 3: 验证 fixture 内容符合已知事实**

Run:
```bash
python3 - <<'PY'
import json
chat = json.load(open('testdata/channels-list.json'))['chat']
schema = json.load(open('testdata/config-schema-channels.json'))['properties']['channels']['properties']
js = open('testdata/plugin-catalog-snippet.js', encoding='utf-8').read()
assert len(chat) == 27, len(chat)
assert 'wecom' in chat and chat['wecom']['installed'] is False
assert len(schema) == 25 and 'qa-channel' in schema and 'wecom' not in schema
assert '@wecom/wecom-openclaw-plugin' in js
print('fixture OK: 27 channels / 25 schema keys / wecom package present')
PY
```
Expected: `fixture OK: 27 channels / 25 schema keys / wecom package present`

- [ ] **Step 4: 提交**

```bash
git add openclaw-tool/testdata
git commit -m "test(openclaw-tool): 抓取 openclaw 2026.6.10 真实 CLI 产物作为 catalog fixture"
```

---

## Task 2: 解析官方插件目录

**Files:**
- Create: `openclaw-tool/openclaw_catalog.py`
- Test: `openclaw-tool/test_openclaw_modules.py`

- [ ] **Step 1: 写失败的测试**

追加到 `test_openclaw_modules.py`（在 `import openclaw_orchestrator as orch` 后加 `import openclaw_catalog as cat`）：

```python
import json

_TESTDATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testdata")


def _fixture(name):
    with open(os.path.join(_TESTDATA, name), encoding="utf-8") as fh:
        return fh.read()


# ---- openclaw_catalog: 插件目录解析 ----
def test_plugin_catalog_channel_packages_not_guessed():
    """四个第三方发布的包名不遵守 @openclaw/<id>，必须来自目录而非拼接。"""
    entries = cat.parse_plugin_catalog(_fixture("plugin-catalog-snippet.js"))
    chans = entries["channels"]
    assert chans["wecom"]["npm_spec"].startswith("@wecom/wecom-openclaw-plugin")
    assert chans["openclaw-weixin"]["npm_spec"].startswith("@tencent-weixin/openclaw-weixin")
    assert chans["yuanbao"]["npm_spec"].startswith("openclaw-plugin-yuanbao")
    assert chans["openclaw-zaloclawbot"]["npm_spec"].startswith("@zalo-platforms/openclaw-zaloclawbot")
    for cid, meta in chans.items():
        assert meta["npm_spec"], cid


def test_plugin_catalog_chinese_labels_from_openclaw():
    entries = cat.parse_plugin_catalog(_fixture("plugin-catalog-snippet.js"))
    assert entries["channels"]["wecom"]["label"] == "WeCom（企业微信）"
    assert "飞书" in entries["channels"]["feishu"]["label"]


def test_plugin_catalog_qr_marker():
    entries = cat.parse_plugin_catalog(_fixture("plugin-catalog-snippet.js"))
    assert entries["channels"]["whatsapp"]["supports_qr"] is True
    assert entries["channels"]["openclaw-zaloclawbot"]["supports_qr"] is True
    assert entries["channels"]["slack"]["supports_qr"] is False


def test_plugin_catalog_providers():
    entries = cat.parse_plugin_catalog(_fixture("plugin-catalog-snippet.js"))
    provs = entries["providers"]
    assert provs["amazon-bedrock"]["npm_spec"] == "@openclaw/amazon-bedrock-provider"
    assert provs["amazon-bedrock"]["label"] == "Amazon Bedrock"
    assert "qwen" in provs


def test_plugin_catalog_corrupt_input_is_not_fatal():
    entries = cat.parse_plugin_catalog("this is not javascript {{{")
    assert entries == {"channels": {}, "providers": {}}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /work/chatop/openclaw-tool && python3 test_openclaw_modules.py 2>&1 | tail -5`
Expected: `FAIL test_plugin_catalog_*`，报 `ModuleNotFoundError: No module named 'openclaw_catalog'`

- [ ] **Step 3: 写实现**

创建 `openclaw-tool/openclaw_catalog.py`：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenClaw 配置器 — 目录服务（三份清单的唯一真源出口）。

设计要点（对齐 spec 2026-07-09-openclaw-catalog-truth-source-design.md）：
  * id 权威 = `openclaw channels list --all --json`；不在其中的 id 一律不显示。
  * 字段来源 = `openclaw config schema` 的 channels.properties。
  * 包名/中文名/QR 标记 = openclaw 自带的官方外部插件目录（dist JS，文件名带哈希）。
  * 本模块不 import tkinter、import 时不调 CLI，可在宿主机 py3.6 直接单测。
"""
import json
import os
from typing import NamedTuple, Optional


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

    目录文件是 JS（外层 `{ entries: [...] }` 的 key 未加引号），但每个条目对象
    自身是合法 JSON。故逐块尝试 json.loads，失败即跳过。
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
    输入损坏时返回空目录（不抛异常）——目录解析是增强，不是命脉。
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
        install = oc.get("install") or {}
        npm_spec = install.get("npmSpec") or obj.get("name")
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
                pid = prov.get("id")
                if not pid:
                    continue
                out["providers"][pid] = {
                    "npm_spec": npm_spec,
                    "label": prov.get("name") or pid,
                    "docs": prov.get("docs"),
                }
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /work/chatop/openclaw-tool && python3 test_openclaw_modules.py 2>&1 | tail -5`
Expected: `18 passed, 0 failed`

- [ ] **Step 5: 提交**

```bash
git add openclaw-tool/openclaw_catalog.py openclaw-tool/test_openclaw_modules.py
git commit -m "feat(openclaw-tool): catalog 解析官方外部插件目录（包名/中文名/QR 标记）"
```

---

## Task 3: 解析 CLI 通道列表与 schema

**Files:**
- Modify: `openclaw-tool/openclaw_catalog.py`
- Test: `openclaw-tool/test_openclaw_modules.py`

- [ ] **Step 1: 写失败的测试**

```python
def test_parse_channels_list():
    st = cat.parse_channels_list(_fixture("channels-list.json"))
    assert len(st) == 27
    assert st["wecom"] == {"installed": False, "configured": False, "accounts": ()}
    assert st["openclaw-weixin"] == {"installed": True, "configured": True, "accounts": ("default",)}


def test_parse_channels_list_bad_json():
    assert cat.parse_channels_list("not json") == {}


def test_parse_schema_channels():
    keys = cat.parse_schema_channels(_fixture("config-schema-channels.json"))
    assert len(keys) == 25
    assert "telegram" in keys and "qa-channel" in keys and "wecom" not in keys
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 test_openclaw_modules.py 2>&1 | tail -5`
Expected: `FAIL test_parse_channels_list`，报 `AttributeError: module 'openclaw_catalog' has no attribute 'parse_channels_list'`

- [ ] **Step 3: 写实现**

追加到 `openclaw_catalog.py`：

```python
# ---------- CLI 输出解析 ----------

def parse_channels_list(json_text):
    """解析 `openclaw channels list --all --json`。

    顶层键 `chat`，每条 {accounts, installed, origin}。origin ∈ {configured, installable}
    —— 它是配置状态，不是 builtin/plugin 轴，故此处只取状态，不推导 origin。
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
    """解析 `openclaw config schema`，返回内置通道字段键集合。"""
    try:
        data = json.loads(json_text)
    except Exception:
        return set()
    try:
        return set(data["properties"]["channels"]["properties"])
    except Exception:
        return set()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 test_openclaw_modules.py 2>&1 | tail -3`
Expected: `21 passed, 0 failed`

- [ ] **Step 5: 提交**

```bash
git add openclaw-tool/openclaw_catalog.py openclaw-tool/test_openclaw_modules.py
git commit -m "feat(openclaw-tool): catalog 解析 channels list --json 与 config schema"
```

---

## Task 4: 合并成通道目录（幻影拒绝 / origin 推导 / 中文名优先级）

**Files:**
- Create: `openclaw-tool/catalog_overrides.py`
- Modify: `openclaw-tool/openclaw_catalog.py`
- Test: `openclaw-tool/test_openclaw_modules.py`

- [ ] **Step 1: 写失败的测试**

```python
def _build_from_fixtures():
    return cat.build_catalog(
        channels_json=_fixture("channels-list.json"),
        schema_json=_fixture("config-schema-channels.json"),
        catalog_js=_fixture("plugin-catalog-snippet.js"),
        openclaw_version="2026.6.10",
    )


def test_build_wecom_visible_with_correct_package():
    """本轮的核心缺陷：企业微信必须出现，且包名不是拼接出来的。"""
    chans = {c.id: c for c in _build_from_fixtures()["channels"]}
    w = chans["wecom"]
    assert w.origin == "plugin"
    assert w.installed is False
    assert w.npm_spec.startswith("@wecom/wecom-openclaw-plugin")
    assert w.label == "WeCom（企业微信）"
    assert w.has_schema is False   # 未装 → 无字段 → GUI 走自由键值编辑器


def test_build_rejects_phantom_channels():
    """webchat/voice-call/raft 在 openclaw 里不存在；即便本地表写了也不得出现。"""
    chans = {c.id: c for c in _build_from_fixtures()["channels"]}
    for phantom in ("webchat", "voice-call", "raft", "zalo-personal"):
        assert phantom not in chans
    assert "qa-channel" not in chans   # schema 里有，但 CLI 不列 → 内部通道，不给用户看
    assert "zalouser" in chans         # 真实 id


def test_build_origin_axis():
    chans = {c.id: c for c in _build_from_fixtures()["channels"]}
    assert len(chans) == 27
    builtin = sorted(c.id for c in chans.values() if c.origin == "builtin")
    assert builtin == ["clickclack", "imessage", "irc", "mattermost", "signal", "sms", "telegram"]
    assert sum(1 for c in chans.values() if c.origin == "plugin") == 20


def test_build_free_kv_fallback_targets():
    """只有这 3 个插件通道没有 schema 字段。"""
    chans = {c.id: c for c in _build_from_fixtures()["channels"]}
    no_schema = sorted(c.id for c in chans.values() if not c.has_schema)
    assert no_schema == ["openclaw-zaloclawbot", "wecom", "yuanbao"]


def test_build_label_priority_and_qr():
    chans = {c.id: c for c in _build_from_fixtures()["channels"]}
    assert chans["wecom"].label == "WeCom（企业微信）"     # openclaw 自带中文
    assert chans["telegram"].label == "Telegram"          # 无目录条目 → 本地表/id
    assert chans["whatsapp"].supports_qr is True          # 目录 "(QR link)"
    assert chans["openclaw-weixin"].supports_qr is True   # 目录无标记 → 本地补充
    assert chans["slack"].supports_qr is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 test_openclaw_modules.py 2>&1 | tail -5`
Expected: `FAIL`，报 `has no attribute 'build_catalog'`

- [ ] **Step 3: 写 `catalog_overrides.py`**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地补充元数据 —— 只放 openclaw 确实不提供的信息。

**这张表是纯增强**：整个文件删掉，配置器功能不塌，只是少了中文名/申请链接。
这是它与被删除的 CHANNEL_PLUGINS 硬编码表的本质区别 —— 后者曾是 id 与包名的
唯一来源，一旦手抄出错（@openclaw/<id> 模式假设）就直接导致企业微信不可见。
绝不要在此文件里新增 openclaw 能回答的东西（id、包名、安装态）。
"""

# openclaw 目录未提供中文名的通道（多为纯内置通道）
CHANNEL_LABELS_ZH = {
    "telegram": "Telegram",
    "imessage": "iMessage",
    "signal": "Signal（信号）",
    "sms": "SMS（短信）",
    "irc": "IRC",
    "mattermost": "Mattermost",
    "clickclack": "ClickClack",
}

# openclaw selectionLabel 未标 "(QR" 但实际走扫码登录的通道
CHANNEL_QR_EXTRA = frozenset({"openclaw-weixin", "yuanbao", "zalouser"})

# 通道认证方式：qr|token|webhook|oauth|builtin。缺省 token。
CHANNEL_AUTH = {
    "whatsapp": "qr", "openclaw-weixin": "qr", "openclaw-zaloclawbot": "qr",
    "yuanbao": "qr", "zalouser": "qr", "signal": "qr",
    "imessage": "builtin", "clickclack": "builtin",
    "feishu": "token", "wecom": "token", "qqbot": "token", "telegram": "token",
    "slack": "token", "discord": "token", "line": "token", "twitch": "token",
    "msteams": "oauth", "googlechat": "oauth",
    "synology-chat": "webhook", "nextcloud-talk": "webhook",
}

# Key 申请地址（openclaw 不提供）
CHANNEL_APPLY_URLS = {
    "wecom": "https://work.weixin.qq.com/wework_admin/frame",
    "feishu": "https://open.feishu.cn/app",
    "qqbot": "https://q.qq.com/#/app/bot",
    "telegram": "https://core.telegram.org/bots#botfather",
    "slack": "https://api.slack.com/apps",
    "discord": "https://discord.com/developers/applications",
    "line": "https://developers.line.biz/console/",
    "msteams": "https://dev.teams.microsoft.com/",
}

# 策展的模型厂商清单。openclaw 的 models.providers 是开放集（propertyNames 仅约束为
# string），故此表性质上就该是策展清单，不是"合法集合"。
# 字段：(id, 中文名, auth, ENV_VAR, apply_url)
MODEL_PROVIDERS = [
    ("ollama", "Ollama（本地，无需登录）", None, None, None),
    ("openai", "OpenAI（GPT 系列）", "api-key", "OPENAI_API_KEY", "https://platform.openai.com/api-keys"),
    ("anthropic", "Anthropic Claude", "api-key", "ANTHROPIC_API_KEY", "https://console.anthropic.com/settings/keys"),
    ("deepseek", "DeepSeek（深度求索）", "api-key", "DEEPSEEK_API_KEY", "https://platform.deepseek.com/api_keys"),
    ("zai", "智谱 GLM（Z.ai）", "api-key", "ZAI_API_KEY", "https://open.bigmodel.cn/usercenter/apikeys"),
    ("moonshot", "月之暗面 Kimi", "api-key", "MOONSHOT_API_KEY", "https://platform.moonshot.cn/console/api-keys"),
    ("volcengine", "火山方舟（豆包）", "api-key", "VOLCENGINE_API_KEY", "https://console.volcengine.com/ark"),
    ("byteplus", "BytePlus", "api-key", "BYTEPLUS_API_KEY", None),
    ("tencent-tokenhub", "腾讯 TokenHub", "api-key", "TENCENT_TOKENHUB_API_KEY", None),
    ("xiaomi", "小米 MiMo", "api-key", "XIAOMI_API_KEY", None),
    ("mistral", "Mistral AI", "api-key", "MISTRAL_API_KEY", "https://console.mistral.ai/api-keys/"),
    ("cohere", "Cohere", "api-key", "COHERE_API_KEY", "https://dashboard.cohere.com/api-keys"),
    ("together", "Together AI", "api-key", "TOGETHER_API_KEY", "https://api.together.ai/settings/api-keys"),
    ("fireworks", "Fireworks AI", "api-key", "FIREWORKS_API_KEY", "https://fireworks.ai/account/api-keys"),
    ("novita", "Novita AI", "api-key", "NOVITA_API_KEY", "https://novita.ai/settings/key-management"),
    ("nvidia", "NVIDIA NIM", "api-key", "NVIDIA_API_KEY", "https://build.nvidia.com/"),
    ("venice", "Venice AI", "api-key", "VENICE_API_KEY", None),
    ("github-copilot", "GitHub Copilot", "oauth", None, "https://github.com/settings/copilot"),
    ("ollama-cloud", "Ollama Cloud", "api-key", "OLLAMA_API_KEY", None),
]

# openclaw 提供中文名的搜索插件（均为 plugin，需安装）
SEARCH_APPLY_URLS = {
    "tavily": "https://app.tavily.com/home",
    "brave": "https://api-dashboard.search.brave.com/app/keys",
    "perplexity": "https://www.perplexity.ai/settings/api",
    "firecrawl": "https://www.firecrawl.dev/app/api-keys",
    "searxng": None,
}
```

- [ ] **Step 4: 写 `build_catalog` 实现**

追加到 `openclaw_catalog.py`：

```python
import catalog_overrides as _ov

# ---------- 合并 ----------

def build_catalog(channels_json, schema_json, catalog_js, openclaw_version=None):
    """把三份来源合并成规范化目录。

    硬规则：id 权威 = channels_json。不在其中的 id 一律不进结果 —— 这条规则
    自动挡掉幻影通道（webchat/voice-call/raft）与内部通道（qa-channel）。
    """
    state = parse_channels_list(channels_json)
    schema_keys = parse_schema_channels(schema_json)
    plugin = parse_plugin_catalog(catalog_js)
    pchans = plugin["channels"]
    pprovs = plugin["providers"]

    channels = []
    for cid in sorted(state):
        st = state[cid]
        meta = pchans.get(cid) or {}
        label = (meta.get("label")
                 or _ov.CHANNEL_LABELS_ZH.get(cid)
                 or cid)
        supports_qr = bool(meta.get("supports_qr")) or cid in _ov.CHANNEL_QR_EXTRA
        channels.append(ChannelEntry(
            id=cid,
            label=label,
            origin="plugin" if cid in pchans else "builtin",
            installed=st["installed"],
            configured=st["configured"],
            accounts=st["accounts"],
            npm_spec=meta.get("npm_spec"),
            auth=_ov.CHANNEL_AUTH.get(cid, "token"),
            supports_qr=supports_qr,
            has_schema=cid in schema_keys,
            apply_url=_ov.CHANNEL_APPLY_URLS.get(cid),
        ))

    providers = []
    for pid, label, auth, env_var, apply_url in _ov.MODEL_PROVIDERS:
        pm = pprovs.get(pid) or {}
        providers.append(CapabilityEntry(
            id=pid, label=label, kind="provider",
            origin="plugin" if pid in pprovs else "builtin",
            installed=False, npm_spec=pm.get("npm_spec"),
            auth=auth, env_var=env_var, apply_url=apply_url,
        ))
    # 目录里有、策展表没有的 provider 插件，一并列出（如 amazon-bedrock / qwen）
    for pid in sorted(pprovs):
        if any(p.id == pid for p in providers):
            continue
        providers.append(CapabilityEntry(
            id=pid, label=pprovs[pid]["label"], kind="provider",
            origin="plugin", installed=False, npm_spec=pprovs[pid]["npm_spec"],
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
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python3 test_openclaw_modules.py 2>&1 | tail -3`
Expected: `26 passed, 0 failed`

- [ ] **Step 6: 提交**

```bash
git add openclaw-tool/openclaw_catalog.py openclaw-tool/catalog_overrides.py openclaw-tool/test_openclaw_modules.py
git commit -m "feat(openclaw-tool): catalog 合并三来源；CLI 为 id 权威，幻影通道自动消失"
```

---

## Task 5: provider id 校正断言

**Files:**
- Test: `openclaw-tool/test_openclaw_modules.py`

- [ ] **Step 1: 写测试（Task 4 的实现已应满足，此处锁死回归）**

```python
def test_provider_ids_corrected():
    provs = {p.id: p for p in _build_from_fixtures()["providers"]}
    assert "zai" in provs and "glm" not in provs        # GLM 的真实 id 是 zai
    assert "bedrock" not in provs                        # 真实 id 是 amazon-bedrock
    assert provs["amazon-bedrock"].origin == "plugin"    # 且是需安装的插件
    assert provs["amazon-bedrock"].npm_spec == "@openclaw/amazon-bedrock-provider"
    assert provs["zai"].origin == "builtin"              # 内置，无需装插件
    assert provs["openai"].env_var == "OPENAI_API_KEY"
```

- [ ] **Step 2: 跑测试**

Run: `python3 test_openclaw_modules.py 2>&1 | tail -3`
Expected: `27 passed, 0 failed`

- [ ] **Step 3: 提交**

```bash
git add openclaw-tool/test_openclaw_modules.py
git commit -m "test(openclaw-tool): 锁死 provider id 校正（glm→zai, bedrock→amazon-bedrock）"
```

---

## Task 6: 三级降级加载 + 原子写 + 快照入口

**Files:**
- Modify: `openclaw-tool/openclaw_catalog.py`
- Test: `openclaw-tool/test_openclaw_modules.py`

- [ ] **Step 1: 写失败的测试**

```python
import tempfile
import shutil


def test_load_catalog_three_tier():
    tmp = tempfile.mkdtemp()
    try:
        cache = os.path.join(tmp, "cache.json")
        factory = os.path.join(tmp, "factory.json")

        # ③ 两者皆缺 → 静态兜底，不抛异常
        c = cat.load_catalog(cache_path=cache, factory_path=factory)
        assert c["meta"]["source"] == "fallback"
        assert c["channels"] == []
        assert any(p.id == "openai" for p in c["providers"])

        # ② 只有出厂快照
        cat.save_catalog(factory, {"channels": [], "providers": [], "search": [],
                                   "meta": {"openclaw_version": "2026.6.10"}})
        c = cat.load_catalog(cache_path=cache, factory_path=factory)
        assert c["meta"]["source"] == "factory"

        # ① 缓存优先
        cat.save_catalog(cache, {"channels": [], "providers": [], "search": [],
                                 "meta": {"openclaw_version": "9999.1.1"}})
        c = cat.load_catalog(cache_path=cache, factory_path=factory)
        assert c["meta"]["source"] == "cache"
        assert c["meta"]["openclaw_version"] == "9999.1.1"
    finally:
        shutil.rmtree(tmp)


def test_save_catalog_is_atomic_and_roundtrips_namedtuples():
    tmp = tempfile.mkdtemp()
    try:
        path = os.path.join(tmp, "c.json")
        built = _build_from_fixtures()
        cat.save_catalog(path, built)
        assert not os.path.exists(path + ".tmp")
        back = cat.load_catalog(cache_path=path, factory_path=os.path.join(tmp, "none.json"))
        chans = {c.id: c for c in back["channels"]}
        assert isinstance(back["channels"][0], cat.ChannelEntry)
        assert chans["wecom"].npm_spec.startswith("@wecom/")
        assert chans["wecom"].supports_qr is False
        assert chans["whatsapp"].supports_qr is True
    finally:
        shutil.rmtree(tmp)


def test_load_catalog_corrupt_cache_falls_through():
    tmp = tempfile.mkdtemp()
    try:
        cache = os.path.join(tmp, "cache.json")
        with open(cache, "w") as fh:
            fh.write("{ broken")
        c = cat.load_catalog(cache_path=cache, factory_path=os.path.join(tmp, "none.json"))
        assert c["meta"]["source"] == "fallback"
    finally:
        shutil.rmtree(tmp)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 test_openclaw_modules.py 2>&1 | tail -5`
Expected: `FAIL`，报 `has no attribute 'load_catalog'`

- [ ] **Step 3: 写实现**

追加到 `openclaw_catalog.py`：

```python
# ---------- 持久化与三级降级 ----------

CACHE_PATH = os.path.expanduser("~/.cache/chatop/openclaw-catalog.json")
FACTORY_PATH = "/usr/share/chatop/openclaw-catalog.json"

_ENTRY_TYPES = {"channels": ChannelEntry, "providers": CapabilityEntry, "search": CapabilityEntry}


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
            kwargs = {f: row.get(f) for f in typ._fields}
            if "accounts" in kwargs:
                kwargs["accounts"] = tuple(kwargs["accounts"] or ())
            rows.append(typ(**kwargs))
        out[key] = rows
    return out


def save_catalog(path, catalog):
    """原子写：先写 .tmp 再 rename，避免半截文件被下次启动读到。"""
    directory = os.path.dirname(path)
    if directory:
        try:
            os.makedirs(directory)
        except OSError:
            pass
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(_to_jsonable(catalog), fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _static_fallback():
    """③ 末级兜底：只有 overrides 里的策展信息，无通道（通道 id 只能来自 CLI）。"""
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 test_openclaw_modules.py 2>&1 | tail -3`
Expected: `30 passed, 0 failed`

- [ ] **Step 5: 提交**

```bash
git add openclaw-tool/openclaw_catalog.py openclaw-tool/test_openclaw_modules.py
git commit -m "feat(openclaw-tool): catalog 三级降级加载 + 原子写"
```

---

## Task 7: 快照采集入口（`python3 -m openclaw_catalog --snapshot`）

**Files:**
- Modify: `openclaw-tool/openclaw_catalog.py`
- Modify: `Dockerfile`

- [ ] **Step 1: 追加 CLI 采集与 `__main__`**

```python
# ---------- 实时采集（仅供刷新按钮 / 构建期快照调用，绝不在 GUI 启动路径） ----------

import glob
import subprocess


def _run(cmd, timeout=60):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, _err = proc.communicate(timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError("命令失败 rc=%s: %s" % (proc.returncode, " ".join(cmd)))
    return out.decode("utf-8", "replace")


def _find_catalog_js(openclaw_bin):
    """dist 里的目录文件名带内容哈希，随版本变，必须 glob。找不到返回 ""。"""
    root = os.path.dirname(os.path.dirname(os.path.realpath(openclaw_bin)))
    pattern = os.path.join(root, "lib", "node_modules", "openclaw", "dist",
                           "official-external-plugin-catalog-*.js")
    hits = sorted(glob.glob(pattern))
    if not hits:
        return ""
    try:
        with open(hits[0], encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return ""


def collect(openclaw_bin="openclaw", timeout=60):
    """串行跑 CLI 采集目录（约 43s）。四条命令互不依赖，但本机内存紧，故不并发。"""
    version = _run([openclaw_bin, "--version"], timeout=15).strip().split()[-1]
    channels_json = _run([openclaw_bin, "channels", "list", "--all", "--json"], timeout)
    schema_json = _run([openclaw_bin, "config", "schema"], timeout)
    catalog_js = _find_catalog_js(openclaw_bin)
    return build_catalog(channels_json, schema_json, catalog_js, openclaw_version=version)


def main(argv=None):
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--snapshot" not in argv:
        sys.stderr.write("用法: python3 -m openclaw_catalog --snapshot [--out PATH] [--bin PATH]\n")
        return 2
    out = None
    binary = "openclaw"
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    if "--bin" in argv:
        binary = argv[argv.index("--bin") + 1]
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
```

- [ ] **Step 2: 在容器内实跑一次，验证真实采集与 fixture 一致**

Run:
```bash
sudo docker cp /work/chatop/openclaw-tool/openclaw_catalog.py chatop-ai:/tmp/oc/openclaw_catalog.py
sudo docker cp /work/chatop/openclaw-tool/catalog_overrides.py chatop-ai:/tmp/oc/catalog_overrides.py
sudo docker exec -u 1000 -w /tmp/oc chatop-ai python3 -m openclaw_catalog --snapshot --out /tmp/oc/snap.json \
  --bin /home/admin/.npm-global/bin/openclaw
sudo docker exec chatop-ai python3 -c "
import json; d=json.load(open('/tmp/oc/snap.json'))
ch={c['id']:c for c in d['channels']}
assert len(ch)==27, len(ch)
assert ch['wecom']['npm_spec'].startswith('@wecom/')
print('真机采集 OK:', d['meta']['openclaw_version'], len(ch), '通道; wecom 包名', ch['wecom']['npm_spec'])
"
```
Expected: `真机采集 OK: 2026.6.10 27 通道; wecom 包名 @wecom/wecom-openclaw-plugin@2026.5.7`

- [ ] **Step 3: Dockerfile 加构建期快照（失败不阻断构建）**

在 `Dockerfile` 的 `COPY openclaw-tool /opt/openclaw-tool`（第 181 行）与 `RUN chmod +x`（第 182 行）之后插入：

```dockerfile
# 构建期烤入 openclaw 目录快照：GUI 启动只读此文件，永不在启动路径调 CLI
# （CLI 每次 8-12s 且无热缓存）。采集失败不阻断构建，运行时降级到静态兜底。
RUN mkdir -p /usr/share/chatop && \
    (cd /opt/openclaw-tool && \
     su admin -c 'export PATH=/home/admin/.npm-global/bin:$PATH && \
       python3 -m openclaw_catalog --snapshot --out /tmp/oc-catalog.json' && \
     cp /tmp/oc-catalog.json /usr/share/chatop/openclaw-catalog.json && \
     echo "openclaw catalog snapshot OK") || \
    echo "WARN: openclaw catalog snapshot 失败，运行时将降级到静态兜底"
```

- [ ] **Step 4: 提交**

```bash
git add openclaw-tool/openclaw_catalog.py Dockerfile
git commit -m "feat(openclaw-tool): 快照采集入口 + Dockerfile 构建期烤入（失败不阻断构建）"
```

---

## Task 8: GUI 改用 catalog 渲染通道，删除 CHANNEL_PLUGINS

**Files:**
- Modify: `openclaw-tool/openclaw_config_gui.py:661-690`（删 `CHANNEL_PLUGINS` / 修 `CHINA_CHANNELS`）
- Modify: `openclaw-tool/openclaw_config_gui.py:2998-3061`（合并两处重复渲染）
- Modify: `openclaw-tool/openclaw_config_gui.py:2382`（删除 `pkg.split("/")[-1]` 假设）

- [ ] **Step 1: 删除 `CHANNEL_PLUGINS` 与幻影 id**

删除 `openclaw_config_gui.py` 第 661–687 行的整个 `CHANNEL_PLUGINS = [...]`。
把第 688 行改为（`yuanbao` 保留，它是真实 id）：

```python
CHINA_CHANNELS = ("feishu", "openclaw-weixin", "qqbot", "yuanbao", "wecom")
```

删除 `CHANNEL_AUTH`（第 692–705 行）整块 —— 它已迁入 `catalog_overrides.CHANNEL_AUTH`。把第 702 行的取值函数改为：

```python
def _channel_auth(channel_key):
    for c in _catalog()["channels"]:
        if c.id == channel_key:
            return c.auth
    return "token"
```

删除 `PAIRING_CHANNELS`（第 855 行起）中的 `webchat` / `voice-call` / `raft` / `zalo-personal` 四条；`zalo-personal` 改为 `zalouser`。

- [ ] **Step 2: 加模块级 catalog 惰性单例**

在 `openclaw_config_gui.py` 的 import 段之后加入：

```python
import openclaw_catalog

_CATALOG_CACHE = {"data": None}


def _catalog(force_reload=False):
    """GUI 侧的 catalog 惰性单例。只读文件，绝不在此调 CLI（启动路径禁调）。"""
    if force_reload or _CATALOG_CACHE["data"] is None:
        _CATALOG_CACHE["data"] = openclaw_catalog.load_catalog()
    return _CATALOG_CACHE["data"]
```

- [ ] **Step 3: 用单一函数替换两处重复渲染**

把 `add_tab_channels`（2998）里第 3009–3024 行与 `_refresh_channel_plugin_list`（3035）里第 3046–3061 行的重复循环，抽成一个方法并双方共用：

```python
    def _render_channel_plugin_grid(self):
        """按 catalog 渲染通道网格。三形态：内置 / 插件已装 / 插件未装（可勾选安装）。

        id 权威来自 catalog（即 `channels list --all --json`），故此处不可能再出现
        幻影通道，也不再用 `pkg.split("/")[-1]` 猜包名与 id 的关系。
        """
        frame = self._channel_plugin_frame
        for w in frame.winfo_children():
            w.destroy()
        self._channel_plugin_vars = []
        self._channel_plugin_widgets = []
        PLUGIN_COLS = 4
        rows = [c for c in _catalog()["channels"] if c.origin == "plugin"]
        for i, entry in enumerate(rows):
            var = tk.BooleanVar(value=False)
            self._channel_plugin_vars.append(var)
            gp = dict(row=i // PLUGIN_COLS, column=i % PLUGIN_COLS, sticky=tk.W, padx=6, pady=1)
            if entry.installed:
                w = _gui_label(frame, text="%s (已安装)" % entry.label)
            elif entry.npm_spec:
                w = _gui_checkbox(frame, text=entry.label, variable=var)
            else:
                # 目录解析失败 → 无包名 → 降级为「复制安装命令」，通道仍可见
                w = _gui_label(frame, text="%s (未安装，需手动)" % entry.label)
            w.grid(**gp)
            self._channel_plugin_widgets.append((entry, var, w))
```

`add_tab_channels` 中把第 3009–3024 行替换为 `self._render_channel_plugin_grid()`；
`_refresh_channel_plugin_list` 的方法体替换为：

```python
    def _refresh_channel_plugin_list(self):
        self.config = load_config()
        if isinstance(self.config, dict) and self.config.get("_load_error"):
            return
        if getattr(self, "_channel_plugin_frame", None):
            self._render_channel_plugin_grid()
```

- [ ] **Step 4: 修 2382 行的安装筛选**

```python
            to_install = [e for e in _catalog()["channels"]
                          if e.origin == "plugin" and not e.installed and e.npm_spec]
```

并把下游用 `(pkg, name)` 解包处改为用 `e.npm_spec` / `e.label`。

- [ ] **Step 5: 语法检查 + 回归测试**

Run:
```bash
cd /work/chatop/openclaw-tool && python3 -m py_compile openclaw_config_gui.py && echo COMPILE_OK
python3 test_openclaw_modules.py 2>&1 | tail -3
grep -c "CHANNEL_PLUGINS" openclaw_config_gui.py
```
Expected: `COMPILE_OK`；`30 passed, 0 failed`；`grep -c` 输出 `0`

- [ ] **Step 6: 提交**

```bash
git add openclaw-tool/openclaw_config_gui.py
git commit -m "fix(openclaw-tool): 通道列表改由 catalog 驱动，删除 CHANNEL_PLUGINS 硬编码表

企业微信/微信/元宝/Zalo ClawBot 由第三方发布，包名不遵守 @openclaw/<id>，
旧硬编码表按该模式假设手抄，恰好漏掉中国区最要紧的三个。同时删除
webchat/voice-call/raft 三个幻影通道，zalo-personal 更正为 zalouser。"
```

---

## Task 9: 未装插件的「安装并配置」+ 自由键值降级

**Files:**
- Modify: `openclaw-tool/openclaw_config_gui.py`

- [ ] **Step 1: 安装动作以 openclaw 的回答为准**

```python
    def _install_channel_plugin(self, entry, on_done=None):
        """装插件 → 重拉 catalog 确认 installed → 再渲染表单。每步以 openclaw 的回答为准。"""
        if not entry.npm_spec:
            self._copy_to_clipboard("openclaw plugins install %s" % entry.id)
            messagebox.showinfo("需手动安装",
                                "未能取得 %s 的插件包名（目录解析失败）。\n"
                                "安装命令已复制到剪贴板，请在终端执行。" % entry.label)
            return

        def work():
            rc, out = run_openclaw_cmd_sync(["plugins", "install", entry.npm_spec], timeout=300)
            if rc != 0:
                self.root.after(0, lambda: messagebox.showerror(
                    "安装失败", "%s 安装失败：\n%s" % (entry.label, out[-800:])))
                return
            fresh = openclaw_catalog.collect(openclaw_bin="openclaw")
            openclaw_catalog.save_catalog(openclaw_catalog.CACHE_PATH, fresh)
            _catalog(force_reload=True)
            now = {c.id: c for c in _catalog()["channels"]}.get(entry.id)
            if not now or not now.installed:
                self.root.after(0, lambda: messagebox.showerror(
                    "安装未生效", "%s 安装命令成功，但 openclaw 仍报告未安装。" % entry.label))
                return
            self.root.after(0, lambda: (self._render_channel_plugin_grid(),
                                        on_done and on_done(now)))

        threading.Thread(target=work, daemon=True).start()
```

- [ ] **Step 2: 无 schema 的通道走自由键值编辑器**

只有 `wecom` / `yuanbao` / `openclaw-zaloclawbot` 三个插件通道在 schema 里没有字段（已由 `test_build_free_kv_fallback_targets` 锁定）。装上后 openclaw 是否补出 schema **未经证实**，故此路径为必需品：

```python
    def _render_channel_form(self, parent, entry):
        """有 schema → 结构化表单；无 schema → 自由键值编辑器 + 官方文档链接。"""
        schema = load_oc_schema()
        fields = (((schema or {}).get("properties", {})
                   .get("channels", {}).get("properties", {})
                   .get(entry.id, {}) or {}).get("properties"))
        if fields:
            return self._render_schema_form(parent, entry, fields)
        return self._render_freeform_kv(parent, entry)

    def _render_freeform_kv(self, parent, entry):
        _gui_label(parent, text="%s 未向 openclaw 暴露字段清单，请按官方文档手工填写键值。"
                   % entry.label).pack(anchor=tk.W)
        if entry.apply_url:
            _gui_button(parent, text="查看官方文档 / 申请凭据",
                        command=lambda: webbrowser.open(entry.apply_url)).pack(anchor=tk.W, pady=2)
        rows_frame = _gui_frame(parent)
        rows_frame.pack(fill=tk.X, pady=4)
        rows = []

        def add_row(k="", v=""):
            rf = _gui_frame(rows_frame)
            rf.pack(fill=tk.X, pady=1)
            kv, vv = tk.StringVar(value=k), tk.StringVar(value=v)
            _gui_entry(rf, textvariable=kv, width_chars=22).pack(side=tk.LEFT, padx=2)
            _gui_entry(rf, textvariable=vv, width_chars=40).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
            _gui_button(rf, text="-", command=lambda: (rf.destroy(), rows.remove((kv, vv)))).pack(side=tk.LEFT)
            rows.append((kv, vv))

        existing = ((self.config.get("channels") or {}).get(entry.id) or {})
        for k, v in sorted(existing.items()):
            add_row(k, "" if isinstance(v, (dict, list)) else str(v))
        if not rows:
            add_row()
        _gui_button(parent, text="+ 添加一行", command=add_row).pack(anchor=tk.W)
        self._freeform_rows[entry.id] = rows
        return rows
```

在 `__init__` 里加 `self._freeform_rows = {}`。保存时把 `self._freeform_rows[cid]` 写回 `config["channels"][cid]`。

- [ ] **Step 3: 语法检查**

Run: `python3 -m py_compile openclaw_config_gui.py && echo COMPILE_OK`
Expected: `COMPILE_OK`

- [ ] **Step 4: 提交**

```bash
git add openclaw-tool/openclaw_config_gui.py
git commit -m "feat(openclaw-tool): 未装插件通道支持 GUI 内一键安装；无 schema 通道降级自由键值编辑器"
```

---

## Task 10: 「刷新清单」按钮 + 来源状态条

**Files:**
- Modify: `openclaw-tool/openclaw_config_gui.py`

- [ ] **Step 1: 状态条明示数据来源**

降级必须可见。上一版 spec 基于错误事实做决策却无从暴露，这条状态条就是防复发的机制：

```python
    def _catalog_source_text(self):
        meta = _catalog()["meta"]
        label = {"cache": "已刷新", "factory": "出厂快照", "fallback": "静态兜底（openclaw 不可用）"}
        ver = meta.get("openclaw_version") or "未知版本"
        return "清单来源：%s（openclaw %s，%d 通道）" % (
            label.get(meta.get("source"), meta.get("source")), ver, len(_catalog()["channels"]))

    def _build_catalog_bar(self, parent):
        bar = _gui_frame(parent)
        bar.pack(fill=tk.X, pady=2)
        self._catalog_lbl = _gui_label(bar, text=self._catalog_source_text())
        self._catalog_lbl.pack(side=tk.LEFT)
        self._catalog_btn = _gui_button(bar, text="刷新清单", command=self._refresh_catalog)
        self._catalog_btn.pack(side=tk.LEFT, padx=8)
```

- [ ] **Step 2: 后台刷新（约 43 秒，串行）**

```python
    def _refresh_catalog(self):
        """后台跑 CLI 重建目录。约 43s（channels 12s + schema 8s + 版本 0.2s，串行）。
        失败保留旧快照并显示错误，绝不静默吞掉。"""
        self._catalog_btn.config(state=tk.DISABLED, text="刷新中…")

        def work():
            try:
                fresh = openclaw_catalog.collect(openclaw_bin="openclaw", timeout=90)
                openclaw_catalog.save_catalog(openclaw_catalog.CACHE_PATH, fresh)
                _catalog(force_reload=True)
                err = None
            except Exception as exc:
                err = str(exc)

            def done():
                self._catalog_btn.config(state=tk.NORMAL, text="刷新清单")
                if err:
                    messagebox.showerror("刷新失败", "已保留原有清单。\n\n%s" % err)
                    return
                self._catalog_lbl.config(text=self._catalog_source_text())
                if getattr(self, "_channel_plugin_frame", None):
                    self._render_channel_plugin_grid()
            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()
```

在 `add_tab_channels` 开头调用 `self._build_catalog_bar(f)`。

- [ ] **Step 3: 语法检查 + 提交**

Run: `python3 -m py_compile openclaw_config_gui.py && echo COMPILE_OK`

```bash
git add openclaw-tool/openclaw_config_gui.py
git commit -m "feat(openclaw-tool): 清单来源状态条 + 刷新按钮（失败保留旧快照）"
```

---

## Task 11 (P2): 扫码按钮 —— 判据来自 openclaw

**Files:**
- Modify: `openclaw-tool/openclaw_orchestrator.py`
- Modify: `openclaw-tool/openclaw_config_gui.py`
- Test: `openclaw-tool/test_openclaw_modules.py`

`supports_qr` 已由 catalog 提供（目录的 `(QR` 标记 + `catalog_overrides.CHANNEL_QR_EXTRA`）。扫码按钮只出现在 `supports_qr=True` 的通道后面。

- [ ] **Step 1: 写失败的测试**

```python
def test_qr_channels_from_catalog():
    chans = {c.id: c for c in _build_from_fixtures()["channels"]}
    qr_ids = sorted(c.id for c in chans.values() if c.supports_qr)
    assert "whatsapp" in qr_ids and "openclaw-weixin" in qr_ids
    assert "openclaw-zaloclawbot" in qr_ids and "yuanbao" in qr_ids
    assert "slack" not in qr_ids and "wecom" not in qr_ids


def test_orchestrator_login_cmd():
    assert orch.build_login_cmd("whatsapp") == ["channels", "login", "--channel", "whatsapp"]
    assert orch.build_login_cmd("whatsapp", account="a1") == [
        "channels", "login", "--channel", "whatsapp", "--account", "a1"]


def test_orchestrator_handoff_path():
    assert orch.handoff_path("whatsapp").endswith("openclaw-oneclick-whatsapp.json")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 test_openclaw_modules.py 2>&1 | tail -5`
Expected: `FAIL test_orchestrator_login_cmd`，报 `has no attribute 'build_login_cmd'`

- [ ] **Step 3: 在 `openclaw_orchestrator.py` 加实现**

```python
import os

HANDOFF_DIR = "/tmp"


def handoff_path(channel_key):
    """终端子进程把 QR/状态写到这里，GUI watcher 轮询读取。"""
    return os.path.join(HANDOFF_DIR, "openclaw-oneclick-%s.json" % channel_key)


def build_login_cmd(channel_key, account=None):
    """`openclaw channels login` 是 openclaw 自带的扫码/授权入口（--help 实证）。"""
    cmd = ["channels", "login", "--channel", channel_key]
    if account:
        cmd += ["--account", account]
    return cmd
```

- [ ] **Step 4: GUI 加扫码按钮**

在通道行渲染处，`entry.supports_qr` 为真时追加：

```python
            if entry.supports_qr:
                _gui_button(row_frame, text="扫码设置",
                            command=lambda e=entry: self._open_qr_dialog(e)).pack(side=tk.LEFT, padx=4)
```

- [ ] **Step 5: 跑测试 + 提交**

Run: `python3 test_openclaw_modules.py 2>&1 | tail -3`
Expected: `33 passed, 0 failed`

```bash
git add openclaw-tool/openclaw_orchestrator.py openclaw-tool/openclaw_config_gui.py openclaw-tool/test_openclaw_modules.py
git commit -m "feat(openclaw-tool): 扫码通道判据来自 openclaw 目录；新增 channels login 命令构造"
```

---

## Task 12 (P2): 二维码弹窗（渲染 + 轮询 + 降级）

**Files:**
- Modify: `openclaw-tool/openclaw_config_gui.py`

`openclaw_qr.py` 的 `capture()` / `render_matrix_tk()` 已完成，直接复用，不改其契约。

- [ ] **Step 1: 弹窗实现**

```python
    def _open_qr_dialog(self, entry):
        """扫码登录：终端跑 channels login（日志可见、不卡 GUI），
        GUI 侧 watcher 轮询交接文件，拿到 QR 就渲染成图片。
        抓不到二维码 → 明确提示「在终端窗口扫码」，永不卡死。"""
        import openclaw_qr

        path = openclaw_orchestrator.handoff_path(entry.id)
        try:
            os.remove(path)
        except OSError:
            pass

        win = tk.Toplevel(self.root)
        win.title("扫码设置 — %s" % entry.label)
        status = _gui_label(win, text="正在启动 openclaw channels login …")
        status.pack(padx=12, pady=8)
        holder = _gui_frame(win)
        holder.pack(padx=12, pady=4)

        openclaw_orchestrator.spawn_login_in_terminal(entry.id, handoff=path)

        state = {"ticks": 0, "drawn": False, "closed": False}
        win.protocol("WM_DELETE_WINDOW", lambda: (state.update(closed=True), win.destroy()))

        def poll():
            if state["closed"]:
                return
            state["ticks"] += 1
            data = openclaw_orchestrator.read_handoff(path)
            if data and not state["drawn"]:
                source, matrix = openclaw_qr.capture(data)
                if matrix:
                    openclaw_qr.render_matrix_tk(holder, matrix).pack()
                    status.config(text="请用 %s 扫描上方二维码（来源：%s）" % (entry.label, source))
                    state["drawn"] = True
                elif data.get("qr_raw") or data.get("qr_ascii"):
                    status.config(text="二维码已在终端窗口显示，请在终端扫码。")
                    state["drawn"] = True
            if data and data.get("status") == "connected":
                status.config(text="已连接。可以关闭本窗口。")
                self._refresh_channel_plugin_list()
                return
            if state["ticks"] > 300:      # 5 分钟
                status.config(text="超时未连接。请检查终端窗口的输出。")
                return
            win.after(1000, poll)

        win.after(500, poll)
```

- [ ] **Step 2: `openclaw_orchestrator` 补两个辅助**

```python
import json
import subprocess


def read_handoff(path):
    """读交接文件；半截写入/不存在 → None（不抛异常）。"""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def spawn_login_in_terminal(channel_key, handoff):
    """在系统终端跑 channels login，输出经 tee 落到交接文件旁的 .log。

    长任务放终端：日志可见、不卡 GUI、扫码超时可由用户直接观察。
    """
    inner = ("openclaw %s 2>&1 | tee %s.log; echo '按回车关闭'; read"
             % (" ".join(build_login_cmd(channel_key)), handoff))
    for term in (["x-terminal-emulator", "-e"], ["xfce4-terminal", "-e"], ["xterm", "-e"]):
        try:
            subprocess.Popen(term + ["bash", "-lc", inner])
            return True
        except Exception:
            continue
    return False
```

- [ ] **Step 3: 语法检查 + 提交**

Run: `python3 -m py_compile openclaw_config_gui.py openclaw_orchestrator.py && echo COMPILE_OK`

```bash
git add openclaw-tool/openclaw_config_gui.py openclaw-tool/openclaw_orchestrator.py
git commit -m "feat(openclaw-tool): 扫码弹窗（GUI 内渲染二维码，抓不到降级到终端提示）"
```

---

## Task 13 (P3): 诊断加 config validate / doctor / gateway probe

**Files:**
- Modify: `openclaw-tool/openclaw_diagnostics.py`
- Test: `openclaw-tool/test_openclaw_modules.py`

三条命令均已实证存在：`openclaw config validate`（不启网关校验配置）、`openclaw doctor --json`、`openclaw gateway probe`。

- [ ] **Step 1: 写失败的测试**

```python
def test_diag_validate_ok():
    res = diag.check_config_valid(runner=lambda cmd, timeout=30: (0, "ok"))
    assert res["status"] == "ok"


def test_diag_validate_reports_reason():
    res = diag.check_config_valid(runner=lambda cmd, timeout=30: (1, "channels.wecom: required"))
    assert res["status"] == "fail"
    assert "channels.wecom" in res["detail"]


def test_diag_gateway_probe_unreachable():
    res = diag.check_gateway_probe(runner=lambda cmd, timeout=30: (1, "connection refused"))
    assert res["status"] == "fail"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 test_openclaw_modules.py 2>&1 | tail -5`
Expected: `FAIL test_diag_validate_ok`，报 `has no attribute 'check_config_valid'`

- [ ] **Step 3: 写实现**

```python
def check_config_valid(runner=None):
    """`openclaw config validate` —— 不启网关，纯 schema 校验。"""
    runner = runner or _default_runner
    rc, out = runner(["config", "validate"], timeout=30)
    if rc == 0:
        return {"key": "config_valid", "名称": "配置合法性", "status": "ok",
                "detail": "配置通过 schema 校验", "fix_action": None, "fix_label": None}
    return {"key": "config_valid", "名称": "配置合法性", "status": "fail",
            "detail": (out or "").strip()[-400:] or "校验失败（无输出）",
            "fix_action": None, "fix_label": "查看详情"}


def check_gateway_probe(runner=None):
    """`openclaw gateway probe` —— 可达性 + 认证能力。"""
    runner = runner or _default_runner
    rc, out = runner(["gateway", "probe"], timeout=30)
    status = "ok" if rc == 0 else "fail"
    return {"key": "gateway_probe", "名称": "网关可达性", "status": status,
            "detail": (out or "").strip()[-400:], "fix_action": None, "fix_label": None}
```

- [ ] **Step 4: 跑测试 + 提交**

Run: `python3 test_openclaw_modules.py 2>&1 | tail -3`
Expected: `36 passed, 0 failed`

```bash
git add openclaw-tool/openclaw_diagnostics.py openclaw-tool/test_openclaw_modules.py
git commit -m "feat(openclaw-tool): 体检加入 config validate 与 gateway probe"
```

---

## Task 14 (P3): 一键闭环 `run_all` —— 配完必须真的能跑

**Files:**
- Modify: `openclaw-tool/openclaw_orchestrator.py`
- Test: `openclaw-tool/test_openclaw_modules.py`

- [ ] **Step 1: 写失败的测试**

```python
def test_run_all_stops_at_invalid_config():
    """配置非法时不得继续起网关 —— 否则错误被网关启动失败掩盖。"""
    steps = []

    def fake(cmd, timeout=30):
        steps.append(cmd[0] + " " + cmd[1])
        if cmd[:2] == ["config", "validate"]:
            return 1, "models.providers.glm: unknown"
        return 0, ""

    result = orch.run_all(runner=fake)
    assert result["ok"] is False
    assert result["failed_step"] == "config_validate"
    assert "gateway start" not in steps      # 未继续


def test_run_all_happy_path_order():
    steps = []

    def fake(cmd, timeout=30):
        steps.append(" ".join(cmd[:2]))
        return 0, "ok"

    result = orch.run_all(runner=fake)
    assert result["ok"] is True
    assert steps == ["config validate", "gateway start", "gateway probe"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 test_openclaw_modules.py 2>&1 | tail -5`
Expected: `FAIL test_run_all_stops_at_invalid_config`

- [ ] **Step 3: 写实现**

```python
RUN_ALL_STEPS = (
    ("config_validate", ["config", "validate"], 30),
    ("gateway_start", ["gateway", "start"], 120),
    ("gateway_probe", ["gateway", "probe"], 30),
)


def run_all(runner=None, on_progress=None):
    """配置 → 校验 → 起网关 → 探活。任一步失败即停在原地并给出可读原因。

    顺序不可调：配置非法时若先起网关，真正的原因会被「网关启动失败」掩盖。
    """
    runner = runner or _default_runner
    for name, cmd, timeout in RUN_ALL_STEPS:
        if on_progress:
            on_progress(name, "running")
        rc, out = runner(cmd, timeout=timeout)
        if rc != 0:
            if on_progress:
                on_progress(name, "failed")
            return {"ok": False, "failed_step": name,
                    "detail": (out or "").strip()[-600:] or "无输出"}
        if on_progress:
            on_progress(name, "ok")
    return {"ok": True, "failed_step": None, "detail": "配置已生效，网关可达"}
```

- [ ] **Step 4: 跑测试 + 提交**

Run: `python3 test_openclaw_modules.py 2>&1 | tail -3`
Expected: `38 passed, 0 failed`

```bash
git add openclaw-tool/openclaw_orchestrator.py openclaw-tool/test_openclaw_modules.py
git commit -m "feat(openclaw-tool): run_all 闭环（校验→起网关→探活），失败停在原地不掩盖原因"
```

---

## Task 15: Spike —— `plugins install <channel-id>` 能否免包名

**Files:** 无（只产出结论，写入 spec 的风险节）

`plugins install --help` 称接受 "marketplace entry"。若它认通道 id，则 `npm_spec` 与整块 dist JS 解析可删除。

- [ ] **Step 1: 在一次性容器里试（不动生产容器）**

Run:
```bash
sudo docker run --rm --entrypoint bash chatop-ai:1.2.3 -lc \
  'export PATH=/home/admin/.npm-global/bin:$PATH; openclaw plugins install wecom 2>&1 | head -20'
```

- [ ] **Step 2: 记录结论**

- 若成功安装 → 在 spec 风险节标注「已证实：可用通道 id 安装」，并开后续任务删除 `_find_catalog_js` 与 `parse_plugin_catalog` 的 `npm_spec` 依赖（**保留** `label` / `supports_qr` 的解析，那部分无替代来源）。
- 若失败 → 标注「已证伪：必须用 npmSpec」，维持现状。

- [ ] **Step 3: 提交结论**

```bash
git add docs/superpowers/specs/2026-07-09-openclaw-catalog-truth-source-design.md
git commit -m "docs(openclaw-tool): 记录 plugins install <channel-id> spike 结论"
```

---

## Task 16: 真机验收

**Files:** 无（验收清单）

单测覆盖不了的，必须在部署容器里手工过一遍。**不以单测冒充真机验证。**

- [ ] **Step 1: 构建镜像（必须先停生产容器，否则导出 OOM）**

Run:
```bash
cd /work/chatop
sudo docker stop chatop-ai
sudo systemctl restart docker      # 回收 buildkit 累积内存（dockerd RSS 4.7G→90M）
free -h
./build-and-run.sh                 # 或 docker compose up -d --build
```
Expected: 构建成功；`docker ps` 见 `chatop-ai` 运行。
若构建失败：立刻 `sudo docker compose start` 用上一版镜像把桌面顶起来，别让用户干等。

- [ ] **Step 2: 验证出厂快照已烤入**

Run:
```bash
sudo docker exec chatop-ai python3 -c "
import json; d=json.load(open('/usr/share/chatop/openclaw-catalog.json'))
ch={c['id']:c for c in d['channels']}
print('通道数', len(ch), '| openclaw', d['meta']['openclaw_version'])
print('wecom:', ch['wecom']['label'], ch['wecom']['npm_spec'])
assert 'webchat' not in ch and 'raft' not in ch
print('OK')"
```
Expected: `通道数 27 | openclaw 2026.6.10` / `wecom: WeCom（企业微信） @wecom/wecom-openclaw-plugin@2026.5.7` / `OK`

- [ ] **Step 3: 桌面上打开配置器，逐项核对**

- [ ] 通道页出现「企业微信」，标「未安装」，且不再出现 webchat / voice-call / raft
- [ ] 状态条显示「清单来源：出厂快照（openclaw 2026.6.10，27 通道）」
- [ ] 点「刷新清单」→ 约 43 秒后状态条变「已刷新」，失败时弹错误且旧清单仍在
- [ ] 企业微信点「安装并配置」→ 装完 openclaw 报告 `installed: true` → 因无 schema，出现自由键值编辑器
- [ ] WhatsApp / 微信 后面出现「扫码设置」按钮；Slack 后面没有
- [ ] 点「扫码设置」→ 终端窗口起 `channels login`，GUI 弹窗渲染出二维码；抓不到时提示「在终端扫码」而非卡死
- [ ] 「一键全自动」跑完给出 `config validate → gateway start → gateway probe` 的逐步状态
- [ ] 配置器**不再段错误**（XIM 修复回归；`tk useinputmethods 0` 仍在 `__init__` 内）

- [ ] **Step 4: 记录真机结果**

把实测结果（含未通过项）如实写入本文件末尾的「真机验收结果」节，再提交。**未通过的项必须写明，不得省略。**

---

## 真机验收结果

（Task 16 执行后填写。未跑的项标「未验」，不得留空或写「应该可以」。）
