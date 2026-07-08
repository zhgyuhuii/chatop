#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 可视化配置程序 — 完整复刻官方 onboard 引导流程
分步向导配置 ~/.openclaw/openclaw.json，每项参数带说明，支持保存与重启网关。
"""

import json
import os
import socket
import subprocess
import sys
import threading
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
except ImportError:
    print("未找到 tkinter。请安装后重试：")
    print("  Ubuntu/Debian: sudo apt-get install python3-tk")
    print("  Fedora: sudo dnf install python3-tkinter")
    sys.exit(1)

# 可选：使用 CustomTkinter 提升整体观感（若已安装）
# 说明：在部分老旧 Linux / Tk 组合下，CustomTkinter 可能触发底层 Tk 段错误。
# 为保证稳定性，这里强制关闭 CustomTkinter，统一回退到 ttk 组件。
try:
    import customtkinter as _ctk  # noqa: F401
except ImportError:
    _ctk = None
ctk = None


def _gui_entry(parent, textvariable=None, width_chars=20, show=None, **kwargs):
    """统一输入框：有 ctk 时用 CTkEntry，否则 ttk.Entry。width_chars 为字符宽度，CTk 会转为像素。"""
    if ctk is not None:
        w = max(80, min(600, width_chars * 10))
        return ctk.CTkEntry(parent, textvariable=textvariable, width=w, show=show or "", **kwargs)
    e = ttk.Entry(parent, textvariable=textvariable, width=width_chars, show=show or "", **kwargs)
    return e


def _gui_combobox(parent, textvariable, values, width_chars=14, **kwargs):
    """统一下拉框：有 ctk 时用 CTkComboBox，否则 ttk.Combobox。"""
    if ctk is not None:
        w = max(80, min(500, width_chars * 10))
        return ctk.CTkComboBox(parent, variable=textvariable, values=list(values), width=w, **kwargs)
    return ttk.Combobox(parent, textvariable=textvariable, values=list(values), width=width_chars, **kwargs)


def _gui_button(parent, text, command=None, **kwargs):
    """统一按钮：有 ctk 时用 CTkButton，否则 ttk.Button。"""
    if ctk is not None:
        return ctk.CTkButton(parent, text=text, command=command, **kwargs)
    return ttk.Button(parent, text=text, command=command, **kwargs)


def _gui_frame(parent, fg_color="transparent", **kwargs):
    """统一容器：有 ctk 时用 CTkFrame，否则 ttk.Frame。"""
    if ctk is not None:
        return ctk.CTkFrame(parent, fg_color=fg_color, **kwargs)
    return ttk.Frame(parent, **kwargs)


def _gui_label(parent, text="", **kwargs):
    """统一标签：有 ctk 时用 CTkLabel，否则 ttk.Label。自动将 foreground 转为 text_color，font 元组转为 CTkFont。"""
    if ctk is not None:
        kw = dict(kwargs)
        if "foreground" in kw:
            kw["text_color"] = kw.pop("foreground")
        if "font" in kw and isinstance(kw["font"], (tuple, list)) and len(kw["font"]) >= 2:
            size = 12
            weight = "normal"
            if len(kw["font"]) >= 2:
                try:
                    size = int(kw["font"][1]) if kw["font"][1] else 12
                except (TypeError, ValueError):
                    pass
            if len(kw["font"]) >= 3 and kw["font"][2] == "bold":
                weight = "bold"
            kw["font"] = ctk.CTkFont(size=size, weight=weight)
        return ctk.CTkLabel(parent, text=text, **kw)
    return ttk.Label(parent, text=text, **kwargs)


def _gui_checkbox(parent, text, variable, **kwargs):
    """统一复选框：有 ctk 时用 CTkCheckBox，否则 ttk.Checkbutton。"""
    if ctk is not None:
        return ctk.CTkCheckBox(parent, text=text, variable=variable, **kwargs)
    return ttk.Checkbutton(parent, text=text, variable=variable, **kwargs)


def _gui_separator(parent, orient="horizontal", **kwargs):
    """统一分隔线：有 ctk 时用细 CTkFrame，否则 ttk.Separator。"""
    if ctk is not None:
        if orient == "horizontal":
            sep = ctk.CTkFrame(parent, fg_color=("gray75", "gray30"), height=2, **kwargs)
        else:
            sep = ctk.CTkFrame(parent, fg_color=("gray75", "gray30"), width=2, **kwargs)
        return sep
    return ttk.Separator(parent, orient=orient, **kwargs)


def _gui_link(parent, text, command, **kwargs):
    """链接样式可点击组件：有 ctk 时用 CTkLabel 仿链接（蓝色、手型光标），否则 ttk.Label 仿链接。"""
    if ctk is not None:
        link_color = "#2563eb"
        hover_color = "#1d4ed8"
        lbl = ctk.CTkLabel(
            parent,
            text=text,
            text_color=link_color,
            font=ctk.CTkFont(underline=True),
            cursor="hand2",
            **kwargs,
        )

        def _on_enter(e):
            lbl.configure(text_color=hover_color)

        def _on_leave(e):
            lbl.configure(text_color=link_color)

        def _on_click(e):
            if command:
                command()

        lbl.bind("<Button-1>", lambda e: _on_click(e))
        lbl.bind("<Enter>", _on_enter)
        lbl.bind("<Leave>", _on_leave)
        return lbl
    # ttk 回退：可点击的蓝色标签
    lbl = ttk.Label(parent, text=text, foreground="#2563eb", cursor="hand2", **kwargs)

    def _on_click(e):
        if command:
            command()

    lbl.bind("<Button-1>", lambda e: _on_click(e))
    return lbl


CONFIG_DIR = Path.home() / ".openclaw"
CONFIG_FILE = CONFIG_DIR / "openclaw.json"
CONFIG_BACKUP = CONFIG_DIR / "openclaw.json.gui-bak"
CUSTOM_PROVIDERS_FILE = CONFIG_DIR / "custom-providers.json"
GUI_LOCK_FILE = CONFIG_DIR / "openclaw-gui.lock"
GUI_SINGLETON_PORT = 18790  # 单例唤醒：已运行实例监听此端口，二次启动时连接并发送 focus 以唤至前台

# 确保使用 UTF-8
if sys.platform != "win32":
    try:
        import locale
        if hasattr(locale, "setlocale"):
            locale.setlocale(locale.LC_ALL, "C.UTF-8")
    except Exception:
        pass


# ---------- 参数说明（官方文档摘要） ----------
PARAM_HINTS = {
    "config_choice": "已有配置时的处理：保持（不覆盖）、修改（在现有基础上改）、重置（清空配置与凭据等后重配）。",
    "gateway.port": "网关监听端口，默认 18789。Control UI 和 WebSocket 客户端通过此端口连接。",
    "gateway.bind": "绑定模式（2026.6.10）：loopback 仅本机(127.0.0.1)；lan 监听局域网；tailnet 仅 Tailscale 网内；auto 自动选择；custom 自定义(配合 customBindHost)。对外监听须配合认证。",
    "gateway.auth.mode": "认证方式（2026.6.10）：token（推荐，本地也建议保留）、password、trusted-proxy（由前置反代注入身份）、none（仅完全信任本机时）。",
    "gateway.auth.token": "网关 Token，连接 Control UI 或 WS 时使用。留空可自动生成。",
    "gateway.auth.password": "网关密码（password 模式时使用）。",
    "gateway.tailscale.mode": "Tailscale 暴露：off 不启用；serve 仅 tailnet 内 HTTPS；funnel 公网 HTTPS（需设密码）。",
    "gateway.reload.mode": "配置热重载：hybrid 安全项即时生效、需重启的自动重启；hot 仅热生效并提示；restart 任何改动都重启；off 不监听。",
    "agents.defaults.workspace": "Agent 工作区目录，存放 AGENTS.md、SOUL.md、TOOLS.md 及 skills 等。",
    "agents.defaults.skipBootstrap": "为 true 时不自动创建/更新工作区引导文件。",
    "agents.defaults.model.primary": "主模型，格式为 provider/model，例如 ollama/xxx、anthropic/claude-sonnet-4-5、openai/gpt-5.2。",
    "agents.defaults.model.fallbacks": "备选模型列表，主模型不可用时按顺序尝试。逗号分隔，如：openai/gpt-4.1, ollama/llama3。",
    "agents.defaults.imageModel.primary": "仅当主模型不支持图像时使用的视觉模型。",
    "agents.defaults.thinkingDefault": "思考深度：off、minimal、low、medium、high、xhigh（部分模型支持）。",
    "session.dmScope": "DM 会话范围：main 共享单会话；per-peer 按联系人；per-channel-peer 按通道+联系人；per-account-channel-peer 最细。多用户建议 per-channel-peer。",
    "session.reset.mode": "会话重置策略：daily 每日定时；idle 空闲超时后重置（当前版本仅支持此两项）。",
    "session.reset.atHour": "daily 模式下每日重置的小时数（0–23）。",
    "session.reset.idleMinutes": "idle 模式下无消息多少分钟后重置。",
    "tools.profile": "工具策略：coding 含文件/终端等；default 常用子集；minimal 最少工具。",
    "tools.web.search.enabled": "是否启用网页搜索（web_search），需在下方配置搜索提供商与 API Key。",
    "tools.web.search.provider": "搜索提供商：Perplexity、Brave、Gemini、Grok、Kimi 等。",
    "tools.web.search.apiKey": "所选搜索提供商的 API Key。",
    "commands.native": "是否注册各通道原生命令（如 Discord/Telegram 的 /model）：auto、true、false。",
    "commands.text": "是否在聊天消息中解析 /命令（如 /model、/reset）。",
    "commands.restart": "是否允许 /restart 及网关重启工具。",
    "commands.config": "是否允许通过聊天 /config 读写配置（慎开）。",
    "channels.telegram.enabled": "是否启用 Telegram 通道。",
    "channels.telegram.botToken": "Telegram Bot Token，从 @BotFather 获取。",
    "channels.telegram.dmPolicy": "DM 策略：pairing 陌生人收配对码需你批准；allowlist 仅允许列表；open 所有人（需 allowFrom 含 *）；disabled 忽略 DM。",
    "channels.telegram.allowFrom": "允许的 Telegram 用户 ID（tg:123456789），逗号分隔。allowlist 时必填。",
    "channels.telegram.groupPolicy": "群组策略：allowlist 仅允许列表中的群；open 所有群；disabled 不收群消息。",
    "channels.discord.enabled": "是否启用 Discord 通道。",
    "channels.discord.token": "Discord Bot Token，从 Discord 开发者门户创建应用后获取。",
    "channels.discord.dmPolicy": "同 Telegram DM 策略。",
    "channels.discord.allowFrom": "允许的 Discord 用户 ID，逗号分隔。",
    "channels.whatsapp.enabled": "是否启用 WhatsApp（需先通过 openclaw channels login 链接设备）。",
    "channels.whatsapp.allowFrom": "允许的手机号，如 +8613800138000，逗号分隔。",
    "channels.whatsapp.dmPolicy": "DM 策略，同 Telegram。",
    "channels.slack.enabled": "是否启用 Slack。",
    "channels.slack.botToken": "Slack Bot Token（xoxb- 开头）。Socket 模式还需 App-Level Token（xapp-）。",
    "channels.slack.appToken": "Slack App-Level Token（xapp-），Socket 模式必填。",
    "channels.slack.dmPolicy": "DM 策略。",
    "channels.slack.allowFrom": "允许的 Slack 用户 ID（U 开头），逗号分隔。",
    "channels.signal.enabled": "是否启用 Signal（需安装 signal-cli）。",
    "channels.signal.allowFrom": "允许的号码或 uuid:，逗号分隔。",
    "channels.signal.dmPolicy": "DM 策略。",
    "channels.defaults.groupPolicy": "所有通道的默认群组策略：allowlist、open、disabled。",
    "channels.defaults.dmPolicy": "所有通道的默认 DM 策略（各通道可单独覆盖）。",
    "channels.dmPolicy": "DM 策略：pairing 需验证码配对后才能对话；allowlist 只允许「允许来自」列表中的用户访问；open 所有人可访问（allowFrom 可填 *）；disabled 不接收 DM。",
    "channels.allowFrom": "允许来自：填写可访问该通道的用户 ID 或标识，逗号分隔。DM 策略为 allowlist 时，只有此列表中的用户可私聊机器人；为 pairing 时此处可留空或填已批准用户。",
    "channels.pairing": "通道配对：当 DM 策略为 pairing 时，陌生人私聊机器人会收到配对码；在此输入配对码并点击「批准配对」后，该用户即可与机器人对话。",
    "skills.nodeManager": "安装 Skills 时使用的包管理器：npm 或 pnpm。",
    "daemon.install": "是否安装/更新 systemd 用户服务（Linux）或 LaunchAgent（macOS），使网关在后台常驻。",
}

# 飞书 Node.js SDK 官方文档（开发前准备 / 依赖安装）
FEISHU_SDK_DOC_URL = "https://open.feishu.cn/document/server-side-sdk/nodejs-sdk/preparation-before-development"

# 各通道 Token/应用 获取地址（点击在浏览器打开）
CHANNEL_TOKEN_URLS = {
    "telegram": ("Telegram Bot Token", "https://t.me/BotFather"),
    "discord": ("Discord Bot Token", "https://discord.com/developers/applications"),
    "slack": ("Slack 应用与 Token", "https://api.slack.com/apps"),
    "feishu": ("飞书/ Lark 开放平台（创建应用获取 App ID/Secret）", "https://open.feishu.cn/app"),
    "feishu_lark": ("Lark 国际版开放平台", "https://open.larksuite.com/app"),
    "googlechat": ("Google Chat API（需启用并创建服务账号）", "https://console.cloud.google.com/apis/library/chat.googleapis.com"),
    "mattermost": ("Mattermost 个人访问令牌（系统控制台）", "https://docs.openclaw.ai/channels/mattermost"),
    "msteams": ("Microsoft Teams 开发者门户（Bot Framework）", "https://dev.teams.microsoft.com"),
    "whatsapp": ("WhatsApp 需在终端运行: openclaw channels login", "https://docs.openclaw.ai/channels/whatsapp"),
    "signal": ("Signal 需安装 signal-cli 并注册", "https://github.com/AsamK/signal-cli"),
    "irc": ("IRC 服务器与 NickServ 配置", "https://docs.openclaw.ai/channels/irc"),
    "bluebubbles": ("BlueBubbles 服务（iMessage 推荐）", "https://docs.openclaw.ai/channels/bluebubbles"),
    "imessage": ("iMessage 需 macOS + imsg", "https://docs.openclaw.ai/channels/imessage"),
}

# 各通道配置与配对/验证引导（基于 OpenClaw 官方文档）
CHANNEL_SETUP_GUIDE = {
    "telegram": """Telegram 通道 — 配置与配对步骤（官方文档）

① 获取 Token：在 Telegram 中打开 @BotFather，发送 /newbot 按提示创建机器人，保存返回的 Bot Token。

② 填写并保存：在本页勾选「启用 Telegram」，填写 Bot Token，点击底部「保存配置」。

③ 启动网关：点击「一键启动 OpenClaw」或「保存并重启 OpenClaw」（会先保存再启动，确保配置生效）。

④ 发起配对：私聊你的 Telegram 机器人发送任意消息，机器人会回复一个配对码（8 位，约 1 小时有效）。

⑤ 批准配对：在终端执行：
   openclaw pairing list telegram
   openclaw pairing approve telegram <配对码>
   完成后即可正常与机器人对话。

群组：将机器人拉入群后，默认需 @ 提及才回复；在 BotFather 可 /setprivacy 关闭隐私模式以查看所有群消息。""",
    "discord": """Discord 通道 — 配置与配对步骤（官方文档）

① 创建应用与 Bot：打开 Discord 开发者门户，新建应用，在 Bot 页创建 Bot，开启 Message Content Intent，复制 Bot Token。

② 邀请 Bot：在 OAuth2 → URL 生成器中勾选 bot、applications.commands 及所需权限，用生成的链接将 Bot 邀请到你的服务器。

③ 填写并保存：在本页勾选「启用 Discord」，填写 Bot Token，点击「保存配置」；再点击「一键启动 OpenClaw」或「保存并重启」。

④ 发起配对：在 Discord 私聊你的 Bot 发送消息，Bot 会回复配对码。

⑤ 批准配对：终端执行：
   openclaw pairing list discord
   openclaw pairing approve discord <配对码>
   或通过其他已连接通道的 Agent 说「批准此 Discord 配对码：<配对码>」。""",
    "feishu": """飞书 Feishu 通道 — 配置与配对步骤（官方文档）

① 创建应用：打开飞书开放平台，创建企业自建应用，在「凭证与基础信息」中复制 App ID（cli_xxx）和 App Secret。

② 配置应用：在「权限管理」中批量导入所需权限；在「应用能力」中启用机器人；在「事件订阅」中添加 im.message.receive_v1，选择「使用长连接接收事件」（需先启动网关并执行 openclaw channels add 配置飞书）。发布应用版本并等待审核通过。

③ 飞书 SDK 与依赖：飞书通道插件依赖飞书官方 Node SDK（@larksuiteoapi/node-sdk）。若启动报错找不到该模块，请在本页点击「安装飞书 SDK」或在 extensions/feishu 目录执行 npm install；开发说明见「飞书 SDK 文档」。
④ 填写并保存：在本页勾选「启用 飞书 Feishu/Lark」，填写 App ID 与 App Secret，点击「验证」可检查凭据，点击「保存配置」；再点击「一键启动 OpenClaw」或「保存并重启」。

⑤ 发起配对：在飞书中找到你的机器人并发送消息，机器人会回复配对码。

⑥ 批准配对：在本页「通道配对」区域选择「飞书 Feishu」、输入配对码后点「批准配对」，或在终端执行：
   openclaw pairing list feishu
   openclaw pairing approve feishu <配对码>
   完成后即可正常对话。

——— 飞书最新推荐方式（非 onboard） ———
• OpenClaw 主向导 openclaw onboard 仅内置 Telegram/Discord/Slack/WhatsApp 等，飞书通过扩展提供，onboard 不会加载扩展里的适配器，因此会提示「feishu does not support onboarding yet」属预期行为，并非取消支持。
• 飞书请用以下任一方式配置（推荐）：① 本程序「4. 通道」页勾选启用飞书并填写 App ID / App Secret 后保存；② 终端执行 openclaw channels add 后选择 Feishu 并填写凭据。

——— 连接不成功时请逐项排查 ———
• 网关已启动：运行 openclaw gateway status，若未运行请先「一键启动 OpenClaw」或执行 openclaw gateway。
• 已用 channels add 登记：在终端执行 openclaw channels add，选择 Feishu 并填写 App ID / App Secret（与配置一致），再保存配置并重启网关。
• 飞书端事件订阅：开放平台 → 事件订阅 → 添加 im.message.receive_v1 → 选择「使用长连接接收事件」。若保存失败，请先启动网关后再在飞书端保存。
• 应用已发布：版本管理与发布中创建版本并提交审核、通过后再试。
• 查看日志：执行 openclaw logs --follow，在飞书发消息给机器人，看是否有报错或「feishu:」相关输出。""",
    "slack": """Slack 通道 — 配置与配对步骤（官方文档）

① 创建应用：在 Slack API 创建应用（或从应用目录），安装到工作区，在「OAuth & Permissions」中获取 Bot User OAuth Token（xoxb- 开头）。

② 填写并保存：在本页勾选「启用 Slack」，填写 Bot Token（及 Socket 模式时需要的 App-Level Token xapp-），点击「验证」可检查 Token，点击「保存配置」；再点击「一键启动 OpenClaw」或「保存并重启」。

③ 配对（默认 DM 策略为 pairing）：在 Slack 中私聊你的 App/Bot 发送消息，会收到配对码。终端执行：
   openclaw pairing list slack
   openclaw pairing approve slack <配对码>
   完成后即可正常对话。""",
}

# 技能中文说明（能做什么）
SKILL_ZH = {
    "1password": "使用 1Password CLI (op)：安装、登录、读取/注入密钥。",
    "apple-notes": "通过 memo CLI 管理 Apple 笔记：创建、查看、编辑、删除、搜索。",
    "apple-reminders": "通过 remindctl 管理 Apple 提醒：列表、添加、完成、删除。",
    "bear-notes": "通过 grizzly CLI 创建、搜索、管理 Bear 笔记。",
    "blogwatcher": "用 blogwatcher CLI 监控博客与 RSS/Atom 更新。",
    "blucli": "BluOS CLI 控制音箱：发现、播放、分组、音量。",
    "bluebubbles": "通过 BlueBubbles 发送与管理 iMessage（推荐 iMessage 集成）。",
    "camsnap": "从 RTSP/ONVIF 摄像头抓取单帧或片段。",
    "clawhub": "用 ClawHub CLI 搜索、安装、更新、发布技能（clawhub.com）。",
    "coding-agent": "将编程任务委托给 Codex、Claude Code 或 Pi：建项目、审 PR、重构。",
    "discord": "Discord 操作：通过 message 工具发消息、管理频道。",
    "eightctl": "控制 Eight Sleep 智能床垫：状态、温度、闹钟、日程。",
    "gemini": "Gemini CLI：问答、摘要、生成。",
    "gh-issues": "拉取 GitHub issues、派子 agent 修 bug 并开 PR、跟进评论。",
    "github": "通过 gh CLI 操作 GitHub：issues、PR、CI、代码审查、API。",
    "gifgrep": "搜索 GIF、下载、提取静帧。",
    "gog": "Google Workspace CLI：Gmail、日历、Drive、联系人、Sheets、Docs。",
    "goplaces": "通过 goplaces CLI 查询 Google Places：搜索、详情、评论。",
    "healthcheck": "主机安全加固与 OpenClaw 健康检查、版本状态。",
    "himalaya": "用 himalaya CLI 管理邮件（IMAP/SMTP）：收发自终端。",
    "imsg": "iMessage/SMS CLI：列出会话、历史、发送消息。",
    "mcporter": "用 mcporter 配置、认证、调用 MCP 服务器（HTTP/stdio）。",
    "model-usage": "CodexBar 本地用量：按模型汇总 Codex/Claude 成本。",
    "nano-banana-pro": "通过 Gemini 3 Pro Image 生成或编辑图片。",
    "nano-pdf": "用 nano-pdf CLI 以自然语言编辑 PDF。",
    "notion": "Notion API：创建与管理页面、数据库、块。",
    "obsidian": "用 obsidian-cli 操作 Obsidian 仓库与 Markdown 笔记。",
    "openai-image-gen": "通过 OpenAI Images API 批量生成图片。",
    "openai-whisper": "本地语音转文字（Whisper CLI，无需 API Key）。",
    "openai-whisper-api": "通过 OpenAI 语音转写 API 转写音频。",
    "openhue": "通过 OpenHue CLI 控制飞利浦 Hue 灯与场景。",
    "oracle": "oracle CLI 使用规范：提示、文件打包、引擎、会话。",
    "ordercli": "Foodora 订单查询（Deliveroo 开发中）。",
    "peekaboo": "用 Peekaboo CLI 捕获与自动化 macOS 界面。",
    "sag": "ElevenLabs 语音合成（mac 风格 say 体验）。",
    "session-logs": "用 jq 搜索、分析自己的会话历史。",
    "sherpa-onnx-tts": "本地离线 TTS（sherpa-onnx）。",
    "skill-creator": "创建或更新 AgentSkills：设计、结构、打包技能。",
    "slack": "通过 slack 工具控制 Slack：回复、置顶、反应等。",
    "songsee": "用 songsee CLI 从音频生成频谱图与特征图。",
    "sonoscli": "控制 Sonos 音箱：发现、状态、播放、音量、分组。",
    "spotify-player": "终端 Spotify 播放/搜索（spogo 或 spotify_player）。",
    "summarize": "总结或提取 URL、播客、本地文件的文字/转录。",
    "things-mac": "通过 things CLI 管理 Things 3：任务、项目、标签（macOS）。",
    "tmux": "远程控制 tmux 会话：发送按键、抓取面板输出。",
    "trello": "通过 Trello REST API 管理看板、列表、卡片。",
    "weather": "通过 wttr.in 或 Open-Meteo 查天气与预报（无需 API Key）。",
    "wacli": "通过 wacli 向他人发 WhatsApp 或搜索/同步历史（非普通聊天）。",
    "xurl": "向 X (Twitter) API 发认证请求：发推、回复、搜索、DM 等。",
    "feishu-doc": "飞书文档读写：云文档、docx 链接。",
    "feishu-drive": "飞书云盘文件管理。",
    "feishu-perm": "飞书文档与文件权限管理。",
    "feishu-wiki": "飞书知识库导航。",
}


def try_acquire_gui_lock():
    """尝试获取 GUI 单例锁。成功返回 True（调用方为唯一实例），失败返回 False（已有实例在运行）。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = str(GUI_LOCK_FILE)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
        try:
            if sys.platform == "win32":
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (OSError, BlockingIOError):
            try:
                os.close(fd)
            except Exception:
                pass
            return False
    except Exception:
        return False


def request_focus_via_socket():
    """向已运行的 GUI 实例发送「前置窗口」请求；若连接成功则发送后退出。"""
    for _ in range(5):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect(("127.0.0.1", GUI_SINGLETON_PORT))
            sock.sendall(b"focus\n")
            sock.close()
            return
        except (socket.error, OSError):
            pass
        try:
            import time
            time.sleep(0.3)
        except Exception:
            pass


def open_url(url):
    """在默认浏览器中打开 URL。"""
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", url], check=True)
        elif sys.platform == "win32":
            subprocess.run(["start", "", url], shell=True, check=True)
        else:
            subprocess.run(["xdg-open", url], check=True)
    except Exception as e:
        messagebox.showinfo("打开链接", f"请手动打开: {url}\n\n{e}")


def check_gateway_running(port=18789):
    """检测 OpenClaw 网关是否在运行。"""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/", method="GET")
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:
        return False


def check_network_ok(timeout=5):
    """检测网络是否可用（用于安装插件前检查，不通则不安装）。"""
    for url in ("https://registry.npmjs.org", "https://www.npmjs.com"):
        try:
            req = urllib.request.Request(url, method="HEAD")
            urllib.request.urlopen(req, timeout=timeout)
            return True
        except Exception:
            continue
    return False


def verify_feishu_credentials(app_id, app_secret):
    """验证飞书 App ID 与 App Secret，调用 tenant_access_token 接口。返回 (成功, 消息)。"""
    app_id = (app_id or "").strip()
    app_secret = (app_secret or "").strip()
    if not app_id or not app_secret:
        return False, "请先填写 App ID 和 App Secret。"
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if result.get("code") == 0:
            return True, "飞书凭据验证成功。"
        return False, result.get("msg", "未知错误") or ("code: " + str(result.get("code", "")))
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            r = json.loads(body)
            return False, r.get("msg", body) or str(e)
        except Exception:
            return False, str(e)
    except Exception as e:
        return False, str(e)


def verify_telegram_token(token):
    """验证 Telegram Bot Token，调用 getMe。返回 (成功, 消息)。"""
    token = (token or "").strip()
    if not token:
        return False, "请先填写 Bot Token。"
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if result.get("ok") is True:
            uname = (result.get("result") or {}).get("username", "")
            return True, f"Telegram 验证成功。Bot: @{uname}"
        return False, result.get("description", "未知错误")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            r = json.loads(body)
            return False, r.get("description", body) or str(e)
        except Exception:
            return False, str(e)
    except Exception as e:
        return False, str(e)


def verify_discord_token(token):
    """验证 Discord Bot Token。返回 (成功, 消息)。"""
    token = (token or "").strip()
    if not token:
        return False, "请先填写 Bot Token。"
    url = "https://discord.com/api/v10/users/@me"
    try:
        req = urllib.request.Request(url, method="GET", headers={"Authorization": f"Bot {token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        uname = result.get("username", "")
        return True, f"Discord 验证成功。Bot: {uname}"
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            r = json.loads(body)
            return False, r.get("message", body) or str(e)
        except Exception:
            return False, str(e)
    except Exception as e:
        return False, str(e)


def verify_slack_token(token):
    """验证 Slack Bot Token (auth.test)。返回 (成功, 消息)。"""
    token = (token or "").strip()
    if not token:
        return False, "请先填写 Bot Token。"
    url = "https://slack.com/api/auth.test"
    try:
        data = urllib.parse.urlencode({"token": token}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if result.get("ok") is True:
            return True, "Slack 验证成功。"
        return False, result.get("error", "未知错误")
    except Exception as e:
        return False, str(e)


def get_channel_connection_status():
    """调用 openclaw status --json 获取通道连接状态，返回多行字符串；失败时返回简短提示。"""
    try:
        r = subprocess.run(
            ["openclaw", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=20,
            cwd=os.path.expanduser("~"),
            env={**os.environ},
        )
        out = (r.stdout or "").strip()
        if not out or r.returncode != 0:
            return "通道连接状态: 无法获取（请确认已安装 openclaw 且网关已启动）"
        # 输出可能混有警告，取最后一个完整 JSON 对象
        start = out.rfind("{")
        if start < 0:
            return "通道连接状态: 无法解析"
        depth = 0
        data = None
        for i in range(start, len(out)):
            if out[i] == "{":
                depth += 1
            elif out[i] == "}":
                depth -= 1
                if depth == 0:
                    data = json.loads(out[start : i + 1])
                    break
        if data is None:
            return "通道连接状态: 无法解析"
        lines = ["通道连接状态:"]
        gw = data.get("gateway") or {}
        reachable = gw.get("reachable", False)
        lines.append(f"  网关: {'可连接' if reachable else '不可连接'}")
        for entry in data.get("channelSummary") or []:
            lines.append(f"  {entry}")
        return "\n".join(lines)
    except subprocess.TimeoutExpired:
        return "通道连接状态: 获取超时"
    except Exception as e:
        return f"通道连接状态: 获取失败 ({e})"


def get_config_summary(config, include_channel_status=False, gateway_status=None):
    """从配置生成一览表文本。include_channel_status=False 时跳过耗时的 openclaw status。
    gateway_status: None=显示「检测中」不请求网络，True/False=直接显示运行中/未运行（用于异步回填）。"""
    if not config or config.get("_load_error"):
        return "未检测到有效配置。"
    lines = []
    g = config.get("gateway") or {}
    port = g.get("port", 18789)
    lines.append(f"网关端口: {port}")
    if gateway_status is None and not include_channel_status:
        lines.append("运行状态: 检测中...")
    else:
        if gateway_status is None:
            gateway_status = check_gateway_running(port)
        lines.append(f"运行状态: {'运行中' if gateway_status else '未运行'}")
    a = config.get("agents") or {}
    d = a.get("defaults") or {}
    m = d.get("model") or {}
    primary = m.get("primary", "") if isinstance(m, dict) else (m if isinstance(m, str) else "未设置")
    lines.append(f"主模型: {primary or '未设置'}")
    ch = config.get("channels") or {}
    enabled_ch = [k for k, v in ch.items() if k != "defaults" and isinstance(v, dict) and v.get("enabled", True)]
    lines.append(f"已配置通道: {', '.join(enabled_ch) if enabled_ch else '无'}")
    workspace = d.get("workspace", str(CONFIG_DIR / "workspace"))
    skills_dir = Path(workspace.replace("~", str(Path.home()))) / "skills"
    if skills_dir.exists():
        skills_count = len([x for x in skills_dir.iterdir() if x.is_dir() and (x / "SKILL.md").exists()])
        lines.append(f"工作区技能数: {skills_count}")
    else:
        lines.append("工作区技能: 无")
    summary = "\n".join(lines)
    if include_channel_status:
        try:
            status = get_channel_connection_status()
            summary += "\n\n" + status
        except Exception:
            pass
    else:
        summary += "\n\n通道连接状态: 点击「刷新一览」获取"
    return summary


# 需通过插件安装的通道（npm 包名）
# 通道扩展插件（openclaw 2026.6.10：telegram/discord/slack/whatsapp 为内置，其余作扩展提供，
# 包名 @openclaw/<key>，均已在 npm 验证存在）。telegram 无独立包(核心内置)故不列。
CHANNEL_PLUGINS = [
    ("@openclaw/feishu", "飞书 Feishu"),
    ("@openclaw/mattermost", "Mattermost"),
    ("@openclaw/msteams", "Microsoft Teams"),
    ("@openclaw/discord", "Discord"),
    ("@openclaw/slack", "Slack"),
    ("@openclaw/whatsapp", "WhatsApp"),
    ("@openclaw/line", "LINE"),
    ("@openclaw/matrix", "Matrix"),
    ("@openclaw/qqbot", "QQ 机器人"),
    ("@openclaw/signal", "Signal"),
    ("@openclaw/zalo", "Zalo"),
    ("@openclaw/nostr", "Nostr"),
    ("@openclaw/twitch", "Twitch"),
    ("@openclaw/sms", "短信 SMS"),
    ("@openclaw/googlechat", "Google Chat"),
    ("@openclaw/nextcloud-talk", "Nextcloud Talk"),
    ("@openclaw/synology-chat", "Synology Chat"),
    ("@openclaw/clickclack", "ClickClack"),
    ("@openclaw/tlon", "Tlon"),
    ("@openclaw/irc", "IRC"),
]

# 安装前打开的官网（按官网要求：如需登录可先在此登录）
OPENCLAW_DOCS_URL = "https://docs.openclaw.ai"
CLAWHUB_URL = "https://clawhub.com"
OLLAMA_OFFICIAL_URL = "https://ollama.com"

# 技能安装/卸载使用最新官方命令（ClawHub 官方文档：install / uninstall）
SKILL_INSTALL_CMD = "npx clawhub@latest install"
SKILL_UNINSTALL_CMD = "npx clawhub@latest uninstall"
# 多技能连续安装时，每次安装之间的等待秒数，用于降低 npm/ClawHub Rate limit 触发概率
SKILL_INSTALL_DELAY_SEC = 15

# 网页搜索各提供商的 API Key 申请官网
WEB_SEARCH_PROVIDER_API_URLS = {
    "perplexity": "https://www.perplexity.ai/settings/api",
    "brave": "https://brave.com/search/api/",
    "gemini": "https://aistudio.google.com/app/apikey",
    "grok": "https://console.x.ai/",
    "kimi": "https://platform.moonshot.cn/console/api-keys",
}

# 技能安装教程（弹窗内展示）
SKILL_INSTALL_GUIDE = """
一、如何下载
  • 技能通过 ClawHub 安装，无需单独下载安装包。本机需先安装 Node.js（含 npm），以便执行 npx 命令。
  • 下载 Node.js：打开 https://nodejs.org/ ，选择 LTS 版本下载并安装（Windows 运行安装程序，macOS 可用安装包或 Homebrew，Linux 用包管理器如 apt/dnf）。
  • 安装后打开终端，执行 node -v 和 npm -v 确认版本（建议 Node 18+）。

二、如何安装技能
  • 方式一（推荐）：在本程序「技能」页勾选需要的技能，点击「安装选中技能」。程序会先打开 ClawHub 官网，再在系统终端中执行 npx clawhub@latest install <技能名>，将技能安装到当前工作区的 skills 目录。
  • 方式二：在终端中进入工作区目录（本程序「1. 配置一览」中显示的 agents.defaults.workspace），执行：
      npx clawhub@latest install <技能名>
    例如：npx clawhub@latest install evomap
  • 多技能时建议一次只安装一个，或等待程序自动间隔约 15 秒，以避免 npm/ClawHub Rate limit 报错。

三、如何运行
  • 安装技能后，技能文件会出现在工作区的 skills/<技能名>/ 下（含 SKILL.md）。无需单独「运行」技能。
  • 请在本程序保存配置后，启动或重启 OpenClaw 网关（如点击「保存并重启 OpenClaw」或「一键启动 OpenClaw」）。网关启动后，Agent 会自动加载工作区内已安装的技能并在对话中按需调用。

四、如何查看是否正常
  • 本程序「技能」页：已安装的技能会显示「(已安装)」；可点击「刷新列表」同步状态。
  • 文件系统：在工作区目录下查看 skills 文件夹，确认存在对应技能子目录且内含 SKILL.md。
  • 终端验证：在终端执行 openclaw gateway status 确认网关已运行；若需查看日志可执行 openclaw logs --follow，再在对话中触发技能观察是否有相关输出。
  • 实际使用：在 WebChat 或各通道中与 Agent 对话，尝试触发已安装技能（如按技能说明中的关键词或功能），确认 Agent 能正确调用即可。
"""


def run_in_system_terminal(cmd):
    """在系统终端中执行命令，便于交互（如 openclaw onboard）。先加载 nvm 再执行，避免未找到命令；命令结束后等待回车再关闭。"""
    nvm_sh = Path(os.environ.get("NVM_DIR", str(Path.home() / ".nvm"))) / "nvm.sh"
    nvm_load = f'[ -s "{nvm_sh}" ] && . "{nvm_sh}" ; ' if nvm_sh.exists() else ""
    hold = '; echo ""; read -p "按回车键关闭此窗口..." -r'
    cmd_hold = nvm_load + cmd + hold
    if sys.platform == "darwin":
        try:
            esc = cmd_hold.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "bash -lc \\"{esc}\\""'], start_new_session=True)
            return True, "已在 macOS 终端中启动，请在终端内按提示操作。"
        except Exception as e:
            return False, str(e)
    if sys.platform == "win32":
        try:
            subprocess.Popen(["start", "cmd", "/k", cmd], shell=True, start_new_session=True)
            return True, "已在 Windows 命令行中启动，请在窗口内按提示操作。"
        except Exception as e:
            return False, str(e)
    for term_cmd in [
        ["gnome-terminal", "--", "bash", "-lc", cmd_hold],
        ["x-terminal-emulator", "-e", f"bash -lc '{cmd_hold}'"],
        ["konsole", "-e", "bash", "-lc", cmd_hold],
        ["xfce4-terminal", "-e", f"bash -lc '{cmd_hold}'"],
        ["xterm", "-e", f"bash -lc '{cmd_hold}'"],
    ]:
        try:
            subprocess.Popen(term_cmd, start_new_session=True, cwd=os.path.expanduser("~"))
            return True, "已在系统终端中启动，请在终端内按提示交互。"
        except FileNotFoundError:
            continue
        except Exception as e:
            continue
    return False, "未找到可用终端（请尝试安装 gnome-terminal、xterm 或 konsole），或手动在终端执行: " + cmd


def run_openclaw_cmd_sync(cmd, timeout=30):
    """在当前进程同步执行 openclaw 命令（先加载 nvm），返回 (成功, 输出文本)。用于界面内配对批准等。"""
    nvm_sh = Path(os.environ.get("NVM_DIR", str(Path.home() / ".nvm"))) / "nvm.sh"
    nvm_load = f'[ -s "{nvm_sh}" ] && . "{nvm_sh}" ; ' if nvm_sh.exists() else ""
    full = nvm_load + cmd
    try:
        r = subprocess.run(
            ["bash", "-lc", full],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.expanduser("~"),
            env={**os.environ},
        )
        out = (r.stdout or "").strip() + ("\n" + (r.stderr or "").strip() if r.stderr else "")
        if r.returncode != 0:
            return False, out or f"退出码: {r.returncode}"
        return True, out or "执行成功。"
    except subprocess.TimeoutExpired:
        return False, "命令执行超时。"
    except Exception as e:
        return False, str(e)


# 通道页策略下拉：配置值 -> 下拉项显示（含用途说明）
DM_POLICY_DISPLAY = {
    "pairing": "pairing（需验证码配对）",
    "allowlist": "allowlist（仅允许列表中的用户访问）",
    "open": "open（所有人）",
    "disabled": "disabled（忽略 DM）",
}
DM_POLICY_VALUES = list(DM_POLICY_DISPLAY.keys())
DM_POLICY_DISPLAY_LIST = list(DM_POLICY_DISPLAY.values())
DM_POLICY_DISPLAY_TO_VALUE = {v: k for k, v in DM_POLICY_DISPLAY.items()}

GROUP_POLICY_DISPLAY = {
    "allowlist": "allowlist（仅允许列表中的群）",
    "open": "open（所有群）",
    "disabled": "disabled（不收群消息）",
}
GROUP_POLICY_VALUES = list(GROUP_POLICY_DISPLAY.keys())
GROUP_POLICY_DISPLAY_LIST = list(GROUP_POLICY_DISPLAY.values())
GROUP_POLICY_DISPLAY_TO_VALUE = {v: k for k, v in GROUP_POLICY_DISPLAY.items()}


def _policy_display_to_value(display_str, display_to_value_map):
    """将下拉显示文案转回配置值；若已是裸值或未知格式则尽量返回合法值。"""
    s = (display_str or "").strip()
    if s in display_to_value_map:
        return display_to_value_map[s]
    if "（" in s:
        return display_to_value_map.get(s, s.split("（")[0].strip()) or list(display_to_value_map.values())[0]
    return s if s in display_to_value_map.values() else (list(display_to_value_map.values())[0] if display_to_value_map else s)


# 支持配对（pairing）的通道：(openclaw 通道名, 显示名)
PAIRING_CHANNELS = [
    ("telegram", "Telegram"),
    ("discord", "Discord"),
    ("feishu", "飞书 Feishu"),
    ("slack", "Slack"),
]

# 模型/认证提供方：(key, 显示名, 认证方式, 环境变量名, 主模型示例, 获取 Key 的 URL)
# 认证方式: none | api_key | oauth | paste_token | custom
# key 为 _custom 时表示用户自定义厂商，需从 _custom_providers 读取
MODEL_PROVIDERS = [
    # === 本地 / 无需认证 ===
    ("ollama", "Ollama（本地，无需登录）", "none", None, "ollama/llama3.3", None),
    ("vllm", "vLLM（本地推理）", "none", None, "vllm/model-name", "https://docs.openclaw.ai/providers/vllm"),
    # === 国际主流 ===
    ("openai", "OpenAI（GPT-4o 等）", "api_key", "OPENAI_API_KEY", "openai/gpt-4o", "https://platform.openai.com/api-keys"),
    ("openai-codex", "OpenAI Codex（OAuth）", "oauth", None, "openai-codex/gpt-5.3-codex", "https://openclaw.ai"),
    ("anthropic", "Anthropic Claude", "api_key", "ANTHROPIC_API_KEY", "anthropic/claude-sonnet-4-5", "https://console.anthropic.com/settings/keys"),
    ("google", "Google Gemini", "api_key", "GEMINI_API_KEY", "google/gemini-2.0-flash", "https://aistudio.google.com/app/apikey"),
    ("openrouter", "OpenRouter（聚合多模型）", "api_key", "OPENROUTER_API_KEY", "openrouter/anthropic/claude-sonnet-4-5", "https://openrouter.ai/keys"),
    ("groq", "Groq", "api_key", "GROQ_API_KEY", "groq/llama-3.3-70b-versatile", "https://console.groq.com/keys"),
    ("mistral", "Mistral AI", "api_key", "MISTRAL_API_KEY", "mistral/mistral-large-latest", "https://console.mistral.ai/api-keys"),
    ("together", "Together AI", "api_key", "TOGETHER_API_KEY", "together/meta-llama/Llama-3-70b-chat-hf", "https://api.together.xyz/settings/api-keys"),
    ("huggingface", "Hugging Face Inference", "api_key", "HF_TOKEN", "huggingface/meta-llama/Llama-3-70b-chat-hf", "https://huggingface.co/settings/tokens"),
    ("nvidia", "NVIDIA NIM", "api_key", "NIM_API_KEY", "nvidia/llama-3.1-70b-instruct", "https://build.nvidia.com/explore/discover"),
    ("bedrock", "Amazon Bedrock", "api_key", "AWS_ACCESS_KEY_ID", "bedrock/us.anthropic.claude-v2", "https://aws.amazon.com/bedrock"),
    # === 国内 / 区域 ===
    ("moonshot", "Moonshot / Kimi（月之暗面）", "api_key", "MOONSHOT_API_KEY", "moonshot/kimi-k2.5", "https://platform.moonshot.cn/console/api-keys"),
    ("glm", "智谱 GLM（ChatGLM）", "api_key", "ZHIPU_API_KEY", "glm/glm-4-flash", "https://open.bigmodel.cn/usercenter/apikeys"),
    ("qianfan", "百度千帆", "api_key", "QIANFAN_ACCESS_KEY", "qianfan/ernie-bot-4", "https://console.bce.baidu.com/qianfan/ais/console/applicationConsole/application"),
    ("qwen", "通义千问 Qwen（OAuth）", "oauth", None, "qwen/qwen-max", "https://openclaw.ai"),
    ("minimax", "MiniMax（海螺 AI）", "api_key", "MINIMAX_API_KEY", "minimax/abab6.5s-chat", "https://platform.minimax.cn/"),
    ("zai", "Z.AI", "api_key", "ZAI_API_KEY", "zai/model-name", "https://docs.openclaw.ai/providers/zai"),
    ("xiaomi", "小米 MiMo", "api_key", "XIAOMI_API_KEY", "xiaomi/model-name", "https://docs.openclaw.ai/providers/xiaomi"),
    # === 网关 / 代理 ===
    ("litellm", "LiteLLM（统一网关）", "api_key", "LITELLM_API_KEY", "litellm/provider/model", "https://docs.litellm.ai/docs/proxy/custom_auth"),
    ("vercel-ai-gateway", "Vercel AI Gateway", "api_key", "VERCEL_AI_GATEWAY_API_KEY", "vercel-ai-gateway/model", "https://sdk.vercel.ai/providers/ai-sdk-providers"),
    ("cloudflare-ai-gateway", "Cloudflare AI Gateway", "api_key", "CLOUDFLARE_AI_GATEWAY_API_KEY", "cloudflare-ai-gateway/model", "https://developers.cloudflare.com/ai-gateway"),
    ("venice", "Venice AI（隐私优先）", "api_key", "VENICE_API_KEY", "venice/model-name", "https://docs.openclaw.ai/providers/venice"),
    ("opencode", "OpenCode（Zen + Go）", "oauth", None, "opencode/claude-opus-4-6", "https://openclaw.ai"),
    ("github-copilot", "GitHub Copilot", "oauth", None, "github-copilot/model", "https://github.com/settings/copilot"),
    # === 自定义厂商（Cherry Studio 风格：支持用户添加任意厂商）===
    ("_custom", "➕ 自定义厂商（Custom Provider）", "custom", None, "custom/model-name", None),
]

# Ollama 推荐模型（全量）：(名称, 约大小, 硬件建议) — 来自 ollama.com/library
OLLAMA_RECOMMENDED = [
    ("llama3.1", "~4.7GB", "推荐 8GB+ 显存"),
    ("deepseek-r1", "多规格", "推理强，7B/70B 等"),
    ("llama3.2", "~2GB", "推荐 8GB+ 显存"),
    ("nomic-embed-text", "~274MB", "嵌入模型，低显存"),
    ("gemma3", "多规格", "Google，多尺寸"),
    ("mistral", "~4.1GB", "推荐 8GB+ 显存"),
    ("qwen2.5", "~1.5GB", "推荐 6GB+ 显存"),
    ("qwen3", "多规格", "阿里，多尺寸"),
    ("llama3", "~4.7GB", "推荐 8GB+ 显存"),
    ("gemma2", "~2.6GB", "推荐 6GB+ 显存"),
    ("phi3", "~1.6GB", "轻量，4GB+ 即可"),
    ("llava", "~4.5GB", "多模态视觉，8GB+ 显存"),
    ("qwen2.5-coder", "~1.5GB", "编程，6GB+ 显存"),
    ("mxbai-embed-large", "~670MB", "嵌入模型"),
    ("gpt-oss", "多规格", "开源对话"),
    ("phi4", "多规格", "推理，多尺寸"),
    ("gemma", "~2.6GB", "轻量"),
    ("qwen", "多规格", "阿里通用"),
    ("llama2", "~3.8GB", "经典 7B"),
    ("qwen2", "多规格", "阿里"),
    ("minicpm-v", "多规格", "视觉多模态"),
    ("codellama", "~3.8GB", "编程，8GB+ 显存"),
    ("llama3.2-vision", "多规格", "视觉"),
    ("tinyllama", "~637MB", "极低显存/CPU"),
    ("dolphin3", "多规格", "对话"),
    ("deepseek-v3", "多规格", "深度求索"),
    ("olmo2", "多规格", "开源"),
    ("mistral-nemo", "多规格", "Mistral"),
    ("bge-m3", "~670MB", "嵌入"),
    ("qwen3-coder", "多规格", "编程"),
    ("llama3.3", "~2GB", "推荐 8GB+ 显存"),
    ("deepseek-coder", "多规格", "编程"),
    ("smollm2", "多规格", "小模型"),
    ("all-minilm", "~90MB", "嵌入"),
    ("mistral-small", "多规格", "小尺寸"),
    ("codegemma", "多规格", "编程"),
    ("granite3.1-moe", "多规格", "IBM MoE"),
    ("snowflake-arctic-embed", "嵌入", "Snowflake"),
    ("falcon3", "多规格", "TII"),
    ("starcoder2", "多规格", "编程"),
    ("llava-llama3", "多规格", "视觉"),
    ("orca-mini", "多规格", "对话"),
    ("qwq", "多规格", "QwQ"),
    ("mixtral", "~26GB", "MoE，24GB+ 显存"),
    ("qwen3-vl", "多规格", "视觉语言"),
    ("llama2-uncensored", "多规格", "无审查"),
    ("deepseek-coder-v2", "多规格", "编程"),
    ("cogito", "多规格", "推理"),
    ("qwen2.5vl", "多规格", "视觉语言"),
    ("mistral-small3.2", "多规格", "Mistral"),
    ("gemma3n", "多规格", "Gemma"),
    ("llama4", "多规格", "Meta"),
    ("phi4-reasoning", "多规格", "推理"),
    ("dolphin-phi", "多规格", "Dolphin"),
    ("magistral", "多规格", "对话"),
    ("qwen3-embedding", "多规格", "嵌入"),
    ("deepscaler", "多规格", "代码"),
    ("dolphin-llama3", "多规格", "Dolphin"),
    ("dolphin-mixtral", "多规格", "Dolphin"),
    ("phi", "多规格", "微软"),
    ("smollm", "多规格", "小模型"),
    ("qwen3.5", "多规格", "阿里"),
    ("lfm2.5-thinking", "多规格", "推理"),
    ("phi4-mini", "多规格", "轻量推理"),
    ("lfm2", "多规格", "LFM"),
    ("granite3.3", "多规格", "IBM"),
    ("codestral", "多规格", "Mistral 编程"),
    ("openthinker", "多规格", "推理"),
    ("dolphin-mistral", "多规格", "Dolphin"),
    ("devstral", "多规格", "编程"),
    ("granite3.2-vision", "多规格", "IBM 视觉"),
    ("granite4", "多规格", "IBM"),
    ("command-r", "多规格", "Cohere"),
    ("qwen3-coder-next", "多规格", "编程"),
    ("granite-code", "多规格", "IBM 编程"),
    ("wizardlm2", "多规格", "对话"),
    ("moondream", "多规格", "视觉"),
    ("hermes3", "多规格", "Nous"),
    ("deepcoder", "多规格", "编程"),
    ("yi", "多规格", "零一"),
    ("mistral-small3.1", "多规格", "Mistral"),
    ("zephyr", "多规格", "HuggingFace"),
    ("mistral-large", "多规格", "Mistral 大模型"),
    ("wizard-vicuna-uncensored", "多规格", "无审查"),
    ("phi3.5", "多规格", "推理"),
    ("embeddinggemma", "~300MB", "嵌入"),
    ("paraphrase-multilingual", "多规格", "多语言嵌入"),
    ("starcoder", "多规格", "编程"),
    ("nous-hermes", "多规格", "Nous"),
    ("deepseek-llm", "多规格", "深度求索"),
    ("deepseek-v2", "多规格", "深度求索"),
    ("falcon", "多规格", "TII"),
    ("translategemma", "多规格", "翻译"),
    ("openchat", "多规格", "对话"),
    ("vicuna", "多规格", "对话"),
    ("glm4", "多规格", "智谱"),
    ("exaone-deep", "多规格", "LG 深度"),
    ("openhermes", "多规格", "Nous"),
    ("stable-code", "多规格", "编程"),
    ("llama2-chinese", "多规格", "中文"),
    ("neural-chat", "多规格", "对话"),
    ("nous-hermes2", "多规格", "Nous"),
    ("sqlcoder", "多规格", "SQL"),
    ("wizardcoder", "多规格", "编程"),
    ("yi-coder", "多规格", "编程"),
    ("stablelm2", "多规格", "Stability"),
    ("llama3-chatqa", "多规格", "问答"),
    ("granite3-dense", "多规格", "IBM"),
    ("granite3.1-dense", "多规格", "IBM"),
    ("dolphincoder", "多规格", "编程"),
    ("wizard-math", "多规格", "数学"),
    ("opencoder", "多规格", "编程"),
    ("llama3-gradient", "多规格", "长上下文"),
    ("samantha-mistral", "多规格", "对话"),
    ("internlm2", "多规格", "上海 AI"),
    ("llama3-groq-tool-use", "多规格", "工具调用"),
    ("llama-guard3", "多规格", "安全"),
    ("starling-lm", "多规格", "对话"),
    ("phind-codellama", "多规格", "编程"),
    ("solar", "多规格", "对话"),
    ("deepseek-v3.1", "多规格", "深度求索"),
    ("xwinlm", "多规格", "对话"),
    ("aya-expanse", "多规格", "多语言"),
    ("aya", "多规格", "Cohere 多语言"),
    ("command-r-plus", "多规格", "Cohere"),
    ("granite3-moe", "多规格", "IBM MoE"),
    ("yarn-llama2", "多规格", "长上下文"),
    ("stable-beluga", "多规格", "对话"),
    ("reader-lm", "多规格", "阅读"),
    ("tinydolphin", "多规格", "轻量"),
    ("codegeex4", "多规格", "编程"),
    ("shieldgemma", "多规格", "安全"),
    ("mistral-openorca", "多规格", "对话"),
    ("llama-pro", "多规格", "Meta"),
    ("yarn-mistral", "多规格", "长上下文"),
    ("nexusraven", "多规格", "函数调用"),
    ("wizardlm", "多规格", "对话"),
    ("qwen3-next", "多规格", "阿里"),
    ("devstral-small-2", "多规格", "编程小模型"),
    ("rnj-1", "多规格", "Essential AI"),
    ("meditron", "多规格", "医疗"),
    ("deepseek-ocr", "多规格", "OCR 视觉"),
    ("reflection", "多规格", "推理"),
    ("nemotron-mini", "多规格", "NVIDIA"),
    ("wizardlm-uncensored", "多规格", "无审查"),
    ("nemotron", "多规格", "NVIDIA"),
    ("athene-v2", "多规格", "编程"),
    ("granite3.2", "多规格", "IBM"),
    ("exaone3.5", "多规格", "LG"),
    ("r1-1776", "多规格", "Perplexity"),
    ("everythinglm", "多规格", "无审查"),
    ("mathstral", "多规格", "数学"),
    ("solar-pro", "多规格", "对话"),
    ("magicoder", "多规格", "编程"),
    ("megadolphin", "多规格", "大模型"),
    ("falcon2", "多规格", "TII"),
    ("stablelm-zephyr", "多规格", "对话"),
    ("duckdb-nsql", "多规格", "SQL"),
    ("nuextract", "多规格", "抽取"),
    ("mistrallite", "多规格", "长上下文"),
    ("bespoke-minicheck", "多规格", "事实核查"),
    ("notux", "多规格", "MoE"),
    ("notus", "多规格", "对话"),
    ("wizard-vicuna", "多规格", "对话"),
    ("firefunction-v2", "多规格", "函数调用"),
    ("codebooga", "多规格", "编程"),
    ("open-orca-platypus2", "多规格", "对话"),
    ("granite-embedding", "多规格", "嵌入"),
    ("tulu3", "多规格", "Allen AI"),
    ("goliath", "多规格", "大模型"),
    ("llava-phi3", "多规格", "视觉"),
    ("bge-large", "多规格", "嵌入"),
    ("dbrx", "多规格", "Databricks"),
    ("nemotron-3-nano", "多规格", "NVIDIA"),
    ("olmo-3", "多规格", "Allen AI"),
    ("sailor2", "多规格", "多语言"),
    ("command-r7b", "多规格", "Cohere 7B"),
    ("deepseek-v2.5", "多规格", "深度求索"),
    ("phi4-mini-reasoning", "多规格", "轻量推理"),
    ("smallthinker", "多规格", "推理"),
    ("granite3-guardian", "多规格", "安全"),
    ("command-a", "多规格", "Cohere"),
    ("kimi-k2.5", "多规格", "月之暗面 多模态"),
    ("marco-o1", "多规格", "阿里推理"),
    ("alfred", "多规格", "对话"),
    ("olmo-3.1", "多规格", "Allen AI"),
    ("devstral-2", "多规格", "编程"),
    ("minimax-m2.5", "多规格", "MiniMax"),
    ("command-r7b-arabic", "多规格", "阿拉伯语"),
    ("glm-5", "多规格", "智谱"),
    ("cogito-2.1", "多规格", "推理"),
    ("functiongemma", "多规格", "函数调用"),
    ("gpt-oss-safeguard", "多规格", "安全"),
    ("nomic-embed-text-v2-moe", "多规格", "嵌入 MoE"),
    ("glm-4.6", "多规格", "智谱"),
    ("gemini-3-flash-preview", "多规格", "Google"),
    ("minimax-m2", "多规格", "MiniMax"),
    ("glm-ocr", "多规格", "智谱 OCR"),
    ("glm-4.7", "多规格", "智谱"),
    ("kimi-k2", "多规格", "月之暗面"),
    ("deepseek-v3.2", "多规格", "深度求索"),
    ("kimi-k2-thinking", "多规格", "月之暗面 推理"),
    ("mistral-large-3", "多规格", "Mistral"),
    ("minimax-m2.1", "多规格", "MiniMax"),
]
OLLAMA_PAGE_SIZE = 10
# 多规格模型可选标签（ollama pull <model>:<tag>；留空或「默认」拉取默认标签）
OLLAMA_TAG_OPTIONS = ["默认", "latest", "3b", "7b", "8b", "13b", "70b", "small", "medium", "large", "vision", "code", "instruct"]


def _format_size(bytes_val):
    """将字节数格式化为可读字符串（如 1.5 GB）。"""
    if not bytes_val:
        return "—"
    for u, s in [(1e12, "TB"), (1e9, "GB"), (1e6, "MB"), (1e3, "KB")]:
        if bytes_val >= u:
            return f"{bytes_val / u:.1f} {s}"
    return f"{bytes_val} B"


def _ollama_vram_hint_from_bytes(bytes_val):
    """根据模型体积（字节）估算推荐显存，用于已安装模型的帮助提示。"""
    if not bytes_val or bytes_val <= 0:
        return "视规格而定"
    gb = bytes_val / (1024 ** 3)
    if gb < 1.5:
        return "约 4GB+ 显存（或 CPU 可跑）"
    if gb < 4:
        return "约 6GB+ 显存"
    if gb < 10:
        return "约 8GB+ 显存"
    if gb < 20:
        return "约 12GB+ 显存"
    if gb < 40:
        return "约 16GB～24GB 显存"
    return "建议 24GB+ 显存"


def _ollama_installed_model_tooltip(name, size_bytes):
    """已安装模型行的帮助提示文案：大小、推荐显存、使用建议。"""
    size_str = _format_size(size_bytes)
    vram = _ollama_vram_hint_from_bytes(size_bytes)
    lines = [
        f"模型: {name}",
        f"占用空间: {size_str}",
        f"推荐显存: {vram}",
        "",
        "使用建议: 显存不足时可关闭其他占用 GPU 的程序，或选择更小规格；首次使用建议在主模型处填写 ollama/模型名。",
    ]
    return "\n".join(lines)


def _ollama_recommended_model_tooltip(name, size_desc, hw):
    """推荐模型行的帮助提示文案：约大小、硬件建议、使用建议。"""
    lines = [
        f"模型: {name}",
        f"约大小: {size_desc or '—'}",
        f"硬件建议: {hw or '—'}",
        "",
        "使用建议: 多规格模型可先安装小规格（如 3b/7b）试跑；嵌入模型用于 RAG/检索；大模型（如 70B）需 24GB+ 显存。",
    ]
    return "\n".join(lines)


def get_ollama_installed_models():
    """通过 Ollama 本地 API 获取已安装模型列表（名称、大小）。返回 [(name, size_bytes), ...]，失败返回 []。"""
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        out = []
        for m in (data.get("models") or []):
            name = (m.get("name") or "").strip()
            if not name:
                continue
            size = m.get("size") or 0
            out.append((name, size))
        return out
    except Exception:
        return []


def load_config():
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"_load_error": str(e)}


def save_config(config):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                old = f.read()
            with open(CONFIG_BACKUP, "w", encoding="utf-8") as f:
                f.write(old)
        except Exception:
            pass
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return True


def load_custom_providers():
    """加载用户自定义的模型厂商列表（Cherry Studio 风格）。"""
    if not CUSTOM_PROVIDERS_FILE.exists():
        return []
    try:
        with open(CUSTOM_PROVIDERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_custom_providers(providers):
    """保存用户自定义的模型厂商列表。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CUSTOM_PROVIDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(providers, f, ensure_ascii=False, indent=2)


def deep_merge(base, override):
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def restart_openclaw(port=None):
    if port is None:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            port = int((cfg.get("gateway") or {}).get("port", 18789))
        except Exception:
            port = 18789
    nvm_sh = Path(os.environ.get("NVM_DIR", str(Path.home() / ".nvm"))) / "nvm.sh"
    cmd = f'[ -s "{nvm_sh}" ] && . "{nvm_sh}" && openclaw gateway --port {port}' if nvm_sh.exists() else f"openclaw gateway --port {port}"
    for name in ("openclaw", "openclaw-gateway"):
        try:
            r = subprocess.run(["systemctl", "--user", "restart", name], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                return True, f"已通过 systemd 重启服务: {name}"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    try:
        subprocess.run(["pkill", "-f", "openclaw-gateway"], capture_output=True, timeout=5)
    except Exception:
        pass
    try:
        subprocess.Popen(["bash", "-lc", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, cwd=str(Path.home()))
        return True, "已后台启动 OpenClaw 网关"
    except Exception as e:
        return False, str(e)


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind("<Enter>", self.show)
        self.widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if not self.text:
            return
        if self.tip_window:
            return
        x, y, _, _ = self.widget.bbox("insert") if self.widget.winfo_class() == "Text" else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 20
        y += self.widget.winfo_rooty() + 20
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        lb = tk.Label(tw, text=self.text, justify=tk.LEFT, background="#ffffcc", relief=tk.SOLID, borderwidth=1, font=("", 9), wraplength=320)
        lb.pack()

    def hide(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


def make_scrollable_tab(notebook, title, scroll_canvases):
    """创建带垂直滚动的标签页，返回 (内层 Frame, 用于放表单内容)。scroll_canvases 用于收集 canvas 以便全局滚轮绑定。"""
    outer = ttk.Frame(notebook)
    notebook.add(outer, text=title)
    canvas = tk.Canvas(outer, highlightthickness=0)
    scroll_canvases.append(canvas)
    vbar = ttk.Scrollbar(outer)
    inner = ttk.Frame(canvas, padding=16)
    inner_id = canvas.create_window(0, 0, window=inner, anchor=tk.NW)

    def _on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_configure(event):
        canvas.itemconfig(inner_id, width=event.width)

    inner.bind("<Configure>", _on_frame_configure)
    canvas.bind("<Configure>", _on_canvas_configure)

    vbar.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    canvas.configure(yscrollcommand=vbar.set)
    vbar.configure(command=canvas.yview)
    return inner


def make_scrollable_tab_inside(parent_frame, scroll_canvases, padding=20):
    """在给定父容器内创建带垂直滚动的区域（用于 CTkTabview 的 tab 内容），返回内层 Frame。"""
    canvas = tk.Canvas(parent_frame, highlightthickness=0)
    scroll_canvases.append(canvas)
    vbar = ttk.Scrollbar(parent_frame)
    inner = ttk.Frame(canvas, padding=padding)
    inner_id = canvas.create_window(0, 0, window=inner, anchor=tk.NW)

    def _on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_configure(event):
        canvas.itemconfig(inner_id, width=event.width)

    inner.bind("<Configure>", _on_frame_configure)
    canvas.bind("<Configure>", _on_canvas_configure)

    vbar.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    canvas.configure(yscrollcommand=vbar.set)
    vbar.configure(command=canvas.yview)
    return inner


def _bilingual(label_text, hint_key):
    """标签双语化：中文在前，英文(取 hint_key 末段)在后 → 「中文 (english)」。
    若中文里已含该英文词则不重复。"""
    eng = (hint_key or "").split(".")[-1]
    if eng and eng.lower() not in (label_text or "").lower():
        return f"{label_text} ({eng})"
    return label_text


def add_label_with_hint(parent, row, label_text, hint_key, column=0):
    """在 parent 的 (row, column) 放标签，带 (?) 悬停说明。控件应放在 (row, column+1)。
    标签统一双语「中文 (english)」。"""
    f = _gui_frame(parent)
    f.grid(row=row, column=column, sticky=tk.W, pady=2)
    lb = _gui_label(f, text=_bilingual(label_text, hint_key))
    lb.pack(side=tk.LEFT)
    hint = PARAM_HINTS.get(hint_key, "")
    if hint:
        info = _gui_label(f, text=" (?)", foreground="gray")
        info.pack(side=tk.LEFT)
        ToolTip(info, hint)
        ToolTip(lb, hint)
    return f


# ============================================================================
# Schema 驱动的「更多」渐进披露：读 `openclaw config schema`(draft-07)，按域递归渲染
# 全部字段 → 「重要项先显示、更多可无穷配置」。标签统一「中文(title) (englishKey)」。
# ============================================================================
_OC_SCHEMA_CACHE = {"data": None, "tried": False}


def load_oc_schema():
    """惰性加载 openclaw 完整 config schema。失败返回 None（「更多」按钮则不显示）。"""
    if _OC_SCHEMA_CACHE["tried"]:
        return _OC_SCHEMA_CACHE["data"]
    _OC_SCHEMA_CACHE["tried"] = True
    try:
        out = subprocess.run(["openclaw", "config", "schema"],
                             capture_output=True, text=True, timeout=40)
        if out.returncode == 0 and out.stdout.strip():
            _OC_SCHEMA_CACHE["data"] = json.loads(out.stdout)
    except Exception:
        _OC_SCHEMA_CACHE["data"] = None
    return _OC_SCHEMA_CACHE["data"]


def schema_node_at(prefix):
    """取 schema 中某点路径(dotted)对应的节点。prefix='' 取根。"""
    node = load_oc_schema()
    if not isinstance(node, dict):
        return None
    if prefix:
        for seg in prefix.split("."):
            props = node.get("properties") if isinstance(node, dict) else None
            if not isinstance(props, dict) or seg not in props:
                return None
            node = props[seg]
    return node


def _cfg_get_path(config, dotted):
    cur = config
    for seg in dotted.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return None
    return cur


def _patch_set_path(patch, dotted, value):
    cur = patch
    segs = dotted.split(".")
    for seg in segs[:-1]:
        nxt = cur.get(seg)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[seg] = nxt
        cur = nxt
    cur[segs[-1]] = value


def _schema_type(node):
    t = node.get("type") if isinstance(node, dict) else None
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), (t[0] if t else None))
    return t


def _is_secret_key(key):
    return any(s in key.lower() for s in ("token", "secret", "password", "apikey", "privatekey"))


# 各通道「申请地址/接入文档」——渲染 channels.<名> 时置顶显示可点链接（穷举 apiKey 之外的申请信息）
CHANNEL_APPLY_URLS = {
    "telegram": ("向 @BotFather 申请 Bot Token", "https://t.me/BotFather"),
    "discord": ("Discord 开发者门户建应用取 Token", "https://discord.com/developers/applications"),
    "slack": ("Slack 应用管理(取 Bot/App Token)", "https://api.slack.com/apps"),
    "feishu": ("飞书开放平台建应用取 App ID/Secret", "https://open.feishu.cn/app"),
    "line": ("LINE Developers Console(Channel Token/Secret)", "https://developers.line.biz/console/"),
    "matrix": ("Matrix：注册账号取 Access Token", "https://matrix.org/"),
    "mattermost": ("Mattermost 系统控制台建 Bot 取 Token", "https://developers.mattermost.com/integrate/reference/bot-accounts/"),
    "msteams": ("Azure 门户建 Bot 取 App ID/Password", "https://portal.azure.com/"),
    "qqbot": ("QQ 开放平台建机器人取 AppID/Secret", "https://q.qq.com/"),
    "whatsapp": ("WhatsApp：openclaw channels login 扫码链接设备", "https://faq.whatsapp.com/"),
    "twitch": ("Twitch 开发者控制台建应用(OAuth)", "https://dev.twitch.tv/console"),
    "sms": ("Twilio 控制台取 Auth Token", "https://www.twilio.com/console"),
    "googlechat": ("Google Cloud 建服务账号/Webhook", "https://console.cloud.google.com/"),
    "zalo": ("Zalo 开发者平台建 OA 取 Token", "https://developers.zalo.me/"),
    "nostr": ("Nostr：生成 nsec 私钥即可(客户端/openclaw)", "https://nostr.com/"),
    "signal": ("Signal：用 signal-cli 链接设备(无需 Token)", "https://github.com/AsamK/signal-cli"),
    "synology-chat": ("Synology Chat 集成里建 Incoming/Outgoing Webhook", "https://www.synology.com/"),
    "nextcloud-talk": ("Nextcloud 管理里建 Talk Bot 取 Secret", "https://nextcloud.com/talk/"),
    "irc": ("IRC：按所连网络注册(如 Libera.Chat)", "https://libera.chat/"),
    "imessage": ("iMessage：需 macOS 或 BlueBubbles 服务端", "https://bluebubbles.app/"),
}


# 常见配置键的中文名（「更多」双语标签用；未命中回退 schema title/key）
_ZH_FIELD = {
    "enabled": "启用", "disabled": "禁用", "mode": "模式", "type": "类型", "name": "名称",
    "port": "端口", "host": "主机", "bind": "绑定", "path": "路径", "url": "地址", "profile": "配置档",
    "token": "令牌", "botToken": "机器人令牌", "userToken": "用户令牌", "appToken": "应用令牌",
    "tokenFile": "令牌文件", "apiKey": "API 密钥", "apiPassword": "API 密码", "apiPasswordFile": "API 密码文件",
    "appId": "应用 ID", "appSecret": "应用密钥", "appPassword": "应用密码", "clientSecret": "客户端密钥",
    "clientSecretFile": "客户端密钥文件", "secret": "密钥", "password": "密码", "passwordFile": "密码文件",
    "signingSecret": "签名密钥", "encryptKey": "加密密钥", "verificationToken": "验证令牌",
    "accessToken": "访问令牌", "channelAccessToken": "频道访问令牌", "channelSecret": "频道密钥",
    "secretFile": "密钥文件", "privateKey": "私钥", "botSecret": "机器人密钥", "botSecretFile": "机器人密钥文件",
    "authToken": "认证令牌", "managedIdentityClientId": "托管标识客户端 ID",
    "webhook": "Webhook", "webhookUrl": "Webhook 地址", "webhookPath": "Webhook 路径",
    "webhookHost": "Webhook 主机", "webhookPort": "Webhook 端口", "webhookSecret": "Webhook 密钥",
    "webhookCertPath": "Webhook 证书路径", "webhookPublicUrl": "Webhook 公网地址", "publicWebhookUrl": "公网 Webhook 地址",
    "dmPolicy": "私信策略", "groupPolicy": "群组策略", "allowFrom": "允许来源", "allowlist": "白名单",
    "model": "模型", "primary": "主模型", "fast": "快速模型", "provider": "提供商", "workspace": "工作区",
    "timeout": "超时", "timeoutMs": "超时(毫秒)", "auth": "认证", "reload": "热重载", "tailscale": "Tailscale",
    "tls": "TLS", "http": "HTTP", "controlUi": "控制界面", "trustedProxies": "受信任代理",
    "customBindHost": "自定义绑定主机", "nodes": "节点", "remote": "远程", "push": "推送",
    "search": "搜索", "web": "网页", "defaults": "默认值", "pairing": "配对", "channels": "通道",
    "gateway": "网关", "agents": "智能体", "tools": "工具", "session": "会话", "commands": "命令",
    "restart": "重启", "config": "配置", "text": "文本", "native": "原生", "logging": "日志",
}


def _zh_label(key, sub):
    """双语标签「中文 (englishKey)」：中文优先取 _ZH_FIELD，回退 schema title，再回退 key。"""
    zh = _ZH_FIELD.get(key)
    if not zh and isinstance(sub, dict):
        zh = sub.get("title")
    return "%s (%s)" % (zh or key, key)


def render_schema_fields(parent, node, prefix, config, vars_store, skip=None, depth=0):
    """递归渲染 node.properties 下全部字段。bool→复选框, enum→下拉, number→输入框,
    object→子框递归, array→JSON 输入框。变量注册到 vars_store[path]=(var, kind)。
    skip: 已在重要项显示过的 dotted 路径集合。标签「中文(title) (key)」。返回字段数。"""
    skip = skip or set()
    props = node.get("properties") if isinstance(node, dict) else None
    if not isinstance(props, dict):
        return 0
    count = 0
    for key, sub in props.items():
        if key.startswith("$") or not isinstance(sub, dict):
            continue
        path = f"{prefix}.{key}" if prefix else key
        if path in skip or path in vars_store:
            continue
        st = _schema_type(sub)
        label = _zh_label(key, sub)
        cur = _cfg_get_path(config, path)
        if st == "object" and isinstance(sub.get("properties"), dict):
            # 懒展开折叠块：点击标题才渲染子级。关键——避免一次性绘制上千控件触发
            # X Server BadAlloc(X_CreatePixmap) 导致进程崩溃、窗口消失。
            container = _gui_frame(parent)
            container.pack(fill=tk.X, anchor="w", pady=1, padx=(depth * 8, 0))
            head = _gui_frame(container)
            head.pack(fill=tk.X, anchor="w")
            body = _gui_frame(container)  # 子级容器：父为 container，pack 后恒在 head 之后
            tbtn = _gui_button(head, "▸ " + label)
            tbtn.pack(side=tk.LEFT)
            if prefix == "channels" and key in CHANNEL_APPLY_URLS:
                desc, url = CHANNEL_APPLY_URLS[key]
                _gui_label(head, text="  申请：" + desc + " ").pack(side=tk.LEFT)
                _gui_link(head, "打开 →", (lambda u=url: open_url(u))).pack(side=tk.LEFT)
            st_o = {"open": False, "done": False}

            def _toggle(nd=sub, p=path, bd=body, s=st_o, bt=tbtn, lb2=label):
                if not s["done"]:
                    render_schema_fields(bd, nd, p, config, vars_store, skip, depth + 1)
                    s["done"] = True
                s["open"] = not s["open"]
                if s["open"]:
                    bd.pack(fill=tk.X, anchor="w")
                    bt.configure(text="▾ " + lb2)
                else:
                    bd.pack_forget()
                    bt.configure(text="▸ " + lb2)

            tbtn.configure(command=_toggle)
            count += 1
            continue
        row = _gui_frame(parent)
        row.pack(fill=tk.X, anchor="w", pady=1)
        lb = _gui_label(row, text=label)
        lb.pack(side=tk.LEFT)
        hint = sub.get("description") or PARAM_HINTS.get(path, "")
        enum = sub.get("enum")
        if st == "boolean":
            var = tk.BooleanVar(value=bool(cur) if cur is not None else bool(sub.get("default", False)))
            _gui_checkbox(row, "", var).pack(side=tk.LEFT)
            vars_store[path] = (var, "bool")
        elif enum:
            var = tk.StringVar(value=(str(cur) if cur is not None else str(sub.get("default", ""))))
            _gui_combobox(row, var, [str(x) for x in enum], width_chars=16).pack(side=tk.LEFT)
            vars_store[path] = (var, "enum")
        elif st in ("number", "integer"):
            var = tk.StringVar(value=(str(cur) if cur is not None else ""))
            _gui_entry(row, textvariable=var, width_chars=16).pack(side=tk.LEFT)
            vars_store[path] = (var, "int" if st == "integer" else "num")
        elif st == "array":
            var = tk.StringVar(value=(json.dumps(cur, ensure_ascii=False) if cur is not None else ""))
            _gui_entry(row, textvariable=var, width_chars=30).pack(side=tk.LEFT)
            _gui_label(row, text=" (JSON)", foreground="gray").pack(side=tk.LEFT)
            vars_store[path] = (var, "json")
        else:
            show = "*" if _is_secret_key(key) else None
            var = tk.StringVar(value=(str(cur) if cur is not None else ""))
            _gui_entry(row, textvariable=var, width_chars=30, show=show).pack(side=tk.LEFT)
            vars_store[path] = (var, "str")
        if hint:
            info = _gui_label(row, text=" (?)", foreground="gray")
            info.pack(side=tk.LEFT)
            ToolTip(info, hint)
        count += 1
    return count


def _is_widget_inside(w, top):
    """判断控件 w 是否在 top 窗口内（即 top 或其子控件）。"""
    while w:
        if w == top:
            return True
        try:
            w = w.master
        except Exception:
            break
    return False


def make_action_dropdown(parent, button_text, items, width=14):
    """用「按钮 + Toplevel 内一排按钮」实现下拉；鼠标移出或点击外部自动关闭，符合常见下拉菜单行为。"""
    frame = _gui_frame(parent)

    def _show_popup(e):
        root_win = frame.winfo_toplevel()
        pop = ctk.CTkToplevel(frame) if ctk else tk.Toplevel(frame)
        pop.wm_overrideredirect(True)
        inner = _gui_frame(pop)
        inner.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        for label, cmd in items:
            def _run(c=cmd):
                try:
                    c()
                finally:
                    if pop.winfo_exists():
                        _dismiss()
            _gui_button(inner, text=label, command=_run).pack(fill=tk.X, pady=1)
        pop.update_idletasks()
        x, y = e.x_root, e.y_root
        h = inner.winfo_reqheight()
        if y + h + 10 > pop.winfo_screenheight():
            y = max(0, y - h - 10)
        pop.wm_geometry("+%d+%d" % (x, y))

        bind_id = [None]  # 用列表以便在闭包中赋值

        leave_after_id = [None]

        def _dismiss():
            if pop.winfo_exists():
                pop.destroy()
            if bind_id[0] is not None:
                try:
                    root_win.unbind("<Button-1>", bind_id[0])
                except Exception:
                    pass
            if leave_after_id[0] is not None:
                try:
                    root_win.after_cancel(leave_after_id[0])
                except Exception:
                    pass

        def _schedule_close_on_leave():
            """鼠标离开弹窗区域后延迟检查，仍在窗外则关闭（避免从子控件移动时误关）。"""
            if leave_after_id[0] is not None:
                try:
                    root_win.after_cancel(leave_after_id[0])
                except Exception:
                    pass
            def _check():
                leave_after_id[0] = None
                if not pop.winfo_exists():
                    return
                try:
                    mx, my = root_win.winfo_pointerxy()
                    px, py = pop.winfo_rootx(), pop.winfo_rooty()
                    pw, ph = pop.winfo_width(), pop.winfo_height()
                    if mx < px or mx > px + pw or my < py or my > py + ph:
                        _dismiss()
                except Exception:
                    pass
            leave_after_id[0] = root_win.after(120, _check)

        def _on_root_click(ev):
            if pop.winfo_exists() and not _is_widget_inside(ev.widget, pop):
                _dismiss()

        pop.bind("<Escape>", lambda _: _dismiss())
        pop.bind("<Leave>", lambda _: _schedule_close_on_leave())
        inner.bind("<Leave>", lambda _: _schedule_close_on_leave())
        for child in inner.winfo_children():
            child.bind("<Leave>", lambda _: _schedule_close_on_leave())
        bind_id[0] = root_win.bind("<Button-1>", _on_root_click, add="+")

    btn = _gui_button(frame, text=button_text)
    btn.bind("<Button-1>", _show_popup)
    btn.pack(side=tk.LEFT, padx=2)
    return frame


class OpenClawConfigApp:
    def __init__(self):
        if ctk is not None:
            # 主窗口使用 CustomTkinter 的 CTk 窗口，统一背景与主题
            try:
                ctk.set_appearance_mode("system")  # dark / light / system
                ctk.set_default_color_theme("blue")
            except Exception:
                pass
            # 使用 CTk 默认的窗口背景色（浅色/深色自适应），使整窗为 CTk 风格
            self.root = ctk.CTk(fg_color=("gray95", "gray14"))
        else:
            self.root = tk.Tk()
            try:
                style = ttk.Style(self.root)
                if style.theme_use():
                    style.theme_use("clam")  # 无 ctk 时用 clam 主题稍作美化
            except Exception:
                pass
        self.root.title("OpenClaw 配置 — 完整引导")
        self.root.minsize(720, 560)
        self.root.geometry("960x680")

        self.config = load_config()
        if isinstance(self.config, dict) and self.config.get("_load_error"):
            msg = self.config.pop("_load_error", "")
            messagebox.showwarning("加载配置", f"读取配置时出错，将使用空配置。\n{msg}")

        self.vars = {}
        self._schema_vars = {}  # 「更多」schema 驱动字段：dotted path -> (var, kind)
        self.scroll_canvases = []
        self._custom_providers = load_custom_providers()  # Cherry Studio 风格：自定义厂商列表
        self.build_ui()
        self._start_singleton_listener()

    def _bring_to_front(self):
        """将主窗口置于前台并获取焦点。"""
        try:
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.attributes("-topmost", False)
            self.root.focus_force()
        except Exception:
            pass

    def _start_singleton_listener(self):
        """在后台线程中监听单例唤醒端口，收到 focus 时唤至前台。"""
        def listen():
            try:
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind(("127.0.0.1", GUI_SINGLETON_PORT))
                server.listen(1)
                server.settimeout(1.0)
                while getattr(self, "_singleton_listen", True):
                    try:
                        conn, _ = server.accept()
                        try:
                            data = conn.recv(64).decode("utf-8", errors="ignore").strip().lower()
                            if data == "focus":
                                self.root.after(0, self._bring_to_front)
                        finally:
                            try:
                                conn.close()
                            except Exception:
                                pass
                    except socket.timeout:
                        continue
                    except (OSError, Exception):
                        break
                try:
                    server.close()
                except Exception:
                    pass
            except Exception:
                pass
        # 说明：原实现会在后台线程中调用 Tk 的 after，从而在部分环境下导致崩溃。
        # 这里暂时不启动单例监听线程，仅保留单实例锁逻辑，避免 Tk 跨线程访问。

    def _on_tab_changed(self, event=None):
        if getattr(self, "tabview", None) is not None:
            name = self.tabview.get()
            self._current_scroll_canvas = self._tab_name_to_canvas.get(name) if getattr(self, "_tab_name_to_canvas", None) else None
            return
        if getattr(self, "notebook", None) is None or not self.scroll_canvases:
            return
        self._current_scroll_canvas = self.scroll_canvases[self.notebook.index(self.notebook.select())]

    def _is_descendant(self, w, ancestor):
        """判断控件 w 是否为 ancestor 自身或其子控件。"""
        while w:
            if w == ancestor:
                return True
            try:
                w = w.master
            except Exception:
                return False
        return False

    def _scroll_target_canvas(self, event=None, delta_units=None):
        """根据鼠标位置决定滚动哪个 canvas：若在技能列表区域则滚动 skill_canvas，否则滚动当前页 canvas。"""
        if delta_units is None and event is not None:
            delta_units = int(-1 * (event.delta / 120)) if hasattr(event, "delta") else 0
        if delta_units == 0:
            return
        if getattr(self, "tabview", None) is not None and getattr(self, "_tab_name_to_canvas", None):
            self._current_scroll_canvas = self._tab_name_to_canvas.get(self.tabview.get())
        if event and hasattr(event, "x_root") and hasattr(event, "y_root"):
            x, y = event.x_root, event.y_root
        else:
            try:
                x, y = self.root.winfo_pointerxy()
            except Exception:
                return
        w = self.root.winfo_containing(x, y)
        if getattr(self, "skill_canvas", None) and w and self._is_descendant(w, self.skill_canvas):
            self.skill_canvas.yview_scroll(delta_units, "units")
            return
        if getattr(self, "_current_scroll_canvas", None):
            self._current_scroll_canvas.yview_scroll(delta_units, "units")

    def _on_mousewheel(self, event):
        self._scroll_target_canvas(event=event)

    def _on_linux_wheel_up(self, event):
        self._scroll_target_canvas(event=event, delta_units=-4)

    def _on_linux_wheel_down(self, event):
        self._scroll_target_canvas(event=event, delta_units=4)

    def build_ui(self):
        tab_names = [
            "0. 已有配置", "1. 网关", "2. 工作区", "3. 模型与认证", "4. 通道",
            "5. 网页搜索", "6. 会话与工具", "7. 命令与高级", "8. 完成", "9. 技能",
        ]
        if ctk is not None:
            # 内容区与窗口同色，边距统一，主窗口整体为 CTk 风格
            content_wrap = ctk.CTkFrame(self.root, fg_color=("gray95", "gray14"), corner_radius=0)
            content_wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 8))
            self._tab_name_to_canvas = {}

            def _on_ctk_tab_changed():
                name = self.tabview.get()
                self._current_scroll_canvas = self._tab_name_to_canvas.get(name)
                if self._current_scroll_canvas is None and self.scroll_canvases:
                    self._current_scroll_canvas = self.scroll_canvases[0]

            self.tabview = ctk.CTkTabview(
                content_wrap,
                command=_on_ctk_tab_changed,
                corner_radius=8,
                border_width=1,
            )
            self.tabview.pack(fill=tk.BOTH, expand=True, padx=0, pady=2)
            self.notebook = None
            for name in tab_names:
                tab_frame = self.tabview.add(name)
                inner = make_scrollable_tab_inside(tab_frame, self.scroll_canvases)
                self._tab_name_to_canvas[name] = self.scroll_canvases[-1] if self.scroll_canvases else None
                if name == "0. 已有配置":
                    self.add_tab_config_choice(inner)
                elif name == "1. 网关":
                    self.add_tab_gateway(inner)
                elif name == "2. 工作区":
                    self.add_tab_workspace(inner)
                elif name == "3. 模型与认证":
                    self.add_tab_model(inner)
                elif name == "4. 通道":
                    self.add_tab_channels(inner)
                elif name == "5. 网页搜索":
                    self.add_tab_web_search(inner)
                elif name == "6. 会话与工具":
                    self.add_tab_session_tools(inner)
                elif name == "7. 命令与高级":
                    self.add_tab_commands(inner)
                elif name == "8. 完成":
                    self.add_tab_finish(inner)
                elif name == "9. 技能":
                    self.add_tab_skills(inner)
            self._current_scroll_canvas = self.scroll_canvases[0] if self.scroll_canvases else None
        else:
            self.tabview = None
            self.notebook = ttk.Notebook(self.root)
            self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
            inner0 = make_scrollable_tab(self.notebook, "0. 已有配置", self.scroll_canvases)
            self.add_tab_config_choice(inner0)
            inner1 = make_scrollable_tab(self.notebook, "1. 网关", self.scroll_canvases)
            self.add_tab_gateway(inner1)
            inner2 = make_scrollable_tab(self.notebook, "2. 工作区", self.scroll_canvases)
            self.add_tab_workspace(inner2)
            inner3 = make_scrollable_tab(self.notebook, "3. 模型与认证", self.scroll_canvases)
            self.add_tab_model(inner3)
            inner4 = make_scrollable_tab(self.notebook, "4. 通道", self.scroll_canvases)
            self.add_tab_channels(inner4)
            inner5 = make_scrollable_tab(self.notebook, "5. 网页搜索", self.scroll_canvases)
            self.add_tab_web_search(inner5)
            inner6 = make_scrollable_tab(self.notebook, "6. 会话与工具", self.scroll_canvases)
            self.add_tab_session_tools(inner6)
            inner7 = make_scrollable_tab(self.notebook, "7. 命令与高级", self.scroll_canvases)
            self.add_tab_commands(inner7)
            inner8 = make_scrollable_tab(self.notebook, "8. 完成", self.scroll_canvases)
            self.add_tab_finish(inner8)
            inner9 = make_scrollable_tab(self.notebook, "9. 技能", self.scroll_canvases)
            self.add_tab_skills(inner9)
            self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
            self._current_scroll_canvas = self.scroll_canvases[0] if self.scroll_canvases else None

        self.root.bind("<MouseWheel>", self._on_mousewheel)
        self.root.bind("<Button-4>", self._on_linux_wheel_up)
        self.root.bind("<Button-5>", self._on_linux_wheel_down)

        if ctk is not None:
            btn_frame = ctk.CTkFrame(self.root, fg_color="transparent")
            btn_frame.pack(fill=tk.X, padx=8, pady=8)
            ctk.CTkButton(btn_frame, text="一键启动 OpenClaw", command=self.do_oneclick_start, fg_color="#28a745", hover_color="#218838").pack(side=tk.LEFT, padx=4)
            ctk.CTkButton(btn_frame, text="保存配置", command=self.do_save).pack(side=tk.LEFT, padx=4)
            ctk.CTkButton(btn_frame, text="保存并重启 OpenClaw", command=self.do_save_restart, fg_color="#007bff", hover_color="#0056b3").pack(side=tk.LEFT, padx=4)
            ctk.CTkButton(btn_frame, text="一键重启", command=self.do_restart, fg_color="#fd7e14", hover_color="#e96a00").pack(side=tk.LEFT, padx=4)
            ctk.CTkButton(btn_frame, text="打开控制台 (Dashboard)", command=self.open_dashboard, fg_color="#6c757d", hover_color="#5a6268").pack(side=tk.LEFT, padx=4)
        else:
            btn_frame = ttk.Frame(self.root, padding="8")
            btn_frame.pack(fill=tk.X)
            ttk.Button(btn_frame, text="一键启动 OpenClaw", command=self.do_oneclick_start).pack(side=tk.LEFT, padx=4)
            ttk.Button(btn_frame, text="保存配置", command=self.do_save).pack(side=tk.LEFT, padx=4)
            ttk.Button(btn_frame, text="保存并重启 OpenClaw", command=self.do_save_restart).pack(side=tk.LEFT, padx=4)
            ttk.Button(btn_frame, text="一键重启", command=self.do_restart).pack(side=tk.LEFT, padx=4)
            ttk.Button(btn_frame, text="打开控制台 (Dashboard)", command=self.open_dashboard).pack(side=tk.LEFT, padx=4)

    def add_tab_config_choice(self, f):
        r = 0
        # 始终显示配置一览区域（无配置时显示占位提示）
        _gui_label(f, text="配置一览（当前 OpenClaw 状态）", font=("", 10, "bold")).grid(row=r, column=0, columnspan=2, sticky=tk.W); r += 1
        overview = tk.Text(f, height=8, width=60, wrap=tk.WORD, font=("", 10), state=tk.DISABLED)
        overview.grid(row=r, column=0, columnspan=2, sticky=tk.EW, pady=4)
        self._overview_text = overview
        if CONFIG_FILE.exists() and self.config and not self.config.get("_load_error"):
            self._update_config_overview(include_channel_status=False)  # 启动时不拉取 openclaw status，避免阻塞窗口
        else:
            self._set_overview_text("尚无配置文件，或加载失败。\n请先完成引导或检查 ~/.openclaw/openclaw.json。\n\n点击「刷新一览」可在创建配置后更新。")
        r += 1
        btn_row = _gui_frame(f)
        btn_row.grid(row=r, column=0, columnspan=2, sticky=tk.W, pady=4); r += 1
        _gui_button(btn_row, text="🔄 刷新一览", command=lambda: self._update_config_overview(include_channel_status=True)).pack(side=tk.LEFT, padx=(0, 8))
        _gui_separator(f, orient=tk.HORIZONTAL).grid(row=r, column=0, columnspan=2, sticky=tk.EW, pady=10); r += 1
        _gui_label(f, text="常用命令（点击后在系统终端中执行，请在终端内查看输出与交互）", font=("", 9, "bold")).grid(row=r, column=0, columnspan=2, sticky=tk.W, pady=(4, 0)); r += 1
        cmd_row = _gui_frame(f)
        cmd_row.grid(row=r, column=0, columnspan=2, sticky=tk.W, pady=4); r += 1
        def _run_cmd_in_terminal(cmd, name):
            ok, msg = run_in_system_terminal(cmd)
            if not ok:
                messagebox.showerror(name, msg)
        _gui_button(cmd_row, text="查看日志", command=lambda: _run_cmd_in_terminal("openclaw logs --follow", "查看日志")).pack(side=tk.LEFT, padx=(0, 6))
        _gui_button(cmd_row, text="自动诊断 (doctor --fix)", command=lambda: _run_cmd_in_terminal("openclaw doctor --fix", "OpenClaw 自动诊断")).pack(side=tk.LEFT, padx=(0, 6))
        _gui_button(cmd_row, text="诊断并修复 (doctor --repair)", command=lambda: _run_cmd_in_terminal("openclaw doctor --repair", "OpenClaw 诊断并修复")).pack(side=tk.LEFT, padx=4)
        _gui_button(cmd_row, text="仅检查 (doctor)", command=lambda: _run_cmd_in_terminal("openclaw doctor", "OpenClaw 诊断检查")).pack(side=tk.LEFT, padx=4)
        _gui_button(cmd_row, text="重置 / 重新引导 (onboard)", command=self._run_onboard_in_terminal).pack(side=tk.LEFT, padx=4)
        _gui_label(f, text="说明：onboard 仅包含内置通道（Telegram/Discord/Slack/WhatsApp 等）；飞书/Mattermost/Teams 通过扩展提供，会提示 does not support onboarding yet。请到「4. 通道」或执行 openclaw channels add 配置（此为推荐方式）。", font=("", 8), foreground="gray").grid(row=r, column=0, columnspan=2, sticky=tk.W, pady=(4, 0)); r += 1
        _gui_separator(f, orient=tk.HORIZONTAL).grid(row=r, column=0, columnspan=2, sticky=tk.EW, pady=8); r += 1
        add_label_with_hint(f, r, "检测到已有配置时的处理方式", "config_choice"); r += 1
        self.vars["config_choice"] = tk.StringVar(value="modify")
        for val, text in [("keep", "保持 — 不覆盖现有配置"), ("modify", "修改 — 在现有基础上更新（推荐）"), ("reset", "重置 — 清空配置与凭据后重新配置")]:
            ttk.Radiobutton(f, text=text, variable=self.vars["config_choice"], value=val).grid(row=r, column=0, columnspan=2, sticky=tk.W, pady=2); r += 1
        _gui_label(f, text="说明：本程序始终以「修改」方式写入你在此处改动的项，不会主动删除未涉及的配置。", font=("", 9), foreground="gray").grid(row=r, column=0, columnspan=2, sticky=tk.W, pady=8)
        f.columnconfigure(0, weight=1)

    def _update_config_overview(self, include_channel_status=False, gateway_status=None):
        """刷新配置一览。启动时 gateway_status=None 先显示「检测中」不阻塞；后台异步请求网关状态后回填。
        用户点「刷新一览」时 include_channel_status=True 会同步拉取通道状态（可稍慢）。"""
        if not getattr(self, "_overview_text", None):
            return
        self.config = load_config()
        if isinstance(self.config, dict) and self.config.get("_load_error"):
            return
        summary = get_config_summary(
            self.config,
            include_channel_status=include_channel_status,
            gateway_status=gateway_status,
        )
        self._overview_text.config(state=tk.NORMAL)
        self._overview_text.delete("1.0", tk.END)
        self._overview_text.insert(tk.END, summary)
        self._overview_text.config(state=tk.DISABLED)
        # 启动时未传 gateway_status 则直接在主线程检测网关并回填，避免在后台线程中调用 Tk
        if gateway_status is None and not include_channel_status:
            try:
                port = (self.config.get("gateway") or {}).get("port", 18789)
                running = check_gateway_running(port)
                summary_done = get_config_summary(
                    self.config, include_channel_status=False, gateway_status=running
                )
                self._set_overview_text(summary_done)
            except Exception:
                pass

    def _set_overview_text(self, summary):
        """仅更新配置一览文本框内容（主线程调用）。"""
        if not getattr(self, "_overview_text", None):
            return
        try:
            self._overview_text.config(state=tk.NORMAL)
            self._overview_text.delete("1.0", tk.END)
            self._overview_text.insert(tk.END, summary)
            self._overview_text.config(state=tk.DISABLED)
        except tk.TclError:
            pass

    def _install_channel_plugins(self, selected_only=True):
        """安装通道插件：先打开官网，再在命令行弹窗中执行 openclaw plugins install（按官网要求可用命令行安装）。"""
        if not check_network_ok():
            messagebox.showwarning("通道插件安装", "网络不可用，请检查网络连接后再试。\n安装已取消。")
            return
        installed_keys = self._channel_plugin_installed_keys()
        if selected_only:
            to_install = [(pkg, name) for (pkg, name, var, w) in self._channel_plugin_widgets
                          if not (isinstance(w, ttk.Label) or (ctk and isinstance(w, ctk.CTkLabel))) and var.get()]
            if not to_install:
                messagebox.showinfo("通道插件安装", "请先勾选要安装的通道插件（灰色「已安装」的不可选）。")
                return
        else:
            to_install = [(pkg, name) for (pkg, name) in CHANNEL_PLUGINS if pkg.split("/")[-1] not in installed_keys]
            if not to_install:
                messagebox.showinfo("通道插件安装", "当前所有通道插件均已安装，无需操作。")
                return
        open_url(OPENCLAW_DOCS_URL)
        cmd = " && ".join(f"openclaw plugins install {pkg}" for pkg, _ in to_install)
        ok, msg = run_in_system_terminal(cmd)
        if not ok:
            messagebox.showerror("通道插件安装", msg)
        self.config = load_config()
        if getattr(self, "_refresh_channel_plugin_list", None):
            self._refresh_channel_plugin_list()

    def _hide_duplicate_channel_extensions(self):
        """将 extensions 下的 feishu/mattermost/msteams 重命名为 .bak，避免与内建插件重复加载。"""
        ext_dir = CONFIG_DIR / "extensions"
        names = ("feishu", "mattermost", "msteams")
        done = []
        for name in names:
            src = ext_dir / name
            dst = ext_dir / f"{name}.bak"
            if not src.exists():
                continue
            if dst.exists():
                done.append(f"{name}: 已存在 {name}.bak，跳过")
                continue
            try:
                src.rename(dst)
                done.append(f"✓ {name} → {name}.bak")
            except Exception as e:
                done.append(f"✗ {name}: {e}")
        if done:
            messagebox.showinfo("重复插件", "扩展目录已重命名（重启 OpenClaw 后生效）：\n\n" + "\n".join(done))
        else:
            messagebox.showinfo("重复插件", "未找到 extensions/feishu、mattermost、msteams 目录，无需操作。")

    def _run_ollama_in_terminal(self):
        """在系统终端中运行 Ollama 服务（ollama serve，官方推荐前台运行可见日志）。"""
        ok, msg = run_in_system_terminal("ollama serve")
        if not ok:
            messagebox.showerror("Ollama", msg)

    def _launch_openclaw_in_terminal(self):
        """在系统终端中启动 OpenClaw 网关（官方文档：openclaw gateway --port <port>）。"""
        try:
            port = int((self.vars.get("gateway.port") and self.vars["gateway.port"].get() or "").strip() or 0)
        except (ValueError, TypeError):
            port = 0
        if not port:
            port = int((self.config.get("gateway") or {}).get("port", 18789))
        cmd = f"openclaw gateway --port {port}"
        ok, msg = run_in_system_terminal(cmd)
        if not ok:
            messagebox.showerror("启动 OpenClaw", msg)

    def _run_channel_verify(self, title, verify_func):
        """执行验证函数 verify_func() -> (success, message)，完成后弹窗提示（在主线程中运行以避免 Tk 跨线程访问）。"""
        try:
            ok, msg = verify_func()
        except Exception as e:
            ok, msg = False, str(e)
        self._show_verify_result(title, ok, msg)

    def _show_verify_result(self, title, success, message):
        if success:
            messagebox.showinfo(f"验证成功 — {title}", message)
        else:
            messagebox.showerror(f"验证失败 — {title}", message)

    def _show_channel_setup_guide(self, channel_key):
        """打开指定通道的配置与配对说明窗口（基于官方文档）。"""
        text = CHANNEL_SETUP_GUIDE.get(channel_key)
        if not text:
            messagebox.showinfo("说明", "该通道暂无单独引导说明，请查看 OpenClaw 官方文档。")
            return
        win = tk.Toplevel(self.root)
        win.title(f"通道配置与配对说明 — {channel_key}")
        win.minsize(480, 360)
        win.geometry("560x420")
        fr = _gui_frame(win)
        fr.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        txt = tk.Text(fr, wrap=tk.WORD, font=("", 10), padx=8, pady=8)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.insert(tk.END, text)
        txt.config(state=tk.DISABLED)
        _gui_button(fr, text="关闭", command=win.destroy).pack(pady=4)

    def _show_skill_install_guide(self):
        """弹出技能安装教程：如何下载、安装、运行与验证。"""
        win = tk.Toplevel(self.root)
        win.title("技能安装教程")
        win.minsize(520, 420)
        win.geometry("580x480")
        fr = _gui_frame(win)
        fr.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        txt = tk.Text(fr, wrap=tk.WORD, font=("", 10), padx=8, pady=8)
        sb = ttk.Scrollbar(fr)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        txt.configure(yscrollcommand=sb.set)
        sb.configure(command=txt.yview)
        txt.insert(tk.END, SKILL_INSTALL_GUIDE.strip())
        txt.config(state=tk.DISABLED)
        _gui_button(fr, text="关闭", command=win.destroy).pack(pady=4)

    def _show_feishu_troubleshoot(self):
        """飞书连接不成功时：排查清单 + 在终端执行网关状态 / channels add / 日志。"""
        win = tk.Toplevel(self.root)
        win.title("飞书通道连接排查")
        win.minsize(460, 380)
        fr = _gui_frame(win)
        fr.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        ttk.Label(fr, text="若看到「feishu does not support onboarding yet」：主向导 onboard 只含内置通道，飞书通过扩展提供、不在 onboard 中。请用本程序「4. 通道」或 openclaw channels add 配置飞书（此为当前推荐方式）。", font=("", 9), wraplength=520, foreground="gray").pack(anchor=tk.W, pady=(0, 6))
        ttk.Label(fr, text="若飞书通道未连接成功，请按下面顺序排查：", font=("", 10, "bold")).pack(anchor=tk.W, pady=(0, 8))
        checklist = [
            "1. 网关已启动：下方点击「查看网关状态」确认；未运行请先点「一键启动 OpenClaw」或执行 openclaw gateway。",
            "2. 已用 channels add 登记：点击「在终端运行 channels add」，选择 Feishu 并填写与配置一致的 App ID / App Secret，保存后重启网关。",
            "3. 飞书开放平台 → 事件订阅：添加 im.message.receive_v1，选择「使用长连接接收事件」。若保存失败，请先启动网关再在飞书端保存。",
            "4. 应用已发布：版本管理与发布中创建版本、提交审核并通过。",
            "5. 查看日志：点击「在终端查看日志」，在飞书中给机器人发消息，观察是否有 feishu 相关输出或报错。",
            "6. 若报错找不到 @larksuiteoapi/node-sdk：请回到「4. 通道」飞书行，点击「安装飞书 SDK」安装插件依赖（含飞书官方 Node SDK）。",
        ]
        for line in checklist:
            ttk.Label(fr, text=line, font=("", 9), wraplength=520).pack(anchor=tk.W, pady=2)
        ttk.Label(fr, text="", font=("", 9)).pack(anchor=tk.W)
        ttk.Label(fr, text="若 channels add 提示「plugin already exists... delete it first」：", font=("", 9, "bold")).pack(anchor=tk.W, pady=(4, 2))
        ttk.Label(fr, text="插件代码在 extensions/feishu 目录，而您的 App ID、App Secret 等配置在 ~/.openclaw/openclaw.json 里，删除或重命名 extensions/feishu 不会影响已有配置。可点击「移除飞书插件目录（保留配置）」将 extensions/feishu 重命名为 feishu.bak，然后重新执行 channels add，会再次安装插件并提示填写凭据（配置文件中已有的会保留）。", font=("", 9), wraplength=520, foreground="gray").pack(anchor=tk.W, pady=2)
        btn_f = _gui_frame(fr)
        btn_f.pack(fill=tk.X, pady=8)
        def _term(cmd, name):
            ok, msg = run_in_system_terminal(cmd)
            if not ok:
                messagebox.showerror(name, msg)
        _gui_button(btn_f, text="查看网关状态", command=lambda: _term("openclaw gateway status", "网关状态")).pack(side=tk.LEFT, padx=2)
        _gui_button(btn_f, text="在终端运行 channels add", command=lambda: _term("openclaw channels add", "channels add")).pack(side=tk.LEFT, padx=2)
        _gui_button(btn_f, text="在终端查看日志", command=lambda: _term("openclaw logs --follow", "网关日志")).pack(side=tk.LEFT, padx=2)
        _gui_button(fr, text="移除飞书插件目录（保留配置）", command=self._feishu_remove_ext_for_reinstall).pack(anchor=tk.W, pady=2)
        _gui_button(fr, text="查看完整配对与配置说明", command=lambda: (win.destroy(), self._show_channel_setup_guide("feishu"))).pack(pady=4)
        _gui_button(fr, text="关闭", command=win.destroy).pack(pady=4)

    def _feishu_install_sdk(self):
        """在 extensions/feishu 目录执行 npm install，安装飞书官方 Node SDK（@larksuiteoapi/node-sdk）等插件依赖。"""
        ext_dir = CONFIG_DIR / "extensions"
        feishu_dir = ext_dir / "feishu"
        if not feishu_dir.exists() or not feishu_dir.is_dir():
            messagebox.showinfo(
                "安装飞书 SDK",
                "飞书插件目录不存在。请先安装飞书通道插件：\n\n"
                "· 在本页「通道插件安装」中勾选「飞书 Feishu」并点击「安装选中的通道插件」，或\n"
                "· 在终端执行：openclaw plugins install @openclaw/feishu\n\n"
                "安装完成后，飞书插件会自带 package.json，再点击「安装飞书 SDK」即可安装依赖（含飞书官方 Node SDK）。"
            )
            open_url(FEISHU_SDK_DOC_URL)
            return
        pkg_json = feishu_dir / "package.json"
        if not pkg_json.exists():
            messagebox.showwarning("安装飞书 SDK", "extensions/feishu 下未找到 package.json，请先通过「安装选中的通道插件」或 openclaw plugins install @openclaw/feishu 安装完整插件。")
            open_url(FEISHU_SDK_DOC_URL)
            return
        ok, out = run_openclaw_cmd_sync(f'cd "{feishu_dir}" && npm install', timeout=120)
        if ok:
            messagebox.showinfo("安装飞书 SDK", "飞书插件依赖（含飞书官方 Node SDK @larksuiteoapi/node-sdk）已安装完成。\n\n请重启网关后生效。")
        else:
            messagebox.showerror("安装飞书 SDK 失败", out or "请检查网络与 Node/npm 环境，或查看飞书 SDK 文档：\n" + FEISHU_SDK_DOC_URL)

    def _feishu_remove_ext_for_reinstall(self):
        """将 extensions/feishu 重命名为 feishu.bak，便于 channels add 重新安装；不影响 openclaw.json 中的配置。"""
        ext_dir = CONFIG_DIR / "extensions"
        feishu_dir = ext_dir / "feishu"
        bak_dir = ext_dir / "feishu.bak"
        if not feishu_dir.exists() or not feishu_dir.is_dir():
            messagebox.showinfo("飞书插件目录", "extensions/feishu 不存在，无需移除。可直接在终端执行 openclaw channels add。")
            return
        try:
            if bak_dir.exists():
                old_bak = ext_dir / "feishu.bak.old"
                if old_bak.exists():
                    import shutil
                    shutil.rmtree(old_bak)
                bak_dir.rename(old_bak)
            feishu_dir.rename(bak_dir)
            messagebox.showinfo(
                "已移除",
                "已将 ~/.openclaw/extensions/feishu 重命名为 feishu.bak。\n\n"
                "您的 App ID、App Secret 等配置仍在 openclaw.json 中，不会丢失。\n\n"
                "请点击「在终端运行 channels add」或手动执行 openclaw channels add，选择 Feishu 后即可重新安装插件并继续配置。"
            )
        except Exception as e:
            messagebox.showerror("操作失败", str(e))

    def _run_pairing_approve_for_channel(self, ch_key):
        """在界面内执行 openclaw pairing approve <channel> <code> 并弹窗显示结果（按通道调用）。"""
        var = getattr(self, "_pairing_code_vars", {}).get(ch_key)
        code = (var.get() or "").strip() if var else ""
        if not code:
            messagebox.showwarning("配对", "请输入从机器人处获得的配对码（通常为 8 位）。")
            return
        cmd = f"openclaw pairing approve {ch_key} {code}"
        ok, out = run_openclaw_cmd_sync(cmd)
        if ok:
            messagebox.showinfo("配对", "批准成功。\n\n" + (out or "该用户/账号已可与机器人对话。"))
            if var:
                var.set("")
        else:
            messagebox.showerror("配对失败", out or "请确认网关已启动、通道已启用，且配对码正确未过期。")

    def _run_pairing_list_terminal_for_channel(self, ch_key):
        """在系统终端中执行 openclaw pairing list <channel>，便于用户查看待批准配对。"""
        cmd = f"openclaw pairing list {ch_key}"
        ok, msg = run_in_system_terminal(cmd)
        if not ok:
            messagebox.showerror("打开终端", msg)

    def add_tab_gateway(self, f):
        g = self.config.get("gateway") or {}
        r = 0
        add_label_with_hint(f, r, "端口", "gateway.port")
        self.vars["gateway.port"] = tk.StringVar(value=str(g.get("port", 18789)))
        _gui_entry(f, textvariable=self.vars["gateway.port"], width_chars=12).grid(row=r, column=1, sticky=tk.W); r += 1
        add_label_with_hint(f, r, "绑定", "gateway.bind")
        self.vars["gateway.bind"] = tk.StringVar(value=g.get("bind", "loopback"))
        _gui_combobox(f, self.vars["gateway.bind"], ["loopback", "lan", "tailnet", "auto", "custom"], width_chars=14).grid(row=r, column=1, sticky=tk.W); r += 1
        add_label_with_hint(f, r, "认证模式", "gateway.auth.mode")
        self.vars["gateway.auth.mode"] = tk.StringVar(value=(g.get("auth") or {}).get("mode", "token"))
        _gui_combobox(f, self.vars["gateway.auth.mode"], ["none", "token", "password", "trusted-proxy"], width_chars=14).grid(row=r, column=1, sticky=tk.W); r += 1
        add_label_with_hint(f, r, "Token", "gateway.auth.token")
        self.vars["gateway.auth.token"] = tk.StringVar(value=(g.get("auth") or {}).get("token", ""))
        _gui_entry(f, textvariable=self.vars["gateway.auth.token"], width_chars=28, show="*").grid(row=r, column=1, sticky=tk.W); r += 1
        add_label_with_hint(f, r, "密码（password 模式）", "gateway.auth.password")
        self.vars["gateway.auth.password"] = tk.StringVar(value=(g.get("auth") or {}).get("password", ""))
        _gui_entry(f, textvariable=self.vars["gateway.auth.password"], width_chars=28, show="*").grid(row=r, column=1, sticky=tk.W); r += 1
        add_label_with_hint(f, r, "Tailscale", "gateway.tailscale.mode")
        self.vars["gateway.tailscale.mode"] = tk.StringVar(value=(g.get("tailscale") or {}).get("mode", "off"))
        _gui_combobox(f, self.vars["gateway.tailscale.mode"], ["off", "serve", "funnel"], width_chars=14).grid(row=r, column=1, sticky=tk.W); r += 1
        add_label_with_hint(f, r, "配置热重载", "gateway.reload.mode")
        self.vars["gateway.reload.mode"] = tk.StringVar(value=(g.get("reload") or {}).get("mode", "hybrid"))
        _gui_combobox(f, self.vars["gateway.reload.mode"], ["hybrid", "hot", "restart", "off"], width_chars=14).grid(row=r, column=1, sticky=tk.W)
        self._add_more_button(f, 90, "gateway", skip=set(self.vars.keys()))
        f.columnconfigure(1, weight=1)

    def add_tab_workspace(self, f):
        a = self.config.get("agents") or {}
        d = a.get("defaults") or {}
        r = 0
        add_label_with_hint(f, r, "工作区目录", "agents.defaults.workspace")
        self.vars["agents.defaults.workspace"] = tk.StringVar(value=d.get("workspace", str(CONFIG_DIR / "workspace")))
        _gui_entry(f, textvariable=self.vars["agents.defaults.workspace"], width_chars=50).grid(row=r, column=1, sticky=tk.EW)
        _gui_button(f, text="浏览…", command=self.browse_workspace).grid(row=r, column=2, padx=4); r += 1
        add_label_with_hint(f, r, "跳过引导文件创建", "agents.defaults.skipBootstrap")
        self.vars["agents.defaults.skipBootstrap"] = tk.BooleanVar(value=d.get("skipBootstrap", False))
        _gui_checkbox(f, text="是（skipBootstrap）", variable=self.vars["agents.defaults.skipBootstrap"]).grid(row=r, column=1, sticky=tk.W)
        self._add_more_button(f, 90, "agents", skip=set(self.vars.keys()))
        f.columnconfigure(1, weight=1)

    def browse_workspace(self):
        path = filedialog.askdirectory(title="选择工作区目录", initialdir=str(Path.home()))
        if path:
            self.vars["agents.defaults.workspace"].set(path)

    def _custom_provider_entries(self):
        """将自定义厂商转为与 MODEL_PROVIDERS 相同格式的元组列表。"""
        return [
            (f"custom:{c['key']}", f"自定义: {c['key']}", "api_key", c["env_var"], f"{c['key']}/model-name", c.get("url"))
            for c in self._custom_providers
        ]

    def _all_providers(self):
        """内置厂商 + 自定义厂商（Cherry Studio 风格：世界全部模型厂商 + 可自定义）。"""
        return list(MODEL_PROVIDERS) + self._custom_provider_entries()

    def _refresh_provider_combobox(self):
        """刷新厂商下拉框的选项列表（添加自定义厂商后调用）。"""
        if not getattr(self, "_provider_cb", None):
            return
        names = [x[1] for x in self._all_providers()]
        try:
            if ctk is not None and hasattr(self._provider_cb, "configure"):
                self._provider_cb.configure(values=names)
            else:
                self._provider_cb["values"] = names
        except Exception:
            pass

    def _show_add_custom_provider_dialog(self):
        """添加自定义厂商对话框（Cherry Studio 风格）。"""
        dlg = tk.Toplevel(self.root)
        dlg.title("添加自定义厂商")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry("460x320")   # 原 420x220 过矮，底部「添加/取消」按钮被裁看不见
        dlg.minsize(420, 300)
        dlg.resizable(True, True)
        frame = ttk.Frame(dlg, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="厂商 Key（如 myprovider、litellm，用于 provider/model 格式）:").pack(anchor=tk.W)
        key_var = tk.StringVar()
        key_ent = ttk.Entry(frame, textvariable=key_var, width=40)
        key_ent.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(frame, text="API Key 环境变量名（如 MY_PROVIDER_API_KEY）:").pack(anchor=tk.W)
        env_var = tk.StringVar()
        env_ent = ttk.Entry(frame, textvariable=env_var, width=40)
        env_ent.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(frame, text="获取 API Key 链接（可选）:").pack(anchor=tk.W)
        url_var = tk.StringVar()
        url_ent = ttk.Entry(frame, textvariable=url_var, width=40)
        url_ent.pack(fill=tk.X, pady=(0, 12))

        def on_ok():
            key = (key_var.get() or "").strip().lower().replace(" ", "-")
            env = (env_var.get() or "").strip()
            if not key:
                messagebox.showwarning("添加自定义厂商", "请输入厂商 Key。", parent=dlg)
                return
            if not env:
                env = key.upper().replace("-", "_") + "_API_KEY"
            existing = [c["key"] for c in self._custom_providers]
            if key in existing:
                messagebox.showwarning("添加自定义厂商", f"厂商 Key「{key}」已存在。", parent=dlg)
                return
            self._custom_providers.append({"key": key, "env_var": env, "url": (url_var.get() or "").strip() or None})
            save_custom_providers(self._custom_providers)
            self._refresh_provider_combobox()
            self.vars["model_auth.provider"].set(f"自定义: {key}")
            dlg.destroy()

        def on_cancel():
            dlg.destroy()

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_row, text="添加", command=on_ok).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="取消", command=on_cancel).pack(side=tk.LEFT)
        dlg.protocol("WM_DELETE_WINDOW", on_cancel)
        key_ent.focus_set()

    def add_tab_model(self, f):
        a = self.config.get("agents") or {}
        d = a.get("defaults") or {}
        m = d.get("model") or {}
        primary = m.get("primary", "") if isinstance(m, dict) else (m if isinstance(m, str) else "")
        fallbacks = m.get("fallbacks", []) if isinstance(m, dict) else []
        fallbacks_str = ", ".join(fallbacks) if isinstance(fallbacks, list) else str(fallbacks)
        env_block = self.config.get("env") or {}
        env_flat = dict(env_block.get("vars") or {})
        for k, v in (env_block if isinstance(env_block, dict) else {}).items():
            if k != "vars" and isinstance(v, str):
                env_flat.setdefault(k, v)
        self._config_env = env_flat
        r = 0
        _gui_label(f, text="认证提供方（世界主流厂商 + 自定义，Cherry Studio 风格）", font=("", 9, "bold")).grid(row=r, column=0, columnspan=2, sticky=tk.W); r += 1
        provider_names = [x[1] for x in self._all_providers()]
        # 根据主模型自动匹配厂商（如 primary=openai/gpt-4o -> 选 OpenAI）
        initial_provider = provider_names[0]
        if primary and "/" in primary:
            prefix = primary.split("/", 1)[0].lower()
            for t in self._all_providers():
                key, name = t[0], t[1]
                if key == prefix or (key.startswith("custom:") and key.split(":", 1)[1] == prefix):
                    initial_provider = name
                    break
        self.vars["model_auth.provider"] = tk.StringVar(value=initial_provider)
        prov_row = _gui_frame(f)
        prov_row.grid(row=r, column=0, columnspan=2, sticky=tk.EW, pady=2); r += 1
        self._provider_cb = _gui_combobox(prov_row, self.vars["model_auth.provider"], provider_names, width_chars=42)
        self._provider_cb.pack(side=tk.LEFT, fill=tk.X, expand=True)
        _gui_button(prov_row, text="➕ 添加自定义厂商", command=self._show_add_custom_provider_dialog).pack(side=tk.LEFT, padx=(8, 0))
        self._model_auth_frame = ttk.LabelFrame(f, text="认证方式", padding=6)
        self._model_auth_frame.grid(row=r, column=0, columnspan=2, sticky=tk.EW, pady=4); r += 1
        self.vars["model_auth.api_key"] = tk.StringVar()
        self._provider_api_keys = {}  # provider_key -> api_key 切换时保留
        self._model_auth_inner = ttk.Frame(self._model_auth_frame)
        self._model_auth_inner.pack(fill=tk.X)
        def on_provider_change(*args):
            self._rebuild_model_auth_panel()
        self.vars["model_auth.provider"].trace_add("write", on_provider_change)
        self._ollama_models_frame = ttk.LabelFrame(f, text="Ollama 模型", padding=6)
        self._ollama_models_frame.grid(row=r, column=0, columnspan=2, sticky=tk.EW, pady=4); r += 1
        self._rebuild_model_auth_panel()
        _gui_separator(f, orient=tk.HORIZONTAL).grid(row=r, column=0, columnspan=2, sticky=tk.EW, pady=8); r += 1
        add_label_with_hint(f, r, "主模型 (provider/model)", "agents.defaults.model.primary")
        self.vars["agents.defaults.model.primary"] = tk.StringVar(value=primary)
        _gui_entry(f, textvariable=self.vars["agents.defaults.model.primary"], width_chars=50).grid(row=r, column=1, sticky=tk.EW); r += 1
        r += 1
        add_label_with_hint(f, r, "备选模型（逗号分隔）", "agents.defaults.model.fallbacks")
        self.vars["agents.defaults.model.fallbacks"] = tk.StringVar(value=fallbacks_str)
        _gui_entry(f, textvariable=self.vars["agents.defaults.model.fallbacks"], width_chars=50).grid(row=r, column=1, sticky=tk.EW); r += 1
        add_label_with_hint(f, r, "图像模型（主模型不支持图时）", "agents.defaults.imageModel.primary")
        im = (d.get("imageModel") or {})
        im_primary = im.get("primary", "") if isinstance(im, dict) else ""
        self.vars["agents.defaults.imageModel.primary"] = tk.StringVar(value=im_primary)
        _gui_entry(f, textvariable=self.vars["agents.defaults.imageModel.primary"], width_chars=50).grid(row=r, column=1, sticky=tk.EW); r += 1
        add_label_with_hint(f, r, "思考深度默认", "agents.defaults.thinkingDefault")
        self.vars["agents.defaults.thinkingDefault"] = tk.StringVar(value=d.get("thinkingDefault", "low"))
        _gui_combobox(f, self.vars["agents.defaults.thinkingDefault"], ["off", "minimal", "low", "medium", "high", "xhigh"], width_chars=14).grid(row=r, column=1, sticky=tk.W)
        self._add_more_button(f, 90, "models", skip=set(self.vars.keys()))
        f.columnconfigure(1, weight=1)

    def _rebuild_model_auth_panel(self):
        # 保存当前提供方的 API Key 到内存，再切换面板
        pv_cur = self.vars["model_auth.provider"].get()
        for t in self._all_providers():
            if t[1] == pv_cur:
                if t[2] in ("api_key", "paste_token") and t[3]:
                    self._provider_api_keys[t[0]] = self.vars["model_auth.api_key"].get().strip()
                break
        for w in self._model_auth_inner.winfo_children():
            w.destroy()
        self._ollama_models_frame.grid_remove()  # 非 Ollama 时隐藏
        pv = self.vars["model_auth.provider"].get()
        prov = None
        for t in self._all_providers():
            if t[1] == pv:
                prov = t
                break
        if not prov:
            prov = self._all_providers()[0]
        key, name, auth_type, env_var, default_model, get_key_url = prov
        # 自定义厂商入口：显示添加说明
        if auth_type == "custom":
            _gui_label(self._model_auth_inner, text="点击右侧「添加自定义厂商」按钮，输入厂商 Key、环境变量名和获取 Key 链接，即可添加任意兼容 OpenClaw 的模型厂商。", foreground="gray", wraplength=480).pack(anchor=tk.W)
            _gui_button(self._model_auth_inner, text="➕ 添加自定义厂商", command=self._show_add_custom_provider_dialog).pack(anchor=tk.W, pady=8)
            if self._custom_providers:
                _gui_label(self._model_auth_inner, text="已添加的自定义厂商会出现在上方下拉列表中，选择后填写 API Key 即可。", foreground="gray", wraplength=480).pack(anchor=tk.W)
            return
        if auth_type == "none":
            _gui_label(self._model_auth_inner, text="Ollama 无需认证；请在上方「主模型」填写如 ollama/llama3.3；下方可查看已安装模型并安装推荐模型。", foreground="gray", wraplength=480).pack(anchor=tk.W)
            btn_row_ollama = _gui_frame(self._model_auth_inner)
            btn_row_ollama.pack(anchor=tk.W, pady=6)
            _gui_link(btn_row_ollama, text="打开 Ollama 官网", command=lambda: open_url(OLLAMA_OFFICIAL_URL)).pack(side=tk.LEFT, padx=(0, 8))
            _gui_button(btn_row_ollama, text="在终端打开 Ollama", command=self._run_ollama_in_terminal).pack(side=tk.LEFT, padx=4)
            _gui_button(btn_row_ollama, text="在终端启动 OpenClaw", command=self._launch_openclaw_in_terminal).pack(side=tk.LEFT, padx=4)
            self._ollama_models_frame.grid()
            self._rebuild_ollama_models_panel()
            return
        self._ollama_models_frame.grid_remove()
        if auth_type == "api_key" and env_var:
            val = self._provider_api_keys.get(key) or self._config_env.get(env_var, "")
            self.vars["model_auth.api_key"].set(val)
            _gui_label(self._model_auth_inner, text=f"API Key（将写入配置 env，或使用环境变量 {env_var}）:").pack(anchor=tk.W)
            row = _gui_frame(self._model_auth_inner)
            row.pack(fill=tk.X, pady=2)
            _gui_entry(row, textvariable=self.vars["model_auth.api_key"], width_chars=44, show="*").pack(side=tk.LEFT, fill=tk.X, expand=True)
            if get_key_url:
                _gui_link(row, text="获取 API Key", command=lambda u=get_key_url: open_url(u)).pack(side=tk.LEFT, padx=4)
            if key == "anthropic":
                _gui_button(self._model_auth_inner, text="或：通过 CLI 粘贴订阅令牌 (paste-token)", command=lambda: self._run_model_auth_login("anthropic", paste_token=True)).pack(anchor=tk.W, pady=4)
            return
        if auth_type == "oauth":
            _gui_label(self._model_auth_inner, text="使用 OpenClaw 官方 CLI 在浏览器中完成 OAuth 登录。点击下方按钮启动登录流程。", wraplength=420).pack(anchor=tk.W)
            _gui_button(self._model_auth_inner, text="在浏览器中登录 (openclaw models auth login)", command=lambda: self._run_model_auth_login(key)).pack(anchor=tk.W, pady=4)
            return
        if auth_type == "paste_token":
            _gui_label(self._model_auth_inner, text="可填写 API Key，或点击下方通过 CLI 粘贴订阅令牌。", wraplength=420).pack(anchor=tk.W)
            if env_var:
                val = self._provider_api_keys.get(key) or self._config_env.get(env_var, "")
                self.vars["model_auth.api_key"].set(val)
                row = _gui_frame(self._model_auth_inner)
                row.pack(fill=tk.X, pady=2)
                _gui_entry(row, textvariable=self.vars["model_auth.api_key"], width_chars=44, show="*").pack(side=tk.LEFT, fill=tk.X, expand=True)
            _gui_button(self._model_auth_inner, text="通过 CLI 粘贴令牌 (paste-token)", command=lambda: self._run_model_auth_login(key, paste_token=True)).pack(anchor=tk.W, pady=4)
            return
        _gui_label(self._model_auth_inner, text="请选择上方认证提供方。", foreground="gray").pack(anchor=tk.W)

    def _run_onboard_in_terminal(self):
        """在系统终端中运行 openclaw onboard，以便用户可交互。"""
        ok, msg = run_in_system_terminal("openclaw onboard")
        if not ok:
            messagebox.showerror("无法打开终端", msg)

    def _run_model_auth_login(self, provider_key, paste_token=False):
        """在系统终端中运行 openclaw models auth login 或 paste-token，便于交互与浏览器登录。"""
        if paste_token:
            cmd = f"openclaw models auth paste-token --provider {provider_key}"
            name = "粘贴令牌"
        else:
            cmd = f"openclaw models auth login --provider {provider_key}"
            name = "模型认证登录"
        ok, msg = run_in_system_terminal(cmd)
        if not ok:
            messagebox.showerror(name, msg)

    def _rebuild_ollama_models_panel(self, installed=None):
        """当认证提供方为 Ollama 时，填充「Ollama 模型」区域。installed=None 时先显示加载中并异步请求 Ollama API，避免启动卡顿。"""
        for w in self._ollama_models_frame.winfo_children():
            w.destroy()
        if not hasattr(self, "_ollama_search_var"):
            self._ollama_search_var = tk.StringVar()
        if not hasattr(self, "_ollama_rec_page"):
            self._ollama_rec_page = 0
        inner = ttk.Frame(self._ollama_models_frame)
        inner.pack(fill=tk.BOTH, expand=True)
        # 已安装的模型（来自 Ollama API）；installed=None 时同步加载，避免在后台线程中调用 Tk 造成崩溃
        if installed is None:
            try:
                installed = get_ollama_installed_models()
            except Exception:
                installed = []
        _gui_label(inner, text="已安装的模型（来自 Ollama）", font=("", 9, "bold")).pack(anchor=tk.W)
        if not installed:
            _gui_label(inner, text="未检测到已安装模型（请确认 Ollama 已运行：ollama serve），或点击下方推荐模型进行安装。", foreground="gray", wraplength=500).pack(anchor=tk.W, pady=2)
        else:
            inst_frame = _gui_frame(inner)
            inst_frame.pack(anchor=tk.W, pady=4)
            for name, size_bytes in installed:
                row = _gui_frame(inst_frame)
                row.pack(anchor=tk.W)
                _gui_label(row, text=f"  {name}  —  {_format_size(size_bytes)}").pack(side=tk.LEFT)
                hint_lb = _gui_label(row, text=" (?)")
                hint_lb.pack(side=tk.LEFT, padx=(2, 0))
                ToolTip(hint_lb, _ollama_installed_model_tooltip(name, size_bytes))
                _gui_link(row, text="设为主模型", command=lambda n=name: self._set_primary_ollama_model(n)).pack(side=tk.LEFT, padx=6)
        _gui_separator(inner, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        _gui_label(inner, text="推荐模型（全部，可搜索；每页 10 个；点击「在终端中安装」执行 ollama pull）", font=("", 9, "bold")).pack(anchor=tk.W)
        search_row = _gui_frame(inner)
        search_row.pack(anchor=tk.W, pady=4)
        _gui_label(search_row, text="搜索（名称/大小/硬件）:").pack(side=tk.LEFT, padx=(0, 4))
        search_ent = _gui_entry(search_row, textvariable=self._ollama_search_var, width_chars=36)
        search_ent.pack(side=tk.LEFT)
        if hasattr(self, "_ollama_search_trace_id"):
            try:
                self._ollama_search_var.trace_remove("write", self._ollama_search_trace_id)
            except Exception:
                pass
        self._ollama_search_trace_id = self._ollama_search_var.trace_add("write", lambda *a: self._ollama_on_search_or_page())
        self._ollama_rec_inner = _gui_frame(inner)
        self._ollama_rec_inner.pack(anchor=tk.W, pady=4)
        pagination_row = _gui_frame(inner)
        pagination_row.pack(anchor=tk.W, pady=4)
        self._ollama_rec_prev_btn = _gui_button(pagination_row, text="上一页", command=self._ollama_prev_page)
        self._ollama_rec_prev_btn.pack(side=tk.LEFT, padx=4)
        self._ollama_rec_page_label = _gui_label(pagination_row, text="第 1/1 页（共 0 个）")
        self._ollama_rec_page_label.pack(side=tk.LEFT, padx=8)
        self._ollama_rec_next_btn = _gui_button(pagination_row, text="下一页", command=self._ollama_next_page)
        self._ollama_rec_next_btn.pack(side=tk.LEFT, padx=4)
        _gui_button(inner, text="刷新已安装列表", command=self._rebuild_ollama_models_panel).pack(anchor=tk.W, pady=4)
        self._refresh_ollama_recommended_list()

    def _ollama_on_search_or_page(self):
        """搜索或翻页后重置到第一页并刷新推荐列表。"""
        self._ollama_rec_page = 0
        self._refresh_ollama_recommended_list()

    def _ollama_prev_page(self):
        """上一页。"""
        if self._ollama_rec_page > 0:
            self._ollama_rec_page -= 1
            self._refresh_ollama_recommended_list()

    def _ollama_next_page(self):
        """下一页。"""
        total = len(self._ollama_filtered_models())
        total_pages = max(1, (total + OLLAMA_PAGE_SIZE - 1) // OLLAMA_PAGE_SIZE)
        if self._ollama_rec_page < total_pages - 1:
            self._ollama_rec_page += 1
            self._refresh_ollama_recommended_list()

    def _ollama_filtered_models(self):
        """根据搜索框内容过滤推荐模型列表。"""
        q = (self._ollama_search_var.get() or "").strip().lower()
        if not q:
            return list(OLLAMA_RECOMMENDED)
        return [
            (name, size, hw) for name, size, hw in OLLAMA_RECOMMENDED
            if q in name.lower() or q in (size or "").lower() or q in (hw or "").lower()
        ]

    def _refresh_ollama_recommended_list(self):
        """根据搜索与当前页刷新推荐模型区域（仅显示当前页 10 条）。"""
        if not getattr(self, "_ollama_rec_inner", None):
            return
        for w in self._ollama_rec_inner.winfo_children():
            w.destroy()
        filtered = self._ollama_filtered_models()
        total = len(filtered)
        page_size = OLLAMA_PAGE_SIZE
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(0, min(self._ollama_rec_page, total_pages - 1))
        self._ollama_rec_page = page
        start = page * page_size
        page_items = filtered[start : start + page_size]
        for model_name, size_desc, hw in page_items:
            row = _gui_frame(self._ollama_rec_inner)
            row.pack(anchor=tk.W)
            _gui_label(row, text=f"  {model_name}  —  {size_desc}  —  {hw}").pack(side=tk.LEFT)
            hint_lb = _gui_label(row, text=" (?)")
            hint_lb.pack(side=tk.LEFT, padx=(2, 0))
            ToolTip(hint_lb, _ollama_recommended_model_tooltip(model_name, size_desc, hw))
            tag_var = tk.StringVar(value="默认")
            tag_cb = _gui_combobox(row, tag_var, OLLAMA_TAG_OPTIONS, width_chars=10)
            tag_cb.pack(side=tk.LEFT, padx=4)
            _gui_label(row, text="规格(可输)").pack(side=tk.LEFT, padx=(0, 2))
            _gui_link(row, text="在终端中安装", command=lambda m=model_name, v=tag_var: self._ollama_pull_in_terminal(m, v.get())).pack(side=tk.LEFT, padx=6)
        self._ollama_rec_page_label.configure(text=f"第 {page + 1}/{total_pages} 页（共 {total} 个）")
        self._ollama_rec_prev_btn.configure(state=tk.NORMAL if page > 0 else "disabled")
        self._ollama_rec_next_btn.configure(state=tk.NORMAL if page < total_pages - 1 else "disabled")

    def _set_primary_ollama_model(self, model_name):
        """将主模型设为 ollama/<name>（仅改 UI 变量，保存时生效）。"""
        self.vars["agents.defaults.model.primary"].set(f"ollama/{model_name}")

    def _ollama_pull_in_terminal(self, model_name, tag=None):
        """在系统终端中执行 ollama pull <model_name> 或 ollama pull <model_name>:<tag>。tag 为空或「默认」时拉取默认标签。"""
        tag = (tag or "").strip()
        if tag in ("", "默认"):
            pull_arg = model_name
        else:
            pull_arg = f"{model_name}:{tag}"
        ok, msg = run_in_system_terminal(f"ollama pull {pull_arg}")
        if not ok:
            messagebox.showerror("Ollama 安装", msg)

    def _channel_plugin_installed_keys(self):
        """已安装的通道插件在 config 中的 key（feishu, mattermost, msteams）。"""
        installs = (self.config.get("plugins") or {}).get("installs") or {}
        return set(k for k in installs if isinstance(installs.get(k), dict))

    def add_tab_channels(self, f):
        ch = self.config.get("channels") or {}
        defaults = ch.get("defaults") or {}
        r = 0
        # 通道插件安装（已安装的灰色不可选，未安装的可勾选；安装成功后自动提示并刷新）
        _gui_label(f, text="通道插件安装（需联网；安装时会先打开官网，再在命令行弹窗中执行；已安装的显示为灰色不可选）", font=("", 9, "bold")).grid(row=r, column=0, columnspan=4, sticky=tk.W); r += 1
        plugin_frame = _gui_frame(f)
        plugin_frame.grid(row=r, column=0, columnspan=4, sticky=tk.W, pady=4); r += 1
        self._channel_plugin_frame = plugin_frame
        self._channel_plugin_vars = []
        self._channel_plugin_widgets = []  # (pkg, name, var, cb_or_label)
        installed_keys = self._channel_plugin_installed_keys()
        for pkg, name in CHANNEL_PLUGINS:
            key = pkg.split("/")[-1]
            is_installed = key in installed_keys
            var = tk.BooleanVar(value=False)
            self._channel_plugin_vars.append(var)
            if is_installed:
                lb = _gui_label(plugin_frame, text=f"{name} (已安装)")
                lb.pack(anchor=tk.W)
                self._channel_plugin_widgets.append((pkg, name, var, lb))
            else:
                cb = _gui_checkbox(plugin_frame, text=name, variable=var)
                cb.pack(anchor=tk.W)
                self._channel_plugin_widgets.append((pkg, name, var, cb))
        btn_plugin = _gui_frame(f)
        btn_plugin.grid(row=r, column=0, columnspan=4, sticky=tk.W, pady=6); r += 1
        _gui_button(btn_plugin, text="安装选中的通道插件", command=lambda: self._install_channel_plugins(selected_only=True)).pack(side=tk.LEFT, padx=4)
        make_action_dropdown(btn_plugin, "更多插件操作 ▼", [
            ("安装未安装的通道插件", lambda: self._install_channel_plugins(selected_only=False)),
            ("刷新已安装状态", self._refresh_channel_plugin_list),
        ], width=16).pack(side=tk.LEFT)
        r += 1
        self._add_tab_channels_rest(f, ch, defaults, r)

    def _refresh_channel_plugin_list(self):
        """根据当前 config 重新生成通道插件列表（已安装的灰色不可选）。"""
        if not getattr(self, "_channel_plugin_frame", None):
            return
        self.config = load_config()
        if isinstance(self.config, dict) and self.config.get("_load_error"):
            return
        for w in self._channel_plugin_frame.winfo_children():
            w.destroy()
        self._channel_plugin_vars = []
        self._channel_plugin_widgets = []
        installed_keys = self._channel_plugin_installed_keys()
        for pkg, name in CHANNEL_PLUGINS:
            key = pkg.split("/")[-1]
            is_installed = key in installed_keys
            var = tk.BooleanVar(value=False)
            self._channel_plugin_vars.append(var)
            if is_installed:
                lb = _gui_label(self._channel_plugin_frame, text=f"{name} (已安装)")
                lb.pack(anchor=tk.W)
                self._channel_plugin_widgets.append((pkg, name, var, lb))
            else:
                cb = _gui_checkbox(self._channel_plugin_frame, text=name, variable=var)
                cb.pack(anchor=tk.W)
                self._channel_plugin_widgets.append((pkg, name, var, cb))

    def _add_tab_channels_rest(self, f, ch, defaults, r):
        """通道页后半部分：重复插件说明、默认策略、各通道配置。"""
        dup_help = _gui_frame(f)
        dup_help.grid(row=r, column=0, columnspan=4, sticky=tk.W, pady=6); r += 1
        _gui_label(dup_help, text="若启动出现「duplicate plugin id」警告（feishu/mattermost/msteams）：表示同一插件被内建与扩展目录各加载一次。", font=("", 8), foreground="gray").pack(anchor=tk.W)
        _gui_button(dup_help, text="清除重复警告（将扩展目录重命名为 .bak 不再加载）", command=self._hide_duplicate_channel_extensions).pack(anchor=tk.W, pady=2)
        _gui_separator(f, orient=tk.HORIZONTAL).grid(row=r, column=0, columnspan=4, sticky=tk.EW, pady=8); r += 1
        add_label_with_hint(f, r, "默认群组策略", "channels.defaults.groupPolicy")
        self.vars["channels.defaults.groupPolicy"] = tk.StringVar(value=GROUP_POLICY_DISPLAY.get(defaults.get("groupPolicy", "allowlist"), "allowlist（仅允许列表中的群）"))
        _gui_combobox(f, self.vars["channels.defaults.groupPolicy"], GROUP_POLICY_DISPLAY_LIST, width_chars=28).grid(row=r, column=1, sticky=tk.W, padx=(8, 0)); r += 1
        add_label_with_hint(f, r, "默认 DM 策略", "channels.defaults.dmPolicy")
        self.vars["channels.defaults.dmPolicy"] = tk.StringVar(value=DM_POLICY_DISPLAY.get(defaults.get("dmPolicy", "pairing"), "pairing（需验证码配对）"))
        _gui_combobox(f, self.vars["channels.defaults.dmPolicy"], DM_POLICY_DISPLAY_LIST, width_chars=28).grid(row=r, column=1, sticky=tk.W, padx=(8, 0)); r += 1
        _gui_separator(f, orient=tk.HORIZONTAL).grid(row=r, column=0, columnspan=4, sticky=tk.EW, pady=8); r += 1

        # 支持配对的通道 key 列表，用于在每个通道后显示配对区
        pairing_channel_keys = [pk for pk, _ in PAIRING_CHANNELS]
        self._pairing_code_vars = {}

        # (ch_key, 显示名, 是否有Token字段, token变量名botToken/token, Token获取URL键, 是否有群组策略)
        channels_list = [
            ("telegram", "Telegram", True, "botToken", "telegram", True),
            ("discord", "Discord", True, "token", "discord", False),
            ("whatsapp", "WhatsApp", False, None, "whatsapp", False),
            ("slack", "Slack", True, "botToken", "slack", False),
            ("signal", "Signal", False, None, "signal", False),
            ("feishu", "飞书 Feishu/Lark", True, "appId", "feishu", False),
            ("googlechat", "Google Chat", True, "serviceAccount", "googlechat", False),
            ("mattermost", "Mattermost", True, "botToken", "mattermost", False),
            ("msteams", "Microsoft Teams", True, "appId", "msteams", False),
            ("irc", "IRC", True, "password", "irc", False),
            ("bluebubbles", "BlueBubbles (iMessage)", True, "serverUrl", "bluebubbles", False),
            ("imessage", "iMessage (macOS 传统)", False, None, "imessage", False),
        ]
        for ch_key, label, has_token, token_field, url_key, has_gp in channels_list:
            cfg = ch.get(ch_key) or {}
            self.vars[f"channels.{ch_key}.enabled"] = tk.BooleanVar(value=cfg.get("enabled", False))
            cb = _gui_checkbox(f, text=f"启用 {label}", variable=self.vars[f"channels.{ch_key}.enabled"])
            cb.grid(row=r, column=0, columnspan=2, sticky=tk.W)
            ToolTip(cb, PARAM_HINTS.get(f"channels.{ch_key}.enabled", ""))
            if url_key in CHANNEL_TOKEN_URLS:
                _, link_url = CHANNEL_TOKEN_URLS[url_key]
                _gui_link(f, text="🌐 获取 Token / 文档", command=lambda u=link_url: open_url(u)).grid(row=r, column=1, columnspan=2, sticky=tk.W, padx=(12, 0))
            r += 1
            if has_token and token_field:
                if token_field == "appId" and ch_key == "feishu":
                    add_label_with_hint(f, r, f"  {label} App ID", "channels.telegram.botToken")
                    self.vars["channels.feishu.appId"] = tk.StringVar(value=cfg.get("appId", ""))
                    _gui_entry(f, textvariable=self.vars["channels.feishu.appId"], width_chars=36).grid(row=r, column=1, sticky=tk.EW, padx=(8, 0))
                    r += 1
                    add_label_with_hint(f, r, "  飞书 App Secret", "channels.telegram.botToken")
                    self.vars["channels.feishu.appSecret"] = tk.StringVar(value=cfg.get("appSecret", ""))
                    _gui_entry(f, textvariable=self.vars["channels.feishu.appSecret"], width_chars=36, show="*").grid(row=r, column=1, sticky=tk.EW, padx=(8, 0))
                    feishu_act = _gui_frame(f)
                    feishu_act.grid(row=r, column=2, sticky=tk.W, padx=(12, 0))
                    _gui_link(feishu_act, text="验证", command=lambda: self._run_channel_verify("飞书", lambda: verify_feishu_credentials(
                        self.vars["channels.feishu.appId"].get(), self.vars["channels.feishu.appSecret"].get()))).pack(side=tk.LEFT, padx=(0, 4))
                    make_action_dropdown(
                        feishu_act, "操作 ▼",
                        [
                            ("配对说明", lambda: self._show_channel_setup_guide("feishu")),
                            ("连接排查", self._show_feishu_troubleshoot),
                            ("安装飞书 SDK", self._feishu_install_sdk),
                            ("飞书 SDK 文档", lambda: open_url(FEISHU_SDK_DOC_URL)),
                            ("在终端中查看待配对列表", lambda: self._run_pairing_list_terminal_for_channel("feishu")),
                        ],
                        width=12,
                    ).pack(side=tk.LEFT)
                elif ch_key == "msteams":
                    add_label_with_hint(f, r, f"  {label} App ID", "channels.telegram.botToken")
                    self.vars["channels.msteams.appId"] = tk.StringVar(value=cfg.get("appId", ""))
                    _gui_entry(f, textvariable=self.vars["channels.msteams.appId"], width_chars=36).grid(row=r, column=1, sticky=tk.EW, padx=(8, 0))
                    r += 1
                    add_label_with_hint(f, r, "  Teams App Password", "channels.telegram.botToken")
                    self.vars["channels.msteams.appPassword"] = tk.StringVar(value=cfg.get("appPassword", ""))
                    _gui_entry(f, textvariable=self.vars["channels.msteams.appPassword"], width_chars=36, show="*").grid(row=r, column=1, sticky=tk.EW, padx=(8, 0))
                elif token_field == "serviceAccount":
                    add_label_with_hint(f, r, f"  {label} 服务账号 JSON 路径", "channels.telegram.botToken")
                    self.vars["channels.googlechat.serviceAccountFile"] = tk.StringVar(value=cfg.get("serviceAccountFile", ""))
                    _gui_entry(f, textvariable=self.vars["channels.googlechat.serviceAccountFile"], width_chars=40).grid(row=r, column=1, sticky=tk.EW, padx=(8, 0))
                elif token_field == "serverUrl":
                    add_label_with_hint(f, r, f"  {label} 服务器 URL", "channels.telegram.botToken")
                    self.vars["channels.bluebubbles.serverUrl"] = tk.StringVar(value=cfg.get("serverUrl", ""))
                    _gui_entry(f, textvariable=self.vars["channels.bluebubbles.serverUrl"], width_chars=40).grid(row=r, column=1, sticky=tk.EW, padx=(8, 0))
                    r += 1
                    self.vars["channels.bluebubbles.password"] = tk.StringVar(value=cfg.get("password", ""))
                    _gui_label(f, text="  密码").grid(row=r, column=0, sticky=tk.W)
                    _gui_entry(f, textvariable=self.vars["channels.bluebubbles.password"], width_chars=36, show="*").grid(row=r, column=1, sticky=tk.EW, padx=(8, 0))
                else:
                    add_label_with_hint(f, r, f"  {label} Token", f"channels.{ch_key}.{token_field}")
                    key = f"channels.{ch_key}.botToken" if token_field == "botToken" else f"channels.{ch_key}.token"
                    if ch_key == "irc":
                        key = "channels.irc.nickservPassword"
                        self.vars[key] = tk.StringVar(value=(cfg.get("nickserv") or {}).get("password", ""))
                    else:
                        self.vars[key] = tk.StringVar(value=cfg.get("botToken", "") or cfg.get("token", ""))
                    _gui_entry(f, textvariable=self.vars[key], width_chars=44, show="*").grid(row=r, column=1, sticky=tk.EW, padx=(8, 0))
                    if ch_key == "telegram":
                        tg_act = _gui_frame(f)
                        tg_act.grid(row=r, column=2, sticky=tk.W, padx=(12, 0))
                        _gui_link(tg_act, text="验证", command=lambda: self._run_channel_verify("Telegram", lambda: verify_telegram_token(self.vars["channels.telegram.botToken"].get()))).pack(side=tk.LEFT, padx=(0, 4))
                        make_action_dropdown(tg_act, "操作 ▼", [
                            ("配对说明", lambda: self._show_channel_setup_guide("telegram")),
                            ("在终端中查看待配对列表", lambda: self._run_pairing_list_terminal_for_channel("telegram")),
                        ], width=14).pack(side=tk.LEFT)
                    elif ch_key == "discord":
                        dc_act = _gui_frame(f)
                        dc_act.grid(row=r, column=2, sticky=tk.W, padx=(12, 0))
                        _gui_link(dc_act, text="验证", command=lambda: self._run_channel_verify("Discord", lambda: verify_discord_token(self.vars["channels.discord.token"].get()))).pack(side=tk.LEFT, padx=(0, 4))
                        make_action_dropdown(dc_act, "操作 ▼", [
                            ("配对说明", lambda: self._show_channel_setup_guide("discord")),
                            ("在终端中查看待配对列表", lambda: self._run_pairing_list_terminal_for_channel("discord")),
                        ], width=14).pack(side=tk.LEFT)
                    elif ch_key == "slack":
                        sl_act = _gui_frame(f)
                        sl_act.grid(row=r, column=2, sticky=tk.W, padx=(12, 0))
                        _gui_link(sl_act, text="验证", command=lambda: self._run_channel_verify("Slack", lambda: verify_slack_token(self.vars["channels.slack.botToken"].get()))).pack(side=tk.LEFT, padx=(0, 4))
                        make_action_dropdown(sl_act, "操作 ▼", [
                            ("配对说明", lambda: self._show_channel_setup_guide("slack")),
                            ("在终端中查看待配对列表", lambda: self._run_pairing_list_terminal_for_channel("slack")),
                        ], width=14).pack(side=tk.LEFT)
                r += 1
                if ch_key == "slack":
                    add_label_with_hint(f, r, "  Slack App Token (xapp-)", "channels.slack.appToken")
                    self.vars["channels.slack.appToken"] = tk.StringVar(value=cfg.get("appToken", ""))
                    _gui_entry(f, textvariable=self.vars["channels.slack.appToken"], width_chars=44, show="*").grid(row=r, column=1, sticky=tk.EW, padx=(8, 0)); r += 1
            add_label_with_hint(f, r, f"  {label} DM 策略", "channels.dmPolicy")
            self.vars[f"channels.{ch_key}.dmPolicy"] = tk.StringVar(value=DM_POLICY_DISPLAY.get(cfg.get("dmPolicy", "pairing"), "pairing（需验证码配对）"))
            _gui_combobox(f, self.vars[f"channels.{ch_key}.dmPolicy"], DM_POLICY_DISPLAY_LIST, width_chars=28).grid(row=r, column=1, sticky=tk.W, padx=(8, 0)); r += 1
            add_label_with_hint(f, r, f"  {label} 允许来自 (逗号分隔)", "channels.allowFrom")
            af = cfg.get("allowFrom") or []
            self.vars[f"channels.{ch_key}.allowFrom"] = tk.StringVar(value=", ".join(af) if isinstance(af, list) else str(af))
            _gui_entry(f, textvariable=self.vars[f"channels.{ch_key}.allowFrom"], width_chars=44).grid(row=r, column=1, sticky=tk.EW, padx=(8, 0)); r += 1
            if has_gp:
                add_label_with_hint(f, r, f"  {label} 群组策略", "channels.telegram.groupPolicy")
                self.vars[f"channels.{ch_key}.groupPolicy"] = tk.StringVar(value=GROUP_POLICY_DISPLAY.get(cfg.get("groupPolicy", "allowlist"), "allowlist（仅允许列表中的群）"))
                _gui_combobox(f, self.vars[f"channels.{ch_key}.groupPolicy"], GROUP_POLICY_DISPLAY_LIST, width_chars=28).grid(row=r, column=1, sticky=tk.W, padx=(8, 0)); r += 1
            # 支持配对的通道：在每个通道后显示配对码输入与批准
            if ch_key in pairing_channel_keys:
                self._pairing_code_vars[ch_key] = tk.StringVar()
                pair_row = ttk.Frame(f)
                pair_row.grid(row=r, column=0, columnspan=4, sticky=tk.W, pady=(2, 4))
                pair_lbl = _gui_label(pair_row, text="  通道配对 ")
                pair_lbl.pack(side=tk.LEFT)
                pair_hint = PARAM_HINTS.get("channels.pairing", "")
                if pair_hint:
                    pair_info = _gui_label(pair_row, text=" (?)", foreground="gray")
                    pair_info.pack(side=tk.LEFT)
                    ToolTip(pair_info, pair_hint)
                    ToolTip(pair_lbl, pair_hint)
                _gui_label(pair_row, text="配对码:").pack(side=tk.LEFT, padx=(0, 4))
                _gui_entry(pair_row, textvariable=self._pairing_code_vars[ch_key], width_chars=12).pack(side=tk.LEFT, padx=(0, 8))
                _gui_link(pair_row, text="批准配对", command=lambda k=ch_key: self._run_pairing_approve_for_channel(k)).pack(side=tk.LEFT, padx=2)
                r += 1
            r += 1
        _gui_label(f, text="WhatsApp 需在终端运行: openclaw channels login。飞书/Teams 等需先安装插件: openclaw plugins install @openclaw/feishu", font=("", 8), foreground="gray").grid(row=r, column=0, columnspan=4, sticky=tk.W, pady=(4, 0))
        self._add_more_button(f, 90, "channels", skip=set(self.vars.keys()))
        f.columnconfigure(1, weight=1)

    def add_tab_web_search(self, f):
        t = self.config.get("tools") or {}
        tw = t.get("web") or {}
        ts = tw.get("search") or {}
        r = 0
        add_label_with_hint(f, r, "启用网页搜索", "tools.web.search.enabled")
        self.vars["tools.web.search.enabled"] = tk.BooleanVar(value=ts.get("enabled", False))
        _gui_checkbox(f, text="是", variable=self.vars["tools.web.search.enabled"]).grid(row=r, column=1, sticky=tk.W); r += 1
        add_label_with_hint(f, r, "搜索提供商", "tools.web.search.provider")
        self.vars["tools.web.search.provider"] = tk.StringVar(value=ts.get("provider", "perplexity"))
        _gui_combobox(f, self.vars["tools.web.search.provider"], ["perplexity", "brave", "gemini", "grok", "kimi"], width_chars=16).grid(row=r, column=1, sticky=tk.W); r += 1
        add_label_with_hint(f, r, "API Key", "tools.web.search.apiKey")
        self.vars["tools.web.search.apiKey"] = tk.StringVar(value=ts.get("apiKey", ""))
        api_key_row = _gui_frame(f)
        api_key_row.grid(row=r, column=1, sticky=tk.EW)
        _gui_entry(api_key_row, textvariable=self.vars["tools.web.search.apiKey"], width_chars=44, show="*").pack(side=tk.LEFT, fill=tk.X, expand=True)
        def _open_web_search_api_url():
            provider = (self.vars["tools.web.search.provider"].get() or "").strip() or "perplexity"
            url = WEB_SEARCH_PROVIDER_API_URLS.get(provider, WEB_SEARCH_PROVIDER_API_URLS["perplexity"])
            open_url(url)
        _gui_link(api_key_row, text="获取 API Key", command=_open_web_search_api_url).pack(side=tk.LEFT, padx=(6, 0))
        self._add_more_button(f, 90, "tools.web", skip=set(self.vars.keys()))
        f.columnconfigure(1, weight=1)

    def add_tab_session_tools(self, f):
        s = self.config.get("session") or {}
        t = self.config.get("tools") or {}
        reset = s.get("reset") or {}
        r = 0
        add_label_with_hint(f, r, "DM 会话范围 (dmScope)", "session.dmScope")
        self.vars["session.dmScope"] = tk.StringVar(value=s.get("dmScope", "per-channel-peer"))
        _gui_combobox(f, self.vars["session.dmScope"], ["main", "per-peer", "per-channel-peer", "per-account-channel-peer"], width_chars=28).grid(row=r, column=1, sticky=tk.W); r += 1
        add_label_with_hint(f, r, "会话重置模式", "session.reset.mode")
        mode_val = reset.get("mode", "idle")
        if mode_val not in ("daily", "idle"):
            mode_val = "idle"
        self.vars["session.reset.mode"] = tk.StringVar(value=mode_val)
        _gui_combobox(f, self.vars["session.reset.mode"], ["daily", "idle"], width_chars=14).grid(row=r, column=1, sticky=tk.W); r += 1
        add_label_with_hint(f, r, "每日重置时刻 (0–23)", "session.reset.atHour")
        self.vars["session.reset.atHour"] = tk.StringVar(value=str(reset.get("atHour", 4)))
        _gui_entry(f, textvariable=self.vars["session.reset.atHour"], width_chars=6).grid(row=r, column=1, sticky=tk.W); r += 1
        add_label_with_hint(f, r, "空闲多少分钟后重置", "session.reset.idleMinutes")
        self.vars["session.reset.idleMinutes"] = tk.StringVar(value=str(reset.get("idleMinutes", 120)))
        _gui_entry(f, textvariable=self.vars["session.reset.idleMinutes"], width_chars=8).grid(row=r, column=1, sticky=tk.W); r += 1
        add_label_with_hint(f, r, "工具策略 (profile)", "tools.profile")
        self.vars["tools.profile"] = tk.StringVar(value=t.get("profile", "coding"))
        _gui_combobox(f, self.vars["tools.profile"], ["coding", "default", "minimal", "full"], width_chars=14).grid(row=r, column=1, sticky=tk.W)
        self._add_more_button(f, 90, "session", skip=set(self.vars.keys()))
        f.columnconfigure(1, weight=1)

    def add_tab_commands(self, f):
        c = self.config.get("commands") or {}
        r = 0
        add_label_with_hint(f, r, "原生命令 (native)", "commands.native")
        self.vars["commands.native"] = tk.StringVar(value=c.get("native", "auto"))
        _gui_combobox(f, self.vars["commands.native"], ["auto", "true", "false"], width_chars=10).grid(row=r, column=1, sticky=tk.W); r += 1
        add_label_with_hint(f, r, "解析文本 /命令", "commands.text")
        self.vars["commands.text"] = tk.BooleanVar(value=c.get("text", True))
        _gui_checkbox(f, text="是", variable=self.vars["commands.text"]).grid(row=r, column=1, sticky=tk.W); r += 1
        add_label_with_hint(f, r, "允许 /restart", "commands.restart")
        self.vars["commands.restart"] = tk.BooleanVar(value=c.get("restart", True))
        _gui_checkbox(f, text="是", variable=self.vars["commands.restart"]).grid(row=r, column=1, sticky=tk.W); r += 1
        add_label_with_hint(f, r, "允许 /config 读写", "commands.config")
        self.vars["commands.config"] = tk.BooleanVar(value=c.get("config", False))
        _gui_checkbox(f, text="是（慎开）", variable=self.vars["commands.config"]).grid(row=r, column=1, sticky=tk.W)
        self._add_more_button(f, 90, "commands", skip=set(self.vars.keys()))
        f.columnconfigure(1, weight=1)

    def add_tab_finish(self, f):
        _gui_label(f, text="配置已按上述步骤填写完毕。请点击下方「保存配置」写入 ~/.openclaw/openclaw.json；").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=4)
        _gui_label(f, text="需要重启网关时点击「保存并重启 OpenClaw」。").grid(row=1, column=0, columnspan=2, sticky=tk.W)
        _gui_label(f, text="「一键启动 OpenClaw」与「保存并重启」会先保存当前界面配置再启动，确保通道等信息生效。", font=("", 9), foreground="gray").grid(row=2, column=0, columnspan=2, sticky=tk.W)
        _gui_label(f, text="打开「控制台 (Dashboard)」可在浏览器中使用 WebChat 与配置界面。", font=("", 9), foreground="gray").grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=8)

    def add_tab_skills(self, f):
        _gui_label(f, text="技能 (Skills)：为 Agent 提供额外能力。安装命令: npx clawhub@latest install <技能名>；安装时会先打开 ClawHub 官网，再在命令行弹窗中执行。", font=("", 9)).grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 2))
        _gui_label(f, text="若终端出现 Rate limit exceeded：多为请求过于频繁，请稍后重试或一次只选一个技能安装；多选时已自动在安装间隔约 15 秒。", font=("", 8), foreground="gray").grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(0, 4))
        _gui_label(f, text="搜索（名称/描述）:").grid(row=2, column=0, sticky=tk.W)
        self.skill_search_var = tk.StringVar()
        self.skill_search_var.trace_add("write", lambda *a: self._filter_skill_checkboxes())
        _gui_entry(f, textvariable=self.skill_search_var, width_chars=40).grid(row=2, column=1, sticky=tk.EW, pady=2, padx=(8, 4))
        link_btn_row = _gui_frame(f)
        link_btn_row.grid(row=2, column=2, sticky=tk.W, padx=4)
        _gui_link(link_btn_row, text="打开 ClawHub 技能官网", command=lambda: open_url("https://clawhub.com")).pack(side=tk.LEFT)
        _gui_button(link_btn_row, text="安装教程", command=self._show_skill_install_guide).pack(side=tk.LEFT, padx=(8, 0))
        _gui_label(f, text="技能列表（勾选未安装的点击「安装选中」；已安装的显示「(已安装)」可点击「卸载」）:").grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))
        btn_row = _gui_frame(f)
        btn_row.grid(row=4, column=0, columnspan=3, sticky=tk.W, pady=(4, 4))
        _gui_button(btn_row, text="全选", command=self._skill_select_all).pack(side=tk.LEFT, padx=2)
        _gui_button(btn_row, text="取消全选", command=self._skill_deselect_all).pack(side=tk.LEFT, padx=2)
        _gui_button(btn_row, text="刷新列表", command=self._refresh_skill_list).pack(side=tk.LEFT, padx=4)
        _gui_button(btn_row, text="安装选中技能", command=self._install_selected_skills).pack(side=tk.LEFT, padx=4)
        list_outer = _gui_frame(f, **({"fg_color": ("gray88", "gray20")} if ctk else {}))
        list_outer.grid(row=5, column=0, columnspan=3, sticky=tk.NSEW, pady=(0, 4))
        skill_canvas = tk.Canvas(list_outer, highlightthickness=0)
        skill_vbar = ttk.Scrollbar(list_outer)
        self.skill_inner_frame = ttk.Frame(skill_canvas, padding=4)
        for col in range(3):
            self.skill_inner_frame.columnconfigure(col, weight=1)
        self.skill_inner_id = skill_canvas.create_window(0, 0, window=self.skill_inner_frame, anchor=tk.NW)
        skill_canvas.configure(yscrollcommand=skill_vbar.set)
        skill_vbar.configure(command=skill_canvas.yview)
        self.skill_inner_frame.bind("<Configure>", lambda e: skill_canvas.configure(scrollregion=skill_canvas.bbox("all")))
        skill_canvas.bind("<Configure>", lambda e: skill_canvas.itemconfig(self.skill_inner_id, width=e.width))
        skill_canvas.bind("<MouseWheel>", lambda e: skill_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        skill_canvas.bind("<Button-4>", lambda e: skill_canvas.yview_scroll(-4, "units"))
        skill_canvas.bind("<Button-5>", lambda e: skill_canvas.yview_scroll(4, "units"))
        skill_vbar.pack(side=tk.RIGHT, fill=tk.Y)
        skill_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.skill_canvas = skill_canvas
        self.skill_desc_label = _gui_label(f, text="")
        self.skill_desc_label.grid(row=6, column=0, columnspan=3, sticky=tk.W, pady=4)
        f.columnconfigure(1, weight=1)
        f.rowconfigure(5, weight=1)
        self._skill_names = sorted(SKILL_ZH.keys())
        self.skill_vars = {}
        self.skill_rows = {}
        for i, name in enumerate(self._skill_names):
            var = tk.BooleanVar(value=False)
            self.skill_vars[name] = var
            row_f = _gui_frame(self.skill_inner_frame)
            cb = _gui_checkbox(row_f, text=name, variable=var)
            cb.pack(side=tk.LEFT)
            ToolTip(cb, SKILL_ZH.get(name, ""))
            lbl = _gui_label(row_f, text="")
            lbl.pack(side=tk.LEFT, padx=8)
            uninstall_btn = _gui_link(row_f, text="卸载", command=lambda n=name: self._uninstall_skill(n))
            self.skill_rows[name] = (row_f, cb, lbl, uninstall_btn)
        self._update_skill_installed_states()
        self._filter_skill_checkboxes()

    def _filter_skill_checkboxes(self):
        q = (self.skill_search_var.get() or "").strip().lower()
        visible = [name for name in self._skill_names if not q or q in name.lower() or (SKILL_ZH.get(name) or "").lower().find(q) >= 0]
        for name in self._skill_names:
            row_f = self.skill_rows[name][0]
            row_f.grid_remove()
        for i, name in enumerate(visible):
            r, c = i // 3, i % 3
            self.skill_rows[name][0].grid(row=r, column=c, sticky=tk.W, padx=4, pady=2)

    def _skill_select_all(self):
        q = (self.skill_search_var.get() or "").strip().lower()
        for name in self._skill_names:
            desc = (SKILL_ZH.get(name) or "").lower()
            if not q or q in name.lower() or q in desc:
                self.skill_vars[name].set(True)

    def _skill_deselect_all(self):
        for var in self.skill_vars.values():
            var.set(False)

    def _installed_skills(self):
        """返回当前工作区下已安装技能名称集合（workspace/skills 下含 SKILL.md 的子目录名）。"""
        workspace = (self.vars.get("agents.defaults.workspace") and self.vars["agents.defaults.workspace"].get()) or str(CONFIG_DIR / "workspace")
        workspace = os.path.expanduser(workspace.strip())
        skills_dir = Path(workspace) / "skills"
        if not skills_dir.exists():
            return set()
        return set(d.name for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists())

    def _update_skill_installed_states(self):
        """根据工作区 skills 目录更新每行「已安装」标签与卸载按钮显示。"""
        installed = self._installed_skills()
        for name in self._skill_names:
            row_f, cb, lbl, uninstall_btn = self.skill_rows[name]
            if name in installed:
                lbl.configure(text="(已安装)")
                uninstall_btn.pack(side=tk.LEFT, padx=4)
            else:
                lbl.configure(text="")
                uninstall_btn.pack_forget()

    def _refresh_skill_list(self):
        self._update_skill_installed_states()
        self._filter_skill_checkboxes()

    def _install_selected_skills(self):
        """安装技能：仅安装未安装的；先打开 ClawHub 官网，再在系统终端中执行 npx clawhub@latest install。多技能时在命令间加入间隔以降低 Rate limit 风险。"""
        selected = [name for name in self._skill_names if self.skill_vars.get(name) and self.skill_vars[name].get()]
        if not selected:
            messagebox.showinfo("技能", "请先勾选要安装的技能。")
            return
        installed = self._installed_skills()
        names = [n for n in selected if n not in installed]
        if not names:
            messagebox.showinfo("技能", "所选技能均已安装，无需重复安装。")
            return
        workspace = (self.vars.get("agents.defaults.workspace") and self.vars["agents.defaults.workspace"].get()) or str(CONFIG_DIR / "workspace")
        workspace = os.path.expanduser(workspace.strip())
        Path(workspace).mkdir(parents=True, exist_ok=True)
        open_url(CLAWHUB_URL)
        install_cmds = [f"{SKILL_INSTALL_CMD} {name}" for name in names]
        # 多个技能时在命令间加入 sleep，降低 npm/ClawHub Rate limit exceeded 概率（仅 Unix）
        if len(install_cmds) > 1 and sys.platform != "win32":
            delay = f"sleep {SKILL_INSTALL_DELAY_SEC}"
            cmd = f'cd "{workspace}" && ' + f" && {delay} && ".join(install_cmds)
        else:
            cmd = f'cd "{workspace}" && ' + " && ".join(install_cmds)
        ok, msg = run_in_system_terminal(cmd)
        if not ok:
            err = "技能安装启动失败：" + msg
            if "rate limit" in msg.lower() or "Rate limit" in msg:
                err += "\n\n若终端中显示 Rate limit exceeded：多为 npm/ClawHub 请求过于频繁，请稍后重试或一次只选一个技能安装。"
            messagebox.showerror("技能安装", err)
        self._update_skill_installed_states()

    def _uninstall_skill(self, skill_name):
        """在系统终端中执行 npx clawhub@latest uninstall <技能名>（ClawHub 官方卸载方式）。"""
        workspace = (self.vars.get("agents.defaults.workspace") and self.vars["agents.defaults.workspace"].get()) or str(CONFIG_DIR / "workspace")
        workspace = os.path.expanduser(workspace.strip())
        if not messagebox.askyesno("卸载技能", f"确定要在工作区中卸载技能「{skill_name}」吗？\n\n将执行: {SKILL_UNINSTALL_CMD} {skill_name}"):
            return
        cmd = f'cd "{workspace}" && {SKILL_UNINSTALL_CMD} {skill_name}'
        ok, msg = run_in_system_terminal(cmd)
        if not ok:
            messagebox.showerror("技能卸载", msg)
        self._update_skill_installed_states()

    def _add_more_button(self, f, row, domain_prefix, skip=None):
        """网格布局 tab 末尾加「更多 ▸」：点击惰性展开该域 schema 全部字段（可无穷配置）。
        schema 不可用则不显示。按钮在 row，展开区在 row+1。"""
        node = schema_node_at(domain_prefix)
        if not isinstance(node, dict) or not isinstance(node.get("properties"), dict):
            return
        holder = _gui_frame(f)
        holder.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(10, 2))
        expand = _gui_frame(f)
        expand.grid(row=row + 1, column=0, columnspan=2, sticky="we")
        expand.grid_remove()
        state = {"open": False, "rendered": False}
        btn = _gui_button(holder, "更多 ▸")
        btn.pack(side=tk.LEFT)
        _gui_label(holder, text="  展开「%s」的全部配置项（可无穷配置）" % domain_prefix,
                   foreground="gray").pack(side=tk.LEFT)

        def toggle():
            if not state["rendered"]:
                n = render_schema_fields(expand, node, domain_prefix, self.config,
                                         self._schema_vars, skip=(skip or set()))
                if n == 0:
                    _gui_label(expand, text="（无更多字段）", foreground="gray").pack(anchor="w")
                state["rendered"] = True
            state["open"] = not state["open"]
            if state["open"]:
                expand.grid()
                btn.configure(text="更多 ▾")
            else:
                expand.grid_remove()
                btn.configure(text="更多 ▸")

        btn.configure(command=toggle)

    def collect_into_config(self):
        patch = {}
        pv = self.vars.get("model_auth.provider") and self.vars["model_auth.provider"].get()
        for t in self._all_providers():
            if t[1] == pv and t[3]:
                self._provider_api_keys[t[0]] = (self.vars["model_auth.api_key"].get() or "").strip()
                break
        env_out = {}
        existing = self.config.get("env") or {}
        if isinstance(existing, dict):
            for k, v in existing.get("vars", {}).items():
                if isinstance(v, str):
                    env_out.setdefault(k, v)
            for k, v in existing.items():
                if k != "vars" and isinstance(v, str):
                    env_out.setdefault(k, v)
        for key, _name, _at, env_var, _dm, _url in self._all_providers():
            if not env_var:
                continue
            val = self._provider_api_keys.get(key, "").strip()
            if val:
                env_out[env_var] = val
        if env_out:
            patch["env"] = deep_merge(self.config.get("env") or {}, env_out)
        try:
            port = int(self.vars["gateway.port"].get().strip())
        except ValueError:
            port = 18789
        # 只写入我们编辑的项，与现有配置深合并，避免覆盖 meta/plugins/hooks 等导致启动失败
        gw = dict(self.config.get("gateway") or {})
        gw["port"] = port
        gw["mode"] = (gw.get("mode") or "local")  # 2026.6.10：gateway 默认强制 mode=local，缺失会拒绝启动
        gw["bind"] = (self.vars["gateway.bind"].get().strip() or "loopback")
        gw["auth"] = deep_merge(gw.get("auth") or {}, {
            "mode": (self.vars["gateway.auth.mode"].get().strip() or "token"),
            "token": self.vars["gateway.auth.token"].get().strip(),
            "password": self.vars["gateway.auth.password"].get().strip(),
        })
        gw["tailscale"] = deep_merge(gw.get("tailscale") or {}, {"mode": (self.vars["gateway.tailscale.mode"].get().strip() or "off")})
        gw["reload"] = deep_merge(gw.get("reload") or {}, {"mode": (self.vars["gateway.reload.mode"].get().strip() or "hybrid")})
        patch["gateway"] = gw

        workspace = (self.vars["agents.defaults.workspace"].get().strip() or str(CONFIG_DIR / "workspace")).strip()
        cur = (self.config.get("agents") or {}).get("defaults") or {}
        cur_model = cur.get("model") or {}
        if isinstance(cur_model, str):
            new_model = {}
        else:
            new_model = dict(cur_model)
        primary = (self.vars["agents.defaults.model.primary"].get().strip() or "").strip()
        if primary:
            new_model["primary"] = primary
        fb_str = (self.vars["agents.defaults.model.fallbacks"].get() or "").strip()
        if fb_str:
            new_model["fallbacks"] = [x.strip() for x in fb_str.split(",") if x.strip()]
        im_primary = (self.vars["agents.defaults.imageModel.primary"].get() or "").strip()
        defs = dict(cur)
        defs["workspace"] = workspace
        defs["model"] = new_model
        defs["skipBootstrap"] = self.vars["agents.defaults.skipBootstrap"].get()
        defs["thinkingDefault"] = (self.vars["agents.defaults.thinkingDefault"].get().strip() or "low")
        if im_primary:
            defs["imageModel"] = deep_merge(defs.get("imageModel") or {}, {"primary": im_primary})
        patch["agents"] = {"defaults": defs}

        ch_existing = dict(self.config.get("channels") or {})
        # 当前版本 channels.defaults 仅支持 groupPolicy，不写入 dmPolicy 避免 Unrecognized key
        ch_defaults = deep_merge(ch_existing.get("defaults") or {}, {
            "groupPolicy": _policy_display_to_value(self.vars["channels.defaults.groupPolicy"].get(), GROUP_POLICY_DISPLAY_TO_VALUE) or "allowlist",
        })
        ch_defaults.pop("dmPolicy", None)  # 从已合并的默认里也去掉，避免写入后校验报错
        patch["channels"] = dict(ch_existing)
        patch["channels"]["defaults"] = ch_defaults

        all_channel_keys = ("telegram", "discord", "whatsapp", "slack", "signal", "feishu", "googlechat", "mattermost", "msteams", "irc", "bluebubbles", "imessage")
        for ch_key in all_channel_keys:
            if f"channels.{ch_key}.enabled" not in self.vars:
                continue
            if not self.vars[f"channels.{ch_key}.enabled"].get():
                # 未勾选时也写入 enabled: false，使禁用状态被保存
                patch["channels"][ch_key] = deep_merge(ch_existing.get(ch_key) or {}, {"enabled": False})
                continue
            entry = {"enabled": True}
            entry["dmPolicy"] = _policy_display_to_value(self.vars[f"channels.{ch_key}.dmPolicy"].get(), DM_POLICY_DISPLAY_TO_VALUE) or "pairing"
            entry["allowFrom"] = [x.strip() for x in self.vars[f"channels.{ch_key}.allowFrom"].get().split(",") if x.strip()]
            if ch_key == "telegram":
                t = self.vars.get("channels.telegram.botToken")
                if t and t.get().strip():
                    entry["botToken"] = t.get().strip()
                g = self.vars.get("channels.telegram.groupPolicy")
                if g:
                    entry["groupPolicy"] = _policy_display_to_value(g.get(), GROUP_POLICY_DISPLAY_TO_VALUE) or "allowlist"
            elif ch_key == "discord":
                t = self.vars.get("channels.discord.token")
                if t and t.get().strip():
                    entry["token"] = t.get().strip()
            elif ch_key == "slack":
                bt = self.vars.get("channels.slack.botToken")
                if bt and bt.get().strip():
                    entry["botToken"] = bt.get().strip()
                at = self.vars.get("channels.slack.appToken")
                if at and at.get().strip():
                    entry["appToken"] = at.get().strip()
            elif ch_key == "feishu":
                ai = self.vars.get("channels.feishu.appId")
                as_ = self.vars.get("channels.feishu.appSecret")
                if ai and ai.get().strip():
                    entry["appId"] = ai.get().strip()
                if as_ and as_.get().strip():
                    entry["appSecret"] = as_.get().strip()
            elif ch_key == "googlechat":
                sf = self.vars.get("channels.googlechat.serviceAccountFile")
                if sf and sf.get().strip():
                    entry["serviceAccountFile"] = sf.get().strip()
            elif ch_key == "mattermost":
                bt = self.vars.get("channels.mattermost.botToken")
                if bt and bt.get().strip():
                    entry["botToken"] = bt.get().strip()
            elif ch_key == "msteams":
                ai = self.vars.get("channels.msteams.appId")
                ap = self.vars.get("channels.msteams.appPassword")
                if ai and ai.get().strip():
                    entry["appId"] = ai.get().strip()
                if ap and ap.get().strip():
                    entry["appPassword"] = ap.get().strip()
            elif ch_key == "irc":
                pw = self.vars.get("channels.irc.nickservPassword")
                if pw and pw.get().strip():
                    entry["nickserv"] = {"enabled": True, "password": pw.get().strip()}
            elif ch_key == "bluebubbles":
                su = self.vars.get("channels.bluebubbles.serverUrl")
                pa = self.vars.get("channels.bluebubbles.password")
                if su and su.get().strip():
                    entry["serverUrl"] = su.get().strip()
                if pa and pa.get().strip():
                    entry["password"] = pa.get().strip()
            patch["channels"][ch_key] = entry

        sess = dict(self.config.get("session") or {})
        patch["session"] = deep_merge(sess, {
            "dmScope": (self.vars["session.dmScope"].get().strip() or "per-channel-peer"),
            "reset": deep_merge(sess.get("reset") or {}, {
                "mode": (self.vars["session.reset.mode"].get().strip() or "idle") if (self.vars["session.reset.mode"].get().strip() in ("daily", "idle")) else "idle",
                "atHour": int((self.vars["session.reset.atHour"].get() or "4").strip() or "4"),
                "idleMinutes": int((self.vars["session.reset.idleMinutes"].get() or "120").strip() or "120"),
            }),
        })
        tools_cur = self.config.get("tools") or {}
        patch["tools"] = deep_merge(tools_cur, {
            "profile": (self.vars["tools.profile"].get().strip() or "coding"),
            "web": deep_merge(tools_cur.get("web") or {}, {
                "search": deep_merge((tools_cur.get("web") or {}).get("search") or {}, {
                    "enabled": self.vars["tools.web.search.enabled"].get(),
                    "provider": (self.vars["tools.web.search.provider"].get().strip() or "perplexity"),
                    "apiKey": (self.vars["tools.web.search.apiKey"].get() or "").strip(),
                }),
            }),
        })
        cmd_cur = self.config.get("commands") or {}
        patch["commands"] = deep_merge(cmd_cur, {
            "native": (self.vars["commands.native"].get().strip() or "auto"),
            "text": self.vars["commands.text"].get(),
            "restart": self.vars["commands.restart"].get(),
            "config": self.vars["commands.config"].get(),
        })

        # 「更多」schema 驱动字段：按点路径合并进 patch（空串跳过，避免用空值覆盖已有配置）
        for path, (var, kind) in self._schema_vars.items():
            try:
                raw = var.get()
            except Exception:
                continue
            if kind == "bool":
                _patch_set_path(patch, path, bool(raw))
                continue
            s = str(raw).strip()
            if s == "":
                continue
            if kind in ("num", "int"):
                try:
                    _patch_set_path(patch, path, int(s) if kind == "int" else float(s))
                except ValueError:
                    continue
            elif kind == "json":
                try:
                    _patch_set_path(patch, path, json.loads(s))
                except Exception:
                    continue
            else:  # str / enum
                _patch_set_path(patch, path, s)
        return patch

    def do_save(self):
        patch = self.collect_into_config()
        merged = deep_merge(self.config, patch)
        merged.pop("_load_error", None)  # 不写入磁盘，避免破坏 OpenClaw 解析
        try:
            save_config(merged)
            self.config = merged
            self._update_config_overview()
            messagebox.showinfo("保存", "配置已保存到\n" + str(CONFIG_FILE))
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def do_save_restart(self):
        self.do_save()
        port = None
        if isinstance(self.config, dict):
            port = (self.config.get("gateway") or {}).get("port")
        ok, msg = restart_openclaw(port=port)
        if ok:
            messagebox.showinfo("重启", msg)
        else:
            messagebox.showerror("重启失败", msg)

    def do_restart(self):
        """一键重启：不保存配置，仅重启 OpenClaw 网关（使用当前已保存的配置）。"""
        port = None
        if isinstance(self.config, dict):
            port = (self.config.get("gateway") or {}).get("port")
        ok, msg = restart_openclaw(port=port)
        if ok:
            messagebox.showinfo("重启", msg)
        else:
            messagebox.showerror("重启失败", msg)

    def do_oneclick_start(self):
        """一键启动 OpenClaw：先保存当前配置再启动，确保通道等信息生效；若未运行则后台启动，若已运行则提示并可打开控制台。"""
        self.do_save()
        port = 18789
        if isinstance(self.config, dict):
            port = (self.config.get("gateway") or {}).get("port", 18789)
        try:
            port = int(port)
        except (TypeError, ValueError):
            port = 18789
        if check_gateway_running(port):
            if messagebox.askyesno("一键启动 OpenClaw", "OpenClaw 网关已在运行。\n是否打开控制台 (Dashboard)？"):
                self.open_dashboard()
            return
        ok, msg = restart_openclaw(port=port)
        if ok:
            self._show_oneclick_success_dialog(msg)
        else:
            messagebox.showerror("一键启动失败", msg)

    def _show_oneclick_success_dialog(self, msg):
        """一键启动成功后弹出对话框，提供「确定」与「关闭」按钮，关闭即退出配置程序。"""
        if ctk is not None:
            win = ctk.CTkToplevel(self.root)
            win.title("一键启动 OpenClaw")
            win.transient(self.root.winfo_toplevel())
            win.grab_set()
            ctk.CTkLabel(win, text=msg, wraplength=360).pack(padx=16, pady=12)
            btn_frame = ctk.CTkFrame(win, fg_color="transparent")
            btn_frame.pack(pady=(0, 12))
            ctk.CTkButton(btn_frame, text="确定", command=win.destroy).pack(side=tk.LEFT, padx=4)
            ctk.CTkButton(btn_frame, text="关闭", command=lambda: (win.destroy(), self.root.destroy()), fg_color="#6c757d").pack(side=tk.LEFT, padx=4)
        else:
            win = tk.Toplevel(self.root)
            win.title("一键启动 OpenClaw")
            win.transient(self.root)
            win.grab_set()
            ttk.Label(win, text=msg, wraplength=360).pack(padx=16, pady=12)
            btn_frame = _gui_frame(win)
            btn_frame.pack(pady=(0, 12))
            _gui_button(btn_frame, text="确定", command=win.destroy).pack(side=tk.LEFT, padx=4)
            _gui_button(btn_frame, text="关闭", command=lambda: (win.destroy(), self.root.destroy())).pack(side=tk.LEFT, padx=4)
        win.wait_window()

    def open_dashboard(self):
        g = self.config.get("gateway") or {}
        port = int(g.get("port", 18789))
        auth = g.get("auth") or {}
        mode = (auth.get("mode") or "token").strip().lower()
        token = (auth.get("token") or "").strip()
        # 使用与 openclaw dashboard 相同逻辑：token 模式时把 token 放在 URL hash 中，Control UI 会自动读取，无需手动设置
        base_url = f"http://127.0.0.1:{port}"
        if mode == "token" and token:
            url = f"{base_url}/#token={urllib.parse.quote(token, safe='')}"
        else:
            url = base_url
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", url], check=True)
            elif sys.platform == "win32":
                subprocess.run(["start", "", url], shell=True, check=True)
            else:
                subprocess.run(["xdg-open", url], check=True)
        except Exception as e:
            msg = f"请手动在浏览器打开: {url}\n\n{e}"
            if mode == "token" and token:
                msg += f"\n\n（该链接已包含 Token，可直接使用；若复制时丢失 #token= 部分，请手动在地址栏补上 #token={token}）"
            messagebox.showinfo("打开控制台", msg)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    if not try_acquire_gui_lock():
        request_focus_via_socket()
        sys.exit(0)
    app = OpenClawConfigApp()
    app.run()
