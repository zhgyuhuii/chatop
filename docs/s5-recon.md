# S5 Task 1 — noVNC UI / 镜像侦察报告

本文件是 S5 计划 Task 1 的产出：对 vendored noVNC 源（`/work/chatop-ai/novnc-src/`，
kasmtech/noVNC 1.3.0，Vite 构建）与运行镜像（`chatop-ai:1.1.0`，base KasmVNC 1.19.0）
做只读侦察，给 Task 2–7 提供「照抄即可」的精确锚点。所有结论都附 `file:line` 或命令输出证据。

侦察方法：源码取自 `novnc-src/`；镜像态用临时容器 `s5-recon`（基于 `chatop-ai:1.1.0`，
侦察后已 `docker rm -f`）。未触碰用户的 `desktop` 容器 / `kasmweb/ubuntu-jammy-desktop:1.14.0` 镜像。

---

## A. 设置面板 + 如何新增一个下拉设置（Task 6/7 模板）

### A.1 关键函数签名（`novnc-src/app/ui.js`）

**`addOption` 定义 —— ui.js:3523**
```js
addOption(selectbox, text, value) {
    const optn = document.createElement("OPTION");
    optn.text = text;       // 显示文本（option 的 label）
    optn.value = value;     // option 的 value
    selectbox.options.add(optn);
},
```
- 签名确认：`UI.addOption(selectElement, label, value)`。`selectbox` 必须是一个 `<select>` DOM 节点。
- 典型用法（ui.js:252）：`UI.addOption(document.getElementById('noVNC_setting_logging'), llevels[i], llevels[i]);`
- 另一处动态填充 option（不走 addOption，直接 appendChild，ui.js:269-271）也可参考：
  ```js
  let qualityDropdown = document.getElementById("noVNC_setting_video_quality");
  qualityDropdown.appendChild(Object.assign(document.createElement("option"),{value:0,label:"Static"}))
  ```

**设置读写 API（`UI.` 命名空间，ui.js 内）**
- `UI.initSetting(name, defaultValue)` — 注册一个设置并给默认值（在 `initSettings()` 里，ui.js:248 起，大量调用）。
- `UI.getSetting(name)` — 读取当前值（如 ui.js:347 `UI.getSetting('clipboard_seamless')`）。
- `UI.forceSetting(name, value)` — 强制写入（如 ui.js:351）。
- `WebUtil.initSettings()` 在 `UI.start()` 早期被 await（ui.js:102），随后 `UI.initSettings()`（ui.js:130）。
- 设置值持久化在 localStorage（noVNC 标准行为，由 WebUtil 管理）。

### A.2 一个现存「下拉设置」的完整 HTML 结构（template）

设置面板容器：`<div id="noVNC_settings" class="noVNC_panel">`（index.html:216），
由设置按钮 `#noVNC_settings_button`（index.html:213）切换。面板内每一项是一个 `<li>`。

**最干净的下拉模板 —— Idle Timeout（index.html:316-323）**
```html
<li class="noVNC_hidden">
    <label for="noVNC_setting_idle_disconnect">Idle Timeout:</label>
    <select id="noVNC_setting_idle_disconnect" name="vncIdleDisconnect">
        <option value=10>10</option>
        <option value=20>20</option>
        <option value=30>30</option>
        <option value=60>60</option>
    </select>
</li>
```

**Scaling Mode（index.html:332-340，带分隔条 `<li><hr></li>`）**
```html
<li>
    <label for="noVNC_setting_resize">Scaling Mode:</label>
    <select id="noVNC_setting_resize" name="vncResize">
        <option value="off">None</option>
        <option value="scale">Local Scaling</option>
        <option value="remote">Remote Resizing</option>
    </select>
</li>
```

**复选开关（switch）模板（index.html:222-225，给布尔设置用）**
```html
<li>
    <label class="switch"><input id="noVNC_setting_shared" type="checkbox">
        <span class="slider round"></span>
        <span class="slider-label">Shared Mode</span>
    </label>
</li>
```

### A.3 给 Task 6/7 的落点
- 新增「语言 / 主题」下拉 → 在 `#noVNC_settings` 面板里照 A.2 的 `<li><label><select id="noVNC_setting_xxx">` 模板加一项。
- 命名约定：`id="noVNC_setting_<name>"`。`<select>` 的 id 前缀必须是 `noVNC_setting_`，
  这样能与 `UI.initSetting('<name>', ...)` / `UI.getSetting('<name>')` 体系对齐（前缀映射见 ui.js 大量调用）。
- option 既可在 HTML 里静态写，也可 `UI.addOption(selectEl, label, value)` 动态填。
- 注意：面板里很多 `<li>` 标了 `class="noVNC_hidden"`（如 idle_disconnect），按需用 JS 取消隐藏。

---

## B. l10n / 语言机制（Task 6 必读）

### B.1 模块结构
- l10n 实现：`novnc-src/app/localization.js`（`class Localizer`，导出单例 `export const l10n`，
  默认导出 `l10n.get.bind(l10n)`）。
- 在 ui.js 引入：`import _, { l10n } from './localization.js';`（ui.js:37）。`_` 即 `l10n.get`，翻译函数。

### B.2 当前语言如何决定（核心证据）
**`Localizer.setup(supportedLanguages)`（localization.js:23-85）读 `navigator.languages` / `navigator.language`：**
```js
setup(supportedLanguages) {
    this.language = 'en';                       // 默认 US English
    let userLanguages;
    if (typeof window.navigator.languages == 'object') {
        userLanguages = window.navigator.languages;
    } else {
        userLanguages = [navigator.language || navigator.userLanguage];
    }
    // 逐个 userLanguage 与 supportedLanguages 做 perfect / fallback 匹配，
    // 命中即 this.language = supportedLanguages[j]; return;
}
```
- **结论：默认就是读浏览器的 `navigator.languages`（首选）/`navigator.language`。** 不读 localStorage、不读任何持久设置。
- `this.language` 字段（localization.js:16）保存最终语言；`this.dictionary`（:19）保存翻译字典。

### B.3 启动时序（ui.js 文件底部，3537-3550）
```js
const LINGUAS = ["af", ... , "zh_CN", "zh_TW", "zu", "zu_ZA"];   // ui.js:3537，可用 locale 白名单
l10n.setup(LINGUAS);                                             // ui.js:3538，按 navigator 选语言
if (l10n.language === "en" || l10n.dictionary !== undefined) {
    UI.prime();                                                  // 英文/已有字典：直接启动
} else {
    fetch('app/locale/' + l10n.language + '.json')               // ui.js:3542，按语言码拉字典
        .then(... response.json())
        .then((translations) => { l10n.dictionary = translations; })
        .catch(err => Log.Error(...))
        .then(UI.prime);
}
```
- 翻译应用点：`l10n.translateDOM()`（ui.js:134，在 UI 初始化里遍历 DOM 替换文本）。
- `_(id)` / `l10n.get(id)` 在 dictionary 命中时返回译文，否则回退原文（localization.js:88-94）。

### B.4 可用 locale 来源（两处都要满足）
1. **白名单数组 `LINGUAS`（ui.js:3537）** —— 含 `"zh_CN"` 和 `"zh_TW"`（已确认）。`setup()` 只在此数组内选。
2. **字典文件目录 `novnc-src/app/locale/*.json`** —— `zh_CN.json`、`zh_TW.json` 均存在（已 `ls` 确认）。
   构建后会落到镜像 WWW_ROOT 的 `app/locale/`，运行时由 `fetch('app/locale/<lang>.json')` 加载。

### B.5 能否在 l10n 初始化前用 localStorage 覆盖 → reload 生效？（Task 6 的确切 hook）
- **可以。** 覆盖点就是 `l10n.language` 这个字段。原生流程：`l10n.setup(LINGUAS)`（:3538）写好
  `l10n.language` → 紧接着 (:3539) 用它决定走 `UI.prime()` 还是 `fetch('app/locale/'+l10n.language+'.json')`。
- **Task 6 应做的修改（在 ui.js:3538 之后、:3539 的 if 之前插入）：**
  ```js
  l10n.setup(LINGUAS);
  // 用户在设置面板里选的语言（存 localStorage）优先于 navigator
  const forcedLang = window.localStorage.getItem('chayuan_lang'); // 自定义 key
  if (forcedLang && LINGUAS.includes(forcedLang)) {
      l10n.language = forcedLang;
  }
  if (l10n.language === "en" || l10n.dictionary !== undefined) { ... }
  ```
  之后下拉 onchange 里写 `localStorage.setItem('chayuan_lang', value); location.reload();` 即可应用。
- **确切 hook 总结：要 set 的变量是 `l10n.language`（来自 `import { l10n } from './localization.js'`），
  set 的时机是 `l10n.setup(LINGUAS)` 之后、那段 `if (l10n.language === "en" ...) / fetch(...)` 之前（ui.js:3538↔3539 之间）。**
  `location.reload()` 会重跑整段，从而应用新语言。
- 备注：不要复用 noVNC `UI.initSetting` 体系的 key 当 hook（那套在 `UI.start()` 内、晚于 l10n.setup），
  l10n 决策发生在模块顶层 import 期，比 UI.start 早，所以直接读 localStorage 最稳。

---

## C. logo 元素 + 品牌字符串 + 标题（Task 2 改名 / 换 logo 清单）

### C.1 `<title>`
- **index.html:17** —— `<title>KasmVNC</title>`
- 运行时还会被 JS 覆盖：`const PAGE_TITLE = "KasmVNC";`（ui.js:58），用于
  `document.title = PAGE_TITLE;`（ui.js:2082）和 `document.title = e.detail.name + " - " + PAGE_TITLE;`（ui.js:3424）。
  → **Task 2 改标题必须同时改 index.html:17 和 ui.js:58**，否则连上桌面后标题又被刷回。

### C.2 logo 元素 + 资源路径
- **logo 块 index.html:99-104：**
  ```html
  <h1 class="noVNC_logo">
      <a href="https://www.kasmweb.com/kasmvnc" target="_blank" title="KasmVNC Learn More">
          <img src="app/images/icons/kasm_logo.svg" alt="KasmVNC Learn More"/>
      </a>
  </h1>
  ```
  - logo 元素：`<h1 class="noVNC_logo">`（无 id，靠 class `noVNC_logo` 定位）。
  - logo 图片资源：`novnc-src/app/images/icons/kasm_logo.svg`（已确认存在，3467 bytes）。
  - 外链 href `https://www.kasmweb.com/kasmvnc` + title/alt `KasmVNC Learn More` 都需改为察元AI。
- **favicon / app icon 一大串**（index.html:22-49）全部指向 `app/images/icons/368_kasm_logo_only_*.png`
  和 apple-touch-icon。Task 2 若要彻底换标 → 替换这些 png + `kasm_logo.svg`。

### C.3 所有可见「KasmVNC」品牌字符串（Task 2 逐条改 → 察元AI）
| file:line | 内容 | 性质 |
|---|---|---|
| index.html:17 | `<title>KasmVNC</title>` | 浏览器标签标题 |
| index.html:72 | `<div>KasmVNC encountered an error:</div>` | 致命错误提示 |
| index.html:101 | `title="KasmVNC Learn More"` | logo 链接 title |
| index.html:102 | `alt="KasmVNC Learn More"` | logo 图片 alt |
| index.html:349 | `<span class="slider-label">Enable KasmVNC Keyboard Shortcuts</span>` | 设置项可见文案 |
| app/ui.js:58 | `const PAGE_TITLE = "KasmVNC";` | 运行时标题（覆盖 index.html:17） |
| app/ui.js:2,1976,2268 | 注释里的 `KasmVNC` | 仅注释，可选改 |
- 另：index.html:56-60 有 `isInsideKasmVDI` 变量（Kasm VDI iframe 探测逻辑），属功能非品牌，不要乱改。

---

## D. 镜像特性 — 家目录 / KasmVNC web server / 启动钩子 / 反代点

侦察容器：`chatop-ai:1.1.0`（base 1.19.0）。以下均为容器内实测。

### D.1 容器用户 + HOME（filebrowser 数据根）
```
HOME=/home/kasm-user
whoami: kasm-user
id: uid=1000(kasm-user) gid=1000(kasm-user) groups=1000(kasm-user)
/home/ 下: kasm-default-profile, kasm-user
```
- **CONFIRMED：容器用户 = `kasm-user`（uid/gid 1000），HOME = `/home/kasm-user`。**
  → Task 4 的 filebrowser 数据根 / 默认浏览目录用 `/home/kasm-user`。

### D.2 Web server 形态 + 是否能加 `/files` 反代（关键裁决）
- **没有 nginx**：`which nginx` → `NO_NGINX`；`/etc/nginx` 不存在。
- Web 服务由 **KasmVNC 内建 httpd**（Xvnc 进程自带）提供，实测进程：
  ```
  /usr/bin/Xvnc :1 ... -httpd /usr/share/kasmvnc/www -sslOnly ... -websocketPort 6901 ...
       -cert /home/kasm-user/.vnc/self.pem ... -interface 0.0.0.0
  ```
  即 web 端口 **6901（https / sslOnly）**，静态根 `-httpd /usr/share/kasmvnc/www`（= WWW_ROOT）。
- KasmVNC 配置里 http 段（`/usr/share/kasmvnc/kasmvnc_defaults.yaml:149-153`）只有：
  ```yaml
  server:
    http:
      headers:
        - Cross-Origin-Embedder-Policy=require-corp
        - Cross-Origin-Opener-Policy=same-origin
      httpd_directory: /usr/share/kasmvnc/www
  ```
  **只有 `httpd_directory`（静态目录）+ headers，没有任何 proxy / upstream / location / reverse 配置项**
  （`grep -niE "proxy|upstream|location|reverse"` 在 defaults.yaml 无 web 反代命中）。
- **裁决（CONFIRMED）：KasmVNC 内建 httpd 只能服务静态文件，无法把 `/files` 反向代理到 filebrowser。
  也没有 nginx 可加 location。** 
  → **Task 4/5 必须把 filebrowser 独立监听一个端口（如 8585），前端用 `location.hostname` + 该端口拼 URL，
  不要指望同源 `/files` 路径。** （COEP/COOP 头是 require-corp/same-origin，跨端口嵌 iframe 需注意 CORP/COEP，
  Task 5 设计时留意：filebrowser 响应可能要带 `Cross-Origin-Resource-Policy: cross-origin` 或改用新标签页打开。）

### D.3 kasm 启动钩子路径（Task 4 启动 filebrowser 的落点）
- `/dockerstartup/vnc_startup.sh` 里有标准 **custom_startup 钩子**（vnc_startup.sh:447-456）：
  ```sh
  function custom_startup (){
      custom_startup_script=/dockerstartup/custom_startup.sh
      if [ -f "$custom_startup_script" ]; then
          if [ ! -x "$custom_startup_script" ]; then
              echo "${custom_startup_script}: not executable, exiting"; ...
          fi
          "$custom_startup_script" &
          KASM_PROCS['custom_startup']=$!
      fi
  }
  ```
  在 vnc_startup.sh:641 与 :722 被调用。**当前镜像里 `/dockerstartup/custom_startup.sh` 不存在**
  （`ls /dockerstartup` 无该文件），所以钩子默认空跑。
  → **Task 4 推荐做法：在 Dockerfile 里写一个可执行的 `/dockerstartup/custom_startup.sh`，
    里面后台拉起 filebrowser（`filebrowser -r /home/kasm-user -a 0.0.0.0 -p 8585 ... &`），
    vnc_startup.sh 会自动 fork 它。** 必须 `chmod +x`，否则脚本里写了 "not executable, exiting"。
- 另有空壳钩子（仅 echo，可作 root/user 时机扩展点，但不如 custom_startup 通用）：
  - `/dockerstartup/kasm_post_run_user.sh`（58B，仅 `echo "Executing kasm_post_run_user.sh"`）
  - `/dockerstartup/kasm_post_run_root.sh`（58B，仅 echo）

### D.4 `/etc/kasmvnc/kasmvnc.yaml` 是否已存在 + 结构（Task 3 的 yaml 要对齐）
- **已存在**，三个层级（优先级低→高被合并，KasmVNC 标准）：
  - 默认：`/usr/share/kasmvnc/kasmvnc_defaults.yaml`（165 行，全量默认，结构见下）
  - 系统级：`/etc/kasmvnc/kasmvnc.yaml`（317B，**当前内容**）：
    ```yaml
    network:
      ssl:
        pem_certificate: ${HOME}/.vnc/self.pem
        pem_key: ${HOME}/.vnc/self.pem
      udp:
        public_ip: 127.0.0.1
    runtime_configuration:
      allow_override_standard_vnc_server_settings: true
      allow_override_list:
        - pointer.enabled
    server:
      allow_environment_variables_to_override_config_settings: true
    ```
  - 用户级：`/home/kasm-user/.vnc/kasmvnc.yaml`（仅 logging 段，运行时生成）
- 顶层 schema（来自 defaults.yaml）：`desktop / network / user_session / keyboard / pointer /
  runtime_configuration / logging / security / data_loss_prevention / server / command_line`。
  - `server.http.httpd_directory: /usr/share/kasmvnc/www`、`server.http.headers: [...]`（D.2 引用）。
  - `network.protocol: http`、`network.interface: 0.0.0.0`、`network.websocket_port: auto`、`network.ssl.require_ssl: true`。
- **Task 3 写 yaml 时**：以 `/etc/kasmvnc/kasmvnc.yaml` 为覆盖入口（合并到 defaults 之上），
  顶层 key 必须用上面这套（如要调 http 头或 httpd_directory 就放 `server.http.*`）。注意 `${HOME}` 变量被支持。

---

## 未决项 / 兜底建议

- **同源 `/files` 反代不可行（D.2，已确认）** → 兜底：filebrowser 独立端口（建议 8585），前端
  `` `${location.protocol}//${location.hostname}:8585/` `` 拼 URL；若 COEP/CORP 阻止 iframe 嵌入，
  改为按钮新标签页打开，或给 filebrowser 配 `Cross-Origin-Resource-Policy: cross-origin`。Task 5 需实测嵌入。
- **l10n 覆盖 hook（B.5）** 是源码改动（ui.js:3538 后插桩），不是配置项；Task 6 落代码后需重新 `npm run build`
  并把产物同步进镜像 WWW_ROOT（`/usr/share/kasmvnc/www`）。本次未实测构建产物，按 Vite 构建惯例处理。
- **品牌替换（C.3）** 改 index.html 还不够，运行时标题由 ui.js:58 `PAGE_TITLE` 覆盖，两处都要改。
- 侦察镜像是 `chatop-ai:1.1.0`（任务允许使用）；用户运行中的 `chatop-ai` 容器跑的是 `chatop-ai:1.0.0`，
  二者 base 相同（1.19.0 系），上述镜像态结论对 1.0.0 同样适用，但若后续在 1.0.0 上验证可再核对。
