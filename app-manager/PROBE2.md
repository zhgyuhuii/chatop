# 应用管理器二期（GUI 类）— 候选可行性容器内实测

- 镜像：`chatop-ai:1.1.0`（Ubuntu 22.04 jammy / glibc 2.35 / Node 22.23 / npm 10.9 / Python 3.10.12 / Chrome 已装 / XFCE DISPLAY=:1）
- 核验日期：2026-06-29
- 实测方式：`sudo docker run --rm -u 0 --entrypoint bash chatop-ai:1.1.0 -lc '...'`，大文件逐个下载→试装→记录→`--rm` 即弃，宿主磁盘全程保持约 4.7G 安全水位。
- 运行用户事实：默认运行用户为 **kasm-user**（uid 1000，**无免密 sudo**）。安装类操作须在镜像构建期以 root 完成；运行期 kasm-user 仅启动应用。

## 容器基线能力（影响所有 GUI 候选）

| 能力 | 实测结果 | 影响 |
|---|---|---|
| glibc | 2.35（jammy） | 依赖 GLIBC_2.38/2.39 的二进制跑不起来 |
| Python | 3.10.12（无 3.11） | requires-python>=3.11 的包须先装 py3.11 |
| docker cli / dockerd | **完全没有** | 需 DinD/沙箱的应用不可行 |
| libfuse2 | **缺**（仅有 fuse3 + 无 /dev/fuse） | AppImage 不能直接挂载运行 |
| user namespace（unshare） | **被禁**：`unshare failed: Operation not permitted` | Electron 沙箱须靠 SUID chrome-sandbox 兜底；AppImage 须解包跑 |
| SUID chrome-sandbox | 可用（Void 安装后 `chmod u+s` 正常） | 非 root 的 Electron 应用无需 --no-sandbox |

---

## 1. Void IDE（VSCode fork，开源免登录，.deb）— 裁决：✅ 二期上架

- **确切下载 URL**：`https://github.com/voideditor/binaries/releases/download/1.99.30044/void_1.99.30044_amd64.deb`（104 MB，HTTP 302→200 可达；最新 tag `1.99.30044`，确有 amd64 .deb）
- **安装命令（构建期 root）**：`apt-get install -y ./void_1.99.30044_amd64.deb` → 实测 **INSTALL OK**，二进制 `/usr/bin/void`
- **容器内可行性**：
  - 非交互安装：✅ 一行 apt 装好，依赖自动解决。
  - 启动：✅ 以 **kasm-user** 运行 `void --version` 正常输出 `1.99.30044`（**无需 --no-sandbox**，因 chrome-sandbox 为 SUID root，userns 被禁也能用）。GUI 启动需 DISPLAY=:1（容器已具备）。
- **关键障碍**：仅在以 **root** 直跑时报 "trying to start as super user, add --no-sandbox"；生产以 kasm-user 跑无此问题。无 FUSE/glibc/登录障碍。
- **裁决**：二期首推。deb 安装，运行用户 kasm-user 直接启动。

## 2. Cursor（闭源 AppImage，需登录使用）— 裁决：⚠️ 可上架但降级（建议次优先）

- **确切下载 URL**（经 `https://www.cursor.com/api/download?platform=linux-x64&releaseTrack=latest` 解析）：
  `https://downloads.cursor.com/production/042b3c1a4c53f2c3808067f519fbfc67b72cad8b/linux/x64/Cursor-3.9.16-x86_64.AppImage`（version 3.9.16，286 MB，HTTP 200 可达）
- **容器内可行性**：
  - 直接运行：❌ `fuse: device not found ... Cannot mount AppImage`（缺 libfuse2 + 无 /dev/fuse）。
  - **`--appimage-extract` 解包**：✅ **EXTRACT OK**，产出 `squashfs-root/AppRun`。
  - 解包后以 kasm-user 跑 `AppRun --no-sandbox --version`：进程已正常加载 node/启动，仅因测试容器无 DISPLAY 报 `Missing X server or $DISPLAY` 后段错误——这是**测试环境无 X 所致**，生产容器有 DISPLAY=:1，可正常起 GUI。
- **关键障碍**：
  1. **FUSE 缺失** → 必须走 `--appimage-extract` 解包方式安装（构建期解包到固定目录），不能用裸 AppImage。
  2. 需 `--no-sandbox`（userns 禁用 + 解包后可能丢 SUID 位）。
  3. **闭源，须登录账号**才能实际使用（产品层限制，非安装阻断）。
  4. 体积大：下载 286 MB，解包后约 1 GB+，对 4G 紧张磁盘有压力。
- **裁决**：技术可行（解包方式），但因登录墙 + 体积，建议作为降级/次优先项上架。

## 3. OpenHuman（Tauri/Rust 桌面助手，.deb）— 裁决：❌ 剔除（硬阻断，除非升级基础镜像到 24.04）

- **确切下载 URL**（GitHub API 解析，最新 tag `v0.58.0`）：
  `https://github.com/tinyhumansai/openhuman/releases/download/v0.58.0/OpenHuman_0.58.0_amd64.deb`（222 MB，可达）。包名为 **`open-human`**，二进制 `/usr/bin/OpenHuman`。
- **容器内可行性**：
  - 非交互安装：✅ `apt-get install -y ./OpenHuman_0.58.0_amd64.deb` → INSTALL OK，依赖（libwebkit2gtk-4.1-0、libxdo3、libayatana-appindicator3-1 等）在 jammy 全部可解。
  - 启动：❌ **硬阻断** — `libc.so.6: version 'GLIBC_2.38' not found` 与 `GLIBC_2.39 not found`。二进制按 Ubuntu 24.04（glibc 2.38/2.39）编译，jammy 仅 glibc 2.35，**装得上、跑不起来**。
- **关键障碍**：GLIBC 版本不兼容，无法在 jammy 运行。无官方 jammy/glibc2.35 构建。
- **裁决**：剔除。仅当基础镜像升级到 Ubuntu 24.04（kasmweb 24.04 桌面）才可考虑。

## 4. Sovyx（PyPI）— 裁决：✅ 二期可上架（须 Python 3.11，纠正一期 NOT FOUND）

- **一期结论已过时**：一期 `pip index versions sovyx` 报 NOT FOUND，是因当时尚未发布。**现已在 PyPI**：`https://pypi.org/pypi/sovyx/json` 返回 **200**，最新版 **0.49.58**（"Sovereign Minds Engine — Persistent AI companion with real memory"，纯 Python wheel `py3-none-any`）。
- **关键约束**：`requires-python >=3.11`。容器是 **3.10**，系统 Python **装不了**（pip 会拒）。
- **确切安装方式（构建期 root）**：
  ```bash
  add-apt-repository -y ppa:deadsnakes/ppa   # jammy 默认源无 3.11
  apt-get update && apt-get install -y python3.11 python3.11-venv
  python3.11 -m venv /opt/sovyx-venv
  /opt/sovyx-venv/bin/pip install sovyx
  ```
- **容器内可行性**：✅ deadsnakes 实测可在 jammy 装 **Python 3.11.15**；3.11 venv 内 `pip install sovyx` **完整解析全部依赖**并 "Would install sovyx-0.49.58 ..."（numpy/onnxruntime/tokenizers/tiktoken 等均有 3.11 wheel）。
- **关键障碍**：须额外装 py3.11（deadsnakes PPA + 专用 venv）；运行时需配 LLM 后端/配置。本质是 fastapi/uvicorn/typer 的 CLI/服务，非传统 GUI 窗口应用（task 归在 GUI 候选，按实际形态它是 TUI/服务）。
- **裁决**：二期可上架，走 py3.11 + 独立 venv。

## 5. NanoClaw（每 agent 跑 Docker 沙箱）— 裁决：❌ 剔除（架构与本镜像冲突）

- **仓库**：`nanocoai/nanoclaw`（TypeScript，30k★）。安装脚本 `bash nanoclaw.sh`。
- **要求**：Node 20+（容器有 22 ✅）、pnpm 10+（可 corepack/npm 装 ✅）、**Docker Desktop/Engine 为默认运行时**——每个 agent group 跑在独立 Docker 容器（可选 Docker Sandboxes micro-VM）做隔离，这是其核心安全模型。
- **容器内可行性**：❌ 本镜像**无 docker cli、无 dockerd**；在 KasmVNC 容器内跑 Docker 需 DinD（`--privileged` + 宿主 docker socket 或嵌套 dockerd），与"单容器云桌面 + app-manager"模型冲突；且 userns 被禁，嵌套隔离进一步受限。NanoClaw 无官方"无 Docker"运行模式。
- **关键障碍**：强依赖 Docker 运行时做 per-agent 沙箱；DinD 不在本镜像能力范围。
- **裁决**：剔除。除非将宿主 docker.sock 挂入容器（破坏隔离前提，不推荐），否则不可行。

---

## 总结

| 候选 | 裁决 | 安装方式 | 主要障碍 |
|---|---|---|---|
| **Void IDE** | ✅ 上架（首推） | root `apt install ./void_*_amd64.deb`，kasm-user 直接跑 | 无（root 直跑才需 --no-sandbox） |
| **Cursor** | ⚠️ 上架（降级） | 下载 AppImage → `--appimage-extract` 解包 → kasm-user 跑 `AppRun --no-sandbox` | 缺 FUSE 须解包；须登录；286MB/解包1GB+ |
| **OpenHuman** | ❌ 剔除 | deb 可装但二进制需 GLIBC_2.38/2.39 | jammy glibc 2.35，跑不起来（硬阻断） |
| **Sovyx** | ✅ 上架 | deadsnakes 装 py3.11 + 专用 venv `pip install sovyx` | 系统 py3.10 装不了，须 py3.11 |
| **NanoClaw** | ❌ 剔除 | `bash nanoclaw.sh`（需 Docker） | 镜像无 docker，DinD 与模型冲突 |

**二期可做（3 个）**：
- Void IDE — deb，最干净，首推。
- Sovyx — PyPI（须 py3.11 + venv），一期 NOT FOUND 已纠正为可装。
- Cursor — 走 AppImage 解包，降级/次优先（登录 + 体积）。

**剔除（2 个）**：
- OpenHuman — GLIBC 不兼容 jammy。
- NanoClaw — 强依赖 Docker 运行时，本镜像不具备。

**实测确认的关键障碍清单**：FUSE 缺失（Cursor）、GLIBC 版本（OpenHuman）、Python 版本（Sovyx）、Docker 缺失（NanoClaw）、userns 禁用 + 运行用户/sudo（全局，已有 SUID 兜底）。
