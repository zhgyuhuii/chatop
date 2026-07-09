"""语言解析与持久化的测试。跑法：cd app-manager && python3.11 -m pytest tests/ -q"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chatop_i18n as i18n
from chatop_i18n.messages import MESSAGES


# ── normalize ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,want", [
    ("zh_CN", "zh_CN"), ("zh-CN", "zh_CN"), ("zh-cn", "zh_CN"),
    ("zh", "zh_CN"), ("zh-Hans", "zh_CN"), ("zh-SG", "zh_CN"),
    ("zh-TW", "zh_TW"), ("zh-Hant", "zh_TW"), ("zh-HK", "zh_TW"),
    ("en", "en"), ("en-US", "en"), ("EN-gb", "en"),
    ("ja", "ja"), ("ja-JP", "ja"),
    ("ko", "ko"), ("ko-KR", "ko"),
])
def test_normalize_accepts_common_spellings(raw, want):
    assert i18n.normalize(raw) == want


@pytest.mark.parametrize("raw", ["", None, "  ", "fr", "de-DE", "xx", "zzz-ZZ"])
def test_normalize_rejects_unsupported(raw):
    assert i18n.normalize(raw) == ""


@pytest.mark.parametrize("raw", [
    "zh-HK", "zh-Hant", "zh-Hant-TW", "zh-Hant-HK", "zh-Hant-MO", "zh-hant-cn",
])
def test_zh_hant_variants_are_traditional_not_simplified(raw):
    """砍到主语言（zh-hant-hk → zh）会让所有未枚举的繁体变体落到 zh_CN，
    港澳台读者拿到简体字。必须按最长前缀回退。"""
    assert i18n.normalize(raw) == "zh_TW"


@pytest.mark.parametrize("raw", ["zh-Hans", "zh-Hans-CN", "zh-SG", "zh-CN", "zh"])
def test_zh_hans_variants_are_simplified(raw):
    assert i18n.normalize(raw) == "zh_CN"


# ── Accept-Language ───────────────────────────────────────────────────────
def test_accept_language_orders_by_q_value():
    hdr = "en;q=0.5, ja;q=0.9, zh-CN;q=0.8"
    assert i18n.parse_accept_language(hdr) == ["ja", "zh_CN", "en"]


def test_accept_language_default_q_is_one_and_order_is_stable():
    assert i18n.parse_accept_language("zh-CN, en, ja") == ["zh_CN", "en", "ja"]


def test_accept_language_drops_unsupported_and_dedupes():
    hdr = "fr-FR;q=1.0, de;q=0.9, zh-CN;q=0.8, zh;q=0.7"
    assert i18n.parse_accept_language(hdr) == ["zh_CN"]


def test_accept_language_handles_garbage():
    assert i18n.parse_accept_language("") == []
    assert i18n.parse_accept_language(None) == []
    assert i18n.parse_accept_language(";;;,,,") == []


def test_accept_language_unparsable_q_is_lowest_priority_not_dropped():
    # q=oops → 0.0，排到最后但仍保留：畸形 q 值不该让整个语言凭空消失。
    assert i18n.parse_accept_language("en;q=oops, ja") == ["ja", "en"]
    assert i18n.parse_accept_language("en;q=oops") == ["en"]


# ── 文件持久化 ────────────────────────────────────────────────────────────
@pytest.fixture
def langfile(tmp_path, monkeypatch):
    p = str(tmp_path / "lang")
    monkeypatch.setattr(i18n, "LANG_FILE", p)
    return p


def test_write_then_read_roundtrip(langfile):
    assert i18n.write_lang_file("ja") == "ja"
    assert i18n.read_lang_file() == "ja"


def test_write_normalizes_before_persisting(langfile):
    i18n.write_lang_file("zh-Hant")
    assert open(langfile).read() == "zh_TW"


def test_write_auto_removes_file(langfile):
    i18n.write_lang_file("ja")
    assert os.path.exists(langfile)
    assert i18n.write_lang_file(i18n.AUTO) == ""
    assert not os.path.exists(langfile)


def test_write_auto_on_missing_file_is_noop(langfile):
    assert i18n.write_lang_file(i18n.AUTO) == ""   # 不该抛


def test_write_rejects_unsupported_and_writes_nothing(langfile):
    assert i18n.write_lang_file("fr") == ""
    assert not os.path.exists(langfile)


def test_read_missing_file_is_empty(langfile):
    assert i18n.read_lang_file() == ""


def test_read_garbage_file_is_empty(langfile):
    with open(langfile, "w") as f:
        f.write("klingon")
    assert i18n.read_lang_file() == ""


def test_write_leaves_no_tmp(langfile):
    i18n.write_lang_file("ko")
    assert not os.path.exists(langfile + ".tmp")


# ── resolve ───────────────────────────────────────────────────────────────
def test_resolve_cookie_wins_over_everything(langfile):
    i18n.write_lang_file("ja")
    assert i18n.resolve("ko", "zh-CN") == ("ko", True)


def test_resolve_falls_back_to_lang_file(langfile):
    i18n.write_lang_file("ja")
    assert i18n.resolve("", "zh-CN") == ("ja", True)


def test_resolve_falls_back_to_accept_language_and_is_not_chosen(langfile):
    assert i18n.resolve("", "ja;q=0.9, en;q=0.5") == ("ja", False)


def test_resolve_defaults_to_zh_cn_when_nothing_known(langfile):
    assert i18n.resolve("", "") == ("zh_CN", False)
    assert i18n.resolve("", "fr-FR") == ("zh_CN", False)


def test_resolve_ignores_garbage_cookie(langfile):
    assert i18n.resolve("klingon", "ja") == ("ja", False)


def test_brand_probe_path_resolves_to_default(langfile):
    """station 的 _brand_intact() 用 urllib 打 /login，不带 cookie 也不带 Accept-Language。"""
    lang, chosen = i18n.resolve("", "")
    assert lang == i18n.DEFAULT and chosen is False


# ── locale 映射 ───────────────────────────────────────────────────────────
def test_locale_for_every_supported_language():
    for code in i18n.SUPPORTED:
        loc = i18n.locale_for(code)
        assert loc.endswith(".UTF-8")


def test_locale_for_unknown_falls_back_to_default():
    assert i18n.locale_for("fr") == i18n.LOCALES[i18n.DEFAULT]


# ── 词典完整性 ────────────────────────────────────────────────────────────
def test_english_is_identity():
    assert i18n.t("Sign in", "en") == "Sign in"


def test_missing_key_falls_back_to_english_source():
    assert i18n.t("Some brand new string", "ja") == "Some brand new string"


def test_every_language_has_metadata():
    for code in i18n.SUPPORTED:
        assert code in i18n.NATIVE_NAMES
        assert code in i18n.LOCALES
        assert code in i18n.HTML_LANG


def test_all_dictionaries_cover_the_same_keys():
    """漏一条就是某个语言下突然冒出英文。以 zh_CN 为基准。"""
    base = set(MESSAGES["zh_CN"])
    for code in ("zh_TW", "ja", "ko"):
        missing = base - set(MESSAGES[code])
        extra = set(MESSAGES[code]) - base
        assert not missing, "%s 缺少: %s" % (code, sorted(missing))
        assert not extra, "%s 多出: %s" % (code, sorted(extra))


def test_english_has_no_dictionary():
    """en 是源语言，有词典说明有人把英文当译文写了。"""
    assert "en" not in MESSAGES


def test_no_translation_is_left_identical_to_source_in_chinese():
    """中文词典里如果译文 == 英文原文，多半是忘了翻。"""
    same = [k for k, v in MESSAGES["zh_CN"].items() if k == v]
    assert not same, "zh_CN 未翻译: %s" % same


# ── app_manager 接线 ──────────────────────────────────────────────────────
@pytest.fixture
def am(langfile, monkeypatch, tmp_path):
    monkeypatch.setenv("FILES_PW", "s3cret")
    monkeypatch.setenv("CHATOP_DATA_DIR", str(tmp_path))
    sys.modules.pop("app_manager", None)
    import app_manager
    monkeypatch.setattr(app_manager, "_i18n", i18n)
    return app_manager


@pytest.mark.parametrize("raw,want", [
    ("/login", "/login"),
    ("/dashboard/x?a=1", "/dashboard/x?a=1"),
    ("//evil.com", "/login"),               # 协议相对 URL
    ("https://evil.com", "/login"),
    ("http://evil.com", "/login"),
    ("/\\evil.com", "/login"),              # 反斜杠：部分浏览器当斜杠
    ("evil.com", "/login"),
    ("", "/login"),
    (None, "/login"),
])
def test_safe_next_blocks_open_redirect(am, raw, want):
    assert am.safe_next(raw) == want


def test_login_page_has_language_dropdown_with_all_options(am):
    html = am._login_html("", "off", "", None, "zh_CN", True)
    assert 'href="/lang?set=auto' in html
    for code in i18n.SUPPORTED:
        assert 'href="/lang?set=%s' % code in html
        assert i18n.NATIVE_NAMES[code] in html


def test_language_dropdown_marks_current_choice(am):
    html = am._login_html("", "off", "", None, "ja", True)
    assert 'href="/lang?set=ja&next=/login" class="on"' in html


def test_language_dropdown_marks_follow_system_when_not_chosen(am):
    html = am._login_html("", "off", "", None, "ja", False)
    assert 'href="/lang?set=auto&next=/login" class="on"' in html
    assert 'href="/lang?set=ja&next=/login" class=""' in html


def test_language_button_label_is_native_name_when_chosen(am):
    assert ">한국어</span>" in am._login_html("", "off", "", None, "ko", True)


def test_language_button_label_is_follow_system_when_auto(am):
    assert ">システムに従う</span>" in am._login_html("", "off", "", None, "ja", False)


def test_restart_note_only_shown_after_explicit_choice(am):
    assert "重启工舱后生效" in am._login_html("", "off", "", None, "zh_CN", True)
    assert "重启工舱后生效" not in am._login_html("", "off", "", None, "zh_CN", False)


@pytest.mark.parametrize("lang", ["zh_CN", "en", "zh_TW", "ja", "ko"])
def test_brand_string_survives_every_language(am, lang):
    """station 的 _brand_intact() 心跳靠登录页里的「察元AI工舱」判断品牌完整性。
    把品牌名塞进词典去翻译，就会在英文界面下把心跳探测弄成 False。"""
    for state in ("off", "active", "needs_activation"):
        assert "察元AI工舱" in am._login_html("", state, "abc", None, lang, True)


@pytest.mark.parametrize("code", list("123456789"))
def test_every_error_code_is_translated_in_japanese(am, code):
    html = am._login_html(code, "needs_activation", "abc", None, "ja", True)
    key = am.LOGIN_ERRORS[code]
    assert MESSAGES["ja"][key] in html
    assert key not in html          # 不该漏出英文原文


def test_error_codes_map_onto_message_dictionary(am):
    """LOGIN_ERRORS 的值必须都是词典里的 key，否则某个错误码在中文下会显示英文。"""
    for code, key in am.LOGIN_ERRORS.items():
        assert key in MESSAGES["zh_CN"], "错误码 %s 的文案未翻译: %r" % (code, key)


def test_html_lang_attribute_follows_language(am):
    assert '<html lang="ja"' in am._login_html("", "off", "", None, "ja", True)
    assert '<html lang="zh-TW"' in am._login_html("", "off", "", None, "zh_TW", True)


def test_resolve_lang_reads_cookie_header(am):
    assert am.resolve_lang("foo=1; chatop_lang=ko; bar=2", "ja") == ("ko", True)


def test_resolve_lang_without_i18n_package_degrades_to_english(am, monkeypatch):
    monkeypatch.setattr(am, "_i18n", None)
    assert am.resolve_lang("chatop_lang=ko", "ja") == ("en", False)
    assert am.tr("Sign in", "ja") == "Sign in"
