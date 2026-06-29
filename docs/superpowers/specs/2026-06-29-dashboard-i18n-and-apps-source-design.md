# 设计：Selkies dashboard 语言切换器 + Manage Apps 国内源

日期：2026-06-29
状态：已确认，待写实施计划

## 背景与问题

chatop（察元AI）的浏览器侧边栏工具条只显示英文（如 Audio Settings、Screen
Settings），用户需要中/英/日/俄/意/德/韩等多语言切换。另外 "Manage Apps" 的
应用列表在国内常加载失败。

## 现状探查（关键事实）

三套 dashboard 的 i18n 现状差异极大：

| Dashboard | i18n 现状 | t() 使用 |
|---|---|---|
| `selkies-dashboard`（compose 默认 `DASHBOARD`） | 完整 18 语言翻译 + 已全量接线 | 123 处 |
| `selkies-dashboard-zinc` | 有 translations.js 数据但**未接线**（getTranslator 从未被 import） | 0 处 |
| `selkies-dashboard-wish` | **完全无 i18n**（无翻译文件） | 0 处 |

- `selkies-dashboard` 的语言由 `navigator.language` 自动检测（`langCode` state，
  默认 `en`），**无手动切换入口、不记忆选择** → 浏览器报英文就一直英文。
- translations.js 已内置 18 语言：en, es, zh, hi, pt, fr, ru, de, tr, it, nl,
  ar, ko, ja, vi, th, fil, da（用户要的中/英/日/俄/意/德/韩全部覆盖）。
- Manage Apps 源 = `linuxserver/proot-apps` 的 `metadata.yml`（GitHub raw），
  由**用户浏览器**客户端 fetch。原 `METADATA_URLS` 里的 `ghproxy.com`/
  `mirror.ghproxy.com` 实测已废（返回错误页 / 连接失败）。

## 范围（Scope）

**做：**
- `selkies-dashboard`：加语言切换器（18 语言）+ 记忆选择 + 修 Apps 源。
- `selkies-dashboard-zinc`、`selkies-dashboard-wish`：**仅**修 Apps 源（让列表能加载）。

**不做（Non-goals）：**
- zinc/wish 的完整多语言（zinc 需全量接线、wish 需从零建 18 语言翻译，成本与
  风险远超收益，且用户默认不使用这两套）。
- "安装 App" 的下载链路国内化（`proot-apps` 工具去 GitHub releases 下载，另一条
  链路，本次不动）。

## 设计

### Part 1 — 语言切换器（仅 `selkies-dashboard`，文件 `src/components/Sidebar.jsx`）

**初始化优先级**（替换现有仅靠 navigator.language 的逻辑）：
1. `localStorage.getItem('selkies_lang')`（用户手动选过的，最高优先）
2. 否则 `navigator.language`/`navigator.userLanguage` 取主语言段（如 `zh-CN`→`zh`）
3. 否则 `en`

读取的 langCode 若不在 18 语言白名单内，回退 `en`。

**UI**：侧边栏顶部控制区新增一个紧凑的语言下拉（原生 `<select>`，🌐 前缀）：
- 列全部 18 种，`<option value=代码>母语名</option>`，母语名映射见下。
- 当前值绑定 `langCode`。

**切换行为**：`onChange` → `setLangCode(值)` + `localStorage.setItem('selkies_lang', 值)`。
`langCode` 变化使现有 `getTranslator(langCode)` 重新求值，123 处 `t()` 实时刷新，
工具条标题（`t("sections.audio.title")` 等）立即变对应语言。**无需新增/修改翻译数据。**

**母语名映射**（18）：
en=English, es=Español, zh=中文, hi=हिन्दी, pt=Português, fr=Français,
ru=Русский, de=Deutsch, tr=Türkçe, it=Italiano, nl=Nederlands, ar=العربية,
ko=한국어, ja=日本語, vi=Tiếng Việt, th=ไทย, fil=Filipino, da=Dansk。

### Part 2 — Manage Apps 源（三套 dashboard）

把各自的 `METADATA_URLS` 改成实测可达、带 CORS、按国内可靠度排序的回退列表
（删除已废的 ghproxy.com / mirror.ghproxy.com）：

```
https://cdn.jsdelivr.net/gh/linuxserver/proot-apps@master/metadata/metadata.yml
https://fastly.jsdelivr.net/gh/linuxserver/proot-apps@master/metadata/metadata.yml
https://gcore.jsdelivr.net/gh/linuxserver/proot-apps@master/metadata/metadata.yml
https://ghfast.top/https://raw.githubusercontent.com/linuxserver/proot-apps/master/metadata/metadata.yml
https://raw.githubusercontent.com/linuxserver/proot-apps/master/metadata/metadata.yml
```

文件：
- `selkies-dashboard/src/components/Sidebar.jsx`（METADATA_URLS）
- `selkies-dashboard-zinc/src/components/dashboard/apps.tsx`（METADATA_URLS）
- `selkies-dashboard-wish/src/components/dashboard/apps.tsx`（METADATA_URLS）

现有"依次 fetch、成功即用"的回退循环保持不变，仅替换 URL 列表。

### Part 3 — 构建 / 部署 / 版本

- 合并构建：本次改动 + 已构建的 1.0.6（aidooo.com 链接）内容一起重建，避免多次导出。
- 版本：VERSION → `1.0.7`；重建镜像、retag latest、用 3002 重启容器验收。
- 改动随提交进 git（selkies-src 已纳入版本控制）。

## 错误处理

- Apps 源：沿用现有"列表依次 fetch，首个成功即用，全失败则显示错误+重试"逻辑。
- 翻译缺键：`getTranslator` 已逐键回退 `en`，个别语言缺某键不会崩。
- localStorage 不可用/值非法：try-catch + 白名单校验，回退浏览器检测/`en`。

## 验证

- 构建日志：走"使用本地 selkies-src"、四套前端 `✓ built`、导出完整。
- 容器内：`selkies-dashboard` 产物含语言下拉；切换到 zh 后工具条为中文。
- 浏览器（3002，需认证）：切换语言即时生效并刷新后仍记住；Manage Apps 列表能加载。
- 运行时不引入 Node-only API（保持浏览器/WPS 可运行）。

## 受影响文件清单

- `selkies-src/addons/selkies-dashboard/src/components/Sidebar.jsx`（switcher + 源）
- `selkies-src/addons/selkies-dashboard-zinc/src/components/dashboard/apps.tsx`（源）
- `selkies-src/addons/selkies-dashboard-wish/src/components/dashboard/apps.tsx`（源）
- `VERSION`（→1.0.7）
