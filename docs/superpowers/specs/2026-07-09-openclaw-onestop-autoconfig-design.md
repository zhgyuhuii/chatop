# OpenClaw 配置器：一步到位编排 + 智能自动配置 设计

日期：2026-07-09
项目：`/work/chatop`（repo: chatop.git，分支 main）
对象：`chatop/openclaw-tool/openclaw_config_gui.py`

## 背景与问题

1. **监控失灵（已修）**：「刷新一览」检测不到 openclaw 运行状态。两处根因：
   - `check_gateway_running` 用 HTTP GET `/` 只认 2xx，网关根路径返回 404/401/426 就抛异常误报「未运行」。→ 已改为 **TCP 端口判活**。
   - `get_channel_connection_status` 裸调 `openclaw status --json`，GUI 由 `.desktop`(Terminal=false) 拉起不经登录 shell，PATH 无 nvm 装的 openclaw → FileNotFoundError 误报「无法获取」。→ 已改为 **`bash -lc` + 加载 nvm**（对齐 `run_openclaw_cmd_sync`）。
2. **通道缺国产/遗漏**：openclaw 已支持但 GUI 缺：腾讯元宝、WebChat、Zalo Personal、Voice Call、Raft。
3. **配置繁琐**：装插件、扫码登录、填 Token 分散手工操作，用户要「点一下就配好」。

## 范围（决策 A）

本轮**不做** WeCom/钉钉适配器（openclaw 无对应 channel 插件，需另写 Node 适配器，属独立子项目）。本轮聚焦：通道补齐（openclaw 已支持者）+ 一步到位编排 + 智能自动配置。

## 架构

新增 3 个同目录小模块，GUI 瘦身为界面装配：

```
openclaw-tool/
├─ openclaw_config_gui.py      # 界面装配（调下面模块）
├─ openclaw_diagnostics.py     # 体检：探测核心组件 → 状态清单（纯逻辑，无 tkinter）
├─ openclaw_orchestrator.py    # 一步到位状态机 + 一键全自动（无 tkinter）
└─ openclaw_qr.py              # 二维码捕获(3 策略)+ASCII→矩阵+渲染（渲染惰性导入 tkinter）
```

**混合编排（决策 C）**：装插件/`channels login` 等长任务在**终端**跑（日志可见、不卡 GUI），终端把 QR 数据/状态写入 `/tmp/openclaw-oneclick-<ch>.json` 交接文件；GUI 端 watcher 轮询读取，**二维码单独在 GUI 弹窗渲染成图片**。

## 组件契约

### openclaw_diagnostics
`probe(config, env) -> list[dict]`，每项：
```python
{"key","名称","status":"ok|fail|warn","detail","fix_action":callable|None,"fix_label"}
```
体检 7 项：nvm/Node、openclaw 已装、网关运行、模型可用、工作区、各已启用通道连接、网络。
判定复用已修的 `check_gateway_running`(TCP) 与 `get_channel_connection_status`(nvm)。

### openclaw_orchestrator
`run(channel_key, auth, callbacks) -> None`（后台线程，回调推进度）。通用状态机：
```
PRECHECK → PLUGIN_CHECK → [PLUGIN_INSTALL] → 按 auth 分支 → POLL_CONNECT → CONNECTED/TIMEOUT
```
auth 五分支：qr（login→QR 弹窗）/ token（填字段→验证→保存→重启）/ webhook（显示 URL→保存）/ oauth（开授权页）/ builtin（启用→保存→重启）。
`run_all()`：环境层→模型兜底(仅未配置)→起网关→遍历已启用通道→汇总。
错误处理：网络/网关/装插件/验证/超时 各步停在原地并给可读原因；**二维码抓不到 → 降级提示「在终端扫码」，永不卡死**。

### openclaw_qr
- `parse_ascii_qr(text) -> matrix|None`：解析 `██`/`▀▄` 半块 ASCII 码 → 0/1 矩阵（纯逻辑）。
- `encode_to_matrix(data) -> matrix|None`：有 `qrcode` 库时把原始串编码成矩阵（可选）。
- `render_matrix_tk(parent, matrix)`：Tk Canvas 画黑白方格（惰性 import tkinter，不依赖 qrcode/PIL）。
- `capture(handoff_file) -> ("raw"|"ascii"|None, data)`：3 策略择优，保底 None。

## 通道 auth 元数据（数据驱动）

每通道注册表加 `auth ∈ {qr,token,webhook,oauth,builtin}`。补齐 5 通道并打标。orchestrator 只 `switch(auth)`，加通道零改逻辑。

## 智能自动配置（决策 C + 模型策略 A）

- 体检面板每红项跟「修复/配置」按钮 = `orchestrator.run(ch)`。
- 顶部「一键全自动」= `orchestrator.run_all()`。
- **模型**：仅当 `model.primary` 空才自动兜底（探测 ollama），已配置不动。
- **无凭据的 token 通道**不阻塞一键流程，收尾列「待填 Token」。

## 第 7 节：测试策略

**可在本机跑的单元测试**（模块不顶层依赖 tkinter/openclaw）：
- `openclaw_qr`：喂已知 ASCII 二维码块（`██` 与 `▀▄` 两种编码）→ 断言矩阵尺寸与若干模块值；喂空/异常 → None。
- `openclaw_diagnostics.probe`：mock env/config/subprocess → 断言状态清单（openclaw 缺→fail+fix；网关停→fail；模型空→warn；工作区缺→fail）。
- 通道注册表完整性：每通道 `auth` 合法；补齐 5 通道存在。
- `orchestrator` 状态机：mock 各步 → 断言状态序列与错误分支（装插件失败即停；QR 抓不到→保底）。

**需真机（部署容器）验证、此处不跑**：真实 `channels login` 二维码捕获、真实 status 轮询、终端弹起。

**回归**：两处监控修复（TCP 判活、nvm 加载 status）。

## 风险与诚实标注

- Yuanbao/Zalo Personal/Voice Call/Raft 的确切 auth 方式官方未逐一写死 → 实现时 `channels login --help`/`channels add` 运行时探测确认，标错按实调整。
- `channels login` 二维码输出格式与 `qrcode` 库是否可用 → 运行时探测；三策略保证至少策略③可用，功能不因环境差异整体失效。
- 本机无 tkinter → GUI 接线仅能 `py_compile` + 逻辑单测保证，端到端交互需真机。
