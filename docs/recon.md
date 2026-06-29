# 侦察报告：官方 kasmweb 镜像 noVNC web 根路径与注入点

> Task 2（phase-1）产物。所有数值均在真实容器内实测确认，禁止凭记忆硬编码。
> 镜像：`kasmweb/ubuntu-jammy-desktop:1.16.1`
> digest：`sha256:b7c2fb2c677ad88a130ec5ea3ab990a86bc5daaa9f18c5296469bb3ca4dc9abe`
> 侦察方式：`sudo docker run -d --name kasm-recon --shm-size=512m -p 6901:6901 -e VNC_PW=recon123 ...`，容器内 `docker exec` 实测。
> 日期：2026-06-29

## 1. WWW_ROOT（前端 web 根目录，最重要）

```
/usr/share/kasmvnc/www
```

这是 KasmVNC 内置 web server 提供 noVNC 客户端页面的真实根目录。**Task 4 的 `COPY` 必须指向此路径。**

三个猜测目录的实测结果：

| 猜测目录 | 是否存在 |
|---|---|
| `/usr/share/kasmvnc/www` | ✅ 存在（即 WWW_ROOT） |
| `/usr/share/kasmvnc` | ✅ 存在（是 www 的父目录，含 `kasmvnc_defaults.yaml` + `www/`） |
| `/usr/local/share/kasmvnc/www` | ❌ 不存在 |

结论：WWW_ROOT 与第一个猜测一致，无偏差。

## 2. index.html 入口文件（精确路径）

```
/usr/share/kasmvnc/www/index.html
```

`find / -name index.html -path "*kasm*"` 全局唯一命中即此文件。
另：`vnc.html -> index.html`（软链接，同一入口）。

## 3. WWW_ROOT 目录结构（`ls -la` 实测）

```
drwxr-xr-x  app            <- 前端 UI 逻辑（ui.js / 图片 / 样式 / 本地化）
drwxr-xr-x  core           <- noVNC 协议核心（rfb.js / websock.js / 编解码）
drwxr-xr-x  dist           <- webpack 打包产物（main.bundle.js 等，页面实际加载这些）
drwxr-xr-x  docs
drwxr-xr-x  Downloads
-rw-r--r--  index.html     <- 入口（23943 字节，单行压缩 HTML）
-rw-r--r--  karma.conf.js
-rw-r--r--  LICENSE.txt
-rw-r--r--  package.json
-rw-r--r--  package-lock.json
drwxr-xr-x  po
-rw-r--r--  screen.html
drwxr-xr-x  snap
drwxr-xr-x  tests
drwxr-xr-x  vendor
lrwxrwxrwx  vnc.html -> index.html
-rw-r--r--  webpack.config.js
```

### app/ 子目录（前端可读源）

```
error-handler.js  images/  locale/  localization.js  sounds/  styles/  ui.js  ui_screen.js  webutil.js
```

### core/ 子目录（noVNC 协议层）

```
base64.js  decoders/  deflator.js  des.js  display.js  encodings.js  inflator.js  input/  mousebuttonmapper.js  output/  rfb.js  util/  websock.js
```

### dist/ 子目录（页面实际加载的打包产物）

```
error_handler.bundle.js  fonts/  images/  main.bundle.js  promise.bundle.js
runtime.bundle.js  style.bundle.css  style.bundle.js  vendors~main.bundle.js
```

> 注意：`index.html` 末尾按顺序加载 `dist/runtime.bundle.js`、`dist/vendors~main.bundle.js`、
> `dist/main.bundle.js`、`dist/error_handler.bundle.js`、`dist/promise.bundle.js`、`dist/style.bundle.js`，
> 样式由 `<link href=dist/style.bundle.css>`。源 `app/ui.js` 是被打包进 `main.bundle.js` 的，
> 运行时页面读的是 `dist/` 下的产物，不是 `app/ui.js` 原文件。

## 4. 控制栏 / 侧边栏注入点（前端结构）

控制栏（左侧可收起的工具条）是后续注入「ChatOps 侧栏」的天然锚点，结构如下（均在 index.html 内）：

- `#noVNC_control_bar_anchor`（`class=noVNC_vcenter`）—— 控制栏外层定位锚
  - `#noVNC_control_bar` —— 控制栏主体（logo + 各功能按钮）
    - `#noVNC_control_bar_handle` —— 收起/展开控制栏的手柄
    - 按钮均为 `.noVNC_button_div` + `.noVNC_button`，含：Drag Viewport / Keys / Power /
      Clipboard / Fullscreen / Displays / Game Cursor / Settings / Disconnect / Connect
- `#noVNC_container` —— 远程画面容器（含 `#noVNC_keyboardinput`）
- `#noVNC_status` —— 状态条

注入候选点（供后续任务参考）：
- 在 `#noVNC_control_bar` 内追加一个新的 `.noVNC_button_div`（与现有按钮风格一致），或
- 在 `#noVNC_control_bar_anchor` 同级注入一个独立侧栏容器，并在 `dist/style.bundle.css` 之外
  追加自有样式 / 脚本（建议新增独立文件而非改 bundle，便于维护）。

样式相关：`app/styles/`（源）与 `dist/style.bundle.css`（产物）。

## 5. web 端口与登录

| 项 | 值 |
|---|---|
| web 端口（容器内 + 映射） | `6901`（HTTPS） |
| 协议 | HTTPS（自签证书，需 `curl -k`） |
| 其它暴露端口 | `4901/tcp`、`5901/tcp`（非 web 访问入口） |
| 默认登录用户名 | `kasm_user`（kasm 镜像默认） |
| 登录密码 | 由 `-e VNC_PW=...` 指定（本次 `recon123`） |

## 6. 连通性实测（curl，替代浏览器人工核对）

```
$ curl -ks -o /dev/null -w "HTTP %{http_code}\n" https://localhost:6901/
HTTP 401
```

- 状态码：**HTTP 401**（Unauthorized）。属预期：KasmVNC 内置 web server 对 `/` 启用 Basic Auth，
  未带凭证即返回 401，正好佐证「该端口确实由 KasmVNC web server 服务」。
- 页面正文：带凭证后返回的即 `/usr/share/kasmvnc/www/index.html`，`<title>KasmVNC</title>`、
  `class=noVNC_loading`、加载 `dist/*.bundle.js`，确认是 KasmVNC/noVNC web 客户端页面。

## 7. 给后续任务的结论

- **Task 4 的 `COPY` 目标根目录 = `/usr/share/kasmvnc/www`（WWW_ROOT），入口 `index.html` 在其根下。**
- 改前端有两条路：改 `index.html` 注入新 DOM/脚本（最直接），或同时替换/追加 `dist/` 产物 + 自有 JS/CSS。
- web 端口固定 `6901`（HTTPS，自签），登录用户 `kasm_user`，密码走 `VNC_PW`。
