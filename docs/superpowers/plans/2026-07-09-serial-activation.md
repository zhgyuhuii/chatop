# 序列号激活 实施计划

> 设计真源：`docs/superpowers/specs/2026-07-09-serial-activation-design.md`

**Goal**：容器首次启动时登录页要求输入序列号（不出图形验证码），验证通过即激活。

**Tech Stack**：Python 3.11 标准库（app-manager 无第三方依赖）、pytest、Docker build-arg。

---

## 实施中发现、并已修掉的两个真缺陷

1. **`O_EXCL` 不足以让并发首启收敛到同一指纹。** 它只保证「谁创建」原子，不保证**内容已写入**。
   竞态输的一方拿到 `FileExistsError` 后去读，读到的是赢家尚未写完的**空文件**，于是退回自己的
   UUID —— 指纹照样会翻，把刚激活的授权作废。改成「先写满 tmp，再 `os.link` 原子占位，一律回读」。
   `test_concurrent_machine_id_converges_to_one_uuid` 在修之前是红的。

2. **先验密码会造出密码预言机。** 若 `POST /login` 先校验密码，则 `e=1`（密码错）与 `e=3`
   （序列号错）的差异让攻击者随便填个序列号就能判断密码对不对。必须 `validate(序列号)` →
   验密码 → `commit()`：这样 `e=1` 只泄漏「序列号有效」，而序列号 tag 有 64 bit，爆破不可行。
   顺带解决「密码错时激活记录已写入」的问题（原 `activate()` 一步到位会落盘）。

## 任务

- [ ] **T1 `chatop_license/base32.py`** — Crockford Base32 解码 + mod-37 校验符。
      测试：金标 `check_char`、`O/I/L` 容错、非法符号抛 `ValueError`。
- [ ] **T2 `chatop_license/codec.py`** — 6/7 字节头解包、EPOCH、`issue_to_date`、`to_iso`。
      **8 字节 seat 头必须拒绝**（chatop 不支持席位码）。
- [ ] **T3 `chatop_license/shortcode.py`** — 截断 HMAC 验签，只接受 24/25 字符。
      测试：spec §2.3 三条跨语言金标 + `signature`/`checksum`/`unknown-key`/`length` 四种失败。
- [ ] **T4 `chatop_license/machine.py`** — `machine_id()`（env → node-id → O_EXCL 创建）、
      `mid()` = `sha256(machine_id)[:16]`、`mid_bytes()`。测试含多线程并发只产一个 UUID。
- [ ] **T5 `station/heartbeat.py::_hid()` 竞态修复** — 改 `O_EXCL` + `FileExistsError` 回读。
      与 T4 共用同一文件，双方并发首启必须收敛到同一 UUID。
- [ ] **T6 `chatop_license/store.py`** — 激活记录原子读写 + HMAC 签名。
      测试：改任一字段 → 验签失败；`tmp` + `os.replace` 原子性。
- [ ] **T7 `chatop_license/gate.py`** — `hmac_keys()`、`state()`、`activate()`、`info()`。
      测试：spec §5 全表（含 bit9 检查、kind 检查、mid 绑定、到期、时钟回拨、无密钥→`off`）。
- [ ] **T8 `app_manager.py` 接线** — `_login_html(err, state)` 双表单、`POST /login` 分支、
      **`GET /auth` 加激活闸门**（堵 cookie 伪造洞）、`state()` mtime 缓存。
- [ ] **T9 Dockerfile / compose** — `COPY chatop_license/`、尾部 `ARG CHATOP_LICENSE_HMAC_KEY`
      写 `/opt/chatop/license-keys.json`、compose 透传 build arg 与 `CHATOP_MACHINE_ID`。
- [ ] **T10 website 模块位** — `modules.js` SEED + `data/license-modules.json` 加 `chatop` bit 9。
- [ ] **T11 构建 1.4.0 + 真机验收** — 含 python3.11 统一。无密钥构建须行为如常（`off`）。

## 验证命令

```bash
cd /work/chatop/app-manager && python3.11 -m pytest tests/ -q      # 新增用例全绿；5 个既有 reconcile 失败不动
cd /work/chatop/station     && <venv311>/bin/python -m pytest tests/ -q
cd /work/chatop/openclaw-tool && python3.11 test_openclaw_modules.py
cd /work/website && node --test server/__tests__/    # 若触及 license 相关
```

## 真机验收结果（2026-07-09，镜像 `chatop-ai:1.4.0`，容器真实指纹 `6b881fb43cc26b73`）

用**测试密钥**（非生产密钥）在真实容器里跑完整链路，序列号由 website 的真实
`issueLicense()` 签发。十步全过：

| # | 场景 | 结果 |
|---|---|---|
| 1 | 无密钥（默认镜像） | 登录页出图形验证码，无序列号框 ✓ |
| 2 | 注入密钥重启 | 登录页换成序列号框 + 真实指纹 + 公众号提示 ✓ |
| 3 | **伪造 `chatop_auth` cookie 打 `/auth`** | **HTTP 302** ✓（激活检查若只放 `POST /login`，这里会是 200） |
| 4 | website `issueLicense()` 签发 | `20800-BE0QP-MJNEV-CEC89-JYP9R`，25 字符 v2 ✓ |
| 5 | 乱码 / 别人的码 / 桌面版 `chat` 码 | `e=3` / `e=4` / `e=5` ✓ |
| 6 | **序列号对但密码错** | **`activation.json` 不存在** ✓（validate/commit 分离生效） |
| 7 | 序列号 + 密码均正确 | 302 → `/`，写入记录，`/auth` 返回 200 ✓ |
| 8 | 激活后登录页 | 恢复图形验证码，显示「授权有效期至 2027-07-10」✓ |
| 9 | `docker restart`（不删卷） | 激活保持 ✓ |
| 10 | 清理并恢复无密钥 | 闸门关闭，行为回到上线前 ✓ |

附带核实：`node-id` 未被 station 翻掉（指纹跨重启稳定）；app-manager 进程是
`python3.11 /usr/local/lib/chatop/app_manager.py`，station 的 `SERVICES` 靠 cmdline 子串
`app_manager.py` 匹配，换解释器没弄瞎状态监控。

## 构建期踩到的坑（与本功能无关，但值得记）

`exporting layers` 反复把 dockerd OOM 掉，真因是本机 **`vm.swappiness = 0`** ——
内核拒绝换出匿名页，dockerd 那 6.1GB 全是匿名内存，于是 **swap 空着 5.6GB 也照样被杀**。
`sudo sysctl -w vm.swappiness=100` 后，导出峰值只吃 415Mi swap 就顺利通过（`DONE 317.8s`）。
此前「加 swap 无效」「必须停生产容器」的结论都是这个前提被忽略导致的误判。

## 尚未完成（需用户决策）

- **生产密钥未注入**：当前发布镜像 `license gate: DISABLED`。要启用闸门需
  `CHATOP_LICENSE_HMAC_KEY=<hex> VERSION=x docker compose build`，密钥取自 website 后台
  「支付配置 → 生成授权密钥」的 `hmacKeys["1"]`。**烤进镜像 = 镜像持有对称密钥**，若推公开
  registry 即等于公开密钥。未经确认不擅自执行。
- **生产站模块表**：`server/data/` 被 gitignore，线上 website 需在后台「模块管理」新增
  `chatop` / bit 9 才能签发工舱序列号。本仓只改了 `modules.js` 的 `SEED`（新装播种用）。
- `vm.swappiness=100` 是临时设置，未写 `/etc/sysctl.conf`，宿主重启后回到 0。
