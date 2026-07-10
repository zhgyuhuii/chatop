import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import app_manager as am

_CONF = (
    "NPM_REGISTRY=https://registry.npmmirror.com\n"
    "NPM_DISTURL=https://npmmirror.com/dist\n"
    "PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple\n"
    "PIP_EXTRA_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/\n"
    "# a comment line\n"
    "GH_PROXIES=https://ghfast.top/ https://gh-proxy.com/\n"
)

def _conf(tmp):
    p = os.path.join(tmp, "mirrors.conf"); open(p, "w").write(_CONF); return p

def test_load_mirrors_parses_keys_and_skips_comments():
    with tempfile.TemporaryDirectory() as t:
        m = am._load_mirrors(_conf(t))
        assert m["NPM_REGISTRY"] == "https://registry.npmmirror.com"
        assert m["GH_PROXIES"] == "https://ghfast.top/ https://gh-proxy.com/"
        assert "# a comment line" not in m and len(m) == 5

def test_install_env_sets_npm_and_pip_vars():
    with tempfile.TemporaryDirectory() as t:
        env = am._install_env(_conf(t))
        assert env["npm_config_registry"] == "https://registry.npmmirror.com"
        assert env["npm_config_disturl"] == "https://npmmirror.com/dist"
        assert env["PIP_INDEX_URL"] == "https://pypi.tuna.tsinghua.edu.cn/simple"
        assert env["PIP_EXTRA_INDEX_URL"] == "https://mirrors.aliyun.com/pypi/simple/"
        # 必须是 os.environ 的超集，别把 PATH/HOME 丢了
        assert "PATH" in env

def test_install_env_missing_conf_is_harmless():
    env = am._install_env("/nonexistent/mirrors.conf")
    assert "PATH" in env and "npm_config_registry" not in env
