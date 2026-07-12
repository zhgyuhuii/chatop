# -*- coding: utf-8 -*-
"""生成 data.json —— 全通道结构化教程。可复现：改这里后重跑即可。

    python3.11 -m agentconfig.tutorials._build_data

主流/国内通道手写详细步骤；长尾通道按 auth 生成合理步骤 + 官方 docs 链接。
凭据字段/申请链接与 catalog_overrides 对齐（同一真源，避免两处漂移）。
"""
from __future__ import annotations

import json
import os
import sys

# 让脚本能找到 catalog_overrides（openclaw-tool）。
sys.path.insert(0, os.environ.get("OPENCLAW_TOOL_DIR", "/work/chatop/openclaw-tool"))
try:
    import catalog_overrides as OV
    CHANNEL_AUTH = OV.CHANNEL_AUTH
    APPLY = OV.CHANNEL_APPLY_URLS
    QR_EXTRA = OV.CHANNEL_QR_EXTRA
    LABELS = OV.CHANNEL_LABELS_ZH
except Exception:
    CHANNEL_AUTH, APPLY, QR_EXTRA, LABELS = {}, {}, set(), {}

ALL_CHANNELS = ['clickclack', 'discord', 'feishu', 'googlechat', 'imessage', 'irc',
                'line', 'matrix', 'mattermost', 'msteams', 'nextcloud-talk', 'nostr',
                'openclaw-weixin', 'openclaw-zaloclawbot', 'qqbot', 'signal', 'slack',
                'sms', 'synology-chat', 'telegram', 'tlon', 'twitch', 'wecom',
                'whatsapp', 'yuanbao', 'zalo', 'zalouser']

DOCS = "https://docs.openclaw.ai/channels/"

# 手写详细教程（label / auth / steps / credential_fields / troubleshooting）。
DETAILED = {
    "telegram": {
        "label": "Telegram", "auth": "token",
        "steps": [
            "在 Telegram 打开 @BotFather，发送 /newbot 按提示创建机器人，保存返回的 Bot Token。",
            "在本页启用 Telegram，填入 Bot Token，保存配置。",
            "点「保存并启动网关」使配置生效。",
            "私聊你的机器人发送任意消息，会收到 8 位配对码（约 1 小时有效）。",
            "在本页「配对」区输入配对码批准；或终端执行 openclaw pairing approve telegram <码>。",
        ],
        "credential_fields": ["Bot Token"],
        "troubleshooting": [
            "群里不回复：@BotFather 里 /setprivacy 关闭隐私模式，或 @ 提及机器人。",
            "无配对码：确认网关已启动（openclaw gateway status）。",
        ],
    },
    "discord": {
        "label": "Discord", "auth": "token",
        "steps": [
            "打开 Discord 开发者门户，新建应用；在 Bot 页创建 Bot 并开启 Message Content Intent，复制 Token。",
            "OAuth2 → URL 生成器勾选 bot、applications.commands 及所需权限，用生成链接把 Bot 邀请进服务器。",
            "在本页启用 Discord，填入 Bot Token，保存配置并启动网关。",
            "私聊 Bot 发送消息获取配对码，在本页或终端 openclaw pairing approve discord <码> 批准。",
        ],
        "credential_fields": ["Bot Token"],
        "troubleshooting": ["收不到消息：确认已开启 Message Content Intent。"],
    },
    "slack": {
        "label": "Slack", "auth": "token",
        "steps": [
            "在 Slack API 创建应用并安装到工作区。",
            "OAuth & Permissions 里取 Bot User OAuth Token（xoxb-）；Socket 模式再取 App-Level Token（xapp-）。",
            "在本页启用 Slack，填入 Token，点「验证」检查，保存配置并启动网关。",
            "私聊 App/Bot 发消息获取配对码，openclaw pairing approve slack <码> 批准。",
        ],
        "credential_fields": ["Bot Token (xoxb-)", "App Token (xapp-)"],
        "troubleshooting": ["Token 验证失败：确认已把应用安装到工作区且勾选了必要 scope。"],
    },
    "feishu": {
        "label": "飞书 Feishu", "auth": "token",
        "steps": [
            "打开飞书开放平台，创建企业自建应用，复制 App ID（cli_）和 App Secret。",
            "权限管理导入所需权限；应用能力启用机器人；事件订阅添加 im.message.receive_v1，选「长连接接收」。",
            "发布应用版本并等待审核通过。",
            "在本页启用飞书，填 App ID / App Secret，点「验证」，保存配置并启动网关。",
            "飞书里给机器人发消息获取配对码，在本页「配对」批准。",
        ],
        "credential_fields": ["App ID (cli_)", "App Secret"],
        "troubleshooting": [
            "onboard 提示 feishu does not support onboarding：属正常，飞书走扩展，用本页或 openclaw channels add 配置。",
            "事件订阅保存失败：先启动网关再在飞书端保存长连接。",
            "找不到 SDK：在 extensions/feishu 执行 npm install（依赖 @larksuiteoapi/node-sdk）。",
        ],
    },
    "wecom": {
        "label": "企业微信 WeCom", "auth": "token",
        "steps": [
            "登录企业微信管理后台，创建自建应用，记录企业 ID（CorpID）、应用 AgentId 与 Secret。",
            "在本页勾选启用企业微信，本程序会自动安装 wecom 插件（openclaw plugins install wecom）。",
            "填入 CorpID / AgentId / Secret，保存配置并启动网关。",
            "在企业微信里给应用发消息，按提示完成配对。",
        ],
        "credential_fields": ["企业 ID (CorpID)", "应用 AgentId", "应用 Secret"],
        "troubleshooting": [
            "unknown channel id：确认插件已装成功（openclaw plugins list）。",
            "收不到消息：检查企业微信后台应用的可信 IP / 接收消息服务器配置。",
        ],
    },
    "openclaw-weixin": {
        "label": "微信（个人号，扫码登录）", "auth": "qr",
        "steps": [
            "在本页勾选启用微信，本程序会自动安装微信通道插件。",
            "点「开始扫码」，用手机微信扫描弹出的二维码登录。",
            "扫码并在手机确认后，回到总览会显示微信已连接。",
        ],
        "credential_fields": [],
        "troubleshooting": [
            "二维码没弹出：在弹出的终端窗口里直接扫码。",
            "登录掉线：微信个人号有风控，避免频繁登录/异地登录。",
        ],
    },
    "yuanbao": {
        "label": "腾讯元宝", "auth": "qr",
        "steps": ["在本页启用元宝并保存。", "点「开始扫码」，用手机扫描二维码登录。",
                  "扫码确认后回到总览查看连接状态。"],
        "credential_fields": [],
        "troubleshooting": ["二维码抓取失败时在终端窗口扫码。"],
    },
    "whatsapp": {
        "label": "WhatsApp", "auth": "qr",
        "steps": ["在本页启用 WhatsApp 并保存。",
                  "点「开始扫码」，用手机 WhatsApp 的「已登录设备」扫描二维码。",
                  "扫码成功后回到总览查看连接状态。"],
        "credential_fields": [],
        "troubleshooting": ["扫码后仍未连接：确认手机 WhatsApp 版本较新且网络正常。"],
    },
    "qqbot": {
        "label": "QQ 机器人", "auth": "token",
        "steps": ["在 QQ 开放平台创建机器人应用，获取 App ID / Token / App Secret。",
                  "在本页启用 QQ 机器人，填入凭据，保存配置并启动网关。",
                  "按平台要求配置回调/沙箱，向机器人发消息测试。"],
        "credential_fields": ["App ID", "Token", "App Secret"],
        "troubleshooting": ["无响应：确认已在 QQ 开放平台配置好消息回调与频道权限。"],
    },
    "line": {
        "label": "LINE", "auth": "token",
        "steps": ["在 LINE Developers 创建 Messaging API channel，取 Channel Access Token 与 Channel Secret。",
                  "在本页启用 LINE，填入凭据，保存配置并启动网关。",
                  "在 LINE 后台把 Webhook 指向网关地址并启用。"],
        "credential_fields": ["Channel Access Token", "Channel Secret"],
        "troubleshooting": ["收不到消息：确认 Webhook 已启用且「自动回复」已关闭。"],
    },
    "imessage": {
        "label": "iMessage", "auth": "builtin",
        "steps": ["iMessage 为内置通道（需 macOS 环境），在本页启用并保存即可。"],
        "credential_fields": [],
        "troubleshooting": ["仅 macOS 可用；需授予终端/自动化的完全磁盘访问权限。"],
    },
    "signal": {
        "label": "Signal（信号）", "auth": "qr",
        "steps": ["在本页启用 Signal 并保存。", "点「开始扫码」，用手机 Signal 关联新设备扫描二维码。",
                  "关联成功后回到总览查看连接状态。"],
        "credential_fields": [],
        "troubleshooting": ["需要本机可运行 signal-cli / 关联设备。"],
    },
    "msteams": {
        "label": "Microsoft Teams", "auth": "oauth",
        "steps": ["在 Microsoft Teams 开发者门户注册应用，配置机器人与权限。",
                  "在本页点授权链接完成 OAuth 登录授权。",
                  "授权完成后保存配置并启动网关。"],
        "credential_fields": [],
        "troubleshooting": ["授权失败：确认租户管理员已同意应用权限。"],
    },
    "googlechat": {
        "label": "Google Chat", "auth": "oauth",
        "steps": ["在 Google Cloud 控制台启用 Google Chat API 并配置应用。",
                  "在本页点授权链接完成授权。", "保存配置并启动网关。"],
        "credential_fields": [],
        "troubleshooting": ["确认已启用 chat.googleapis.com 且配置了正确的服务账号。"],
    },
}


def build():
    out = {"openclaw": {}}
    for cid in ALL_CHANNELS:
        auth = CHANNEL_AUTH.get(cid) or ("qr" if cid in QR_EXTRA else "token")
        if cid in DETAILED:
            e = dict(DETAILED[cid])
        else:
            label = LABELS.get(cid, cid)
            e = {"label": label, "auth": auth,
                 "steps": _generic_steps(cid, auth),
                 "credential_fields": [], "troubleshooting": [
                     "查看日志排错：openclaw logs --follow，向机器人发消息观察输出。"]}
        e["id"] = cid
        e.setdefault("auth", auth)
        e["apply_url"] = APPLY.get(cid) or e.get("apply_url")
        e["docs_url"] = DOCS + cid
        out["openclaw"][cid] = e
    return out


def _generic_steps(cid, auth):
    if auth == "qr":
        return ["在本页启用该通道并保存。", "点「开始扫码」，用对应 App 扫描二维码登录。",
                "扫码确认后回到总览查看连接状态。"]
    if auth == "builtin":
        return ["内置通道，在本页启用并保存即可，无需外部凭据。"]
    if auth == "oauth":
        return ["到该平台注册应用并配置权限。", "在本页点授权链接完成 OAuth 授权。",
                "保存配置并启动网关。"]
    if auth == "webhook":
        return ["复制本页显示的 Webhook 地址。", "到对端后台填入该地址并保存。",
                "保存配置并启动网关后测试收发。"]
    return ["到该平台开发者后台创建应用/机器人，获取凭据。",
            "在本页填写凭据并保存配置。", "启动网关；如走配对，按提示输入配对码。"]


def main():
    data = build()
    path = os.path.join(os.path.dirname(__file__), "data.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    print("wrote %s — %d channels" % (path, len(data["openclaw"])))


if __name__ == "__main__":
    main()
