# S5 实施计划：noVNC 品牌 / 权限 / 文件传输 / 语言 / 主题

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 在 chatop-ai（底座 kasmweb 1.19.0 + 注入 noVNC 1.3.0）上补充 5 项：名称、logo、文件上传/下载（旁挂 filebrowser + 控制栏按钮 + 内嵌 iframe）、剪贴板权限默认、语言切换（全量动态枚举）、主题切换（轻量亮/暗），全程不移除 KasmVNC 既有能力。

**Architecture:** 改 vendored 的 `novnc-src/`（前端，Vite 构建注入 web 根），加 `kasmvnc.yaml`（权限），Dockerfile 装并启 `filebrowser` + 反代 `/files`。不重编译 C++。

**Tech Stack:** kasmtech/noVNC 1.3.0（Vite/原生 JS）、filebrowser（Go 单二进制）、KasmVNC 1.5.0 内置 web server、Docker。

**关键环境约束（每个 subagent 必须知道）：**
- Docker 必须 `sudo`（admin 不在 docker 组）。
- 磁盘紧（~9G），勿 prune，勿动镜像 `kasmweb/ubuntu-jammy-desktop:1.14.0` 与运行中的 `desktop` 容器（用户的）。
- 改前端后必须 Vite 重建镜像才生效；构建用 `sudo docker build`。
- 已确认：WWW_ROOT=`/usr/share/kasmvnc/www`；控制栏锚点 `#noVNC_control_bar`；按钮模式 `<div class="noVNC_button_div"><input id="noVNC_xxx_button" class="noVNC_button"></div>`；ui.js 有 `addControlbarHandlers()`/`addOption()`/`initSetting()`/`getSetting()`；剪贴板设置 `clipboard_up`/`clipboard_down` 已存在。

---

## File Structure（S5 改动/新增）

```
/work/chatop-ai/
  novnc-src/index.html               # 控制栏加上传/下载按钮 + iframe 面板容器；<title>/品牌
  novnc-src/app/ui.js                # 按钮处理器、语言下拉、主题下拉、iframe 面板开合
  novnc-src/app/styles/*.css         # 上传/下载按钮图标、iframe 面板、主题(亮/暗)CSS 变量
  novnc-src/app/locale/...           # (语言数据已存在，构建期生成；不手改)
  assets/logo.png                    # 察元AI logo（新增）
  kasmvnc.yaml                       # 剪贴板权限默认（新增，构建期 COPY）
  filebrowser/start-filebrowser.sh   # 启动脚本（新增，接入 kasm 启动流程）
  Dockerfile                         # 装 filebrowser + COPY kasmvnc.yaml/logo + 反代 /files
  docs/s5-recon.md                   # Task 1 产出：ui.js API/logo 元素/家目录/反代点
```

---

## Task 1: 侦察 noVNC UI 内部与镜像细节（先核实，不凭印象）

**Files:** Create `/work/chatop-ai/docs/s5-recon.md`

- [ ] **Step 1: 读 ui.js 的设置面板与 l10n API**

Run（在 `/work/chatop-ai/novnc-src`）：
```
grep -nE "addOption|initSetting|getSetting|forceSetting|addSetting|_languageChanged|l10n|locale|navigator.language|loadSetting|saveSetting" app/ui.js | head -40
sed -n '1,40p' core/util/localization.js 2>/dev/null || find . -name "localization*.js" -o -name "l10n*.js"
grep -nE "noVNC_setting_|noVNC_settings" index.html | head -40
```
记录到 s5-recon.md：①设置面板里现有 option 的 HTML 结构（一个 `<select>`/`<input>` 范例 + 其容器 id）；②如何新增一个设置下拉（addOption 的签名）；③l10n 模块如何决定语言（是否读 navigator.language，能否用 localStorage 覆盖后 reload 生效）。

- [ ] **Step 2: 定位 logo 元素与品牌串**

Run:
```
grep -nE "noVNC_logo|logo|noVNC_status|noVNC_connect_dlg|brand|<title>" index.html | head
ls app/images 2>/dev/null; ls public 2>/dev/null
grep -rnE "KasmVNC|noVNC" app/*.js index.html | grep -iE "title|brand|heading" | head
```
记录：logo 元素 id/资源路径、`<title>` 行、连接面板品牌串位置。

- [ ] **Step 3: 镜像侧细节（家目录 + KasmVNC web server 反代点 + 启动流程）**

Run:
```
sudo docker run -d --name s5-recon --shm-size=512m -e VNC_PW=recon123 chatop-ai:1.1.0 >/dev/null; sleep 6
# 家目录
sudo docker exec s5-recon bash -lc 'echo HOME=$HOME; id; ls -ld /home/* '
# KasmVNC 启动命令 + 是否能加反代/额外 location（看 Xvnc httpd 是否支持代理，或需独立端口）
sudo docker exec s5-recon bash -lc 'ps aux | grep -iE "Xvnc|kasmvnc|nginx" | grep -v grep'
# kasm 的自定义启动钩子目录（kasmweb 镜像支持 custom startup 脚本）
sudo docker exec s5-recon bash -lc 'ls -la /dockerstartup 2>/dev/null; ls -la /dockerstartup/custom_startup.sh 2>/dev/null; ls /etc/kasmvnc 2>/dev/null'
sudo docker rm -f s5-recon >/dev/null
```
记录：①容器内用户家目录（filebrowser 数据根）；②KasmVNC web server 是否能反代 `/files`，还是 filebrowser 走独立端口（如 `-p 8080`）由前端按 `location.hostname` 拼 URL；③kasm 镜像的自定义启动脚本挂载点（用来拉起 filebrowser）。

- [ ] **Step 4: 写 `docs/s5-recon.md` 并提交**

把以上确认值写成可被后续 Task 引用的参考；提交：
```
cd /work/chatop-ai && git add docs/s5-recon.md && git commit -m "docs(chatop-ai): S5 侦察 noVNC UI API/logo/家目录/反代点"
```

---

## Task 2: 品牌 —— 名称 + logo → 察元AI

**Files:** Modify `novnc-src/index.html`、(可能) `novnc-src/app/ui.js`；Create `assets/logo.png`

- [ ] **Step 1: 放置 logo**

把一张察元AI logo 存为 `/work/chatop-ai/assets/logo.png`（若暂无品牌图，用占位纯色 PNG，512x512，后续替换）。

- [ ] **Step 2: 改名称**

依据 `docs/s5-recon.md` 定位的 `<title>` 与品牌串，在 `novnc-src/index.html` 把标题改为 `察元AI`；连接/状态面板若有 "KasmVNC" 品牌串，改为 `察元AI`。**只改品牌展示串，不动功能元素 id。**

- [ ] **Step 3: 换 logo 资源**

依据 recon 定位的 logo 元素/资源，在 Dockerfile 增加把 `assets/logo.png` 拷到 noVNC logo 资源路径（或改 index.html 的 logo `src` 指向我们注入的文件）。具体路径以 recon 为准。

- [ ] **Step 4: 提交（构建验证留到 Task 8 统一做）**

```
cd /work/chatop-ai && git add novnc-src/index.html assets/logo.png && git commit -m "feat(chatop-ai): 品牌名称与 logo 改为察元AI"
```

---

## Task 3: 剪贴板权限默认（kasmvnc.yaml）

**Files:** Create `/work/chatop-ai/kasmvnc.yaml`；Modify `Dockerfile`

- [ ] **Step 1: 写 `kasmvnc.yaml`**（最小，仅设剪贴板上/下行默认；键名以 KasmVNC 1.5.0 文档为准，recon 时若发现镜像已有默认 yaml 可对照其结构）

```yaml
data_loss_prevention:
  clipboard:
    server_to_client:
      enabled: true
    client_to_server:
      enabled: true
```

- [ ] **Step 2: Dockerfile 增加 COPY**

在最终 stage 增加：
```dockerfile
COPY kasmvnc.yaml /etc/kasmvnc/kasmvnc.yaml
```
（实际路径以 Task 1 recon 的 `/etc/kasmvnc` 确认为准。）

- [ ] **Step 3: 提交**

```
cd /work/chatop-ai && git add kasmvnc.yaml Dockerfile && git commit -m "feat(chatop-ai): kasmvnc.yaml 设剪贴板上/下行权限默认"
```

---

## Task 4: filebrowser 旁挂（后端 + 启动 + 反代/暴露）

**Files:** Create `/work/chatop-ai/filebrowser/start-filebrowser.sh`；Modify `Dockerfile`

- [ ] **Step 1: 写启动脚本** `filebrowser/start-filebrowser.sh`

```bash
#!/usr/bin/env bash
# 启动 filebrowser，数据根=用户家目录，无认证(同源受 KasmVNC BasicAuth 保护)或随 VNC_PW
set -e
ROOT="${FB_ROOT:-$HOME}"
ADDR="127.0.0.1"
PORT="${FB_PORT:-8088}"
DB="/tmp/filebrowser.db"
filebrowser config init --database "$DB" >/dev/null 2>&1 || true
filebrowser config set --database "$DB" --root "$ROOT" --address "$ADDR" --port "$PORT" \
  --baseurl /files >/dev/null 2>&1 || true
# 只读由 FB_READONLY 控制(留待 Task 5 的权限开关)
exec filebrowser --database "$DB" --root "$ROOT" --address "$ADDR" --port "$PORT" --baseurl /files
```
（家目录、是否同源反代、baseurl 以 Task 1 recon 结论为准；若 KasmVNC web server 不能反代，则改为独立端口暴露并在 compose 加 `-p`。）

- [ ] **Step 2: Dockerfile 装 filebrowser + 接入启动**

在最终 stage：
```dockerfile
# 安装 filebrowser（官方安装脚本，单二进制）
RUN curl -fsSL https://raw.githubusercontent.com/filebrowser/filebrowser/master/get.sh | bash || \
    (curl -fsSL -o /tmp/fb.tar.gz https://github.com/filebrowser/filebrowser/releases/latest/download/linux-amd64-filebrowser.tar.gz \
     && tar -xzf /tmp/fb.tar.gz -C /usr/local/bin filebrowser && rm /tmp/fb.tar.gz)
COPY filebrowser/start-filebrowser.sh /usr/local/bin/start-filebrowser.sh
RUN chmod +x /usr/local/bin/start-filebrowser.sh
# 接入 kasm 自定义启动钩子（路径以 recon 的 /dockerstartup 为准）
RUN mkdir -p /dockerstartup && printf '#!/bin/bash\n/usr/local/bin/start-filebrowser.sh &\n' >> /dockerstartup/custom_startup.sh && chmod +x /dockerstartup/custom_startup.sh
```
（具体钩子机制以 recon 为准——kasmweb 支持 `/dockerstartup/custom_startup.sh` 或 `/custom_startup.sh`。）

- [ ] **Step 3: 提交**

```
cd /work/chatop-ai && git add filebrowser/start-filebrowser.sh Dockerfile && git commit -m "feat(chatop-ai): 旁挂 filebrowser(数据根=家目录, /files)"
```

---

## Task 5: 控制栏上传/下载按钮 + 内嵌 iframe 面板

**Files:** Modify `novnc-src/index.html`、`novnc-src/app/ui.js`、`novnc-src/app/styles/*.css`

- [ ] **Step 1: index.html 加两个控制栏按钮 + 一个 iframe 面板容器**

在 `#noVNC_control_bar` 内、剪贴板按钮附近，按现有 `noVNC_button_div` 模式加：
```html
<div class="noVNC_button_div noVNC_hide_on_disconnect" id="chatop_files_div">
  <input type="image" alt="文件" src="app/images/clipboard.svg"
         id="chatop_files_button" class="noVNC_button" title="文件上传/下载">
</div>
```
并在控制栏面板区（参考剪贴板面板 `noVNC_clipboard` 的结构）加一个可开合的 iframe 面板容器 `#chatop_files_panel`，内含 `<iframe id="chatop_files_iframe">`。具体 DOM 位置与 class 以 recon 的剪贴板面板范例对照实现。

- [ ] **Step 2: ui.js 加按钮处理器 + 面板开合 + iframe 懒加载**

在 `addControlbarHandlers()` 内仿 `addClickHandle('noVNC_clipboard_button', UI.toggleClipboardPanel)` 加：
```js
UI.addClickHandle('chatop_files_button', UI.toggleFilesPanel);
```
并实现 `toggleFilesPanel()`：开合 `#chatop_files_panel`，首次打开时给 `#chatop_files_iframe` 设 `src = '/files'`（同源；若 recon 定为独立端口，则 `https://${location.hostname}:8088/files`）。env 控制：若上传/下载被禁则不显示按钮（读取构建期注入的开关，见 Step 3）。

- [ ] **Step 3: 权限开关（按钮显隐）**

通过构建期写入一个 `window.CHATOP_FILES = { upload: true, download: true }`（由 Dockerfile/env 生成的小 JS 片段或 index.html 内联），ui.js 据此决定是否显示按钮 / filebrowser 是否只读（只读=仅下载，对应 Task 4 的 `FB_READONLY`）。语义对齐 chatop `SELKIES_FILE_TRANSFERS`。

- [ ] **Step 4: CSS**

在 `app/styles` 给按钮加图标、给 `#chatop_files_panel` 加面板样式（参考剪贴板面板样式）。

- [ ] **Step 5: 提交**

```
cd /work/chatop-ai && git add novnc-src/index.html novnc-src/app/ui.js novnc-src/app/styles && git commit -m "feat(chatop-ai): 控制栏上传/下载按钮 + 内嵌 filebrowser iframe 面板 + 权限开关"
```

---

## Task 6: 语言切换器（设置面板，全量动态枚举）

**Files:** Modify `novnc-src/index.html`、`novnc-src/app/ui.js`

- [ ] **Step 1: 设置面板加语言下拉**

在 `#noVNC_settings`（或 recon 定位的设置面板容器）加一个 `<select id="chatop_setting_language">`，仿现有设置项 HTML 结构。

- [ ] **Step 2: ui.js 动态填充 + 切换逻辑**

- 启动时：fetch/读取 noVNC 编译出的可用 locale 列表（recon 确定来源：`app/locale/` 下的清单或 l10n 模块暴露的列表）。**有多少列多少**，母语名用 `Intl.DisplayNames`（回退 locale 码）。
- 初值优先级：`localStorage('chatop_lang')` → `navigator.language` → `en`。
- `onChange`：`localStorage.setItem('chatop_lang', val)` 后 `location.reload()`。
- 启动早期（l10n 加载前）：若有 `localStorage('chatop_lang')`，覆盖 noVNC 的语言选择来源（recon 确认 l10n 取语言的 hook；最稳为在 l10n init 前把存储值赋给它读取的变量）。

- [ ] **Step 3: 提交**

```
cd /work/chatop-ai && git add novnc-src/index.html novnc-src/app/ui.js && git commit -m "feat(chatop-ai): 设置面板语言切换器(全量动态枚举+记忆+刷新生效)"
```

---

## Task 7: 主题切换器（轻量亮/暗）

**Files:** Modify `novnc-src/index.html`、`novnc-src/app/ui.js`、`novnc-src/app/styles/*.css`

- [ ] **Step 1: 设置面板加主题下拉**

加 `<select id="chatop_setting_theme">`，选项：暗(默认)/亮。

- [ ] **Step 2: CSS 主题变量**

在 `app/styles` 定义一套基础 CSS 变量（背景/前景/控件色），暗色为现状，亮色为一套浅色；通过 `body.chatop-theme-light` 覆盖。**只做基础两档，不深美化。**

- [ ] **Step 3: ui.js 切换 + 记忆**

启动读 `localStorage('chatop_theme')`（默认 dark）→ 给 body 加对应 class；`onChange` 写 localStorage + 即时切 class（无需 reload）。

- [ ] **Step 4: 提交**

```
cd /work/chatop-ai && git add novnc-src/index.html novnc-src/app/ui.js novnc-src/app/styles && git commit -m "feat(chatop-ai): 设置面板主题切换器(亮/暗+记忆)"
```

---

## Task 8: 构建 + 端到端验证（全部 S5 特性）

**Files:** 无新增（验证 + 收尾）

- [ ] **Step 1: 重建镜像**

```
cd /work/chatop-ai && sudo docker build --build-arg VERSION=$(cat VERSION) -t chatop-ai:$(cat VERSION) . 2>&1 | tail -8
```
Expected: web stage Vite 构建成功；filebrowser 安装成功；最终镜像导出。

- [ ] **Step 2: 启动并自动化验证**

```
cd /work/chatop-ai && sudo VERSION=$(cat VERSION) docker compose up -d && sleep 12
# 品牌：标题/ sentinel
curl -ks -u kasm_user:$(grep PASSWORD .env|cut -d= -f2) https://localhost:6901/index.html | grep -oE "<title>[^<]*" | head
# filebrowser 在线（同源 /files 或独立端口）
sudo docker exec chatop-ai bash -lc 'pgrep -a filebrowser; curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8088/files/ || true'
# 上传/下载按钮存在于注入前端
curl -ks -u kasm_user:$(grep PASSWORD .env|cut -d= -f2) https://localhost:6901/index.html | grep -c "chatop_files_button"
# 语言/主题设置项存在
curl -ks -u kasm_user:$(grep PASSWORD .env|cut -d= -f2) https://localhost:6901/index.html | grep -cE "chatop_setting_language|chatop_setting_theme"
sudo docker logs chatop-ai 2>&1 | tail -15
```
Interpret：title 含"察元AI"；filebrowser 进程在跑且 `/files` 返回 2xx/3xx；`chatop_files_button` 出现；语言/主题设置项出现。

- [ ] **Step 3: 标注人工浏览器核对清单**

只能人工的：登录后控制栏出现上传/下载按钮、点击弹 iframe 面板加载 filebrowser、上传一个文件桌面可见、下载桌面文件、语言下拉切换刷新后界面变对应语言并记忆、主题亮/暗即时切换并记忆、名称/logo 为察元AI、KasmVNC 原功能(剪贴板/全屏/设置)仍在。

- [ ] **Step 4: 停容器并提交收尾**

```
cd /work/chatop-ai && sudo docker compose down
git add -A && git commit -m "chore(chatop-ai): S5 构建与端到端验证收尾" || echo "无改动"
```

---

## Self-Review

**Spec coverage（对照 S5 设计文档）：** 名称→T2；logo→T2；权限(剪贴板)→T3；文件上传下载(filebrowser+按钮+iframe+开关)→T4/T5；语言切换(全量动态)→T6；主题(轻量亮暗)→T7；构建注入与验证→T8；"不移除 KasmVNC 已有"→各 Task 只加不删 + T8 回归核对。✓

**Placeholder scan：** 凡"以 recon 为准"的点都集中由 Task 1 显式产出 `docs/s5-recon.md`，后续 Task 引用——属"先核实再写死"的实测分支，非占位。具体 noVNC API（addOption 签名、l10n hook、logo 元素、kasm 启动钩子、家目录、反代可行性）由 Task 1 落定，实现 Task 的 subagent 据 recon 读源码写精确代码。

**一致性：** 元素 id（`chatop_files_button`/`chatop_files_panel`/`chatop_setting_language`/`chatop_setting_theme`）、localStorage 键（`chatop_lang`/`chatop_theme`）、filebrowser 端口(8088)/baseurl(`/files`) 在各 Task 间一致。

**风险：** ①KasmVNC 内置 web server 能否反代 `/files` 未定（Task 1 验，不行则独立端口）；②noVNC l10n 是否支持 localStorage 覆盖+reload 生效（Task 1 验，不行则退化为构建期固定或加载前注入）；③filebrowser 官方安装脚本网络可达性（Dockerfile 给了 release tar 回退）。
