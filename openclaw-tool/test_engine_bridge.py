import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_bridge as eb


class _F:  # 模拟引擎 FieldSpec 的鸭子类型
    def __init__(self, key, kind, secret=False, label="", options=None, value=None):
        self.key, self.kind, self.secret = key, kind, secret
        self.label, self.options, self.value = label, options or [], value


def test_widget_kind_for_secret():
    assert eb.widget_kind(_F("channels.telegram.botToken", "secret", secret=True)) == "entry_secret"

def test_widget_kind_for_bool():
    assert eb.widget_kind(_F("x", "bool")) == "checkbutton"

def test_widget_kind_for_select():
    assert eb.widget_kind(_F("x", "select", options=["a", "b"])) == "combobox"

def test_widget_kind_for_text():
    assert eb.widget_kind(_F("x", "text")) == "entry"

def test_widget_kind_for_number():
    assert eb.widget_kind(_F("x", "number")) == "entry"

def test_field_rows_from_describe():
    # 引擎不可用时返回空列表（离线兜底），可用时返回 (FieldSpec, widget_kind) 行
    rows = eb.field_rows_for_channel("telegram")
    assert isinstance(rows, list)
    for spec, kind in rows:
        assert kind in ("entry", "entry_secret", "checkbutton", "combobox")
