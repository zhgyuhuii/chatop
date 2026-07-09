"""chatop 多语言：登录页 / noVNC / XFCE 三层共用同一份语言选择。

选择的**唯一真源**是卷内文件 `~/.local/share/chatop/lang`（容器级，因为 XFCE 只有一份）。
浏览器侧用 cookie `chatop_lang` 做镜像，让 noVNC 的 JS 也能读到（故意不设 HttpOnly）。

未选择（文件与 cookie 都没有）＝「跟随系统」：
  - 登录页按浏览器的 Accept-Language 解析
  - noVNC 走它自带的 navigator.languages 探测
  - XFCE 用镜像 ENV 的默认值 zh_CN.UTF-8

语言集合刻意只有 5 种。这不是系统层的限制（容器里已有 222 个 locale、170 个 language-pack，
XFCE 的 .mo 一应俱全），而是**我们自己的文案翻译量**的限制 —— 开放到 noVNC 那 243 种，
登录页和自定义文案只能退回英文，阿拉伯/泰文等还会因缺字体显示成豆腐块。

品牌名「察元AI工舱」在所有语言下保持不变：它是品牌，且 station 的心跳探测
(`heartbeat._brand_intact`) 靠登录页里这五个字判断品牌完整性。
"""
import os

from .messages import MESSAGES

DEFAULT = "zh_CN"
SUPPORTED = ("zh_CN", "en", "zh_TW", "ja", "ko")

# 下拉里显示的母语名
NATIVE_NAMES = {
    "zh_CN": "简体中文",
    "en": "English",
    "zh_TW": "繁體中文",
    "ja": "日本語",
    "ko": "한국어",
}

# 语言代码 → glibc locale（喂给 LC_ALL，vnc_startup.sh 再派生 LANG/LANGUAGE）
LOCALES = {
    "zh_CN": "zh_CN.UTF-8",
    "en": "en_US.UTF-8",
    "zh_TW": "zh_TW.UTF-8",
    "ja": "ja_JP.UTF-8",
    "ko": "ko_KR.UTF-8",
}

# HTML lang 属性
HTML_LANG = {
    "zh_CN": "zh-CN", "en": "en", "zh_TW": "zh-TW", "ja": "ja", "ko": "ko",
}

COOKIE = "chatop_lang"
AUTO = "auto"

DATA_DIR = os.path.expanduser(
    os.environ.get("CHATOP_DATA_DIR") or "~/.local/share/chatop")
LANG_FILE = os.path.join(DATA_DIR, "lang")

# Accept-Language 的子标签 → 我们的代码。先查全称，再查主语言。
_ALIASES = {
    "zh": "zh_CN", "zh-cn": "zh_CN", "zh-hans": "zh_CN", "zh-sg": "zh_CN",
    "zh-tw": "zh_TW", "zh-hant": "zh_TW", "zh-hk": "zh_TW", "zh-mo": "zh_TW",
    "en": "en", "ja": "ja", "ko": "ko",
}


def normalize(code):
    """任意写法（zh-CN / zh_cn / ja-JP / en-US）→ SUPPORTED 里的代码，认不出返回 ""。"""
    if not code:
        return ""
    raw = code.strip().replace("_", "-").lower()
    # 精确匹配 SUPPORTED（zh_CN → zh-cn）
    for s in SUPPORTED:
        if raw == s.replace("_", "-").lower():
            return s
    # 从最长前缀往短了退：zh-hant-hk 先命中 zh-hant(→zh_TW)，退无可退才到 zh(→zh_CN)。
    # 直接砍到主语言会把所有 zh-Hant-* 判成简体，港澳台读者拿到简体字。
    parts = raw.split("-")
    for n in range(len(parts), 0, -1):
        hit = _ALIASES.get("-".join(parts[:n]))
        if hit:
            return hit
    return ""


def parse_accept_language(header):
    """→ 按 q 值降序的语言代码列表（已 normalize，去掉认不出的）。"""
    out = []
    for i, part in enumerate((header or "").split(",")):
        piece = part.strip()
        if not piece:
            continue
        tag, _, params = piece.partition(";")
        q = 1.0
        for p in params.split(";"):
            k, _, v = p.strip().partition("=")
            if k == "q":
                try:
                    q = float(v)
                except ValueError:
                    q = 0.0
        code = normalize(tag)
        if code:
            # i 作次序键，保证同 q 值时保留原顺序（Python sort 稳定，这里显式一点）
            out.append((-q, i, code))
    out.sort()
    seen, result = set(), []
    for _, _, code in out:
        if code not in seen:
            seen.add(code)
            result.append(code)
    return result


def read_lang_file(path=None):
    """→ 已选语言代码，或 "" 表示未选择（跟随系统）。"""
    try:
        with open(path or LANG_FILE, encoding="utf-8") as f:
            return normalize(f.read().strip())
    except OSError:
        return ""


def write_lang_file(code, path=None):
    """原子写。code 为 AUTO 或空则删除文件（回到跟随系统）。"""
    path = path or LANG_FILE
    if code == AUTO or not code:
        try:
            os.remove(path)
        except OSError:
            pass
        return ""
    code = normalize(code)
    if not code:
        return ""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        pass
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(code)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return code


def resolve(cookie_value="", accept_language="", lang_file=None):
    """→ (lang, chosen)。chosen=False 表示「跟随系统」，下拉里该高亮「跟随系统」。

    优先级：cookie（浏览器本次选择）> 卷内文件（容器级选择）> Accept-Language > DEFAULT。
    cookie 排在文件前面，是为了让「换个浏览器只看英文」这种临时需求不改动整机设置……
    但 /lang 端点两者一起写，正常使用下两者恒等。
    """
    code = normalize(cookie_value)
    if code:
        return (code, True)
    code = read_lang_file(lang_file)
    if code:
        return (code, True)
    for c in parse_accept_language(accept_language):
        return (c, False)
    return (DEFAULT, False)


def locale_for(code):
    return LOCALES.get(normalize(code) or DEFAULT, LOCALES[DEFAULT])


def t(key, lang):
    """英文原文即 key（与 noVNC 的 gettext 式约定一致）。缺译回落原文。"""
    if lang == "en":
        return key
    return MESSAGES.get(lang, {}).get(key, key)
