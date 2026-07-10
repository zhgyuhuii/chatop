# 应用市场国内化设计（离线可用 + 语言联动 + 国产扩充）

- 日期：2026-07-10
- 状态：设计已确认（brainstorming 完成，方案 A）
- 影响范围：`app-manager/`（catalog + app_manager.py + 助手脚本）、`novnc-src/app/ui.js`、`Dockerfile`

## 1. 背景与目标

左侧应用市场当前有 112 个应用（94 个 `proot-gui` 走 `ghcr.io/linuxserver/proot-apps`，其余为 npm/pip/AppImage/vscode 扩展）。面向中国大陆用户存在四个问题：

1. **国内下载难**：所有下载源均境外（ghcr.io / npmjs / pypi / github / cdn.jsdelivr），运行时安装命令**未配任何国内镜像**（镜像回退只在构建期的 `chatop-preinstall.sh`，运行时市场安装走默认源，易超时/被墙）。
2. **无按语言选版本**：`chatop_lang` 只驱动 UI 文案和桌面 locale，`public_catalog()` 无视语言返回同一份清单；微信/WPS 是 linuxserver 社区国际版，不是官方国内最新版。
3. **离线/被墙图标裂**：94 个 `proot-gui` 图标字段是 `cdn.jsdelivr.net`（大陆已被墙），离线/断网时图标全裂（列表文字仍可渲染，因 catalog 本地）。
4. **国产应用缺位**：无 QQ、钉钉、飞书等国产实用工具，无 Qoder/通义灵码等国产 AI 编程工具，国产不置顶。

**目标**：中文默认国产置顶（境外降权保留、全可见）；按语言下载 cn/intl 变体；离线/被墙能看列表（图标不裂）；安装全线走国内镜像回退；扩充国产应用与 AI 工具。

## 2. 已锁定的产品决策

| 维度 | 决定 |
|---|---|
| 中文默认清单 | 国产置顶 + 境外降权保留（一套清单，加 origin 标签 + rank 权重，全可见） |
| 语言→下载源 | cn/intl 两变体（zh_CN/zh_TW→cn 优先，en/ja/ko→intl；多数应用单源） |
| 旗舰应用交付 | 全部按需下载，不预装（镜像最小；被墙时列表可见、安装需联网走国内源） |
| 离线可用性 | 列表文字本地渲染 + 全部图标本地化（离线/被墙不裂） |
| 换源 | 执行层/PATH 层统一给 npm/pip/github/ghcr 加国内镜像回退，catalog 尽量零改动 |

## 3. 关键调研结论（2026-07，已交叉核实）

- 基础镜像 `kasmweb/core-ubuntu-jammy` = Ubuntu 22.04 / glibc 2.35 → **glibc≥2.28 门槛天然满足**（Trae/Lingma/Qoder/Comate 不踩雷）。
- 微信官方固定直链 deb + AppImage；WPS/QQ/钉钉/飞书/百度网盘/uTools/ToDesk 官方 deb；QQ/QQ音乐/Motrix 有 AppImage；腾讯会议有官方 flatpak。多数国产 CDN 国内直连。
- AI 工具：桌面 IDE = 通义灵码/Trae/Qoder（deb）；纯终端 = Qwen Code / CodeBuddy Code（npm）；CodeGeeX/Fitten = VSCode 扩展。**避雷**：iFlow 已关停、MarsCode 已并入 Trae、CodeBuddy IDE 无 Linux 版。
- 镜像源：npm→registry.npmmirror.com；pip→清华+阿里；GitHub→gh-proxy.com（须多域名可配回退）；ghcr→DaoCloud(主)+南大(备)；**jsdelivr 大陆已废**（图标必须本地化）。
- `proot-apps` 支持完整镜像引用（`proot-apps install ghcr.io/org/...:app`）→ 可指向国内 ghcr 镜像加速；自建自定义应用镜像仓成本高，本期不做，仅留口子。
- **需上镜像前实测复核**：QQ/钉钉/飞书/腾讯会议/搜狗/向日葵实时下载链；deb-user 应用在本镜像的缺库情况；网易云 2019 老包（已排除）；搜狗/向日葵/Comate/Fitten/aiXcoder（列二期）。

## 4. 架构：方案 A（就地扩展 + 用户态 deb/AppImage 安装）

三块公共能力（图标本地化、语言联动、镜像回退）全做；新增的唯一安装机制是 `deb-user`；proot-apps 自定义镜像仓留作未来增强，不在本期。

### 4.1 Catalog 数据模型

给 `apps-catalog.json` 每条应用新增字段（全部可选，向后兼容）：

- `origin`：`cn | intl | global`（global=全球同包，如 VLC/Blender）。排序与语言选源依据。
- `rank`：整数，越大越靠前。分层：国产旗舰 100 / 国产 AI-IDE 90 / 国产 AI-CLI 85 / 国产常用工具 70 / 境外 AI 50 / 全球通用 20-30。
- `category`：语义分类（im/office/browser/ai-ide/ai-cli/media/tool/dev/proot-gui…），比现有 5 类更细。
- `icon`：一律本地文件名，禁远程 URL。
- `kind`：扩展枚举，新增 `deb-user`。

双变体应用（cn≠intl 的少数）用 `variants` 承载，`public_catalog` 按语言挑一个摊平下发：

```jsonc
{
  "id": "wps", "name": "WPS Office", "category": "office", "rank": 95,
  "icon": "wps.png",
  "variants": {
    "cn":   { "origin":"cn",   "kind":"deb-user",  "install":"...linux.wps.cn...", "detect":"...", "remove":"...", "launch":"...", "homepage":"https://linux.wps.cn/" },
    "intl": { "origin":"intl", "kind":"proot-app", "install":"proot-apps install wpsoffice", "detect":"...", "remove":"...", "launch":"proot-apps run wpsoffice" }
  }
}
```

**选源与排序规则**（真源 = `chatop_lang` cookie）：

- 语言 ∈ {zh_CN, zh_TW} → 区域 = cn；语言 ∈ {en, ja, ko} → 区域 = intl。
- 有 `variants`：选对应区域变体；该区域缺失则回退另一个，保证不空。
- 无 `variants`：`origin` 仅用于排序，源不变。
- 排序：`rank` 降序 → 区域匹配优先（cn 语言下 origin=cn 靠前）→ name 升序。

### 4.2 语言感知的下发（app_manager.py）

- `public_catalog(lang)`：`do_GET("/apps/catalog")` 用**现有** `resolve_lang(Cookie, Accept-Language)` 解析 lang 传入（不新造语言解析）。
- 每条应用：有 `variants` 则按区域摊平并入顶层、丢弃另一变体与 `variants` 键；计算 `effective_origin`。
- 排序按 4.1 规则；前端拿到即已排序。
- 下发字段：沿用「命令只后端持有」，`install/detect/remove` 不下发；新增下发 `category / origin / rank`；派生 `badge`（origin=="cn" → "国产"）。

### 4.3 前端（novnc-src/app/ui.js）

- `iconSrc` 统一 `'app-icons/'+a.icon`（保留 `http` 分支兜底老缓存 catalog）。
- 卡片按后端顺序直接渲染（不在前端排序）；`origin=="cn"` 显示「国产」小标签。
- 分类筛选改用新的 `category`。
- 语言切换 → `/lang` 写 cookie → 应用面板下次刷新时 `/apps/catalog` 带新语言重排选源，**不需重启桌面**（与桌面 locale 那层解耦，互不影响）。

### 4.4 安装执行层 + 国内镜像回退

catalog install 命令写成「镜像无关」，镜像回退在执行层/PATH 层做：

1. **npm**：`_worker` 注入 `npm_config_registry=https://registry.npmmirror.com`、`npm_config_disturl=https://npmmirror.com/dist`。命令串不变。
2. **pip/pipx**：注入 `PIP_INDEX_URL=清华`、`PIP_EXTRA_INDEX_URL=阿里`。命令串不变。
3. **GitHub 下载类**（void/rtk/hermes）：新增 `chatop-fetch <url> <out>` 助手，直连 → gh-proxy.com → gh-proxy.org → … 逐个回退；代理域名列表读 `/etc/chatop/mirrors.conf`（可配、不硬编码）。catalog 里裸 `curl` 换成 `chatop-fetch`，`gui-install.sh` 内部下载亦改走它。
4. **proot-apps**（94 个）：PATH 垫片——真二进制改名 `proot-apps-real`，`/usr/local/bin/proot-apps` 垫片把 `install <短名>` 改写为完整镜像引用并按 DaoCloud → 南大 → 直连 ghcr 回退。**94 个条目与 preinstall 一字不改**即获加速。

**镜像配置真源**：`/etc/chatop/mirrors.conf`（npm/pip registry、gh 代理域名列表、ghcr 镜像列表），`_worker` env 注入、`chatop-fetch`、`proot-apps` 垫片三处共读。改策略只改这一个文件 / 容器 env。

### 4.5 新安装类型 `deb-user`（官方 deb 免 root）

分流：官方提供 AppImage 的（微信/QQ/QQ音乐/Motrix）走现有 `gui-install.sh`（`kind=appimage`）；`deb-user` 只服务纯 deb（WPS/钉钉/飞书/百度网盘/uTools/ToDesk）。

新助手 `chatop-deb-install.sh <id> <deb_url|RESOLVER> <显示名> [exec_args]`，装进 home 卷、免 root，与 AppImage 路径同构：

```
1. chatop-fetch 拉 deb（国内代理回退）
2. dpkg -x app.deb ~/Applications/<id>   # 只解包文件，不跑 maintainer 脚本、不需 root
3. 读解包出的 usr/share/applications/*.desktop 定位主程序与图标
4. 生成 ~/.local/share/applications/chatop-<id>.desktop（Exec 指向解包主程序，Electron 补 --no-sandbox）
5. 复制到 ~/Desktop，刷新桌面
```

- `detect`：`test -d ~/Applications/<id>`
- `remove`：复用 `gui-uninstall.sh <id>`（deb-user 与 AppImage 同用 `~/Applications/<id>` + `chatop-<id>.desktop` 布局，卸载一套通吃）
- `launch`：解包后主程序路径

**风险与对策**：

1. 动态/临时下载链（QQ/钉钉/飞书/腾讯会议/搜狗/向日葵）：install 字段写 resolver（照搬 Cursor `CURSOR_API`，安装时现抓官网直链再喂 chatop-fetch）；能写死的（微信固定直链）直接给 URL。
2. `dpkg -x` 不装依赖：构建期（root）烤入一组桌面通用运行库（libnss3/libgtk/libasound/libgbm 等）作共享底座；个别应用缺专属库者上镜像前实测补库。
3. 容器内 Electron/FUSE：Electron 补 `--no-sandbox`；AppImage 用 `--appimage-extract` 跑（FUSE 已禁）。

特殊项：搜狗输入法依赖 Fcitx（非 Fcitx5）且临时链 → 列二期/可选，不挡主线。

### 4.6 图标本地化

- 构建期把 catalog 所有远程图标（94 proot svg + 新增应用图标）拉到 `app-manager/icons/`；拉取走 gh-proxy/npmmirror 回退；catalog `icon` 全改本地文件名。
- 扩展 `fetch-icons.sh` 完成抓取；新增 catalog lint：断言每个 icon 本地存在、无 `http` 残留。
- 已有 `COPY app-manager/icons/ → www/app-icons/`，前端 `'app-icons/'+icon` 命中 → 离线/被墙零裂。

## 5. 内容清单（新增 + 归类）

新增国产桌面应用（origin=cn）：

| id | 名称 | kind | 源 |
|---|---|---|---|
| wechat | 微信 | appimage | linux.weixin.qq.com（官方 AppImage） |
| wps | WPS Office | deb-user | linux.wps.cn（+ intl 变体=旧 proot wpsoffice） |
| qq | QQ | appimage | im.qq.com |
| dingtalk | 钉钉 | deb-user | dingtalk.com（resolver） |
| feishu | 飞书 | deb-user | feishu.cn（resolver） |
| tencent-meeting | 腾讯会议 | deb-user | meeting.tencent.com（resolver） |
| baidu-netdisk | 百度网盘 | deb-user | pan.baidu.com |
| qq-music | QQ音乐 | appimage | y.qq.com |
| todesk | ToDesk | deb-user | dl.todesk.com |
| utools | uTools | deb-user | u-tools.cn |
| motrix | Motrix | appimage | motrix.app（gh-proxy） |

新增国产 AI（origin=cn）：qoder（deb-user, ai-ide）、lingma 通义灵码（deb-user, ai-ide）、trae（deb-user, ai-ide）、codebuddy（cli-npm）、codegeex（vscode-ext）。

归类既有：`qwen-code`(阿里) / `mimo-code`(小米) 标 origin=cn 并提 rank；claude-code/codex/cursor/void 标 intl；旧 `wechat`/`wpsoffice`（proot 社区版）并入新条目的 intl 变体（境外用户仍可用）。

排除并注明理由：讯飞输入法（无官方独立 Linux 页）、迅雷（仅信创残缺版）、网易云音乐（2019 停更易崩）。二期/需实测：搜狗输入法、向日葵、Comate、Fitten、aiXcoder。

## 6. 离线/被墙行为契约

- 列表：任何网络状态都能渲染（本地 catalog + 本地图标）。
- 安装：断网/被墙时快速失败，把「直连→各镜像」尝试轨迹写进现有 per-app 日志流；镜像全失败给「网络不可达或镜像不可用」明确诊断，不静默卡死。

## 7. 测试策略

- 单元：`public_catalog(lang)` 变体摊平 + 排序（zh_CN 选 cn、en 选 intl、国产置顶顺序）；变体缺失回退；`mirrors.conf` 解析 + env 注入。
- 契约/lint：每条 app 有 origin+rank、icon 本地存在、variants 结构合法、无远程 icon。
- 助手冒烟：`chatop-fetch` 多域名回退、`proot-apps` 垫片改写镜像引用（mock 网络）。
- deb-user：CI 难全联网 → detect/dry-run 测试 + 人工验收清单（微信/WPS/QQ 等实机装+起）。

## 8. 分期实施

- **P1（离线+换源，低风险先行）**：图标本地化 + `mirrors.conf` + npm/pip env 注入 + proot-apps 垫片 + `chatop-fetch`。交付即修复离线图标裂与国内安装超时。
- **P2（语言联动）**：catalog 数据模型（origin/rank/category/variants）+ `public_catalog` 语言感知 + 前端排序/国产标签。
- **P3（内容扩充）**：`deb-user` 机制 + 桌面运行库底座 + 微信/WPS/QQ 等国产应用 + AI 工具扩充。

## 9. 未来增强（不在本期）

- 自建 proot-apps 自定义应用镜像仓（统一安装路径、可完全离线缓存）。
- 二期应用：搜狗输入法（Fcitx）、向日葵、Comate、Fitten、aiXcoder。
