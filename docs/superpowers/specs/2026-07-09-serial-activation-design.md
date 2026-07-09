# chatop 容器首次启动序列号激活 — 设计

**日期**：2026-07-09
**范围**：`/work/chatop`（主）+ `/work/website`（一个模块位）
**参照**：`/work/chayuan-desktop` 的 license 验签实现

---

## 1. 目标

容器首次启动时，登录页不出图形验证码，改为要求输入**序列号**。序列号由 website
（aidooo.com）签发，与本机**指纹**数学绑定。验证通过即写入激活记录，此后正常登录。

用户获取序列号的路径：登录页显示本机指纹 → 关注公众号 → 提交指纹 → 后台
「特殊授权」签发 → 用户在 `https://aidooo.com/query?mid=<指纹>` 查得序列号。

## 2. 既有事实（已实证，非转述）

### 2.1 website 已是完整签发中心

`server/license/shortcode.js` 的 `sign(fields, machineFp, hmacKey)`：

```
header = pack({ver, kind, modules, value, issueDate, nonce})
body   = header ‖ HMAC-SHA256(header ‖ machineFp, hmacKey)[:8]
serial = group5(base32Crockford(body) + checkChar(body))
```

- `machineFp` 是 **8 个原始字节**（`Buffer.from(mid,'hex')`），不是 16 个 ASCII 字符。
- `ver` 字段**不是编解码版本号，是密钥 id**（`issue.js`: `ver: activeKeyId`）。
  v1/v2 布局由 `modules > 0xff` 自动切换（`codec.js: widthsFor`）。
- 验签端按 `hmacKeys[fields.ver]` 取密钥；取不到 → `unknown-key`。

头部位布局：

| 版本 | 字节 | 布局 | 序列号长度（去连字符） |
|---|---|---|---|
| v1 | 6 | ver(4) kind(1) modules(8) value(14) issueDate(13) nonce(8) | 24 |
| v2 | 7 | ver(4) kind(1) modules(16) value(14) issueDate(13) nonce(8) | 25 |
| seat | 8 | ver(4) kind(4) maxUsers(16) durDays(14) issueDate(13) nonce(13) | 27 |

`kind`：0=时长（value=天数），1=次数。`issueDate` = 距 `EPOCH 2026-01-01T00:00:00Z` 的天数。

### 2.2 模块位图

`server/data/license-modules.json` 现有 bit 0–8（video, chat, kb, avatar, ocr, asr,
note, wps, video_edit）。**chatop 取 bit 9**。

`modules = 512 > 0xff` ⇒ v2 七字节头 ⇒ **chatop 的序列号是 25 字符（5 组 ×5）**。

`getConfig()` 里的 `products` 是 `modules.productsMap()` 实时派生的，签发端
（`licenses/comp`）与验签端（`/api/license/verify`）自动一致，无需两处手工同步。

### 2.3 跨语言金标（用 website 真实 JS 签、chayuan Python 验，py3.6/3.11 均通过）

测试密钥 `00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff`，
指纹 `a1b2c3d4e5f60718`（→ 8 字节 `bytes.fromhex`）：

| fields | 序列号 | 说明 |
|---|---|---|
| `ver=1 kind=0 modules=512 value=3650 issueDate=190 nonce=7` | `20803-J20QR-3VNWP-KW28Y-4KXPC` | chatop，25 字符 v2 |
| `ver=1 kind=0 modules=2 value=30 issueDate=190 nonce=7` | `20807-G5Y0Y-8AMVS-ZGZYH-G2R4` | chat(bit1)，24 字符 v1 |
| `ver=1 kind=1 modules=512 value=50 issueDate=190 nonce=7` | `30800-1J0QR-3JS5A-B682F-T824X` | 次数型 |

失败分支：换指纹 → `signature`；改一字符 → `checksum`；换密钥 id → `unknown-key`。

**关键结论：第二条（chat 序列号）在同一把密钥下验签同样返回 `valid=True`。**
所以「验签通过」远不足以放行，**必须再查 `modules & (1 << 9)`**，否则任何察元桌面版
的序列号都能开工舱。

### 2.4 chatop 侧约束

- 登录页由 app-manager（裸 `http.server`，零第三方依赖）的内联 `_LOGIN_TMPL` 渲染。
- 唯一跨容器重建存活的是 `chatop-home` 卷（`/home/admin`）。`/etc/machine-id` 在镜像层，
  **同镜像所有容器完全相同**；container id / MAC 在 `compose down/up` 后即变。
- station 已有 `~/.local/share/chatop/node-id`（首启生成 UUID，卷内持久）。
- 容器内 admin 无 sudo，卷归 uid 1000 ⇒ **造不出用户改不了的文件**。
- 登录页必须保留「察元AI工舱」字样：station `_brand_intact()` 心跳靠它判断品牌完整性。
- 运行时统一 python3.11（见 `python311-unification`）。

## 3. 架构

```
┌─ website (aidooo.com) ─────────────┐
│ 后台「特殊授权」licenses/comp       │
│   输入 mid + 模块[chatop] + 天数    │
│   → issueLicense() → 序列号         │
│ /query?mid=<mid> 查号（已存在）     │
└────────────────────────────────────┘
              │ 人工/公众号传递序列号
              ▼
┌─ chatop 容器 ──────────────────────┐
│ 登录页 (app_manager.py)            │
│   ├─ gate.state() == needs_activation → 渲染 序列号 + 指纹 + 提示  │
│   └─ gate.state() == active         → 渲染 图形验证码（现状）      │
│ POST /login → gate.activate(serial) → 写 activation.json          │
│ GET  /auth  → cookie_ok AND state in (off, active)                │
└────────────────────────────────────┘
```

### 3.1 `chatop_license` 包（`app-manager/chatop_license/`）

纯标准库，随 `app_manager.py` 一起 COPY 进镜像。

| 文件 | 职责 | 依赖 |
|---|---|---|
| `base32.py` | Crockford Base32 解码 + mod-37 校验符 | — |
| `codec.py` | 6/7 字节头解包、EPOCH、签发日→到期日 | — |
| `shortcode.py` | 截断 HMAC 验签 | base32, codec |
| `machine.py` | `machine_id()` / `mid()` / `mid_bytes()` | — |
| `store.py` | 激活记录原子读写 + 签名校验 | — |
| `gate.py` | 唯一对外入口：`state()` / `activate()` / `info()` | 以上全部 |

前三个从 chayuan-desktop 逐字移植，保持字节兼容。差异：**只接受 24/25 字符**
（seat 27 字符按 `length` 拒绝），与 website 的 JS `verify()` 一致。

### 3.2 指纹

```
mid = sha256(machine_id.encode())[:16]      # 16 位小写 hex
machine_fp = bytes.fromhex(mid)             # 8 字节，喂给 HMAC
```

`machine_id` 优先级：

1. 环境变量 `CHATOP_MACHINE_ID`（非空）—— 运维逃生口，换卷不换号
2. `~/.local/share/chatop/node-id`（station 的匿名工位 UUID，卷内持久）
3. 不存在则以 `O_CREAT|O_EXCL` 原子创建 `uuid4()`

**必须顺手修的竞态**：`station/station/heartbeat.py::_hid()` 现为「读失败→生成→写」，
而 `custom_startup.sh` 并行拉起 station 与 app-manager。首启双写会让指纹翻一次，
把刚激活的记录作废。改为 `O_EXCL` 创建 + `FileExistsError` 回读。

**已知代价**：`docker compose down -v`（删卷）后指纹变化，需重新领序列号。
`CHATOP_MACHINE_ID` 是该场景的出口。

### 3.3 密钥投递

`gate.hmac_keys()` 解析顺序：

1. 环境变量 `CHATOP_LICENSE_HMAC_KEY`（hex）→ `{active_key_id: bytes}`
2. 文件 `/opt/chatop/license-keys.json`：`{"active_key_id":1,"hmac_keys":{"1":"<hex>"}}`
3. 都没有 → 返回 `{}`

Dockerfile 尾部（产品层，避免 ARG 提前消费导致上游 5GB 层全部重建）：

```dockerfile
ARG CHATOP_LICENSE_HMAC_KEY=""
RUN if [ -n "$CHATOP_LICENSE_HMAC_KEY" ]; then \
      mkdir -p /opt/chatop && \
      printf '{"active_key_id":1,"hmac_keys":{"1":"%s"}}\n' "$CHATOP_LICENSE_HMAC_KEY" \
        > /opt/chatop/license-keys.json && chmod 0644 /opt/chatop/license-keys.json; \
    fi
```

**密钥不进 git。** 不传 `--build-arg` ⇒ 无密钥 ⇒ `state()=="off"` ⇒ 闸门关闭，
行为与今天完全一致（防止自建/开发镜像把自己锁在门外）。

**已向用户明示并由用户选定的取舍**：纯离线验证要求镜像内含对称 HMAC 密钥。
镜像一旦推到公开 registry，任何人可提取密钥为任意指纹自签序列号。这与
chayuan-desktop `embedded.py` 自述的「B1 是已声明的弱兜底，非数学防 keygen」同级。
这是**业务闸门，不是 DRM**。

### 3.4 状态机

`gate.state()` 返回四态：

| 状态 | 条件 | 登录页表现 |
|---|---|---|
| `off` | 无 HMAC 密钥 | 现状：用户名 + 密码 + 图形验证码 |
| `needs_activation` | 无记录 / 签名不符 / 记录 mid ≠ 本机 mid | 用户名 + 密码 + **序列号** + 指纹 + 提示 |
| `expired` | 记录有效但已过期，或检测到时钟回拨 | 同上，附「授权已到期」提示 |
| `active` | 记录有效且未过期 | 现状 |

`gate.activate(serial)` 校验顺序（每步映射一个错误码）：

1. `verify_shortcode` → `length`/`decode`/`checksum` → **3**；`unknown-key` → **3**；
   `signature` → **4**（与本机指纹不匹配）
2. `fields["modules"] & (1 << 9)` == 0 → **5**（不含工舱授权）
3. `fields["kind"] != 0` → **6**（次数型不支持：我们不记次数，卖了兑现不了）
4. `expireAt <= now` → **7**（序列号已过期）
5. 全过 → 写激活记录，返回成功

### 3.5 激活记录

`~/.local/share/chatop/activation.json`（卷内持久，原子写 `tmp` + `os.replace`）：

```json
{"v": 1, "mid": "a1b2c3d4e5f60718", "serial": "20803-J20QR-3VNWP-KW28Y-4KXPC",
 "modules": 512, "kind": "time", "expire_at": "2036-07-07T00:00:00.000Z",
 "activated_at": "2026-07-09T12:00:00.000Z", "seen_max": "2026-07-09T12:00:00.000Z",
 "sig": "<hmac-hex>"}
```

- `sig = HMAC-SHA256(record_key, canonical)`，`canonical = json.dumps(去掉 sig, sort_keys=True,
  separators=(',',':'))`；`record_key = HMAC(active_hmac_key, b"chatop-activation-v1").digest()`
  —— 不引入新密钥。
- `seen_max`：单调时间基线，仅在登录成功时推进。`now < seen_max - 86400` ⇒ 判定时钟回拨 ⇒ `expired`。

它挡住：手改到期日、把 A 机记录拷到 B 机（`mid` 不符）、把系统时钟拨回去续命。
它**挡不住**拥有宿主 root 的人 —— 那个人可以 `docker exec` 改任何东西。不做过度设计。

### 3.6 登录页与鉴权接线

`_login_html(err_code, state)` 按状态渲染两套表单。未激活时序列号占掉图形验证码原来的位置，
下方一行本机指纹 + 复制按钮 + 提示「请关注公众号获取序列号，输入本机指纹即可获取序列号」。
页脚那张关注二维码**已经存在**（`_brand_footer_html`），提示语正好指着它。

`POST /login`（未激活时）：先验序列号（失败 `_ratelimit_record_fail`，复用现成 IP 软限流），
再验用户名密码，两者全过才写激活记录并发登录 cookie。

**必须堵的洞**：现在 `chatop_auth` cookie 的值就是常量 `AUTH_TOKEN`，
而 `AUTH_TOKEN = HMAC(sha256("chatop-auth|"+密码), "v1")` —— **知道密码的人可以自行算出该
cookie 并伪造，完全绕过登录表单**。因此激活检查不能只放在 `POST /login`，必须放进
`GET /auth`（Caddy `forward_auth` 端点，所有受保护路径都过它）：

```python
_auth_ok = _cookie_ok(cookie) and gate.state() in ("off", "active")
```

这样授权到期会立刻把人弹回激活页，而不是等 cookie 过期。`state()` 按
`(mtime, size)` 缓存，避免每个 HTTP 请求都读盘。

Caddyfile **不改**：`/login`、`/captcha` 已在 public 白名单，激活复用 `POST /login`。

### 3.7 website 侧

`server/payment/modules.js` 的 `SEED` 与 `server/data/license-modules.json` 各加一条：

```js
{ id: 'chatop', name: '察元AI工舱', desc: '云桌面工舱激活',
  bit: 9, icon: '', accent: '', enabled: true, order: 12 }
```

取号闭环不需要新代码：`/query` 页面已实现「粘贴 16 位指纹 → 查序列号 → 复制」。

## 4. 错误码

| 码 | 文案 |
|---|---|
| 1 | 用户名或密码错误 |
| 2 | 验证码错误或已过期 |
| 3 | 序列号无效，请检查是否输入完整 |
| 4 | 该序列号不是为本机签发的（指纹不匹配） |
| 5 | 该序列号不包含「察元AI工舱」授权 |
| 6 | 次数型序列号不适用于工舱，请使用时长型 |
| 7 | 该序列号已过期 |
| 8 | 授权已到期，请输入新序列号 |
| 9 | 系统时间异常，请校正后重试 |

## 5. 测试

`app-manager/tests/test_chatop_license.py`，跑法 `cd app-manager && python3.11 -m pytest tests/ -q`。
金标向量用 §2.3 的三条（测试密钥，非生产密钥）。

| 用例 | 期望 |
|---|---|
| `20803-…-4KXPC` + `a1b2c3d4e5f60718` | 验签 valid，modules=512，kind=0 |
| `20807-…-G2R4`（chat bit1） | 验签 valid，但 `activate()` 拒绝 → 码 5 |
| `30800-…-T824X`（kind=1） | 验签 valid，但 `activate()` 拒绝 → 码 6 |
| 换指纹 / 改一字符 / 换密钥 id | `signature` / `checksum` / `unknown-key` |
| 27 字符 seat 码 | `length` |
| 无密钥 | `state()=="off"`；登录页出验证码而非序列号框 |
| 记录 mid 不符 / 改 sig / 改 expire_at | `needs_activation` |
| 时钟回拨 > 1 天 | `expired` |
| 到期 | `expired` |
| 有效 cookie + 未激活 | `_auth_ok()` 为 False |
| 多线程并发 `machine_id()` | 只产出一个 UUID |

## 6. 非目标（YAGNI）

- 在线验证 / 吊销通道（website 的 `POST /api/license/verify` 已存在，将来要接只是加一条分支）
- Ed25519 令牌路径（`.lic` 文件、统一权益码）
- 次数型计次、席位/多用户
- 防宿主 root 篡改
