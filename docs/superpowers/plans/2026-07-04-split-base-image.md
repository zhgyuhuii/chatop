# 拆分 base 镜像 + 增量产品镜像 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把固定/重/联网的构建内容沉到 `chatop-base:latest`（很少重建），产品 `chatop-ai:<VERSION>` 只留快变内容，实现秒级、零下载的迭代构建。

**Architecture:** 新增 `Dockerfile.base` 承载所有固定层并 `USER 1000` 收尾；现有 `Dockerfile` 改成 `FROM chatop-base:latest` 只做快变 COPY；`build-base.sh` 建 base，`build-and-run.sh` 自举（无 base 就先建）后只重打产品层。

**Tech Stack:** Docker / BuildKit (dockerfile:1.7)、docker compose、kasmweb/core-ubuntu-jammy 基础镜像、bash 构建脚本。

**验证说明：** 本计划无单元测试；每个任务的"验证"= 构建成功或运行时行为观察。设计与验收见 `docs/superpowers/specs/2026-07-04-split-base-image-design.md`。

**前置：** 参考基线是当前健康的 Linux 服务器容器 `chatop-ai`（拆分前后行为须一致）。所有 `docker` 命令在本仓库根 `/work/chatop` 下，`admin` 无 docker 权限，需 `sudo docker ...`。

---

### Task 1: 创建 `Dockerfile.base`（固定层）

**Files:**
- Create: `/work/chatop/Dockerfile.base`

- [ ] **Step 1: 写出 `Dockerfile.base`**

内容如下（每个 RUN 块逐字取自当前 `Dockerfile` 对应行，仅重排为 base 独立顺序）：

```dockerfile
# syntax=docker/dockerfile:1.7
# chatop-base：固定/重/联网的一切。很少重建。产品镜像 FROM 此镜像。
FROM kasmweb/core-ubuntu-jammy:1.19.0
ARG VERSION=1.1.0
LABEL maintainer="chatop-ai" build_version="chatop-base ${VERSION}"

USER root

# === filebrowser 二进制（KasmVNC 开源版无文件传输） ===
ARG FB_ARCH=linux-amd64
RUN set -eux; \
    curl -fsSL -o /tmp/fb.tar.gz "https://github.com/filebrowser/filebrowser/releases/latest/download/${FB_ARCH}-filebrowser.tar.gz"; \
    tar -xzf /tmp/fb.tar.gz -C /usr/local/bin filebrowser; \
    rm -f /tmp/fb.tar.gz; \
    chmod +x /usr/local/bin/filebrowser; \
    /usr/local/bin/filebrowser version

# === Caddy 二进制（单端口反代 KasmVNC + filebrowser） ===
ARG CADDY_VERSION=2.11.4
RUN set -eux; \
    curl -fsSL -o /tmp/caddy.tar.gz "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_amd64.tar.gz"; \
    tar -xzf /tmp/caddy.tar.gz -C /usr/local/bin caddy; \
    rm -f /tmp/caddy.tar.gz; \
    chmod +x /usr/local/bin/caddy; \
    /usr/local/bin/caddy version
ENV XDG_DATA_HOME=/tmp/caddy XDG_CONFIG_HOME=/tmp/caddy

# === CJK 字体（中文渲染前提） ===
RUN apt-get update && apt-get install -y --no-install-recommends \
      fonts-noto-cjk fonts-noto-color-emoji \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# === Node 22 + pipx（npm 类 AI 工具前提） ===
RUN set -eux; \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -; \
    apt-get install -y --no-install-recommends nodejs; \
    node -v; npm -v; \
    apt-get install -y --no-install-recommends pipx; \
    rm -rf /var/lib/apt/lists/*

# === 用户级 npm 前缀 + PATH（登录 shell 与交互 shell 都加载） ===
RUN set -eux; \
    printf '\n# chatop app-manager user-level tooling\nexport NPM_CONFIG_PREFIX="$HOME/.npm-global"\nexport PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"\n' \
      > /etc/profile.d/chatop-apps.sh; \
    chmod +x /etc/profile.d/chatop-apps.sh; \
    printf '\n# chatop: 交互式(非登录)终端也加载用户级工具 PATH\n[ -f /etc/profile.d/chatop-apps.sh ] && . /etc/profile.d/chatop-apps.sh\n' \
      >> /etc/bash.bashrc

# === vnc_startup 登录名 + 剪贴板补丁 ===
RUN sed -i 's/-u kasm_user -wo/-u "${LOGIN_USER:-admin}" -wo/' /dockerstartup/vnc_startup.sh && \
    sed -i 's/kasm_user:\$VNC_PW/${LOGIN_USER:-admin}:\$VNC_PW/g' /dockerstartup/vnc_startup.sh && \
    sed -i '/^APP_NAME=/a if [ "${CLIPBOARD_OUT:-1}" = "0" ]; then export KASM_SVC_SEND_CUT_TEXT="-SendCutText=0"; else export KASM_SVC_SEND_CUT_TEXT="-SendCutText=1"; fi; if [ "${CLIPBOARD_IN:-1}" = "0" ]; then export KASM_SVC_ACCEPT_CUT_TEXT="-AcceptCutText=0"; else export KASM_SVC_ACCEPT_CUT_TEXT="-AcceptCutText=1"; fi' /dockerstartup/vnc_startup.sh
ENV LOGIN_USER=admin

# === Python 3.11（Sovyx 需 >=3.11；deadsnakes PPA） ===
RUN apt-get update && apt-get install -y --no-install-recommends software-properties-common && \
    add-apt-repository -y ppa:deadsnakes/ppa && apt-get update && \
    apt-get install -y --no-install-recommends python3.11 python3.11-venv python3.11-distutils && \
    python3.11 --version && rm -rf /var/lib/apt/lists/*

# === 系统中文化：locale + 语言包 ===
RUN apt-get update && apt-get install -y --no-install-recommends \
      locales language-pack-zh-hans language-pack-gnome-zh-hans \
    && locale-gen zh_CN.UTF-8 \
    && update-locale LANG=zh_CN.UTF-8 LANGUAGE=zh_CN:zh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
ENV LANG=zh_CN.UTF-8 LANGUAGE=zh_CN:zh LC_ALL=zh_CN.UTF-8

# === Google Chrome（Web 智能体载体；容器内加 --no-sandbox） ===
RUN set -eux; \
    apt-get update; \
    curl -fsSL -o /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb; \
    apt-get install -y --no-install-recommends /tmp/chrome.deb; \
    rm -f /tmp/chrome.deb; \
    sed -i 's#^Exec=/usr/bin/google-chrome-stable#Exec=/usr/bin/google-chrome-stable --no-sandbox --start-maximized#' \
        /usr/share/applications/google-chrome.desktop; \
    /usr/bin/google-chrome-stable --version; \
    printf '#!/bin/bash\nexec /opt/google/chrome/google-chrome --no-sandbox --start-maximized "$@"\n' \
        > /usr/local/bin/google-chrome-stable; \
    cp /usr/local/bin/google-chrome-stable /usr/local/bin/google-chrome; \
    chmod +x /usr/local/bin/google-chrome-stable /usr/local/bin/google-chrome; \
    sed -i 's/^WebBrowser=.*/WebBrowser=google-chrome/' /etc/xdg/xfce4/helpers.rc; \
    printf '[Default Applications]\nx-scheme-handler/http=google-chrome.desktop\nx-scheme-handler/https=google-chrome.desktop\ntext/html=google-chrome.desktop\nx-scheme-handler/about=google-chrome.desktop\n' \
        > /etc/xdg/mimeapps.list; \
    apt-get clean; rm -rf /var/lib/apt/lists/*

# === proot-apps（userspace PRoot GUI 应用安装器） ===
RUN mkdir -p /tmp/pa && \
    PAPPS=$(curl -sX GET "https://api.github.com/repos/linuxserver/proot-apps/releases/latest" | awk '/tag_name/{print $4;exit}' FS='[""]') && \
    curl -L "https://github.com/linuxserver/proot-apps/releases/download/${PAPPS}/proot-apps-x86_64.tar.gz" | tar -xzf - -C /tmp/pa/ && \
    install -m755 /tmp/pa/proot-apps /tmp/pa/proot /tmp/pa/jq /tmp/pa/ncat /usr/local/bin/ && \
    rm -rf /tmp/pa

# === 用户改名 kasm-user → ${APP_USER} + home 实体迁移 ===
ARG APP_USER=admin
RUN if [ "$APP_USER" != "kasm-user" ]; then \
      usermod  -l "$APP_USER" -d "/home/$APP_USER" -m -s /bin/bash kasm-user && \
      groupmod -n "$APP_USER" kasm-user && \
      sed -i "s#/home/kasm-user#/home/$APP_USER#g" \
          /dockerstartup/vnc_startup.sh \
          /dockerstartup/kasm_pre_shutdown_user.sh \
          /etc/cups/cups-pdf.conf && \
      ! test -e /home/kasm-user ; \
    fi
WORKDIR /home/${APP_USER}
ENV HOME=/home/${APP_USER}
RUN mkdir -p /opt/chatop && \
    mv /home/kasm-default-profile /opt/chatop/default-profile && \
    sed -i 's#/home/kasm-default-profile#/opt/chatop/default-profile#' /dockerstartup/kasm_default_profile.sh && \
    ! test -e /home/kasm-default-profile && ! test -e /home/kasm-user
ENV XDG_CONFIG_HOME=/tmp/caddy XDG_DATA_HOME=${HOME}/.local/share
ENV NPM_CONFIG_PREFIX=${HOME}/.npm-global PATH=${HOME}/.npm-global/bin:${HOME}/.local/bin:${PATH}

# === 核心工具预装(AI CLI：claude/codex/openclaw/rtk...) → seed-home ===
RUN mkdir -p /usr/local/lib/chatop /etc/chatop
COPY app-manager/chatop-preinstall.sh /usr/local/lib/chatop/chatop-preinstall.sh
RUN sed -i 's/\r$//' /usr/local/lib/chatop/chatop-preinstall.sh && \
    chmod +x /usr/local/lib/chatop/chatop-preinstall.sh
RUN su admin -c 'bash /usr/local/lib/chatop/chatop-preinstall.sh' && \
    mv /home/admin /opt/chatop-seed-home && \
    mkdir -p /home/admin && chown admin:admin /home/admin && chmod 755 /home/admin && \
    ! test -e /home/kasm-user
# 构建期可能建出 root 属主 /tmp/caddy，运行时 uid 1000 写不进，删掉让运行时重建
RUN rm -rf /tmp/caddy
# 恢复运行用户 uid 1000
USER 1000
```

- [ ] **Step 2: 构建 base，验证成功**

Run:
```bash
cd /work/chatop && sudo docker build -f Dockerfile.base --build-arg APP_USER=admin -t chatop-base:latest .
```
Expected: 构建成功，最后 `naming to docker.io/library/chatop-base:latest`。首次会联网下载（filebrowser/caddy/apt/node/python/chrome/proot-apps/npm 工具），耗时数分钟属正常。

- [ ] **Step 3: 校验 base 结束态与当前 Dockerfile 第 261 行一致**

Run:
```bash
sudo docker run --rm --entrypoint sh chatop-base:latest -c \
  'id; echo HOME=$HOME; echo PATH=$PATH; echo LANG=$LANG; \
   ls -d /opt/chatop-seed-home /opt/chatop/default-profile; \
   which caddy filebrowser node python3.11 google-chrome proot-apps; \
   ! test -e /home/kasm-user && echo NO-KASM-USER-OK; \
   test -x /usr/local/lib/chatop/chatop-preinstall.sh && echo PREINSTALL-OK'
```
Expected: `uid=1000`、`HOME=/home/admin`、PATH 含 `/home/admin/.npm-global/bin:/home/admin/.local/bin`、`LANG=zh_CN.UTF-8`、两个 /opt 目录存在、六个二进制都有路径、打印 `NO-KASM-USER-OK` 与 `PREINSTALL-OK`。

- [ ] **Step 4: 提交**

```bash
cd /work/chatop
git add Dockerfile.base
git commit -m "build(base): 新增 Dockerfile.base 承载固定/重/联网层 → chatop-base

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: 改写 `Dockerfile`（产品/增量层，FROM chatop-base）

**Files:**
- Modify: `/work/chatop/Dockerfile`（整体替换为下方内容）

- [ ] **Step 1: 用以下内容整体替换 `Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1.7
# 前端构建（改前端只重跑此 stage）
FROM node:20-alpine AS web
WORKDIR /src
COPY novnc-src/ ./
RUN --mount=type=cache,target=/root/.npm npm install && npm run build

# 产品镜像 = 固定 chatop-base + 快变内容（改这些才重打，且不联网）
FROM chatop-base:latest
ARG VERSION=1.1.0
LABEL maintainer="chatop-ai" build_version="chatop-ai ${VERSION}"
USER root

# === app-manager：后端 + catalog + 图标 + 启动脚本 + GUI/CLI 脚本 + 播种脚本 ===
RUN mkdir -p /usr/local/lib/chatop /etc/chatop
COPY app-manager/app_manager.py /usr/local/lib/chatop/app_manager.py
COPY app-manager/apps-catalog.json /etc/chatop/apps-catalog.json
COPY app-manager/icons/ /usr/share/kasmvnc/www/app-icons/
COPY app-manager/start-app-manager.sh /usr/local/bin/start-app-manager.sh
COPY app-manager/gui-install.sh app-manager/gui-uninstall.sh /usr/local/lib/chatop/
COPY app-manager/chatop-run-cli.sh /usr/local/bin/chatop-run-cli
COPY app-manager/chatop-seed-home.sh /usr/local/bin/chatop-seed-home.sh

# === Caddy 反代配置 + 启动脚本；filebrowser 启动脚本 ===
COPY caddy/Caddyfile /etc/caddy/Caddyfile
COPY caddy/start-caddy.sh /usr/local/bin/start-caddy.sh
COPY filebrowser/start-filebrowser.sh /usr/local/bin/start-filebrowser.sh

# === 品牌资源 + KasmVNC 剪贴板配置 ===
COPY assets/background.png /usr/share/backgrounds/chayuanai/wallpaper.png
COPY assets/background.png /usr/share/backgrounds/bg_default.png
COPY assets/set-wallpaper.sh /usr/local/bin/set-wallpaper.sh
COPY kasmvnc.yaml /etc/kasmvnc/kasmvnc.yaml

# === CRLF 兜底 + 可执行位（Windows 检出可能带 CRLF，shebang 会挂） ===
RUN sed -i 's/\r$//' \
        /usr/local/lib/chatop/gui-install.sh /usr/local/lib/chatop/gui-uninstall.sh \
        /usr/local/bin/start-app-manager.sh /usr/local/bin/chatop-run-cli \
        /usr/local/bin/chatop-seed-home.sh /usr/local/bin/start-caddy.sh \
        /usr/local/bin/start-filebrowser.sh /usr/local/bin/set-wallpaper.sh \
        /etc/caddy/Caddyfile && \
    chmod +x /usr/local/lib/chatop/gui-install.sh /usr/local/lib/chatop/gui-uninstall.sh \
        /usr/local/bin/start-app-manager.sh /usr/local/bin/chatop-run-cli \
        /usr/local/bin/chatop-seed-home.sh /usr/local/bin/start-caddy.sh \
        /usr/local/bin/set-wallpaper.sh

# === filebrowser 启动脚本(幂等 authoritative 覆盖：noauth + db 放 /tmp) ===
RUN printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -e' \
  'ROOT="${FB_ROOT:-$HOME}"; PORT="${FB_PORT:-8585}"; DB="/tmp/filebrowser.db"' \
  'rm -f "$DB"' \
  'exec filebrowser --noauth -d "$DB" -r "$ROOT" -b /files -a 127.0.0.1 -p "$PORT"' \
  > /usr/local/bin/start-filebrowser.sh && chmod +x /usr/local/bin/start-filebrowser.sh

# === custom_startup（常驻，末尾 wait；否则被 KASM_PROCS 判死无限重启拖垮 VNC） ===
RUN printf '#!/bin/bash\nexport KASM_BASIC="$(echo -n "${LOGIN_USER:-admin}:${FILES_PW:-${VNC_PW:-password}}" | base64 -w0)"\n/usr/local/bin/chatop-seed-home.sh >/tmp/seed.log 2>&1\n/usr/local/bin/start-filebrowser.sh >/tmp/filebrowser.log 2>&1 &\nXDG_DATA_HOME=/tmp/caddy XDG_CONFIG_HOME=/tmp/caddy /usr/local/bin/start-caddy.sh >/tmp/caddy.log 2>&1 &\n/usr/local/bin/start-app-manager.sh >/tmp/app-mgr.log 2>&1 &\n/usr/local/bin/set-wallpaper.sh >/tmp/set-wallpaper.log 2>&1 &\nmkdir -p $HOME/.local/bin; ln -sf /usr/local/bin/proot /usr/local/bin/jq /usr/local/bin/ncat /usr/local/bin/proot-apps $HOME/.local/bin/ 2>/dev/null\nwait\n' > /dockerstartup/custom_startup.sh && \
    chmod +x /dockerstartup/custom_startup.sh

# === 注入定制前端 dist（放最后：前端迭代只重跑这层）+ 品牌图标/splash 覆盖 ===
COPY --from=web --chown=root:root /src/dist/ /usr/share/kasmvnc/www/
COPY assets/logo-sm.png /usr/share/kasmvnc/www/app-icons/chatop-logo.png
COPY app-manager/apps-icon.svg /usr/share/kasmvnc/www/app-icons/apps.svg
COPY assets/background-splash.jpg /usr/share/kasmvnc/www/app/images/splash.jpg

# 恢复运行用户 uid 1000
USER 1000
```

- [ ] **Step 2: 构建产品镜像（依赖 Task 1 的 base 已在本地）**

Run:
```bash
cd /work/chatop && sudo docker build --build-arg VERSION=1.1.0 -t chatop-ai:1.1.0 .
```
Expected: 构建成功。base 那些重层**不出现**（因为都在 `chatop-base` 里，不在本 Dockerfile）；只跑 web stage + 若干 COPY/RUN 层，秒级~一分钟级。

- [ ] **Step 3: 验证产品镜像结束态**

Run:
```bash
sudo docker run --rm --entrypoint sh chatop-ai:1.1.0 -c \
  'id; test -x /usr/local/bin/start-caddy.sh && test -x /usr/local/bin/start-app-manager.sh && \
   test -x /dockerstartup/custom_startup.sh && test -f /usr/share/kasmvnc/www/app-icons/chatop-logo.png && \
   head -1 /usr/local/bin/start-caddy.sh | cat -A && echo APP-OK'
```
Expected: `uid=1000`、shebang 行是 `#!/usr/bin/env bash$`（无 `^M`）、打印 `APP-OK`。

- [ ] **Step 4: 提交**

```bash
cd /work/chatop
git add Dockerfile
git commit -m "build(app): Dockerfile 改 FROM chatop-base:latest，只保留快变增量层

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: build 脚本 + compose 适配

**Files:**
- Create: `/work/chatop/build-base.sh`
- Modify: `/work/chatop/build-and-run.sh`
- Modify: `/work/chatop/docker-compose.yml`

- [ ] **Step 1: 创建 `build-base.sh`**

```bash
#!/usr/bin/env bash
# 构建固定基础镜像 chatop-base:latest。依赖变了 / 想更新 AI 工具 / 新机器首次 才需跑。
set -euo pipefail
cd "$(dirname "$0")"
# 读取 .env 里的 LOGIN_USER 作为系统用户名（默认 admin）
if [ -f .env ]; then set -a; . ./.env; set +a; fi
sudo docker build -f Dockerfile.base \
  --build-arg APP_USER="${LOGIN_USER:-admin}" \
  --build-arg LOGIN_USER="${LOGIN_USER:-admin}" \
  -t chatop-base:latest .
echo "chatop-base:latest 构建完成。之后 ./build-and-run.sh 会自动使用它。"
```

- [ ] **Step 2: 用以下内容整体替换 `build-and-run.sh`（加自举）**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "请先 cp .env.example .env 并改密码"; exit 1; }
export VERSION="$(cat VERSION)"
# 自举：本地没有 base 就先建一次（新机器一条命令搞定）
if ! sudo docker image inspect chatop-base:latest >/dev/null 2>&1; then
  echo "未发现 chatop-base:latest，先构建 base（首次较慢，之后飞快）..."
  ./build-base.sh
fi
sudo docker compose up -d --build
echo "已启动：https://localhost:$(grep -E '^PORT=' .env | cut -d= -f2 || echo 6901)"
```

- [ ] **Step 3: 改 `docker-compose.yml`——移除 APP_USER build-arg，加 pull_policy**

在 `docker-compose.yml` 的 `services.chatop-ai.build` 段：删除 `args` 下的 `APP_USER: ${LOGIN_USER:-admin}` 行（APP_USER 现在是 base-build-time 参数，产品 build 不再需要）。`args` 仅保留 `VERSION: ${VERSION:-1.0.0}`。

在 `services.chatop-ai` 下（与 `image:` 同级）新增一行，避免 Docker 把本地 `chatop-base:latest` 当远程去 pull：

```yaml
    pull_policy: build
```

- [ ] **Step 4: 赋可执行位并语法自检**

Run:
```bash
cd /work/chatop && chmod +x build-base.sh build-and-run.sh && \
  bash -n build-base.sh && bash -n build-and-run.sh && \
  sudo docker compose config >/dev/null && echo SCRIPTS-OK
```
Expected: 打印 `SCRIPTS-OK`（`compose config` 校验 yml 合法、无解析错）。

- [ ] **Step 5: 提交**

```bash
cd /work/chatop
git add build-base.sh build-and-run.sh docker-compose.yml
git commit -m "build(scripts): 加 build-base.sh + build-and-run.sh 自举 base + compose 适配

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: 端到端运行 + 增量提速验证

**Files:** 无（纯验证）

- [ ] **Step 1: 全流程起容器**

Run:
```bash
cd /work/chatop && ./build-and-run.sh
```
Expected: base 已在本地则跳过 base 构建，只重打产品层；最后打印 `已启动：https://localhost:6901`。

- [ ] **Step 2: 验证运行时行为与拆分前一致**

Run:
```bash
sleep 8
curl -sk --max-time 8 -o /dev/null -w '%{http_code}\n' https://127.0.0.1:6901/login
sudo docker exec chatop-ai sh -c "ss -ltnp | grep -E '7443|8686' && echo GW-OK"
sudo docker exec chatop-ai sh -c "su admin -c 'which claude codex openclaw' && echo TOOLS-OK"
```
Expected: `/login` 返回 `200`；打印 `GW-OK`（Caddy 7443 + app-manager 8686 在听）；`TOOLS-OK`（AI 工具在 admin PATH 里，来自 base seed-home）。

- [ ] **Step 3: 验证"改代码零下载"——核心收益**

Run:
```bash
cd /work/chatop
touch app-manager/app_manager.py
sudo docker compose build 2>&1 | tee /tmp/rebuild.log | tail -5
echo "--- 下载/安装关键字命中数(应为0) ---"
grep -cE 'apt-get|npm i -g|deb.nodesource|dl.google.com|releases/download' /tmp/rebuild.log
```
Expected: 最后一行为 `0`——改 app-manager 代码重建时**没有任何 apt/npm/二进制下载**发生，只重打 COPY 层。这就是本次改造的核心验收。

- [ ] **Step 4: 无提交（本任务纯验证）**

若前三步任一不达预期，回到对应 Task 修正后重跑。

---

### Task 5: 更新文档 + 清理

**Files:**
- Modify: `/work/chatop/docs/superpowers/specs/2026-07-04-split-base-image-design.md`（状态改为"已实现"）
- 视情况 Modify: `README`/`CLAUDE.md` 若有构建说明处补一句 base/app 两步流程

- [ ] **Step 1: 标记设计文档为已实现**

把设计文档头部 `- 状态：待实现（...）` 改为 `- 状态：已实现（2026-07-04）`。

- [ ] **Step 2: 提交收尾**

```bash
cd /work/chatop
git add -A
git commit -m "docs: 标记拆分 base 镜像设计为已实现

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 3: 汇总给用户**

汇报：改动文件清单、Task 4 Step 3 的"0 下载"验证结果、以及新工作流（日常 `./build-and-run.sh`；更新 base/AI 工具时 `./build-base.sh`）。询问是否 push（push 需 `sudo git push`，见记忆 git-push-auth）。

---

## 自审（对照 spec）

- **Spec 覆盖**：架构(§3)→Task1/2；拆分线(§4)→Task1/2 逐块；build 流程(§5)→Task3；边界情况(§6 CRLF/用户名/pull_policy/自举)→Task2 sed、Task3；验收标准(§8 1-5)→Task1 Step2、Task4 Step3(零下载)、Task4 Step2(行为一致)、Task2/build-and-run(自举)。全覆盖。
- **占位符扫描**：无 TBD/TODO；每个改文件步骤都给了完整内容或精确编辑指令。
- **类型/命名一致**：镜像名统一 `chatop-base:latest` / `chatop-ai:<VERSION>`；脚本 `build-base.sh` / `build-and-run.sh` 前后一致；`APP_USER`/`LOGIN_USER` build-arg 归属一致（base）。
- **已知取舍**：`su admin` 与 `mv /home/admin` 沿用当前 Dockerfile 的硬编码 admin 假设（非本次改造范围，保持行为一致）。
