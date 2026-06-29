# chatop-ai 第一阶段：构建基座 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 产出一个可构建、可启动的 `chatop-ai` 镜像：基于官方 kasmweb 桌面镜像，把**自定义注入的 noVNC 前端**覆盖进 web 根目录，启动后浏览器能连接、能看到桌面，并能证明"被服务的前端就是我们注入的那份"。

**Architecture:** 纯加法——`FROM` 官方 kasmweb 桌面镜像（已内置最新 KasmVNC，原有功能全保留），把改版 noVNC 前端构建产物 `COPY` 覆盖镜像的 web 根目录。**不重编译 C++**。第一阶段先打通"注入 → 构建 → 运行 → 验证"管线，前端内容本身保持与上游一致（仅加一个 sentinel 标记证明注入生效）。

**Tech Stack:** Docker / docker-compose、kasmweb/ubuntu-jammy-desktop（KasmVNC 内置）、kasmtech/noVNC（前端源码，npm 构建）、filebrowser（后续阶段）。

**底座说明（对设计文档的细化）：** 第一阶段底座用 **`kasmweb/ubuntu-jammy-desktop`**（自带可用 XFCE 桌面），先保证有可见桌面、专注验证 noVNC 注入管线。设计文档里"用更小的 `core-ubuntu-jammy` + 自装桌面"属于**瘦身优化**，瘦身是本期非目标，留到后续瘦身子项目再做。

---

## File Structure（第一阶段产出）

```
/work/chatop-ai/
  .git/                         # 本阶段 git init
  .gitignore                    # 忽略构建产物 / .env
  VERSION                       # 1.0.0
  README.md                     # 项目说明 + 构建运行命令
  Dockerfile                    # FROM 官方镜像 + 注入 noVNC
  docker-compose.yml            # 构建 + 运行
  .env.example                  # PORT / 密码等
  build-and-run.sh              # 便捷入口
  novnc-src/                    # vendor 的 kasmtech/noVNC 源码（本阶段近乎原样）
  docs/
    2026-06-29-chatop-ai-kasmvnc-design.md      # 已存在
    2026-06-29-phase1-build-base-plan.md         # 本文件
    recon.md                    # 任务2/3 产出：实测的 web 根路径、端口、noVNC 构建方式
```

每个文件单一职责：`Dockerfile` 只管镜像组装，`docker-compose.yml` 只管构建/运行参数，`build-and-run.sh` 只是便捷壳。

---

## Task 1: 项目脚手架 + git init

**Files:**
- Create: `/work/chatop-ai/.gitignore`
- Create: `/work/chatop-ai/VERSION`
- Create: `/work/chatop-ai/README.md`

- [ ] **Step 1: 初始化 git 仓**

Run:
```bash
cd /work/chatop-ai && git init -q && git branch -M main && git status
```
Expected: 干净的新仓库，当前分支 `main`，`docs/` 下两个 md 为 untracked。

- [ ] **Step 2: 写 `.gitignore`**

```gitignore
# 构建 / 运行产物
*.log
.env
novnc-src/node_modules/
novnc-src/build/
novnc-src/dist/
# 本地临时
*.tmp
.DS_Store
```

- [ ] **Step 3: 写 `VERSION`**

```
1.0.0
```

- [ ] **Step 4: 写 `README.md`**

```markdown
# chatop-ai

基于最新 KasmVNC 的定制云桌面（纯加法式定制：名称/图标/权限/语言切换/主题切换/文件上传下载）。
设计见 `docs/2026-06-29-chatop-ai-kasmvnc-design.md`。

## 构建并运行
\`\`\`bash
cp .env.example .env   # 按需改端口/密码
./build-and-run.sh
\`\`\`
访问 https://localhost:${PORT:-6901}
```

- [ ] **Step 5: 提交**

```bash
cd /work/chatop-ai && git add .gitignore VERSION README.md docs/ && \
git commit -m "chore(chatop-ai): 项目脚手架 + 设计文档与第一阶段计划"
```

---

## Task 2: 侦察底座镜像（实测 web 根路径 / 端口 / 注入点）

> 目的：在真环境确认事实，**不凭印象写死路径**（设计文档列为风险点）。

**Files:**
- Create: `/work/chatop-ai/docs/recon.md`

- [ ] **Step 1: 拉取并后台启动官方镜像**

Run:
```bash
docker pull kasmweb/ubuntu-jammy-desktop:1.16.1
docker run -d --name kasm-recon --shm-size=512m -p 6901:6901 \
  -e VNC_PW=recon123 kasmweb/ubuntu-jammy-desktop:1.16.1
sleep 8 && docker ps --filter name=kasm-recon
```
Expected: 容器 `kasm-recon` 处于 Up 状态，映射 6901。

- [ ] **Step 2: 定位 noVNC web 根目录与入口文件**

Run:
```bash
docker exec kasm-recon bash -lc \
 'for d in /usr/share/kasmvnc/www /usr/share/kasmvnc /usr/local/share/kasmvnc/www; do \
    [ -d "$d" ] && echo "DIR: $d" && ls "$d" | head; done; \
  echo "---- index ----"; find / -name "index.html" -path "*kasm*" 2>/dev/null | head; \
  echo "---- app js ----"; find / -name "*.js" -path "*kasm*www*" 2>/dev/null | head'
```
Expected: 打印出真实的 www 根目录（很可能是 `/usr/share/kasmvnc/www`）及其下的 `index.html` / `app/` 等。**记录确切路径。**

- [ ] **Step 3: 浏览器人工核对**

打开 https://localhost:6901 （账号 `kasm_user` / 密码 `recon123`，接受自签证书），确认能看到 KasmVNC 控制面板 + 桌面。

- [ ] **Step 4: 把实测结论写进 `docs/recon.md`**

记录：①确切 web 根路径（记为 `WWW_ROOT`）；②入口 `index.html` 位置；③控制栏/侧边菜单在前端中的大致文件；④登录用户名与端口。后续 Task 用 `WWW_ROOT` 这个确定值。

- [ ] **Step 5: 清理侦察容器并提交**

```bash
docker rm -f kasm-recon
cd /work/chatop-ai && git add docs/recon.md && \
git commit -m "docs(chatop-ai): 侦察官方镜像 web 根路径与注入点(WWW_ROOT)"
```

---

## Task 3: Vendor noVNC 源码并确认构建方式

> 第一阶段前端"近乎原样"，目的只是跑通构建+注入；真正的品牌/主题/语言/按钮改动在后续阶段。

**Files:**
- Create: `/work/chatop-ai/novnc-src/`（clone 产物）
- Modify: `/work/chatop-ai/docs/recon.md`（追加 noVNC 构建方式）

- [ ] **Step 1: clone kasmtech/noVNC 并锁定 commit**

Run:
```bash
cd /work/chatop-ai && git clone https://github.com/kasmtech/noVNC.git novnc-src
cd novnc-src && git rev-parse HEAD | tee ../docs/novnc-commit.txt && \
ls && echo "---" && cat package.json 2>/dev/null | head -40
```
Expected: 拿到 noVNC 源码；记录其 HEAD commit（可复现）。查看 `package.json` 的 `scripts` 段确定构建命令。

- [ ] **Step 2: 确认是否需要构建步骤**

Run:
```bash
cd /work/chatop-ai/novnc-src && \
echo "scripts:" && node -e "console.log(Object.keys(require('./package.json').scripts||{}))" 2>/dev/null; \
ls app core vendor 2>/dev/null
```
判定规则：
- 若存在 `build`/`dist` 类脚本 → 前端需 `npm install && npm run build`，产物在 `build/` 或 `dist/`。
- 若是纯静态 ES 模块（`app/` + `core/` + `vendor/` 直接被 web server 服务，无打包）→ **无需构建**，直接整目录作为静态资源注入。
把结论（"需构建/无需构建" + 产物目录）追加进 `docs/recon.md`。

- [ ] **Step 3: 移除嵌套 .git，纳入主仓**

```bash
cd /work/chatop-ai && rm -rf novnc-src/.git && \
git add novnc-src docs/recon.md docs/novnc-commit.txt && \
git commit -m "vendor(chatop-ai): 纳入 kasmtech/noVNC 源码 + 记录构建方式"
```

---

## Task 4: 注入式 Dockerfile（覆盖 web 根）

**Files:**
- Create: `/work/chatop-ai/Dockerfile`

- [ ] **Step 1: 在 noVNC 入口加 sentinel 标记**

在 `novnc-src` 的 `index.html`（路径以 Task 2/3 实测为准）`<head>` 内加一行可验证标记：
```html
<!-- CHATOP-AI-INJECTED v1.0.0 -->
```
作用：构建后在浏览器"查看源代码"里看到它，即证明**被服务的是我们注入的前端**，而非镜像原版。

- [ ] **Step 2: 写 `Dockerfile`**

> `WWW_ROOT` 用 Task 2 实测值替换（下面以最可能的 `/usr/share/kasmvnc/www` 为默认；若 Task 2 实测不同，改这一处）。若 Task 3 判定"需构建"，则增加一个 builder stage，下方给出两种形态，按实测二选一保留。

形态 A（noVNC 无需构建，纯静态注入——多数情况）：
```dockerfile
# syntax=docker/dockerfile:1.7
FROM kasmweb/ubuntu-jammy-desktop:1.16.1
ARG VERSION=1.0.0
LABEL maintainer="chatop-ai" build_version="chatop-ai ${VERSION}"
# 覆盖 KasmVNC 自带 noVNC 前端（WWW_ROOT 以 docs/recon.md 实测为准）
COPY --chown=root:root novnc-src/ /usr/share/kasmvnc/www/
```

形态 B（noVNC 需 npm 构建）：
```dockerfile
# syntax=docker/dockerfile:1.7
FROM node:20-alpine AS web
WORKDIR /src
COPY novnc-src/ ./
RUN --mount=type=cache,target=/root/.npm npm install && npm run build

FROM kasmweb/ubuntu-jammy-desktop:1.16.1
ARG VERSION=1.0.0
LABEL maintainer="chatop-ai" build_version="chatop-ai ${VERSION}"
COPY --from=web --chown=root:root /src/build/ /usr/share/kasmvnc/www/
```

- [ ] **Step 3: 构建镜像**

Run:
```bash
cd /work/chatop-ai && docker build --build-arg VERSION=$(cat VERSION) -t chatop-ai:$(cat VERSION) .
```
Expected: 构建成功，无报错；最后一层 COPY 注入 www 完成。

- [ ] **Step 4: 提交**

```bash
cd /work/chatop-ai && git add Dockerfile novnc-src/ && \
git commit -m "feat(chatop-ai): 注入式 Dockerfile 覆盖 noVNC web 根 + sentinel 标记"
```

---

## Task 5: compose / 运行脚本 / 端到端验证

**Files:**
- Create: `/work/chatop-ai/docker-compose.yml`
- Create: `/work/chatop-ai/.env.example`
- Create: `/work/chatop-ai/build-and-run.sh`

- [ ] **Step 1: 写 `.env.example`**

```bash
# 对外端口
PORT=6901
# 登录密码（VNC_PW）
PASSWORD=change-me
```

- [ ] **Step 2: 写 `docker-compose.yml`**

```yaml
services:
  chatop-ai:
    build:
      context: .
      args:
        VERSION: ${VERSION:-1.0.0}
    image: chatop-ai:${VERSION:-1.0.0}
    container_name: chatop-ai
    environment:
      - VNC_PW=${PASSWORD:?请在 .env 设置 PASSWORD}
    ports:
      - "${PORT:-6901}:6901"
    shm_size: "1gb"
    restart: unless-stopped
```

- [ ] **Step 3: 写 `build-and-run.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "请先 cp .env.example .env 并改密码"; exit 1; }
export VERSION="$(cat VERSION)"
docker compose up -d --build
echo "已启动：https://localhost:$(grep -E '^PORT=' .env | cut -d= -f2 || echo 6901)"
```
然后：`chmod +x build-and-run.sh`

- [ ] **Step 4: 端到端启动**

Run:
```bash
cd /work/chatop-ai && cp -n .env.example .env && \
sed -i 's/change-me/test12345/' .env && ./build-and-run.sh && sleep 8 && \
docker ps --filter name=chatop-ai
```
Expected: 容器 Up，端口映射到 `.env` 的 PORT。

- [ ] **Step 5: 验证注入生效（sentinel）+ 桌面可用**

Run（验证 sentinel 出现在被服务的页面里）：
```bash
curl -ks https://localhost:6901/ | grep -c "CHATOP-AI-INJECTED" || \
docker exec chatop-ai bash -lc 'grep -rc "CHATOP-AI-INJECTED" /usr/share/kasmvnc/www/index.html'
```
Expected: ≥1，证明**被服务的前端是我们注入的那份**。
再人工：浏览器开 https://localhost:6901 （`kasm_user` / `test12345`），确认 KasmVNC 控制面板 + 桌面正常、原有功能（剪贴板等）仍在（回归核对：不得移除上游能力）。

- [ ] **Step 6: 停容器并提交**

```bash
cd /work/chatop-ai && docker compose down && \
git add docker-compose.yml .env.example build-and-run.sh && \
git commit -m "feat(chatop-ai): compose+运行脚本+端到端验证(注入 sentinel 通过)"
```

---

## Self-Review

**Spec coverage（对照设计文档第一阶段"构建基座"）：**
- "新建 /work/chatop-ai 独立 git 仓" → Task 1 ✓
- "FROM 官方核心镜像，已有功能全保留" → Task 4（用 desktop 变体，已在抬头说明对设计的细化）+ Task 5 Step 5 回归核对 ✓
- "拉 kasmtech/noVNC 改→构建→覆盖 www" → Task 3（vendor+构建方式）+ Task 4（注入）✓
- "不碰 C++" → 全程仅 COPY 静态前端，无 builder.sh/C++ 编译 ✓
- 风险点"www 路径需实测""core vs desktop""noVNC 构建方式" → Task 2/3 侦察任务显式解决 ✓

**Placeholder scan：** 无 TODO/TBD。`WWW_ROOT` 与"形态 A/B 二选一"不是占位，而是**显式的实测分支**，判定规则与默认值都已给出。

**Type/路径一致性：** `novnc-src/`、`/usr/share/kasmvnc/www/`、sentinel 字符串 `CHATOP-AI-INJECTED`、容器名 `chatop-ai`/`kasm-recon` 在各 Task 间一致。

**未决项的处理方式：** 凡真环境才能定的值（www 路径、是否需构建）都落在 Task 2/3 的产出 `docs/recon.md`，后续 Task 引用确定值——符合"先核实再写死"。
