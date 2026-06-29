# noVNC 前端构建方式（Task 3 实测结论）

来源：`git clone --depth 1 https://github.com/kasmtech/noVNC.git`
锁定 commit：见 `docs/novnc-commit.txt`（`e9c0f7088e08ad7030b91c8602ab056dcc8da107`）
包名/版本：`@kasmtech/novnc` `1.3.0`

## 判定：需要构建（Vite），非纯静态

`package.json` 的 `scripts.build`：

```
vite build && mkdir -p dist/app dist/core/decoders/qoi && cp -a app/locale dist/app \
  && cp package.json dist/ && cp core/decoders/qoi/qoi_viewer_bg.wasm dist/core/decoders/qoi \
  && cp dist/index.html dist/vnc.html
```

- 构建命令：`npm install && npm run build`
- 产物目录：**`dist/`**（自包含 web 根：含 `index.html`、`vnc.html`、`app/locale`、打包后的 `*.bundle.js`、qoi wasm 等）
- 顶层源码结构：`app/`（UI 源，含 `app/ui.js`）、`core/`、`po/`（i18n 翻译）、`public/`、`index.html`、`vite.config.js`

## 对 Dockerfile 的影响（Task 4）

采用计划中的「形态 B」：builder stage 用 `node` 跑 `npm install && npm run build`，
再把 `dist/` 覆盖进镜像 web 根 `WWW_ROOT=/usr/share/kasmvnc/www`（见 `docs/recon.md`）。

`COPY dist/ → www/` 是**合并覆盖**（不删 www 中镜像自带、dist 里没有的文件），
符合「KasmVNC 已有的不动」的加法原则。

## 风险（Task 4/5 实测验证）

运行页面加载的是 `dist/*.bundle.js`（recon 确认）。我们克隆的是 noVNC `1.3.0` HEAD，
与 kasmweb 1.16.1 镜像内置的 noVNC 版本**可能存在版本耦合差异**（KasmVNC 的 noVNC fork
与服务端版本绑定）。若 Task 5 端到端发现注入后 VNC 连接异常，则把 `novnc-src` 锁到
镜像实际使用的 noVNC commit 再构建；phase-1 先按 HEAD 实测。
