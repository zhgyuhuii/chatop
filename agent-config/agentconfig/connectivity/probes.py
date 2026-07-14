# -*- coding: utf-8 -*-
"""逐通道只读连通性探针。纯 stdlib；测试通过 monkeypatch _http_json 注入假响应。
安全红线：探针只发只读请求；返回 message 绝不含明文 token（脱敏由调用方保证不回传原值）。"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from ..core.types import Diagnostic, LEVEL_OK, LEVEL_WARN, LEVEL_ERROR

_TIMEOUT = 8  # 每探针默认超时（秒）


def _http_json(method, url, headers=None, data=None, timeout=_TIMEOUT):
    """发只读 HTTP 并解析 JSON。返回 (status, obj|None, err|None)。测试 monkeypatch 此函数。"""
    body = None
    if isinstance(data, dict):
        body = json.dumps(data).encode("utf-8")
        headers = {**(headers or {}), "Content-Type": "application/json"}
    elif isinstance(data, (bytes, str)):
        body = data.encode("utf-8") if isinstance(data, str) else data
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw), None
            except ValueError:
                return resp.status, None, "非 JSON 响应"
    except urllib.error.HTTPError as e:
        try:
            obj = json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            obj = None
        return e.code, obj, f"HTTP {e.code}"
    except Exception as e:  # 超时/DNS/连接
        return 0, None, str(e)


def _fallback_probe(channel: str, cfg: dict) -> Diagnostic:
    """无专属只读端点（扫码/webhook/无 API）通道：只判配置完整性，不联网。"""
    has_content = any(bool(v) for k, v in (cfg or {}).items() if k != "enabled")
    if not cfg or not has_content:
        return Diagnostic(id=f"conn:{channel}:empty", level=LEVEL_WARN,
                          message="尚未填写凭据，无法校验连通性。", auto_fix=None)
    return Diagnostic(id=f"conn:{channel}:config-ok", level=LEVEL_OK,
                      message="已填写配置（该通道无在线校验端点，实际连通以网关运行为准）。")


def _first(cfg: dict, *keys):
    for k in keys:
        v = cfg.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _probe_telegram(cfg: dict) -> Diagnostic:
    tok = _first(cfg, "botToken", "token", "bot_token")
    if not tok:
        return Diagnostic(id="conn:telegram:empty", level=LEVEL_WARN, message="请先填写 Bot Token。")
    st, obj, err = _http_json("GET", f"https://api.telegram.org/bot{tok}/getMe")
    if obj and obj.get("ok") is True:
        uname = (obj.get("result") or {}).get("username", "")
        return Diagnostic(id="conn:telegram:ok", level=LEVEL_OK, message=f"连接成功，Bot：@{uname}")
    msg = (obj or {}).get("description") or err or "校验失败"
    return Diagnostic(id="conn:telegram:fail", level=LEVEL_ERROR, message=f"连接失败：{msg}")


def _probe_discord(cfg: dict) -> Diagnostic:
    tok = _first(cfg, "botToken", "token", "bot_token")
    if not tok:
        return Diagnostic(id="conn:discord:empty", level=LEVEL_WARN, message="请先填写 Bot Token。")
    st, obj, err = _http_json("GET", "https://discord.com/api/v10/users/@me",
                              headers={"Authorization": f"Bot {tok}"})
    if st == 200 and obj and obj.get("username"):
        return Diagnostic(id="conn:discord:ok", level=LEVEL_OK, message=f"连接成功，Bot：{obj['username']}")
    msg = (obj or {}).get("message") or err or "校验失败"
    return Diagnostic(id="conn:discord:fail", level=LEVEL_ERROR, message=f"连接失败：{msg}")


def _probe_slack(cfg: dict) -> Diagnostic:
    tok = _first(cfg, "botToken", "token", "bot_token", "botOAuthToken")
    if not tok:
        return Diagnostic(id="conn:slack:empty", level=LEVEL_WARN, message="请先填写 Bot Token。")
    st, obj, err = _http_json("POST", "https://slack.com/api/auth.test",
                              headers={"Authorization": f"Bearer {tok}"})
    if obj and obj.get("ok") is True:
        return Diagnostic(id="conn:slack:ok", level=LEVEL_OK, message="连接成功。")
    msg = (obj or {}).get("error") or err or "校验失败"
    return Diagnostic(id="conn:slack:fail", level=LEVEL_ERROR, message=f"连接失败：{msg}")


def _probe_feishu(cfg: dict) -> Diagnostic:
    aid = _first(cfg, "appId", "app_id")
    sec = _first(cfg, "appSecret", "app_secret")
    if not aid or not sec:
        return Diagnostic(id="conn:feishu:empty", level=LEVEL_WARN, message="请先填写 App ID 和 App Secret。")
    st, obj, err = _http_json(
        "POST", "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data={"app_id": aid, "app_secret": sec})
    if obj and obj.get("code") == 0:
        return Diagnostic(id="conn:feishu:ok", level=LEVEL_OK, message="飞书凭据校验成功。")
    msg = (obj or {}).get("msg") or err or "校验失败"
    return Diagnostic(id="conn:feishu:fail", level=LEVEL_ERROR, message=f"连接失败：{msg}")


def _probe_line(cfg: dict) -> Diagnostic:
    tok = _first(cfg, "channelAccessToken", "channel_access_token", "token")
    if not tok:
        return Diagnostic(id="conn:line:empty", level=LEVEL_WARN, message="请先填写 Channel Access Token。")
    st, obj, err = _http_json("GET", "https://api.line.me/v2/bot/info",
                              headers={"Authorization": f"Bearer {tok}"})
    if st == 200 and obj and (obj.get("userId") or obj.get("basicId")):
        return Diagnostic(id="conn:line:ok", level=LEVEL_OK,
                          message=f"连接成功：{obj.get('displayName') or obj.get('basicId')}")
    msg = (obj or {}).get("message") or err or "校验失败"
    return Diagnostic(id="conn:line:fail", level=LEVEL_ERROR, message=f"连接失败：{msg}")


def _probe_qqbot(cfg: dict) -> Diagnostic:
    aid = _first(cfg, "appId", "app_id", "botAppId")
    sec = _first(cfg, "clientSecret", "client_secret", "appSecret", "secret")
    if not aid or not sec:
        return Diagnostic(id="conn:qqbot:empty", level=LEVEL_WARN, message="请先填写 AppID 和 Secret。")
    st, obj, err = _http_json(
        "POST", "https://bots.qq.com/app/getAppAccessToken",
        data={"appId": aid, "clientSecret": sec})
    if obj and obj.get("access_token"):
        return Diagnostic(id="conn:qqbot:ok", level=LEVEL_OK, message="QQ 机器人凭据校验成功。")
    msg = (obj or {}).get("message") or (obj or {}).get("msg") or err or "校验失败"
    return Diagnostic(id="conn:qqbot:fail", level=LEVEL_ERROR, message=f"连接失败：{msg}")


CHANNEL_PROBES: dict = {}  # cid -> callable(cfg)->Diagnostic；后续任务注册

CHANNEL_PROBES.update({
    "telegram": _probe_telegram,
    "discord": _probe_discord,
    "slack": _probe_slack,
    "feishu": _probe_feishu,
    "line": _probe_line,
    "qqbot": _probe_qqbot,
})


def check(channel: str, channel_cfg: dict) -> Diagnostic:
    fn = CHANNEL_PROBES.get(channel)
    if fn is None:
        return _fallback_probe(channel, channel_cfg or {})
    try:
        return fn(channel_cfg or {})
    except Exception as e:  # 探针内部异常不外泄堆栈
        return Diagnostic(id=f"conn:{channel}:probe-error", level=LEVEL_ERROR,
                          message=f"连通性校验出错：{e}")
