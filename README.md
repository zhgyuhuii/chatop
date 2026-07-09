# chatop-ai

基于最新 KasmVNC 的定制云桌面（纯加法式定制：名称/图标/权限/语言切换/主题切换/文件上传下载）。
设计见 `docs/2026-06-29-chatop-ai-kasmvnc-design.md`。

## 构建并运行
```bash
cp .env.example .env   # 按需改端口/密码
./build-and-run.sh
```
访问 https://localhost:${PORT:-6901}

## 作为 ChaCMD 指挥系统的执行侧

本镜像 = 一名数字员工的工作站（**执行侧**）。中央编排/调度由 **ChaCMD 指挥系统**（`/work/chayuan-desktop`：`chacmd/` 后端 + `chayuan-client/` 前端）承担——两个项目的完整运行与端到端联调见 **`/work/chayuan-desktop/chacmd/README.md`**。

容器内 `agent-bridge/`（反连客户端）主动**反连**到 ChaCMD 网关并按昵称注册 + 心跳（NAT/隔离友好，中央不主动连容器）：
- 网关：`ws://<chacmd-host>:8767/bridge`
- 注册：`nickname`（逻辑标识，非 IP）+ 所属 `dept`

调度器、CI 门禁、评审、晨审队列等中央机制部署在 DMZ 隔离区（宿主禁 IP 转发、容器互不可见）。

## 许可证

本项目以 **GPL-2.0** 发布，全文见 [`LICENSE`](./LICENSE)。

之所以开源，是因为云桌面底座 **KasmVNC 采用 GPL-2.0**，我们随镜像再分发它。
源码公开、不限并发、不锁品牌 —— 你可以自由修改、再分发，并从源码自行构建镜像。

官方镜像内置序列号激活闸门（`app-manager/chatop_license/`，纯离线 HMAC 校验）。
序列号买到的是**开箱即跑的官方构建、持续更新与商业支持**，不是"解锁功能"；
依据 GPL-2.0 第 6 条，本项目不对你行使许可证权利施加任何进一步限制。

几个需要留意的边界：

- `novnc-src/` 是 vendored 的 [@kasmtech/noVNC](https://github.com/kasmtech/noVNC)，
  适用 **MPL-2.0**（及 BSD / OFL / CC BY-SA）而非本仓库的 GPL-2.0，
  保留其自身的 [`novnc-src/LICENSE.txt`](./novnc-src/LICENSE.txt)。
- **分发镜像即分发 KasmVNC**：GPL-2.0 第 3 条要求随附对应源码，或提供一份
  有效期至少三年的书面源码获取要约。
- 官方镜像内预装 **Google Chrome 与 Claude Code 等专有软件**，它们各自受上游
  条款约束，不在本项目 GPL-2.0 覆盖范围内；公开再分发前请自行确认其条款。

完整的第三方组件清单与许可说明见 [`THIRD-PARTY-NOTICES.md`](./THIRD-PARTY-NOTICES.md)。
