# 察元桌面客户端(Lite)集成进 chatop 容器 · 设计

- 日期：2026-07-10
- 状态：设计已确认（SKU=Lite、交付=烤入镜像+播种桌面图标）
- 影响：`/work/chatop` 的 `Dockerfile`、`app-manager/chatop-seed-home.sh`、新增 `vendor/`（gitignore）；构建产物来自 `/work/chayuan-desktop`

## 1. 目标

把 `/work/chayuan-desktop` 的桌面客户端以**轻量 Lite SKU** 打进 chatop 云桌面容器，桌面/开始菜单出现「察元AI」图标，点开即用。轻量优先，不追求全模型。

## 2. 关键事实（摸底结论）

- 客户端是 **Tauri 2 + React 19**（Rust 编译，用 **WebKitGTK** 而非 Electron/Chromium）。
- Linux 产物：`dist-lite/*.AppImage` + `*.deb`（`build-desktop.sh --lite-only`）。选 **AppImage** 烤入（单文件自包含，`--appimage-extract` 免 FUSE，与 chatop 现有 `gui-install.sh` 同构）。
- **Lite ≈ 400–600MB**：Tauri 壳 + PyInstaller Python sidecar（本机 `127.0.0.1:62581` 自启），**不嵌模型，首次启动联网下载模型**。
- 运行依赖：**`libwebkit2gtk-4.1-0` + `libgtk-3-0`**（Tauri）。chatop P3 已烤 `libgtk-3-0`，**缺 `libwebkit2gtk-4.1-0`**（jammy 源可装）。
- 构建需 Rust+pnpm+webkitgtk-dev+Python/Poetry 全套 → **只能在 chayuan-desktop 仓构建，绝不进 chatop Dockerfile 多阶段编译**。

## 3. 架构：产物分离 + 烤入播种

```
[chayuan-desktop 仓]                         [chatop 仓]
build-desktop.sh --lite-only                 vendor/chayuan-desktop-lite-x86_64.AppImage (gitignore)
   → dist-lite/*.AppImage      --手工/脚本拷贝-->        │
                                             Dockerfile: COPY + 构建期 --appimage-extract
                                                → /opt/chatop-seed-home/Applications/chayuan/squashfs-root
                                             + chatop-chayuan.desktop (Exec=AppRun, Icon=察元logo)
                                             + seed WANT+1
                                             首启 seed-home 播种到 $HOME → 桌面/菜单出图标
```

**为什么产物分离**：chatop 构建上下文不含 chayuan-desktop 源；把 Rust 工具链+monorepo 塞进 chatop 构建会重且强耦合。产物（AppImage）放 `vendor/` 且 gitignore（不把 ~500MB 二进制提交进 git；Docker 构建上下文仍能读到未跟踪文件）。

## 4. chatop 侧改动

### 4.1 运行库补 WebKitGTK
在 P3 新增的桌面运行库 apt 层追加 `libwebkit2gtk-4.1-0`（Tauri 必需）。

### 4.2 vendor 落点 + gitignore
- 约定路径 `vendor/chayuan-desktop-lite-x86_64.AppImage`。
- `.gitignore` 加 `vendor/*.AppImage`（产物不进 git）。
- 构建前必须先在 chayuan-desktop 构建并拷入；缺文件时 Dockerfile 该步应**可跳过或明确报错**（用 build-arg 开关 `WITH_CHAYUAN_DESKTOP=1/0`，默认 0，缺产物不阻断日常构建）。

### 4.3 Dockerfile：构建期解包 + 桌面项
- `ARG WITH_CHAYUAN_DESKTOP=0`
- `WITH_CHAYUAN_DESKTOP=1` 时：COPY vendor AppImage → 构建期 `--appimage-extract` 到 `/opt/chatop-seed-home/Applications/chayuan/`（seed home 下，随现有播种机制回卷）。
- 生成 `/opt/chatop-seed-home/.local/share/applications/chatop-chayuan.desktop` 与 `Desktop/` 副本：
  ```
  [Desktop Entry]
  Name=察元AI
  Exec=$HOME/Applications/chayuan/squashfs-root/AppRun
  Icon=<解包出的图标 或 chatop 内置察元 logo>
  Type=Application
  Categories=Office;
  ```
  注意 Exec 的 `$HOME` 在 .desktop 里不展开——用绝对占位，播种时 home 路径固定 `/home/${APP_USER}`，构建期即可写死绝对路径。

### 4.4 seed 版本
`chatop-seed-home.sh` 的 `WANT` +1（现值 4 → 5），注释「v5: 察元桌面客户端 Lite 图标」。让已有 home 卷升级时补出图标。

## 5. chayuan-desktop 侧（构建步骤，不改其代码）

```bash
cd /work/chayuan-desktop
./build-desktop.sh --lite-only          # 需 Rust+pnpm+webkitgtk-dev+Poetry 环境
cp dist-lite/*.AppImage /work/chatop/vendor/chayuan-desktop-lite-x86_64.AppImage
```

## 6. 已知约束与取舍

- **首启联网拉模型**：Lite 不嵌模型，首次启动需联网下载；纯离线容器里客户端能起、但模型功能要等联网。可接受（用户选 Lite 已知）。
- **镜像体积**：+~500MB（5.3GB→约 5.8GB）。低于 OpenHuman(1.3GB) 当初不预装的线，作为自家旗舰客户端可接受。
- **sidecar 数据目录**：Tauri 首启选 `CHAYUAN_ROOT`；容器内落 home 卷即持久化。若首启弹目录选择框影响体验，二期可用 env 预设默认目录（本期不做）。
- **构建耦合**：chatop 构建依赖「先在 chayuan-desktop 出产物并拷入 vendor」。用 `WITH_CHAYUAN_DESKTOP` 开关隔离，缺产物不影响日常 chatop 构建。

## 7. 测试/验收

- 构建期：`WITH_CHAYUAN_DESKTOP=1` 时镜像内存在 `/opt/chatop-seed-home/Applications/chayuan/squashfs-root/AppRun` 与 `chatop-chayuan.desktop`；`libwebkit2gtk-4.1-0` 已装（`dpkg -l | grep webkit2gtk-4.1`）。
- 运行期人工验收：首启后桌面/菜单出现「察元AI」图标；点开 Tauri 窗口起、sidecar `curl 127.0.0.1:62581/healthz` 通。
- 回归：`WITH_CHAYUAN_DESKTOP=0`（默认）时 chatop 构建与现状一致。

## 8. 未来增强（不做）
- thin SKU（15MB 连远程察元服务器）作为另一 catalog 条目。
- 首启数据目录 env 预设、模型离线内嵌（走 integrated）。
