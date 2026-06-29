# S5 设计：noVNC 品牌 / 权限 / 文件传输 / 语言 / 主题

日期：2026-06-29
状态：已确认，待写实施计划
前置：S1（Linux 底座 / noVNC 注入管线）已通过自动化验证；S5 在其上做 noVNC 定制。
依赖风险：S1 的浏览器像素流核对需通过；若 noVNC 1.3.0 与镜像内置版本耦合异常，先锁版本再做 S5。

## 目标（参考 chatop，不照搬；KasmVNC 已有的不移除）

在 noVNC 前端 + 镜像配置上补充 5 项：名称、logo、文件上传/下载、权限配置、语言切换、主题切换。

## 已探明的 noVNC 结构（kasmtech/noVNC 1.3.0，vendored 在 `novnc-src/`）

- 控制栏：`index.html` 内 `#noVNC_control_bar`，按钮统一模式
  `<div class="noVNC_button_div"><input id="noVNC_xxx_button" class="noVNC_button"></div>`。
  现有按钮：拖拽 / 快捷键 / 电源 / 剪贴板 / 全屏 / 显示器 / 游戏模式 / 设置 / 断开 / 连接。
- 控制栏处理器集中在 `app/ui.js` 的 `addControlbarHandlers()`（约 line 478）。
- 设置面板：`#noVNC_settings_button` 触发；`app/ui.js` 有 `addOption()`、`initSetting()`、
  `getSetting()`、`forceSetting()` 等设置 API。
- 权限：剪贴板上/下行已是设置项 `clipboard_up` / `clipboard_down`（ui.js line 342-362），
  服务端对应 `kasmvnc.yaml` 的 `data_loss_prevention.clipboard.*`。
- i18n：`po/` 已含数百种语言（含 zh_CN/zh_TW/ja/ru/it/de/ko/fr/es…），gettext 机制，
  Vite 构建把 `app/locale` 拷进 `dist/app/locale`。**当前无运行时切换 UI**，只跟 `navigator.language`。

## 设计决策

### 1. 名称
- `index.html` 的 `<title>` 与连接/状态面板品牌串 → "察元AI"。
- 通过 noVNC 既有 i18n 串或直接改模板，保持可被翻译覆盖。

### 2. logo
- 替换 noVNC 连接/状态面板 logo 资源（recon 定位实际 logo 元素/资源路径）。
- 放置察元AI logo（项目根 `assets/logo.png`，构建期拷入）。

### 3. 文件上传/下载（旁挂 filebrowser + 控制栏按钮 + 内嵌 iframe 面板）
- **后端**：镜像内安装 `filebrowser`（单二进制 Go 程序），数据根 = 用户主目录
  （`/home/kasm-user` 或镜像实际家目录，recon 确认），后台启动；KasmVNC 内置 web server
  反代 `/files` → filebrowser（优先同源，贴近 chatop `/files` 体验）。
- **前端**：控制栏新增「上传」「下载」两个 `noVNC_button_div`（插在剪贴板按钮附近）；
  点击在 noVNC 内**弹一个 iframe 面板**加载 `/files`（不离开桌面页面）。
- **权限开关**：env 控制按钮显隐（允许上传 / 允许下载 可独立）+ filebrowser 只读/读写
  （只读=仅下载）。语义对齐 chatop 的 `SELKIES_FILE_TRANSFERS=upload,download`。

### 4. 权限配置（剪贴板）
- COPY 一份 `kasmvnc.yaml` 设默认（`data_loss_prevention.clipboard.server_to_client` /
  `client_to_server` 开关），与前端 `clipboard_up/down` 设置一致。
- 不移除 noVNC 既有剪贴板 UI，仅设默认 + 暴露开关。

### 5. 语言切换（全量）
- 设置面板加「语言」下拉。**动态枚举** `dist/app/locale` 实际存在的 locale（有多少列多少），
  不在代码里写死语言清单。母语名用 `Intl.DisplayNames` 生成（回退 locale 码）。
- 切换行为：写 `localStorage('chatop_lang')` **+ 刷新页面**；noVNC 的 l10n 在启动时按存储值
  加载对应翻译（最稳，避免运行时重渲染所有串的复杂度）。无翻译数据改动（po/ 已就绪）。

### 6. 主题切换（轻量）
- 设置面板加「主题」下拉：亮 / 暗（用户已表示主题深美化留后期）。
- 用 CSS 变量 + body class 切换 + `localStorage('chatop_theme')` 记忆。先做基础两档，不深美化。

## Dockerfile 扩展（在 S1 基础上）

- 安装 filebrowser + 写其配置（数据根、端口、禁注册、随密码）+ 启动脚本（接入 kasm 的启动流程）。
- 配置 KasmVNC 内置 web server 反代 `/files`（或独立端口，recon 定方案，优先同源）。
- COPY `kasmvnc.yaml`、`assets/logo.png`。
- 改版 noVNC（含 1-6）按已验证的 form B（Vite 构建）注入 `/usr/share/kasmvnc/www`。

## 非目标

- 深度主题美化（后期）。
- Windows（S2）、AI 智能体预装（S3）、察元AI 嵌入与开机自启（S4）。
- 不重编译 KasmVNC C++。

## 验证

- 构建出镜像启动后：控制栏出现上传/下载按钮；点击弹 iframe 面板加载 `/files`，能上传文件到桌面、
  能下载桌面文件；设置面板语言下拉切换后刷新生效并记忆；主题亮/暗切换生效并记忆；
  名称/logo 为察元AI；剪贴板权限默认按 kasmvnc.yaml；KasmVNC 原有功能全部仍在（回归核对）。
- 人工浏览器核对（同 S1，沿用一次会话验全部）。
