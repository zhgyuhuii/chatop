# 察元 AI 工舱（chatop）— 多工舱部署

在**同一台宿主**上部署任意多个互相隔离的 chatop 工舱：每个工舱有独立的登录名、密码、
数据目录和容器，端口自动避让，互不影响。适合一机多用户/多环境。

## 快速开始

```bash
cd workbay
./new-workbay.sh          # 交互输入用户名 + 密码，自动分配端口并起容器
```

再来一个用户，端口自动顺延（6901 被占就用 6902…）：

```bash
./new-workbay.sh          # 输入 bob / ...，自动分到下一个空闲端口
```

非交互（自动化/脚本）：

```bash
WB_USER=alice WB_PW='强密码' ./new-workbay.sh
```

国内加速用阿里云 ACR 镜像：

```bash
CHATOP_IMAGE=crpi-4i9j7th8clu2wz0j.cn-beijing.personal.cr.aliyuncs.com/cmdbird/chatop:latest \
  ./new-workbay.sh
```

## 改账号 / 改密码

```bash
./reset-workbay.sh alice  # 改 alice 工舱的登录名和/或密码，端口不变
```

## 停 / 删某个工舱

```bash
cd workbays/alice && sudo docker compose -p chatop-alice down   # 停（数据保留在 workbays/alice/home）
rm -rf workbays/alice                                            # 连数据一起删
```

## 目录结构

```
workbay/
  new-workbay.sh              # 新建工舱
  reset-workbay.sh            # 改账号/密码
  scripts/
    _workbay-lib.sh           # 公共函数（端口探测/密码转义/安全读 .env）
    workbay.compose.tmpl.yml  # 工舱 compose 模板
    tests/test_workbay_lib.sh # 纯逻辑单测
  workbays/<user>/            # 每个工舱：.env / docker-compose.yml / workbay.json / home/
```

## 关键点

- **端口自动避让**：`BASE_PORT`（默认 6901）起，跳过宿主已监听与 docker 已发布的端口。
- **数据隔离**：每个工舱 `workbays/<user>/home` 绑定挂载到容器内 `/home/admin`。删容器不丢数据。
- **内部用户恒为 admin**：镜像内 OS 用户/家目录固定 `admin` / `/home/admin`；`LOGIN_USER`
  只是 Web 登录时显示/校验的用户名，卷始终挂 `/home/admin`。
- **密码含特殊字符安全**：`$` 空格 反引号 引号都逐字保住——写 `.env` 时 `$`→`$$`
  规避 docker compose 变量插值；读回绝不 `source`（会把密码当命令执行），而是逐字读。

## 自测

```bash
bash scripts/tests/test_workbay_lib.sh   # 纯逻辑单测，不需要 docker
```
