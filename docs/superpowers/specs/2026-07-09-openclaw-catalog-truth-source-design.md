# OpenClaw 配置器 P1：清单真源化设计

日期：2026-07-09
项目：`/work/chatop`（repo: chatop.git，分支 main）
对象：`openclaw-tool/`
上游 spec：`2026-07-09-openclaw-onestop-autoconfig-design.md`（本文档**修正**其中一处事实错误，见「对上一版 spec 的更正」）

## 分期

用户诉求拆为三期，本文档只覆盖 P1：

- **P1（本文档）**：清单真源化 —— 通道/厂商/搜索三份清单改由 openclaw 自身驱动。
- **P2**：扫码设置按钮 —— 支持二维码的通道后加按钮，走 `openclaw channels login`。
- **P3**：智能配置闭环 —— 配完自动 validate → 起网关 → 探活自检。

P2 依赖 P1（需要正确的通道身份与 `supports_qr` 元数据），P3 依赖 P1+P2。

## 背景：实证得到的 openclaw 能力模型

openclaw 2026.6.10 的能力分**两层**：

- **内置（builtin）**：25 个通道在 `openclaw config schema` 的 `channels.properties` 下；provider 有内置定义、读环境变量。
- **可安装插件（installable）**：官方外部插件目录含 21 plugin + 20 channel + 19 provider，须 `openclaw plugins install` 后才可用。

真源出口（均已实测）：

| 数据 | 来源 | 产出 |
|---|---|---|
| 通道 id 全集 + `installed/configured/enabled` | `openclaw channels list --all --json` | 27 个 id，顶层键 `chat` |
| 内置通道表单字段 | `openclaw config schema` → `channels.properties.<id>` | 25 个 |
| 外部插件包名 / 中文名 / QR 标记 / 文档路径 | `dist/official-external-plugin-catalog-<hash>.js` | 60 条目 |
| 模型目录 | `openclaw models list --all --json` | 142 模型 / 20 provider 前缀 |

### 关键实测事实

1. **CLI 慢**：`channels list --all` 12.3s、`models list --all --json` 10.3s、`plugins list` 10.5s、`config schema` 8.2s，**无热缓存**（`openclaw --version` 仅 0.18s，故慢的是 openclaw 初始化而非 node 启动）。四条串行约 43s。→ **启动路径禁止调 CLI**，必须快照。
2. **openclaw 自带中文标签**：目录中 `selectionLabel` 形如 `WeCom（企业微信）`、`Feishu/Lark (飞书)`、`Yuanbao (元宝)`，共 20 条。→ 中文名不需自维护。
3. **openclaw 自带 QR 标记**：`WhatsApp (QR link)`、`Zalo ClawBot (QR)`。→ P2 的扫码按钮判据由 openclaw 提供。
4. **provider id 是开放集**：`models.providers` 无 `properties`，`propertyNames` 为 `{"type":"string"}`。约束只有 `api`（10 种协议枚举）与 `auth`（`api-key|aws-sdk|oauth|token`）。→ **不存在"合法 provider 闭集"**。
5. **GUI 从不写 `models.providers.<id>`**：源码中 `models.providers` 与 `baseUrl` 各 0 次命中；厂商 Key 仅被写入 `config.env.<ENV_VAR>`。

## 问题诊断（机械根因）

`CHANNEL_PLUGINS`（20 条）包名**清一色 `@openclaw/<id>`**。openclaw 官方目录里 20 个外部通道包中，有 4 个由第三方厂商发布、不遵守该命名：

| 通道 | 真实包名 | 手抄表 |
|---|---|---|
| 企业微信 | `@wecom/wecom-openclaw-plugin` | 缺 |
| 微信 | `@tencent-weixin/openclaw-weixin` | 缺 |
| 元宝 | `openclaw-plugin-yuanbao` | 缺 |
| Zalo ClawBot | `@zalo-platforms/openclaw-zaloclawbot` | 缺 |

手抄表套用 `@openclaw/<id>` 的模式假设，**恰好漏掉的全是中国区最要紧的三个**。这就是「企业微信没在通道中显示配置」的根因。

派生缺陷：

- **幻影通道**：`webchat` / `voice-call` / `raft` 出现在 GUI，但 27 个真实 id 与 25 个 schema 键中均查无此项。
- **id 误写**：`zalo-personal`（真实为 `zalouser`）、provider `glm`（真实为 `zai`）、`bedrock`（真实为插件 `amazon-bedrock`）。
- **有名无实**：表中列出企业微信/Bedrock/百炼，但它们是未安装插件，点开配不了、配了不生效。

## 对上一版 spec 的更正

`2026-07-09-openclaw-onestop-autoconfig-design.md` 第 17 行称：

> 本轮**不做** WeCom/钉钉适配器（openclaw 无对应 channel 插件，需另写 Node 适配器，属独立子项目）

**该前提为假**。`@wecom/wecom-openclaw-plugin@2026.5.7` 存在于 openclaw 自带的官方外部插件目录，`kind: channel`；`openclaw channels list --all` 明确列出 `WeCom: not installed, not configured, disabled`。企业微信无需另写适配器，只需 `plugins install`。

该 spec 第 12 行列出的待补通道 `WebChat` / `Voice Call` / `Raft` 亦不存在于 openclaw，属虚构。

**教训**：上一版基于一个未经 CLI 核实的事实做了排除决策，且无任何机制让该错误暴露。本设计以「CLI 输出为唯一 id 权威」+「快照标注 openclaw 版本与生成时间」双重手段防止复发。

## 架构

新增 `openclaw-tool/openclaw_catalog.py`，不 import tkinter、import 时不调 CLI，作为三份清单的**唯一真源出口**。GUI 不再直接接触 CLI 或硬编码表。

```
openclaw-tool/
├─ openclaw_catalog.py      # 新增：目录服务（纯数据，可脱离 GUI 单测）
├─ catalog_overrides.py     # 新增：本地补充元数据（纯增强，删掉不影响功能）
├─ openclaw_config_gui.py   # 改：渲染 catalog.channels()，删 CHANNEL_PLUGINS
├─ openclaw_orchestrator.py # 改：auth 来自目录，对外契约不变
├─ openclaw_diagnostics.py  # 不变
└─ openclaw_qr.py           # 不变
```

### 数据模型

```python
@dataclass(frozen=True)
class ChannelEntry:
    id: str                 # openclaw 真实 id，如 "wecom"
    label: str              # 中文优先
    origin: str             # "builtin" | "installable"
    installed: bool         # ← CLI 权威
    configured: bool
    enabled: bool
    npm_spec: str | None    # 仅 installable
    auth: str               # qr|token|webhook|oauth|builtin
    supports_qr: bool       # ← P2 判据
    apply_url: str | None
```

Provider 与 Search 复用同一形状，去掉通道专属字段：

```python
@dataclass(frozen=True)
class CapabilityEntry:          # provider / search 共用
    id: str                     # openclaw 真实 id，如 "zai"、"amazon-bedrock"
    label: str
    kind: str                   # "provider" | "search"
    origin: str                 # "builtin" | "installable"
    installed: bool
    npm_spec: str | None
    auth: str | None            # provider: api-key|aws-sdk|oauth|token
    env_var: str | None         # provider: 写入 config.env 的变量名
    apply_url: str | None
```

`catalog.channels()` / `catalog.providers()` / `catalog.search()` 三个只读访问器，是 GUI 的全部入口。

### 合并规则（优先级从高到低）

1. `channels list --all --json` → id 全集 + 三态。**id 权威**。
2. `config schema` → `channels.properties.<id>` → 内置通道表单字段。
3. 官方插件目录 → `npm_spec` / `selectionLabel`（中文）/ QR 标记 / `docsPath`。
4. `catalog_overrides.py` → Key 申请地址等 openclaw 确实没有的信息。

**硬规则**：id 不在来源 1 中的一律不显示。幻影通道由此自动消失，且不可能再由手抄引入。

**中文名**取 `selectionLabel` > 本地补充 > `label` > `id`。**`supports_qr`** 取目录的 `(QR` 标记 > 本地补充。openclaw 新增通道时零改动即可获得中文名与 QR 判据。

## 快照、刷新与降级

三级读取：

```
① ~/.cache/chatop/openclaw-catalog.json     用户点「刷新清单」后写
② /usr/share/chatop/openclaw-catalog.json   构建期烤入的出厂快照
③ catalog_overrides 里的静态兜底
```

GUI 启动只读文件，**秒开**，启动路径永不调 CLI。此为硬约束：配置器打不开的代价极高（参见 XIM 段错误事故），不得依赖一个 12 秒且可能失败的外部进程。

**构建期**：Dockerfile 在装完 openclaw 的层之后执行
`python3 -m openclaw_catalog --snapshot > /usr/share/chatop/openclaw-catalog.json`。
该步**失败不阻断构建**（`|| true`），运行时落到 ③。镜像永远能出。

**运行期刷新**：GUI 增「刷新清单」按钮，后台线程串行跑四条 CLI（~43s），带进度与取消。成功才原子写 ①（`.tmp` → `rename`）；失败保留旧快照并显示错误，不静默吞掉。

**降级必须可见**。目录顶部状态条明示来源级别、openclaw 版本、快照生成时间：

```
清单来源：出厂快照（openclaw 2026.6.10，镜像构建于 2026-07-09）   [刷新清单]
```

## GUI 侧改动

通道行三形态：

| 状态 | 显示 | 主按钮 |
|---|---|---|
| `builtin` | 通道名 | 配置 |
| `installable` + 已装 | 通道名 | 配置 |
| `installable` + 未装 | 通道名 +「未安装」徽标 | **安装并配置** |

「安装并配置」= `plugins install <npm_spec>` → 重拉 `channels list --all --json` 确认 `installed: true` → 拉 `config schema` 取字段 → 渲染表单。每步以 openclaw 的回答为准，不假设成功。

**表单降级（必需路径）**：WeCom 目录条目的 `channelConfigs.wecom.schema` 为 `{"type":"object","additionalProperties":true}`，无 `properties`。装后 `config schema` 是否长出 `channels.properties.wecom` 字段清单，未经证实。故：取得到字段 → 结构化表单；取不到 → 自由键值编辑器（增减行）+ 目录 `docsPath` 的「查看官方文档」链接。同一插件不同版本暴不暴露 schema 都可能变，此降级为必需品。

`npm_spec` 缺失（目录解析失败）时，该通道仍显示（id 与状态来自 CLI），「一键安装」降级为「复制安装命令」。

### 硬编码表处置

- `CHANNEL_PLUGINS`（20 条）→ **删除**。信息 100% 被目录覆盖，且已被证明是错误来源。
- `MODEL_PROVIDERS`（41 条）→ **保留形态，修正内容**。因 provider id 是开放集，该表本就应是**策展清单**，性质无误。修正 `glm`→`zai`、`bedrock`→`amazon-bedrock`（且标为需安装插件），并为 19 个 provider 插件加「未安装」态。
- `WEB_SEARCH_PROVIDER_API_URLS`（5 条）→ 归入目录 `search` 维度，按插件处理。
- `CHINA_CHANNELS` / `CHANNEL_AUTH` 中的 `zalo-personal` / `webchat` / `voice-call` / `raft` → 按真实 id 校正或删除。

### 不做（YAGNI）

不改 `openclaw_qr.py` / `openclaw_orchestrator.py` / `openclaw_diagnostics.py` 的对外契约。P1 只替换其数据来源（orchestrator 的 `auth` 从目录取而非 `CHANNEL_AUTH`）。这三个模块在 P2/P3 才动。

## 测试策略

`openclaw_catalog.py` 可在宿主机直接单测。CLI 输出全部走 fixture，存入 `openclaw-tool/testdata/`（`channels-list.json`、裁剪版 `config-schema.json`、`plugin-catalog.js` 片段）。新增测试并入既有 `test_openclaw_modules.py`。

每条断言对应一个**已证实的真实缺陷**：

1. **企业微信可见且包名正确** — `id="wecom"`、`origin="installable"`、`installed=False`、`npm_spec="@wecom/wecom-openclaw-plugin@2026.5.7"`。此测试在当前代码上必须**红**。
2. **幻影通道被拒** — 即使本地补充表写了 `webchat`/`voice-call`/`raft`，结果中也不得出现。锁死「CLI 是 id 权威」。
3. **包名不靠命名假设** — 四个非 `@openclaw/*` 包名（wecom/weixin/yuanbao/zaloclawbot）取自目录而非拼接。防止 `@openclaw/<id>` 假设复活。
4. **中文名优先级** — `selectionLabel` 优先（`wecom` → `WeCom（企业微信）`），缺失落本地表，再缺落 `id`。
5. **`supports_qr` 由目录推导** — `whatsapp`、`openclaw-zaloclawbot` 为真；`slack` 为假。
6. **三级降级** — 缓存 → 出厂快照 → 静态兜底，末级不抛异常。
7. **目录解析失败不致命** — 喂损坏的 `plugin-catalog.js`，通道仍列出，`npm_spec is None`。
8. **provider id 校正** — `zai` 在表内、`glm` 不在；`amazon-bedrock` 标为需安装插件。

**必须真机验证、不以单测冒充**：`plugins install` 真能装上；装后 `config schema` 是否长出 `wecom` 字段；刷新按钮的 43 秒后台流程在 Tk 下不卡死。进 plan 的验收清单，在部署容器手工过一遍。

## 风险与诚实标注

- **`npm_spec` 依赖解析带内容哈希的 dist JS**（`official-external-plugin-catalog-<hash>.js`），升级即变名。做法：glob `official-external-plugin-catalog-*.js`；解析失败降级为「复制安装命令」。**目录解析是增强，不是命脉**。
- **Spike（进 plan）**：试 `openclaw plugins install wecom`。`plugins install --help` 称接受 "marketplace entry"，若认通道 id，则 `npm_spec` 与 JS 解析可整块删除。**在临时容器（`docker run --rm` 同镜像）中跑，不动生产容器**。
- **装后是否有 schema 未知** → 自由键值编辑器为必需降级路径。
- **`models auth login --provider <id>` 是否校验 id，本轮未验成**（TTY 检查先于 provider 校验短路）。故「`glm` 会让登录按钮失败」目前只是强推断。P1 仅修 id 本身（`glm`→`zai` 有独立证据：`zai` 有 14 个 GLM 模型，`glm` 前缀零模型）；登录按钮行为留 P3 在真 TTY 下验证。
- **刷新一次 ~43s**。四条 CLI 互不依赖、可并发（约 12s），但会同起四个 node 进程；本机仅 7.3G 内存且生产容器常驻 → **默认串行**，并发留作后续优化。
