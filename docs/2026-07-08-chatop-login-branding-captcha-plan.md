# chatop 登录品牌补全 + 图形验证码 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 chatop 云桌面登录页/等待页补全品牌信息（logo/关注我们二维码/aidooo.com/版权），登录加纯 SVG 图形验证码 + IP 软限流防批量破解，去掉用户名浏览器回填，左侧菜单加「关于我们」。

**Architecture:** 登录逻辑在 `app-manager/app_manager.py`（stdlib http.server，Caddy forward_auth 把关）。验证码用无状态签名 cookie（复用 `AUTH_TOKEN` 做 HMAC），SVG 纯字符串渲染无需 PIL。等待页/左侧菜单在 `novnc-src/`（web 构建阶段烤进 www）。二维码资产从 chayuan-client 复制。

**Tech Stack:** Python 3 stdlib（http.server/hmac/base64/secrets）、原生 HTML/CSS/JS（noVNC）、Docker、Caddy、pytest。

设计依据：`docs/2026-07-08-chatop-login-branding-captcha-design.md`

---

## 文件结构

- `app-manager/app_manager.py` — 新增验证码核心函数 + IP 限流 + `/captcha` 路由 + `POST /login` 校验 + 登录页模板改造 + 品牌页脚。
- `app-manager/tests/test_app_manager.py` — 新增验证码/限流纯函数测试。
- `caddy/Caddyfile` — `@public` 放行 `/captcha`。
- `assets/follow-qr.jpg` — 从 chayuan-client 复制的公众号二维码（新建）。
- `Dockerfile` — COPY 二维码资产到 www/app-icons。
- `novnc-src/index.html` — 等待页品牌页脚 + 左侧菜单「关于我们」按钮。
- `novnc-src/app/styles/base.css` — 等待页页脚样式。
- `novnc-src/app/ui.js` — 「关于我们」点击绑定。
- `novnc-src/app/images/info.svg` — 「关于我们」图标（新建）。

约定：验证码字符集 `23456789ABCDEFGHJKMNPQRSTUVWXYZ`（去 0/O/1/I/L）；答案 cookie `chatop_cap`（120s、HMAC 签名、一次性）；限流常量 `RL_MAX=5 / RL_WINDOW=600 / RL_DELAY=2`；错误码 `e=1`（用户名/密码）、`e=2`（验证码）。

---

## Task 1: 复制公众号二维码资产 + Dockerfile COPY

**Files:**
- Create: `assets/follow-qr.jpg`
- Modify: `Dockerfile:275`（其后加一行）

- [ ] **Step 1: 复制资产**（源实为 JPEG，改正扩展名为 .jpg）

Run:
```bash
cp /work/chayuan-desktop/chayuan-client/images/pay/follow.png /work/chatop/assets/follow-qr.jpg
file /work/chatop/assets/follow-qr.jpg
```
Expected: `JPEG image data ... 430x430`

- [ ] **Step 2: Dockerfile 加 COPY**（在 `COPY assets/logo-sm.png ...`（275 行）之后加）

```dockerfile
COPY assets/follow-qr.jpg /usr/share/kasmvnc/www/app-icons/follow-qr.jpg
```

- [ ] **Step 3: Commit**

```bash
git add assets/follow-qr.jpg Dockerfile
git commit -m "feat(chatop): 加入智灵鸟公众号二维码资产 + 打进 www/app-icons"
```

---

## Task 2: 验证码核心（纯函数，TDD）

**Files:**
- Modify: `app-manager/app_manager.py:25`（auth import 块）、其后新增函数
- Test: `app-manager/tests/test_app_manager.py`

- [ ] **Step 1: 写失败测试**（追加到 `test_app_manager.py` 末尾）

```python
import base64 as _b64

def test_captcha_check_roundtrip():
    ans, cookie = am._captcha_new()
    assert am._captcha_check(cookie, ans)              # 原样正确
    assert am._captcha_check(cookie, ans.lower())      # 大小写不敏感
    assert am._captcha_check(cookie, " " + ans + " ")  # 去空格
    assert not am._captcha_check(cookie, "ZZZZ")        # 答案错
    assert not am._captcha_check("garbage", ans)        # cookie 非法
    assert not am._captcha_check(cookie[:-1] + ("0" if cookie[-1] != "0" else "1"), ans)  # 签名被篡改

def test_captcha_expired():
    payload = "abcd|1"  # exp=1（1970 年，必过期）
    sig = am.hmac.new(am.AUTH_TOKEN.encode(), payload.encode(), am.hashlib.sha256).hexdigest()
    cookie = _b64.urlsafe_b64encode(payload.encode()).decode() + "." + sig
    assert not am._captcha_check(cookie, "abcd")

def test_captcha_svg_well_formed():
    ans, _ = am._captcha_new()
    svg = am._captcha_svg(ans)
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /work/chatop/app-manager && python3 -m pytest tests/test_app_manager.py -k captcha -q`
Expected: FAIL（`AttributeError: module 'app_manager' has no attribute '_captcha_new'`）

- [ ] **Step 3: 实现**（改 `app_manager.py:25` 的 import 行，并在 `_logo_data_uri` 定义之前/之后新增函数）

把 `app_manager.py:25` 从：
```python
import hmac, hashlib, base64
```
改为：
```python
import hmac, hashlib, base64, time, secrets, random
```

在 `app_manager.py` 的 `AUTH_COOKIE = "chatop_auth"`（30 行）之后新增：
```python
# === 登录图形验证码：纯 SVG + 无状态签名 cookie（复用 AUTH_TOKEN 做 HMAC，无需 PIL） ===
CAPTCHA_CHARS = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # 去掉易混的 0/O/1/I/L
CAPTCHA_TTL = 120
CAPTCHA_COOKIE = "chatop_cap"

def _captcha_new(n=4):
    """生成 (答案, 签名cookie值)。答案小写入签名，校验时大小写不敏感。"""
    ans = "".join(secrets.choice(CAPTCHA_CHARS) for _ in range(n))
    payload = "%s|%d" % (ans.lower(), int(time.time()) + CAPTCHA_TTL)
    sig = hmac.new(AUTH_TOKEN.encode(), payload.encode(), hashlib.sha256).hexdigest()
    cookie = base64.urlsafe_b64encode(payload.encode()).decode() + "." + sig
    return ans, cookie

def _captcha_check(cookie_value, user_input):
    """验签 + 未过期 + 大小写不敏感比对。任一不过返回 False。"""
    if not cookie_value or "." not in cookie_value:
        return False
    b64, _, sig = cookie_value.partition(".")
    try:
        payload = base64.urlsafe_b64decode(b64.encode()).decode()
    except Exception:
        return False
    expect = hmac.new(AUTH_TOKEN.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expect):
        return False
    ans, _, exp = payload.partition("|")
    try:
        if int(exp) < int(time.time()):
            return False
    except ValueError:
        return False
    return hmac.compare_digest(ans, (user_input or "").strip().lower())

def _captcha_svg(text):
    """把验证码渲染成扭曲 SVG 字符串（干扰线 + 每字随机旋转/位移/颜色）。"""
    W, H = 130, 44
    colors = ["#2563eb", "#7c3aed", "#0891b2", "#be123c", "#15803d"]
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (W, H, W, H),
           '<rect width="100%%" height="100%%" fill="#0b1220"/>']
    for _ in range(2):
        out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="1" opacity="0.5"/>' % (
            random.randint(0, W), random.randint(0, H), random.randint(0, W), random.randint(0, H), random.choice(colors)))
    step = W // (len(text) + 1)
    for i, ch in enumerate(text):
        x = step * (i + 1); y = 30 + random.randint(-4, 4); rot = random.randint(-28, 28)
        out.append('<text x="%d" y="%d" fill="%s" font-size="26" font-family="monospace" font-weight="bold" transform="rotate(%d %d %d)">%s</text>' % (
            x, y, random.choice(colors), rot, x, y, ch))
    out.append('</svg>')
    return "".join(out)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /work/chatop/app-manager && python3 -m pytest tests/test_app_manager.py -k captcha -q`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add app-manager/app_manager.py app-manager/tests/test_app_manager.py
git commit -m "feat(app-manager): 图形验证码核心(纯SVG+无状态签名cookie)+测试"
```

---

## Task 3: IP 软限流（纯函数，TDD）

**Files:**
- Modify: `app-manager/app_manager.py`（Task 2 新增函数之后）
- Test: `app-manager/tests/test_app_manager.py`

- [ ] **Step 1: 写失败测试**（追加）

```python
def test_ratelimit_delays_after_threshold():
    am._LOGIN_FAILS.clear()
    ip = "1.2.3.4"
    for _ in range(am.RL_MAX):
        assert am._ratelimit_delay(ip, now=1000) == 0
        am._ratelimit_record_fail(ip, now=1000)
    assert am._ratelimit_delay(ip, now=1000) == am.RL_DELAY   # 达阈值 → 延时
    am._ratelimit_reset(ip)
    assert am._ratelimit_delay(ip, now=1000) == 0             # 成功登录清零

def test_ratelimit_window_expires():
    am._LOGIN_FAILS.clear()
    ip = "5.6.7.8"
    for _ in range(am.RL_MAX):
        am._ratelimit_record_fail(ip, now=1000)
    assert am._ratelimit_delay(ip, now=1000) == am.RL_DELAY
    assert am._ratelimit_delay(ip, now=1000 + am.RL_WINDOW + 1) == 0  # 窗口过期不再延时
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /work/chatop/app-manager && python3 -m pytest tests/test_app_manager.py -k ratelimit -q`
Expected: FAIL（`AttributeError ... _LOGIN_FAILS`）

- [ ] **Step 3: 实现**（在 Task 2 的验证码函数之后新增）

```python
# === 登录 IP 软限流：进程内计数，达阈值后每次强制延时（不永久锁死，避免误伤） ===
_LOGIN_FAILS = {}   # ip -> [fail_count, first_ts]
RL_MAX = 5
RL_WINDOW = 600     # 10 分钟窗口
RL_DELAY = 2        # 达阈值后每次登录前 sleep 秒数

def _ratelimit_delay(ip, now=None):
    now = int(now if now is not None else time.time())
    c = _LOGIN_FAILS.get(ip)
    if not c or now - c[1] > RL_WINDOW:
        return 0
    return RL_DELAY if c[0] >= RL_MAX else 0

def _ratelimit_record_fail(ip, now=None):
    now = int(now if now is not None else time.time())
    c = _LOGIN_FAILS.get(ip)
    if not c or now - c[1] > RL_WINDOW:
        _LOGIN_FAILS[ip] = [1, now]
    else:
        c[0] += 1

def _ratelimit_reset(ip):
    _LOGIN_FAILS.pop(ip, None)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /work/chatop/app-manager && python3 -m pytest tests/test_app_manager.py -k ratelimit -q`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add app-manager/app_manager.py app-manager/tests/test_app_manager.py
git commit -m "feat(app-manager): 登录 IP 软限流(达阈值强制延时)+测试"
```

---

## Task 4: 通用 cookie 取值 + 品牌页脚/二维码 helper

**Files:**
- Modify: `app-manager/app_manager.py`（`_cookie_ok` 附近，86 行后）

- [ ] **Step 1: 实现**（在 `_cookie_ok` 定义之后新增；无独立单测，被 Task 5/6 使用并在集成验证覆盖）

```python
def _get_cookie(cookie_header, name):
    for part in (cookie_header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return ""

def _follow_qr_data_uri():
    try:
        with open("/usr/share/kasmvnc/www/app-icons/follow-qr.jpg", "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    except OSError:
        return ""

def _brand_footer_html(qr_uri):
    qr = ('<img class="qr" src="%s" alt="关注我们二维码">' % qr_uri) if qr_uri else ''
    return ('<div class="brandfoot">%s'
            '<div class="bf_txt"><div class="bf_follow">关注我们</div>'
            '<a class="bf_link" href="https://aidooo.com" target="_blank" rel="noopener">aidooo.com</a>'
            '<div class="bf_cr">版权所有 © 北京智灵鸟科技中心</div></div></div>') % qr
```

- [ ] **Step 2: py 语法检查**

Run: `cd /work/chatop && python3 -m py_compile app-manager/app_manager.py`
Expected: 无输出（成功）

- [ ] **Step 3: Commit**

```bash
git add app-manager/app_manager.py
git commit -m "feat(app-manager): 通用 cookie 取值 + 二维码/品牌页脚 helper"
```

---

## Task 5: 登录页模板改造（去回填 + 验证码 + 品牌页脚 + 双错误码）

**Files:**
- Modify: `app-manager/app_manager.py:39-79`（`_LOGIN_TMPL` 与 `_login_html`）

- [ ] **Step 1: 改模板 CSS**（在 `.foot{...}`（62 行）之后、`</style>` 之前加）

```css
.caprow{display:flex;gap:10px;align-items:center}
.capimg{height:44px;border-radius:8px;cursor:pointer;flex:0 0 auto}
.brandfoot{margin-top:22px;padding-top:16px;border-top:1px solid rgba(255,255,255,.08);
 display:flex;align-items:center;gap:14px;justify-content:center;text-align:left}
.brandfoot .qr{width:88px;height:88px;object-fit:contain;border-radius:8px;background:#fff;padding:4px}
.brandfoot .bf_txt{display:flex;flex-direction:column;gap:4px}
.brandfoot .bf_follow{font-size:13px;color:#cdd9ea;font-weight:600}
.brandfoot .bf_link{font-size:13px;color:#3b82f6;text-decoration:none}
.brandfoot .bf_cr{font-size:11px;color:#5f7399}
```

- [ ] **Step 2: 改模板表单**（把 68-71 行整段替换）

把：
```html
<label>用户名</label><input name="username" value="" autofocus autocomplete="username">
<label>密码</label><input name="password" type="password" autocomplete="current-password">
<button type="submit">登 录</button></form>
<div class="foot">Powered by 察元AI工舱</div>
```
替换为：
```html
<label>用户名</label><input name="username" value="" autofocus autocomplete="off" readonly onfocus="this.removeAttribute('readonly')">
<label>密码</label><input name="password" type="password" autocomplete="new-password" readonly onfocus="this.removeAttribute('readonly')">
<label>验证码</label>
<div class="caprow"><input name="captcha" autocomplete="off" maxlength="6" style="flex:1;text-transform:uppercase">
<img class="capimg" src="/captcha" alt="验证码" title="点击刷新" onclick="this.src='/captcha?'+Date.now()"></div>
<button type="submit">登 录</button></form>
__FOOT__
<div class="foot">Powered by 察元AI工舱</div>
```

- [ ] **Step 3: 改 `_login_html`**（把 74-79 行整段替换，支持错误码 + 品牌页脚）

```python
def _login_html(err_code=""):
    logo = _logo_data_uri()
    img = ('<img class="logo" src="%s" alt="察元AI工舱">' % logo) if logo else ''
    msg = {"1": "用户名或密码错误", "2": "验证码错误或已过期"}.get(str(err_code), "")
    err = ('<div class="err">%s</div>' % msg) if msg else ''
    foot = _brand_footer_html(_follow_qr_data_uri())
    return (_LOGIN_TMPL
            .replace("__LOGOIMG__", img)
            .replace("__ERR__", err)
            .replace("__FOOT__", foot))
```

- [ ] **Step 4: py 语法检查 + 渲染冒烟**

Run:
```bash
cd /work/chatop && python3 -c "import sys; sys.path.insert(0,'app-manager'); import app_manager as am; h=am._login_html('2'); assert '__FOOT__' not in h and '__ERR__' not in h and '/captcha' in h and 'readonly' in h and '验证码错误' in h and 'aidooo.com' in h; print('login html ok')"
```
Expected: `login html ok`

- [ ] **Step 5: Commit**

```bash
git add app-manager/app_manager.py
git commit -m "feat(app-manager): 登录页去回填+图形验证码+品牌页脚(关注我们/aidooo.com/版权)"
```

---

## Task 6: 接线 /captcha 路由 + POST /login 校验验证码与限流

**Files:**
- Modify: `app-manager/app_manager.py:412-421`（do_GET 加 /captcha）、`:475-484`（do_POST /login）

- [ ] **Step 1: do_GET 加 /captcha**（在 `do_GET` 里 `/login` 分支（416 行）之后加）

```python
        # 登录图形验证码（SVG）：下发签名 cookie，Caddy @public 放行
        if self.path.split("?", 1)[0].rstrip("/") == "/captcha":
            ans, cookie = _captcha_new()
            b = _captcha_svg(ans).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Set-Cookie",
                "%s=%s; Path=/; HttpOnly; SameSite=Lax; Secure; Max-Age=%d" % (CAPTCHA_COOKIE, cookie, CAPTCHA_TTL))
            self.send_header("Content-Length", str(len(b)))
            self.end_headers(); self.wfile.write(b); return
```

- [ ] **Step 2: 改 do_POST /login**（把 475-484 行整段替换）

```python
        if self.path.split("?",1)[0].rstrip("/") == "/login":
            n=int(self.headers.get("Content-Length",0))
            form=parse_qs(self.rfile.read(n).decode("utf-8","ignore"))
            u=form.get("username",[""])[0]; p=form.get("password",[""])[0]
            cap=form.get("captcha",[""])[0]
            ip=self.client_address[0]
            delay=_ratelimit_delay(ip)
            if delay: time.sleep(delay)
            # 先校验验证码（无状态签名 cookie）
            if not _captcha_check(_get_cookie(self.headers.get("Cookie",""), CAPTCHA_COOKIE), cap):
                _ratelimit_record_fail(ip)
                self.send_response(302); self.send_header("Location","/login?e=2"); self.end_headers(); return
            if u==AUTH_USER and AUTH_PW and hmac.compare_digest(p, AUTH_PW):
                _ratelimit_reset(ip)
                self.send_response(302); self.send_header("Location","/")
                self.send_header("Set-Cookie",
                    "%s=%s; Path=/; HttpOnly; SameSite=Lax; Secure; Max-Age=86400" % (AUTH_COOKIE, AUTH_TOKEN))
                self.send_header("Set-Cookie", "%s=; Path=/; Max-Age=0" % CAPTCHA_COOKIE)  # 验证码一次性
                self.end_headers(); return
            _ratelimit_record_fail(ip)
            self.send_response(302); self.send_header("Location","/login?e=1"); self.end_headers(); return
```

- [ ] **Step 3: 改 do_GET /login 传错误码**（把 414-416 行替换，从 `e=1` 布尔改成传 `e` 值）

```python
        if self.path.split("?",1)[0].rstrip("/") == "/login":
            err = parse_qs(urlparse(self.path).query).get("e",[""])[0]
            return self._send_html(200, _login_html(err))
```

- [ ] **Step 4: py 语法检查 + 全量单测**

Run:
```bash
cd /work/chatop && python3 -m py_compile app-manager/app_manager.py && cd app-manager && python3 -m pytest tests/test_app_manager.py -q
```
Expected: py_compile 无输出；pytest 全部 PASS（含新增 captcha/ratelimit）

- [ ] **Step 5: Commit**

```bash
git add app-manager/app_manager.py
git commit -m "feat(app-manager): 接线 /captcha + 登录校验验证码/软限流 + 双错误码"
```

---

## Task 7: Caddy 放行 /captcha

**Files:**
- Modify: `caddy/Caddyfile:9`

- [ ] **Step 1: 改 @public**（把第 9 行）

从：
```
    @public path /login /login/* /auth /auth/*
```
改为：
```
    @public path /login /login/* /auth /auth/* /captcha /captcha/*
```

- [ ] **Step 2: 提交**

```bash
git add caddy/Caddyfile
git commit -m "feat(caddy): 放行未登录访问 /captcha"
```

---

## Task 8: 等待页品牌页脚（novnc-src）

**Files:**
- Modify: `novnc-src/index.html:734`（`.chatop_transition_brand` 闭合 `</div>` 之后插入）
- Modify: `novnc-src/app/styles/base.css:1036`（`#noVNC_transition_text{...}` 之后加）

- [ ] **Step 1: index.html 插入页脚**（在 734 行 `</div>`（`.chatop_transition_brand` 闭合）之后、`<div id="noVNC_transition_text">`（735 行）之前插入）

```html
        <div class="chatop_transition_footer">
            <img class="cf_qr" src="/app-icons/follow-qr.jpg" alt="关注我们二维码">
            <div class="cf_txt">
                <div class="cf_follow">关注我们</div>
                <a class="cf_link" href="https://aidooo.com" target="_blank" rel="noopener">aidooo.com</a>
                <div class="cf_cr">版权所有 © 北京智灵鸟科技中心</div>
            </div>
        </div>
```

- [ ] **Step 2: base.css 加样式**（在 1036 行 `#noVNC_transition_text{...}` 闭合之后加）

```css
.chatop_transition_footer {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 44px;
  opacity: 0.9;
}
.chatop_transition_footer .cf_qr {
  width: 104px;
  height: 104px;
  object-fit: contain;
  border-radius: 8px;
  background: #fff;
  padding: 4px;
}
.chatop_transition_footer .cf_txt {
  display: flex;
  flex-direction: column;
  gap: 5px;
  text-align: left;
}
.chatop_transition_footer .cf_follow { font-size: 0.95em; font-weight: 600; color: #cdd9ea; }
.chatop_transition_footer .cf_link { font-size: 0.9em; color: #0084C2; text-decoration: none; }
.chatop_transition_footer .cf_cr { font-size: 0.78em; color: #5f7399; }
```

- [ ] **Step 3: Commit**

```bash
git add novnc-src/index.html novnc-src/app/styles/base.css
git commit -m "feat(novnc): 连接等待页加品牌页脚(关注我们二维码/aidooo.com/版权)"
```

---

## Task 9: 左侧菜单「关于我们」

**Files:**
- Create: `novnc-src/app/images/info.svg`
- Modify: `novnc-src/index.html:631`（退出按钮 div 之后插入）
- Modify: `novnc-src/app/ui.js:631`（logout 绑定之后加）

- [ ] **Step 1: 建图标**（`novnc-src/app/images/info.svg`）

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
```

- [ ] **Step 2: index.html 加按钮**（在 631 行 `退出` 那个 `noVNC_button_div` 闭合 `</div>`（631 行）之后插入）

```html
                <!-- chatop: 关于我们（新窗口打开 aidooo.com）——置于「退出」下方 -->
                <div class="noVNC_button_div" >
                    <input type="image" alt="关于我们" src="app/images/info.svg"
                        id="chatop_about_button" class="noVNC_button"
                        title="关于我们">
                    关于我们
                </div>
```

- [ ] **Step 3: ui.js 绑定**（在 627-631 行 logout 的 `addClickHandle` 块之后加）

```javascript
        // chatop: 关于我们 → 新窗口打开 aidooo.com
        UI.addClickHandle('chatop_about_button', () => {
            window.open('https://aidooo.com', '_blank', 'noopener');
        });
```

- [ ] **Step 4: Commit**

```bash
git add novnc-src/app/images/info.svg novnc-src/index.html novnc-src/app/ui.js
git commit -m "feat(novnc): 左侧菜单加「关于我们」→ aidooo.com"
```

---

## Task 10: 构建镜像 + 部署 + 端到端验证

**Files:** 无（构建/验证）

- [ ] **Step 1: 构建镜像**

Run: `cd /work/chatop && ./build-and-run.sh`（或项目既定构建脚本；版本号按需 bump）
Expected: 镜像构建成功，容器 chatop-ai 起来

- [ ] **Step 2: 验证登录页（curl）**

Run:
```bash
curl -sk https://127.0.0.1:7443/login | grep -E "readonly|/captcha|aidooo|北京智灵鸟"
curl -sk -i https://127.0.0.1:7443/captcha | grep -iE "image/svg|Set-Cookie: chatop_cap"
```
Expected: 登录页含 readonly、/captcha、aidooo.com、版权文案；/captcha 返回 svg + 种 chatop_cap cookie

- [ ] **Step 3: 验证登录流（错验证码被拒 / 正确通过）**

在浏览器打开桌面地址实测：
- 用户名/密码框加载时为空（浏览器不回填 admin）；验证码图显示、点击刷新换图。
- 故意填错验证码 → 回登录页提示「验证码错误或已过期」（`?e=2`）。
- 填对验证码 + 正确密码（admin / test12345）→ 进桌面。
- 连续 5 次失败后，后续登录明显变慢（软限流）。

- [ ] **Step 4: 验证等待页 + 左侧菜单**

- 点登录后进入「正在连接察元AI工舱…」等待页，底部显示关注我们二维码 + aidooo.com + 版权。
- 进桌面后左侧菜单有「关于我们」，点击新标签打开 aidooo.com。

- [ ] **Step 5: 全量单测复跑 + 收尾**

Run: `cd /work/chatop/app-manager && python3 -m pytest tests/test_app_manager.py -q`
Expected: 全 PASS

汇总改动范围 + 验证结果；`git status` 确认无误改；按用户指示决定是否 push。

---

## Self-Review 记录

- **Spec 覆盖**：①去默认用户名→Task5；②图形验证码→Task2/4/6/7；③登录页+等待页品牌块→Task4/5(登录页)+Task8(等待页)；④左侧菜单关于我们→Task9；资产→Task1；验证→Task10。全覆盖。
- **占位扫描**：无 TBD/TODO，代码块均完整。
- **一致性**：`CAPTCHA_COOKIE/AUTH_TOKEN/_captcha_new/_captcha_check/_get_cookie/_follow_qr_data_uri/_brand_footer_html/__FOOT__/e=1/e=2/RL_*` 跨任务命名一致；`follow-qr.jpg` 路径在 Task1/4/8 一致。
