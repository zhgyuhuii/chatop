# syntax=docker/dockerfile:1.7
# =============================================================================
# Selkies + 察元AI (chatop) 构建
# 对应 build-and-run.sh 的逻辑：构建 Selkies → 注入 baseimage → 构建 察元AI
# 使用：存在 selkies-src 时用本地代码，否则从 GitHub 克隆
# 需启用 BuildKit（Docker 23+ 默认开启）以支持 RUN --mount=type=cache 缓存加速
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: 构建 Selkies 前端
# -----------------------------------------------------------------------------
# 锁 digest 保证可复现构建（如需升级：重新解析 tag 的 digest 后更新此处）
FROM ghcr.io/linuxserver/baseimage-alpine:3.22@sha256:97004e5491cae35367e243bc4fa9db1468f3c8e1ee8819ed212f28d39b86954a AS selkies-build

ARG SELKIES_REPO=https://github.com/selkies-project/selkies.git
# 锁定到验证过的 Selkies commit，避免跟随 main 漂移导致前端 break；置空则取 main 最新。
# 必须用 2026-03-27 之前的 commit：之后上游把 addons/gst-web-core 改名为 selkies-web-core
# 并移除了 selkies-dashboard-zinc，本 Dockerfile 仍按旧结构构建三套 dashboard。
# 7dd6a93(2026-03-24) 已核对含 gst-web-core + 三个 dashboard + universal-touch-gamepad。
ARG SELKIES_COMMIT=7dd6a93065332e5b3fe48fe5e5eb911a91f82746

RUN apk add --no-cache cmake git nodejs npm

# 限制 Node/Vite 构建的 V8 堆，防止单次构建内存失控把宿主机 dockerd 拖到 OOM
# （宿主仅 7.3G 内存；此前多套 dashboard 构建峰值 ~4.7G 导致 dockerd 被 OOM 杀掉）
ENV NODE_OPTIONS=--max-old-space-size=2048

# 优先使用本地 selkies-src，不存在则克隆；复制 logo.png 或 logo.svg 到各 dashboard
COPY . /build-context
RUN if [ -f /build-context/logo.png ] || [ -f /build-context/logo.svg ]; then \
      for d in selkies-dashboard selkies-dashboard-zinc selkies-dashboard-wish; do \
        mkdir -p /build-context/selkies-src/addons/$d/public 2>/dev/null || true; \
      done; \
    fi
RUN if [ -d /build-context/selkies-src ] && [ -f /build-context/selkies-src/addons/gst-web-core/package.json ]; then \
      cp -a /build-context/selkies-src /src; \
      echo "使用本地 selkies-src"; \
    elif [ -n "$SELKIES_COMMIT" ]; then \
      mkdir -p /src && cd /src && git init -q && git remote add origin "$SELKIES_REPO" && \
      git fetch --depth 1 origin "$SELKIES_COMMIT" && git checkout -f FETCH_HEAD; \
      echo "从 GitHub 浅取指定 commit $SELKIES_COMMIT"; \
    else \
      git clone --depth 1 "$SELKIES_REPO" /src; \
      echo "从 GitHub 克隆 Selkies main 最新"; \
    fi

# 将 logo 复制到各 dashboard 的 public 目录；支持 logo.png 或 logo.svg
RUN if [ -f /build-context/logo.png ]; then \
      for d in selkies-dashboard selkies-dashboard-zinc selkies-dashboard-wish; do \
        mkdir -p /src/addons/$d/public && cp /build-context/logo.png /src/addons/$d/public/logo.png; \
      done; \
      sed -i 's|href="icon.png"|href="logo.png"|g; s|href="logo.svg"|href="logo.png"|g' /src/addons/selkies-dashboard/index.html 2>/dev/null || true; \
      find /src/addons \( -name "*.jsx" -o -name "*.tsx" \) -exec sed -i 's|src="logo.svg"|src="logo.png"|g; s|src="/logo.svg"|src="/logo.png"|g' {} \; 2>/dev/null || true; \
      echo "已添加 logo.png"; \
    elif [ -f /build-context/logo.svg ]; then \
      for d in selkies-dashboard selkies-dashboard-zinc selkies-dashboard-wish; do \
        mkdir -p /src/addons/$d/public && cp /build-context/logo.svg /src/addons/$d/public/logo.svg; \
      done; \
      sed -i 's|href="icon.png"|href="logo.svg"|g; s|type="image/png" href="logo.png"|type="image/svg+xml" href="logo.svg"|g' /src/addons/selkies-dashboard/index.html 2>/dev/null || true; \
      find /src/addons \( -name "*.jsx" -o -name "*.tsx" \) -exec sed -i 's|src="logo.png"|src="logo.svg"|g; s|src="/logo.png"|src="/logo.svg"|g' {} \; 2>/dev/null || true; \
      echo "已添加 logo.svg"; \
    fi

# npm 缓存挂载：4 次 npm install 复用同一下载缓存，重建大幅提速（缓存不进镜像层）
RUN --mount=type=cache,target=/root/.npm \
  cd /src/addons/gst-web-core && npm install && npm run build && \
  DASHBOARDS="selkies-dashboard selkies-dashboard-zinc selkies-dashboard-wish" && \
  mkdir /buildout && \
  for DASH in $DASHBOARDS; do \
    cd /src/addons/$DASH && \
    cp ../gst-web-core/dist/selkies-core.js src/ && \
    npm install && npm run build && \
    mkdir -p dist/src dist/nginx && \
    cp ../gst-web-core/dist/selkies-core.js dist/src/ && \
    cp ../universal-touch-gamepad/universalTouchGamepad.js dist/src/ && \
    cp ../gst-web-core/nginx/* dist/nginx/ && \
    (cp -r ../gst-web-core/dist/jsdb dist/ 2>/dev/null || mkdir -p dist/jsdb) && \
    mkdir -p /buildout/$DASH && \
    cp -ar dist/* /buildout/$DASH/; \
  done

# -----------------------------------------------------------------------------
# Stage 2: 基于 linuxserver webtop:ubuntu-kde 上游基础镜像，注入自定义 Selkies 与 logo
# -----------------------------------------------------------------------------
# 锁 digest 保证可复现构建（如需升级：重新解析 tag 的 digest 后更新此处）
FROM ghcr.io/linuxserver/webtop:ubuntu-kde@sha256:32fb57cb5a97314faf690935b1b973562982afb5463a35764e3a57e7bcd40476

ARG BUILD_DATE
ARG VERSION=1.0.0
LABEL build_version="察元AI (chatop) Ubuntu KDE - ${VERSION} Build-date:- ${BUILD_DATE}"
LABEL maintainer="chatop"

ENV TITLE="察元AI"

# 注入自定义构建的 Selkies
COPY --from=selkies-build /buildout/selkies-dashboard /usr/share/selkies/selkies-dashboard
COPY --from=selkies-build /buildout/selkies-dashboard-zinc /usr/share/selkies/selkies-dashboard-zinc
COPY --from=selkies-build /buildout/selkies-dashboard-wish /usr/share/selkies/selkies-dashboard-wish

# ========== openclaw-tool + WhiteSur GTK/图标主题（仓库根目录的 zip）==========
# apt 缓存挂载：包下载缓存复用，重建提速；缓存为外部挂载不进镜像层，故无需手动 rm lists
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && apt-get install -y --no-install-recommends \
      unzip sassc libxml2-utils python3-tk python3-pip \
      gtk2-engines-murrine gtk2-engines-pixbuf gnome-themes-extra && \
    pip3 install --no-cache-dir customtkinter 2>/dev/null || true

# 仅安装仓库中实际存在的 WhiteSur GTK 主题与图标主题
COPY WhiteSur-gtk-theme-master.zip WhiteSur-icon-theme-master.zip /tmp/themes/
RUN cd /tmp/themes && for z in *.zip; do [ -f "$z" ] && unzip -o -q "$z"; done && rm -f *.zip && \
    export HOME=/root USER=root && \
    (cd WhiteSur-gtk-theme-master 2>/dev/null && chmod +x install.sh && ./install.sh) || true && \
    (cd WhiteSur-icon-theme-master 2>/dev/null && chmod +x install.sh && ./install.sh -a) || true && \
    gtk-update-icon-cache -f /usr/share/icons 2>/dev/null || true && \
    echo "=== 已安装 GTK 主题 ===" && ls /usr/share/themes/ 2>/dev/null | head -20 && \
    echo "=== 已安装图标主题 ===" && ls /usr/share/icons/ 2>/dev/null | grep -E "WhiteSur" | head -20 && \
    rm -rf /tmp/themes

# openclaw-tool 配置程序
COPY openclaw-tool /opt/openclaw-tool
RUN find /opt/openclaw-tool -type f \( -name "*.desktop" -o -name "*.sh" -o -name "*.txt" \) -exec sed -i 's|/openclaw-tool|/opt/openclaw-tool|g' {} \; 2>/dev/null || true
RUN OC_DESKTOP=$(find /opt/openclaw-tool -name "*.desktop" -type f | head -1) && \
    if [ -n "$OC_DESKTOP" ]; then cp "$OC_DESKTOP" /usr/share/applications/openclaw-tool.desktop; mkdir -p /etc/skel/Desktop; cp /usr/share/applications/openclaw-tool.desktop /etc/skel/Desktop/; fi
RUN mkdir -p /etc/skel/.config && \
    printf '[General]\nColorScheme=MacVenturaDark\n\n[KDE]\nLookAndFeelPackage=com.github.vinceliuice.MacVentura-Dark\n\n[Icons]\nTheme=WhiteSur\n' > /etc/skel/.config/kdeglobals 2>/dev/null || true && \
    printf '[org.kde.kdecoration2]\ntheme=MacVentura\n' > /etc/skel/.config/kwinrc 2>/dev/null || true

# 添加 logo（支持 logo.png 或 logo.svg）+ 开机动画 + SDDM 登录主题
COPY logo* /tmp/
COPY custom-splash/ /tmp/custom-splash/
COPY custom-sddm/ /tmp/custom-sddm/
RUN echo "**** add logo ****" && \
  if [ -f /tmp/logo.png ]; then \
    cp /tmp/logo.png /usr/share/selkies/www/icon.png && \
    cp /tmp/logo.png /usr/share/selkies/www/logo.png; \
  elif [ -f /tmp/logo.svg ]; then \
    apt-get update && apt-get install -y --no-install-recommends librsvg2-bin && \
    rsvg-convert -w 180 -h 180 /tmp/logo.svg -o /usr/share/selkies/www/icon.png && \
    cp /tmp/logo.svg /usr/share/selkies/www/logo.svg && \
    apt-get purge -y librsvg2-bin && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*; \
  else \
    curl -sLo /usr/share/selkies/www/icon.png \
      https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/webtop-logo.png; \
  fi && \
  mkdir -p /usr/share/plasma/look-and-feel/org.chatop.custom-splash && \
  cp -a /tmp/custom-splash/* /usr/share/plasma/look-and-feel/org.chatop.custom-splash/ 2>/dev/null || true && \
  mkdir -p /usr/share/plasma/look-and-feel/org.chatop.custom-splash/contents/splash/images && \
  curl -sLo /usr/share/plasma/look-and-feel/org.chatop.custom-splash/contents/splash/images/busywidget.svgz \
    "https://raw.githubusercontent.com/KDE/plasma-workspace/master/lookandfeel/org.kde.breeze/contents/splash/images/busywidget.svgz" 2>/dev/null || true && \
  ( [ -f /tmp/logo.png ] && cp /tmp/logo.png /usr/share/plasma/look-and-feel/org.chatop.custom-splash/contents/splash/images/logo.png ) || \
  ( [ -f /tmp/logo.svg ] && cp /tmp/logo.svg /usr/share/plasma/look-and-feel/org.chatop.custom-splash/contents/splash/images/logo.svg ) || \
  ( curl -sLo /usr/share/plasma/look-and-feel/org.chatop.custom-splash/contents/splash/images/logo.png \
    https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/webtop-logo.png ) && \
  mkdir -p /usr/share/sddm/themes/chatop /tmp/custom-sddm/images && \
  cp -a /tmp/custom-sddm/* /usr/share/sddm/themes/chatop/ && \
  ( [ -f /tmp/logo.png ] && cp /tmp/logo.png /usr/share/sddm/themes/chatop/images/logo.png ) || \
  ( [ -f /tmp/logo.svg ] && cp /tmp/logo.svg /usr/share/sddm/themes/chatop/images/logo.svg ) || true && \
  mkdir -p /etc/sddm.conf.d && printf '[Theme]\nCurrent=chatop\n' > /etc/sddm.conf.d/theme.conf && \
  rm -rf /config/.cache /tmp/*

# 构建时界面定制：custom-defaults 在首次启动时复制到 /config
COPY custom-defaults/ /custom-defaults/
COPY custom-cont-init.d/91-set-hostname.sh /custom-cont-init.d/91-set-hostname.sh
COPY custom-cont-init.d/92-themes-and-openclaw.sh /custom-cont-init.d/92-themes-and-openclaw.sh
COPY custom-cont-init.d/93-load-custom-defaults.sh /custom-cont-init.d/93-load-custom-defaults.sh
# 自定义 init：KDE 面板居中、logo 覆盖、禁用 PackageKit、默认浏览器、终端、用户名、提示符
COPY custom-cont-init.d/94-kde-panel-center.sh /custom-cont-init.d/94-kde-panel-center.sh
COPY custom-cont-init.d/95-copy-logo.sh /custom-cont-init.d/95-copy-logo.sh
COPY custom-cont-init.d/96-disable-packagekit.sh /custom-cont-init.d/96-disable-packagekit.sh
COPY custom-cont-init.d/97-set-default-browser.sh /custom-cont-init.d/97-set-default-browser.sh
COPY custom-cont-init.d/98-fix-terminal.sh /custom-cont-init.d/98-fix-terminal.sh
COPY custom-cont-init.d/99-custom-user-prompt.sh /custom-cont-init.d/99-custom-user-prompt.sh
COPY custom-cont-init.d/99-set-username /custom-cont-init.d/99-set-username
RUN chmod +x /custom-cont-init.d/91-set-hostname.sh /custom-cont-init.d/92-themes-and-openclaw.sh /custom-cont-init.d/93-load-custom-defaults.sh /custom-cont-init.d/94-kde-panel-center.sh /custom-cont-init.d/95-copy-logo.sh /custom-cont-init.d/96-disable-packagekit.sh /custom-cont-init.d/97-set-default-browser.sh /custom-cont-init.d/98-fix-terminal.sh /custom-cont-init.d/99-custom-user-prompt.sh /custom-cont-init.d/99-set-username

# 镜像构建完成后垃圾清理，减小体积
COPY scripts/cleanup-image.sh /tmp/cleanup-image.sh
RUN chmod +x /tmp/cleanup-image.sh && /tmp/cleanup-image.sh && rm -f /tmp/cleanup-image.sh

EXPOSE 3001
VOLUME /config
