# chatop 一键安装器

面向终端用户的跨平台安装脚本：一条命令完成「检查/安装 Docker → 设置账号密码 → 拉取 chatop 镜像 → 启动 → 打开浏览器」。

## 用户怎么装

**Linux / macOS：**

```bash
curl -fsSL https://<你的域名>/install.sh | bash
```

**Windows（PowerShell）：**

```powershell
irm https://<你的域名>/install.ps1 | iex
```

安装过程中会提示设置**登录用户名和密码**（密码留空则自动生成）。装完自动打开
`https://localhost:6901`（自签证书，浏览器提示不安全点继续即可）。

### 非交互（预设账号/端口/镜像）

Linux/macOS：

```bash
CHATOP_USER=admin CHATOP_PASSWORD=yourpass CHATOP_PORT=6901 \
CHATOP_IMAGE=chatop:latest \
curl -fsSL https://<你的域名>/install.sh | bash
```

Windows：

```powershell
$env:CHATOP_USER="admin"; $env:CHATOP_PASSWORD="yourpass"
$env:CHATOP_IMAGE="chatop:latest"
irm https://<你的域名>/install.ps1 | iex
```

## 各平台 Docker 处理

| 平台 | 无 Docker 时 |
|---|---|
| Linux | 自动用官方脚本 `get.docker.com` 安装 + 启动 docker 服务 |
| macOS | 有 Homebrew → `brew install --cask docker` 并启动；无则打开下载页引导 |
| Windows | 有 winget/choco → 自动装 Docker Desktop（需 WSL2，可能要重启）；否则打开下载页引导。装好重跑即自动继续 |

Docker Desktop（Mac/Win）静默安装受平台限制，可能需要用户确认许可/重启——脚本已做
「尽力全自动 + 失败即引导 + 重跑续装」的兜底。

## 上线前必须做的两件事（维护者）

1. **推送镜像到 registry**。镜像统一命名 `chatop`、标签统一 `latest`（用户始终拉最新版，
   不用记版本号）。把当前正式镜像 tag 成 `chatop:latest` 后推送：

   ```bash
   # Docker Hub：需带命名空间（你的用户名）
   docker tag chatop-ai:<当前版本> <你的用户名>/chatop:latest
   docker push <你的用户名>/chatop:latest
   # 装机端对应用 CHATOP_IMAGE=<你的用户名>/chatop:latest
   ```

   安装器默认 `CHATOP_IMAGE=chatop:latest`（裸名，适合自建 registry）；推 Docker Hub
   时把默认值或用户传参改成 `<你的用户名>/chatop:latest`。

   > 每次发新版都覆盖同一个 `:latest` tag，用户重装/`docker compose pull` 即拿到最新。
   > 注意：国内用户从 Docker Hub 拉取常超时，建议同时推一份到阿里云 ACR 并让
   > `CHATOP_IMAGE` 指向 ACR 加速地址。

2. **托管脚本**。把 `install.sh` / `install.ps1` 放到你的官网或 GitHub Raw，
   把上面命令里的 `https://<你的域名>/` 换成真实地址。

## 生成的运行时布局

安装器在用户机器 `~/.chatop`（Windows `%USERPROFILE%\.chatop`）生成：

- `.env`：`LOGIN_USER` / `PASSWORD` / `PORT` / `CHATOP_IMAGE`（权限 600；密码里的 `$`
  会转义成 `$$`，因为 docker compose 会对 .env 值做变量插值）。
- `docker-compose.yml`：只引用镜像（不含 build），映射 `PORT:7443`（容器内 Caddy），
  挂 `chatop-home` 卷到 `/home/<用户名>`，`restart: unless-stopped`。

停止 / 重启：

```bash
cd ~/.chatop && docker compose down     # 停止（保留数据卷）
cd ~/.chatop && docker compose up -d     # 重启
```

## 已验证

- `install.sh` 生成的 `docker-compose.yml` 通过 `docker compose config`；端口/镜像/卷/env 解析正确。
- 密码含特殊字符 `$` 时，真容器 `printenv VNC_PW` 收到的值与用户输入**逐字节一致**
  （`.env` 里 `$`→`$$` 转义经实测验证）。
- `install.ps1` 源码 100% ASCII（PS 5.1 在 CJK 代码页下会误解码非 ASCII 的 .ps1）。
