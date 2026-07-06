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
