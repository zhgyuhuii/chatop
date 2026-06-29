# chatop-ai

基于最新 KasmVNC 的定制云桌面（纯加法式定制：名称/图标/权限/语言切换/主题切换/文件上传下载）。
设计见 `docs/2026-06-29-chatop-ai-kasmvnc-design.md`。

## 构建并运行
```bash
cp .env.example .env   # 按需改端口/密码
./build-and-run.sh
```
访问 https://localhost:${PORT:-6901}
