# chatop 登录页/等待页/左侧菜单 品牌补全 + 登录防暴破 设计

- 日期：2026-07-08
- 范围：`/work/chatop`（基于 KASM/noVNC 改造的云桌面，品牌「察元AI工舱」/「智灵鸟」）
- 目标分支：`main`

## 1. 背景与需求

chatop 的登录不是 KASM 原生 basic-auth 弹窗，而是自绘品牌登录页 + 签名 Cookie：把关在 Caddy 的 `forward_auth`，登录页/校验端点由 `app-manager/app_manager.py`（stdlib `http.server`）动态生成（见 `app_manager.py:23-24`、`caddy/Caddyfile:39-52`）。等待页与左侧菜单在 `novnc-src/`（改造过的 noVNC 前端）。

本次要做四件事：

1. **登录页用户名不要默认任何值**。运行态模板已是 `value=""`（commit c3c8b8e 已修），残留根因是浏览器凭据自动回填。
2. **登录加图形字符验证码**防批量破解（用户已选「图形字符验证码」，不依赖微信）。
3. **登录页 + 等待页补全品牌信息**：logo、「关注我们」二维码、「关注我们」文案、网址 `aidooo.com`、版权「北京智灵鸟科技中心」。
4. **左侧菜单加「关于我们」** → 新窗口打开 `https://aidooo.com`。

## 2. 关键现状（文件:行号）

- 登录页模板 `_LOGIN_TMPL`：`app-manager/app_manager.py:39-72`；用户名 input `app_manager.py:68`（`value="" autocomplete="username"`）；密码 `:69`；`.foot` 区 `:71`。
- 登录校验 `POST /login`：`app_manager.py:475-484`（`:479` `hmac.compare_digest`）；`GET /login` `:414-416`；`GET /auth`（forward_auth 校验点）`:418-421`；`GET /captcha` 需新增。
- 认证密钥/常量：`AUTH_USER/AUTH_PW/AUTH_TOKEN/AUTH_COOKIE` `app_manager.py:26-30`（`AUTH_TOKEN` 可复用作验证码 HMAC 密钥）。
- Caddy 未登录放行清单 `@public`：`caddy/Caddyfile:8`（需加 `/captcha`）；`/login /auth` 反代 app-manager `Caddyfile:8-12`。
- 等待页 DOM `#noVNC_transition`：`novnc-src/index.html:729-740`（`.chatop_transition_brand` `:734`）；文案 JS `novnc-src/app/ui.js:850-876`；样式 `novnc-src/app/styles/base.css:1000-1036`。
- 左侧控制栏 `#noVNC_control_bar`：`novnc-src/index.html:80-654`；退出按钮 `chatop_logout_button` `:625-631`；点击绑定 `ui.js` `addFilesHandlers()` `:609-635`，`addClickHandle` `:1439-1447`。已有 `aidooo.com` 硬链接在设置面板 `index.html:614`。
- logo 资产：`assets/logo-sm.png` → `Dockerfile:275` COPY 到 `www/app-icons/chatop-logo.png`；登录页 logo 内联 `app_manager.py:32-37 _logo_data_uri()`。
- 二维码资产源：`/work/chayuan-desktop/chayuan-client/images/pay/follow.png`（智灵鸟公众号「关注我们」码，430×430，实为 JPEG，sha256 8ae710e0…）。

## 3. 设计

### 3.1 去默认用户名（防浏览器回填）

改 `app_manager.py:68-69`：用户名/密码 input 加 `readonly onfocus="this.removeAttribute('readonly')"`，`autocomplete` 改为 `off`（用户名）/`new-password`（密码）。效果：页面加载时两框为空、聚焦后才可输入，浏览器不再回填「创建时用户名」admin。模板 `value=""` 保持。

### 3.2 图形字符验证码（纯 SVG，零依赖，无状态）

- **生成 `GET /captcha`**（`app_manager.py` 新增 handler）：
  - 随机 4 位，字符集 `23456789ABCDEFGHJKMNPQRSTUVWXYZ`（去 0/O/1/I/L 等易混）。
  - 渲染为 **SVG 字符串**（每字随机旋转/位移/颜色 + 2 条干扰线），`Content-Type: image/svg+xml`，禁缓存。**不用 PIL/字体**（容器无 PIL 也能跑）。
  - 无状态答案：`payload = lower(answer) + "|" + str(exp_ts)`；`sig = hmac_sha256(AUTH_TOKEN, payload)`；下发短时效 cookie `chatop_cap = base64(payload) + "." + sig`（`Path=/`，`HttpOnly`，`Max-Age=120`）。
- **校验（`POST /login` `:479` 前）**：读 `chatop_cap` cookie → 验签 → 校验未过期（120s）→ 大小写不敏感比对表单 `captcha` 字段。任一不过：返回登录页并在 `__ERR__` 区提示「验证码错误或已过期」，同时下发新验证码 cookie（自动换一张，避免卡死）。校验通过后该 cookie 失效（一次性：登录成功即清；失败则轮换）。
- **登录页模板**（`app_manager.py:39-72`）：密码框下方加一行——`<img src="/captcha" onclick="this.src='/captcha?'+Date.now()">`（点击刷新）+ `<input name="captcha" autocomplete="off">`。
- **Caddy**：`Caddyfile:8` `@public` 加 `/captcha`，否则未登录取不到图。
- **IP 软限流**（defense-in-depth）：`app_manager.py` 进程内 `dict[ip] -> (fail_count, first_ts)`；同 IP 连续失败 ≥5 次后，每次 `POST /login` 前 `time.sleep(2)`（软延时，不永久锁死，避免误伤）；成功登录清零；计数窗口 10 分钟。

### 3.3 登录页 + 等待页 品牌信息块

统一「品牌页脚」内容顺序：`[关注我们二维码] 关注我们 · aidooo.com · 版权所有 © 北京智灵鸟科技中心`（`aidooo.com` 可点，新窗口）。

- **登录页**：加在 `app_manager.py:71` `.foot` 区。二维码仿 `_logo_data_uri()` 新增 `_follow_qr_data_uri()` 读 `app-icons/follow-qr.png` 转 base64 内联。
- **等待页**：`index.html:734` `.chatop_transition_brand` 之后插入 `.chatop_transition_footer`（二维码 `<img src="/app-icons/follow-qr.png">` + 文案 + 链接 + 版权）；样式加在 `base.css:1036` 之后（居中、二维码约 96–120px、字号小、弱化色）。

### 3.4 左侧菜单「关于我们」

- `index.html` 控制栏退出按钮（`:631`）附近加 `noVNC_button_div`，`id="chatop_about_button"` + 图标 + 文字「关于我们」，跟 `chatop_apps_button` 同款结构。
- `ui.js:631` 后加 `UI.addClickHandle('chatop_about_button', () => window.open('https://aidooo.com', '_blank'));`
- 图标复用现有某个 svg（如信息/i 图标）或加一枚简单 svg。

### 3.5 资产与构建

- 复制 `/work/chayuan-desktop/chayuan-client/images/pay/follow.png` → `chatop/assets/follow-qr.png`。
- `Dockerfile` 仿 `:275` 加一行 `COPY assets/follow-qr.png /usr/share/kasmvnc/www/app-icons/follow-qr.png`。
- 改动生效需 **rebuild 镜像 + 重启**（登录页来自 app_manager 进程；等待页/菜单烤在 www）。

## 4. 验证计划

rebuild 后在恢复的桌面/浏览器实测：

1. 打开登录页：用户名/密码框为空（即便浏览器存过 admin），验证码图显示、点击可刷新。
2. 错验证码 → 被拒并提示、自动换图；对验证码 + 正确密码 → 登录成功进桌面。
3. 同 IP 连续 5 次失败 → 后续请求明显变慢（软限流）。
4. 登录页 + 等待页底部品牌块正确（二维码可扫、aidooo.com 可点、版权文案正确）。
5. 左侧菜单「关于我们」→ 新标签打开 aidooo.com。
6. app-manager 单测 `app-manager/tests/test_app_manager.py` 通过 + 新增 /captcha 与 /login 验证码分支测试。

## 5. 风险 / 取舍

- **防浏览器回填**是 cat-and-mouse；`readonly+onfocus` 是当前最稳的纯前端手段，叠加验证码后即使回填也无法批量破解，满足「避免批量破解」主诉。
- **无状态验证码 cookie**：跨多 app-manager 实例天然一致（无需共享 session）；一次性通过「成功即清 / 失败即轮换」近似实现。
- **IP 限流**用进程内 dict，重启即清；对本单机镜像足够，不引入 Redis。
- SVG 验证码对 OCR 的抵抗弱于扭曲位图，但对「脚本无脑撞库」已足够；若日后要更强可换 PIL 位图（需在镜像装 Pillow）。
