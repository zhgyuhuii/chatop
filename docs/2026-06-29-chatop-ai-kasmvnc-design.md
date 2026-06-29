# 设计：chatop-ai —— 基于最新 KasmVNC 的定制云桌面

日期：2026-06-29
状态：已确认，待写实施计划
项目目录：`/work/chatop-ai`（独立 git 仓，不动 `/work/chatop`）

## 背景与目标

在**最新 KasmVNC 源码**之上新建一个独立项目 `chatop-ai`，做**纯加法式**定制：
KasmVNC 已有的能力一律保留、不移除不隐藏，只在其上"补充"以下能力：

1. 名称（品牌标题）
2. 图标 / logo
3. 权限配置（剪贴板上/下行）
4. 语言切换（i18n 切换器）
5. 主题切换
6. 文件**上传 / 下载**（左侧控制栏按钮 + 网页传输）

实现思路**参考 chatop（Selkies）但不照搬**：借鉴它的交互与"网页文件传输"模式，
用 KasmVNC 自己的机制独立实现，不把 Selkies 的代码搬过来。

## 关键事实（调研结论，决定架构）

1. **开源 KasmVNC 没有文件上传/下载**。README 开源功能清单只有剪贴板（含二进制
   剪贴板：文本/图片/富文本）+ 编码设置；无文件传输、无音频、无主题、无语言切换器。
   社区 issue #209 证实"standalone 文件传输"属于 Kasm Workspaces 平台（闭源）功能。
   → 上传/下载是本项目**唯一需要自己补的"硬"能力**，其余是前端/配置活。

2. **KasmVNC 的网页代码内置在它的 web server 里，以静态文件形式放在 www 目录**
   （如 `/usr/share/kasmvnc/www`）。→ 改前端**只需替换 www 目录文件，无需重编译 C++**。
   "基于 kasm 源码改" = 拉 `kasmtech/noVNC` 前端源码 → 改 → `npm build` → 覆盖 www。

3. **chatop/Selkies 的文件传输实测做法**：
   - 下载 = HTTP 文件端点 `/files`，前端是 `<iframe src="/files">` 文件列表
     （`selkies-src/.../dashboard/files.tsx:113`）。本质是网页文件服务器。
   - 上传 = 控制栏按钮触发 `requestFileUpload` 事件 → core 上传 + 进度提示。
   - → 即"旁挂一个网页文件服务"。这与本项目推荐的实现路线天然一致。

4. **最新 KasmVNC = 1.4.0**；Kasm 1.15 起控制面板 UI 已重设计（交互精简、docking
   tab 重排、移动端优化、移除 webpack）。这些新 UI **全部保留**。

## 架构

### 构建基座（纯加法）

```
FROM kasmweb/core-ubuntu-jammy        # 官方核心镜像，内置最新 KasmVNC，已有功能全保留
  └─ 注入改版 noVNC 前端（覆盖 www）   # 拉 kasmtech/noVNC 源码改 + 构建
  └─ COPY kasmvnc.yaml                 # 权限/DLP 配置
  └─ 安装 + 起 filebrowser（旁挂）     # 文件上传/下载后端
  └─ COPY 品牌资源（logo/标题）
```

- **不 fork-and-maintain 整个 KasmVNC C++ 仓**：避免长期维护重 fork 的负担。
- 仅在需要服务端级改动时才考虑全量 `builder/build.sh` 编译（当前需求不需要）。
- 选 `core-ubuntu-jammy`（核心镜像）而非 `ubuntu-jammy-desktop`：core 更小更干净，
  桌面环境 + 应用按需在 Dockerfile 里装；若后续要现成桌面再换 desktop 变体。
  （此点在第一阶段验证：core 是否自带可用桌面，否则改用 desktop 变体。）

### 六项补充的落点

| 补充 | 落点 | 参考 chatop |
|---|---|---|
| 名称 | noVNC 前端标题/品牌字符串 + 页面 title | 概念参考 |
| 图标 / logo | noVNC www 资源 + 控制栏图标 | 概念参考 |
| 权限配置（剪贴板上/下） | `kasmvnc.yaml` 的 `data_loss_prevention.clipboard.{server_to_client,client_to_server}.enabled`（COPY 配置） | — |
| 语言切换 | noVNC 控制栏加切换器，用 noVNC 自身 i18n（不照搬 Selkies translations.js） | 思路参考 |
| 主题切换 | noVNC 控制栏加主题切换器（亮/暗/品牌色等） | 思路参考 |
| **上传 / 下载** | 左侧控制栏加**上传/下载按钮** + 旁挂 **filebrowser** 映射用户主目录，复刻 chatop `/files` 网页传输体验 | **体验照搬，实现独立** |

### 文件上传/下载详细设计（复刻 chatop 的 `/files` 模式）

- 容器内运行轻量 `filebrowser`（单二进制 Go 程序），数据根映射到用户主目录
  （`~/` 或 `~/Desktop`，第一阶段定）。
- KasmVNC 内置 web server 反代 / 或独立端口暴露 filebrowser 到路径 `/files`。
- noVNC **左侧控制栏新增两个按钮**：
  - "下载"：打开 / 内嵌 `/files`（iframe 或新标签），用户从中下载容器内文件。
  - "上传"：打开 `/files` 上传界面（filebrowser 自带上传），把本地文件传进容器。
- **权限开关**：通过 env / 配置控制
  - 按钮显隐（是否允许上传 / 是否允许下载，可独立开关，对齐 chatop 的
    `SELKIES_FILE_TRANSFERS=upload,download` 语义）。
  - filebrowser 只读 / 读写（只读 = 仅下载）。

## 非目标（Non-goals，后期单独立项）

- 深度主题美化 / macOS 风外观还原。
- 镜像瘦身、桌面环境替换（XFCE 等）。
- 音频 / 麦克风 pass-through（开源 KasmVNC 同样缺，本期不补）。
- 应用安装/卸载商店（本期不做；如需，后期参考 chatop 的 proot-apps Manage Apps 另立项）。
- 全量 KasmVNC C++ 服务端改造（本期用旁挂方案规避）。

## 子项目分解与顺序（每个独立可验收）

1. **构建基座**：`core-ubuntu-jammy` + 改版 noVNC 能起来、能连、能看到桌面。
2. **名称 / 图标**：品牌标题 + logo 注入并显示。
3. **上传 / 下载**：旁挂 filebrowser + 控制栏按钮 + 权限开关。
4. **权限配置**：`kasmvnc.yaml` 剪贴板上/下行开关生效。
5. **语言切换**：控制栏语言切换器（至少中/英，记忆选择）。
6. **主题切换**：控制栏主题切换器。

> 本设计文档先落第 1 阶段（构建基座）的实施计划；后续阶段各自再出计划。

## 风险与未决点（第一阶段验证）

- `core-ubuntu-jammy` 是否自带可直接用的桌面会话；若无，改用 `ubuntu-jammy-desktop`
  变体作底座（不影响"加法"策略）。
- `kasmtech/noVNC` 当前源码结构与构建方式（npm build 产物目录、www 注入路径）需在
  第一阶段实地核对；KasmVNC 不同版本 www 路径可能不同，用 `dpkg -L` / 容器内 `find`
  确认实际路径，不凭印象写死。
- filebrowser 暴露方式：走 KasmVNC 内置 web server 反代 `/files`，还是独立端口 —
  第一阶段确定（优先同源 `/files` 以贴近 chatop 体验）。
- 品牌/主题/语言改动落在 noVNC 前端哪些文件，需在第一阶段把前端源码结构摸清后细化。

## 验证（总体）

- 每阶段构建出镜像并实际启动，浏览器访问验收对应能力。
- 文件传输：网页上传一个文件 → 桌面内可见；桌面内文件 → 网页可下载。
- 权限：关闭上传后按钮消失 / filebrowser 只读。
- 语言/主题：切换即时生效并刷新后记忆。
- 全程不移除 KasmVNC 原有能力（回归核对控制面板原功能仍在）。
