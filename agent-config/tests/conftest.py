# -*- coding: utf-8 -*-
import os
import sys

# 引擎复用 openclaw-tool 的纯模块；测试里指到仓内。
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
os.environ.setdefault("OPENCLAW_TOOL_DIR", os.path.join(_REPO, "openclaw-tool"))
sys.path.insert(0, os.path.dirname(_HERE))  # agent-config/ 上 agentconfig 包


def build_catalog_snapshot(home):
    """用 testdata 构建目录快照，写到 home 下缓存，让 describe 能列出通道。"""
    import json
    sys.path.insert(0, os.environ["OPENCLAW_TOOL_DIR"])
    import openclaw_catalog as cat
    td = os.path.join(os.environ["OPENCLAW_TOOL_DIR"], "testdata")
    channels = open(os.path.join(td, "channels-list.json"), encoding="utf-8").read()
    schema = open(os.path.join(td, "config-schema-channels.json"), encoding="utf-8").read()
    catjs = open(os.path.join(td, "plugin-catalog-snippet.js"), encoding="utf-8").read()
    models = open(os.path.join(td, "models-list.json"), encoding="utf-8").read()
    catalog = cat.build_catalog(channels, schema, catjs, models, openclaw_version="2026.6.10")
    dst = os.path.join(home, ".cache/chatop/openclaw-catalog.json")
    cat.save_catalog(dst, catalog)
    return dst
