#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""本地补充元数据 —— 只放 openclaw 确实不提供的信息。

**这张表是纯增强**：整个文件删掉，配置器功能不塌，只是少了中文名/申请链接。
这是它与被删除的 CHANNEL_PLUGINS 硬编码表的本质区别 —— 后者曾是 id 与包名的
唯一来源，一旦手抄出错（@openclaw/<id> 模式假设）就直接导致企业微信不可见。

绝不要在此文件里新增 openclaw 能回答的东西（通道 id、插件包名、安装状态）。
那些一律走 openclaw_catalog 从 CLI / schema / 官方插件目录取。
"""

# openclaw 官方目录未提供中文名的通道（多为纯内置通道，目录里没有它们的条目）
CHANNEL_LABELS_ZH = {
    "telegram": "Telegram",
    "imessage": "iMessage",
    "signal": "Signal（信号）",
    "sms": "SMS（短信）",
    "irc": "IRC",
    "mattermost": "Mattermost",
    "clickclack": "ClickClack",
}

# openclaw 的 selectionLabel 未标 "(QR" 但实际走扫码登录的通道。
# 目录已标的（whatsapp "(QR link)"、openclaw-zaloclawbot "(QR)"）不必列在这里。
CHANNEL_QR_EXTRA = frozenset({"openclaw-weixin", "yuanbao", "zalouser"})

# 通道认证方式：qr|token|webhook|oauth|builtin。缺省 token。
CHANNEL_AUTH = {
    "whatsapp": "qr",
    "openclaw-weixin": "qr",
    "openclaw-zaloclawbot": "qr",
    "yuanbao": "qr",
    "zalouser": "qr",
    "signal": "qr",
    "imessage": "builtin",
    "clickclack": "builtin",
    "feishu": "token",
    "wecom": "token",
    "qqbot": "token",
    "telegram": "token",
    "slack": "token",
    "discord": "token",
    "line": "token",
    "twitch": "token",
    "zalo": "token",
    "nostr": "token",
    "msteams": "oauth",
    "googlechat": "oauth",
    "synology-chat": "webhook",
    "nextcloud-talk": "webhook",
}

# 凭据申请地址（openclaw 不提供这类信息）
CHANNEL_APPLY_URLS = {
    "wecom": "https://work.weixin.qq.com/wework_admin/frame",
    "feishu": "https://open.feishu.cn/app",
    "qqbot": "https://q.qq.com/#/app/bot",
    "telegram": "https://core.telegram.org/bots#botfather",
    "slack": "https://api.slack.com/apps",
    "discord": "https://discord.com/developers/applications",
    "line": "https://developers.line.biz/console/",
    "msteams": "https://dev.teams.microsoft.com/",
    "googlechat": "https://console.cloud.google.com/apis/library/chat.googleapis.com",
    "twitch": "https://dev.twitch.tv/console/apps",
}

# 策展的模型厂商清单。
#
# openclaw 的 models.providers 是**开放集**（schema 里 propertyNames 仅约束为 string，
# 无 properties 闭集），故此表性质上就该是「策展清单」，不是「合法集合」。真正的约束
# 是 api（10 种协议枚举）与 auth（api-key|aws-sdk|oauth|token）。
#
# 字段：(id, 中文名, auth, ENV_VAR, apply_url)
# id 必须是 openclaw 的真实 provider id —— glm 是错的，真实 id 为 zai（14 个 GLM 模型）。
MODEL_PROVIDERS = [
    ("ollama", "Ollama（本地，无需登录）", None, None, None),
    ("openai", "OpenAI（GPT 系列）", "api-key", "OPENAI_API_KEY",
     "https://platform.openai.com/api-keys"),
    ("anthropic", "Anthropic Claude", "api-key", "ANTHROPIC_API_KEY",
     "https://console.anthropic.com/settings/keys"),
    ("deepseek", "DeepSeek（深度求索）", "api-key", "DEEPSEEK_API_KEY",
     "https://platform.deepseek.com/api_keys"),
    ("zai", "智谱 GLM（Z.ai）", "api-key", "ZAI_API_KEY",
     "https://open.bigmodel.cn/usercenter/apikeys"),
    ("moonshot", "月之暗面 Kimi", "api-key", "MOONSHOT_API_KEY",
     "https://platform.moonshot.cn/console/api-keys"),
    ("volcengine", "火山方舟（豆包）", "api-key", "VOLCENGINE_API_KEY",
     "https://console.volcengine.com/ark"),
    ("byteplus", "BytePlus", "api-key", "BYTEPLUS_API_KEY", None),
    ("tencent-tokenhub", "腾讯 TokenHub", "api-key", "TENCENT_TOKENHUB_API_KEY", None),
    ("xiaomi", "小米 MiMo", "api-key", "XIAOMI_API_KEY", None),
    ("mistral", "Mistral AI", "api-key", "MISTRAL_API_KEY",
     "https://console.mistral.ai/api-keys/"),
    ("cohere", "Cohere", "api-key", "COHERE_API_KEY",
     "https://dashboard.cohere.com/api-keys"),
    ("together", "Together AI", "api-key", "TOGETHER_API_KEY",
     "https://api.together.ai/settings/api-keys"),
    ("fireworks", "Fireworks AI", "api-key", "FIREWORKS_API_KEY",
     "https://fireworks.ai/account/api-keys"),
    ("novita", "Novita AI", "api-key", "NOVITA_API_KEY",
     "https://novita.ai/settings/key-management"),
    ("nvidia", "NVIDIA NIM", "api-key", "NVIDIA_API_KEY", "https://build.nvidia.com/"),
    ("venice", "Venice AI", "api-key", "VENICE_API_KEY", None),
    ("ollama-cloud", "Ollama Cloud", "api-key", "OLLAMA_API_KEY", None),
    ("github-copilot", "GitHub Copilot", "oauth", None,
     "https://github.com/settings/copilot"),
]

# 搜索能力在 openclaw 里也是插件。此处只放申请地址。
SEARCH_APPLY_URLS = {
    "tavily": "https://app.tavily.com/home",
    "brave": "https://api-dashboard.search.brave.com/app/keys",
    "perplexity": "https://www.perplexity.ai/settings/api",
    "firecrawl": "https://www.firecrawl.dev/app/api-keys",
    "searxng": None,
}

# 通道字段策展覆盖：{通道id: {字段key: {label?, help?, apply_url?, order?}}}
# 有条目 = 该字段提升为「主字段」（默认显示）；只补展示信息，不造字段（真源永远是 schema）。
CHANNEL_FIELD_OVERRIDES = {
    "telegram": {"channels.telegram.botToken": {
        "label": "Bot Token", "help": "Telegram 找 @BotFather 创建机器人获取。",
        "apply_url": "https://t.me/BotFather", "order": 0}},
    "discord": {"channels.discord.token": {
        "label": "Bot Token", "apply_url": "https://discord.com/developers/applications", "order": 0}},
    "slack": {"channels.slack.botToken": {"label": "Bot Token (xoxb-)", "order": 0},
              "channels.slack.appToken": {"label": "App Token (xapp-)", "order": 1},
              "channels.slack.signingSecret": {"label": "Signing Secret", "order": 2}},
    "feishu": {"channels.feishu.appId": {"label": "App ID (cli_)", "order": 0},
               "channels.feishu.appSecret": {"label": "App Secret", "order": 1}},
    "line": {"channels.line.channelAccessToken": {"label": "Channel Access Token", "order": 0},
             "channels.line.channelSecret": {"label": "Channel Secret", "order": 1}},
    "qqbot": {"channels.qqbot.appId": {"label": "App ID", "order": 0},
              "channels.qqbot.token": {"label": "Token", "order": 1},
              "channels.qqbot.appSecret": {"label": "App Secret", "order": 2}},
    "matrix": {"channels.matrix.homeserver": {"label": "Homeserver 地址", "order": 0},
               "channels.matrix.accessToken": {"label": "Access Token", "order": 1}},
}


def merge_field_overrides(cid, fields):
    """叠策展信息到 schema 字段：补 label/help/apply_url；有策展条目或 secret=主字段(advanced=False)；
    按 (advanced, order, name) 排序（主字段在前）。就地改 fields 内元素。"""
    ovr = CHANNEL_FIELD_OVERRIDES.get(cid) or {}
    for f in fields:
        o = ovr.get(f.get("key")) or {}
        if o.get("label"):
            f["label"] = o["label"]
        if o.get("help"):
            f["help"] = o["help"]
        if o.get("apply_url"):
            f["apply_url"] = o["apply_url"]
        f["advanced"] = not (f.get("secret") or f.get("key") in ovr)
    fields.sort(key=lambda f: (f.get("advanced", True),
                               ovr.get(f.get("key"), {}).get("order", 999),
                               f.get("name", "")))
    return fields
