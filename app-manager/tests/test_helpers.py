import os, subprocess, tempfile
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FETCH = os.path.join(HERE, "chatop-fetch.sh")
SHIM = os.path.join(HERE, "proot-apps-shim.sh")
DEB = os.path.join(HERE, "chatop-deb-install.sh")

def test_deb_install_dryrun_no_download():
    r = subprocess.run(["bash", DEB, "demo", "https://x/y.deb", "Demo", "--dry-run"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "dpkg -x" in r.stdout

_CONF = "GH_PROXIES=https://ghfast.top/ https://gh-proxy.com/\n"

def _run(args, conf):
    env = dict(os.environ, MIRRORS_CONF=conf)
    return subprocess.run(["bash", FETCH, *args], env=env,
                          capture_output=True, text=True)

def test_fetch_dryrun_lists_direct_then_proxies():
    with tempfile.TemporaryDirectory() as t:
        cp = os.path.join(t, "mirrors.conf"); open(cp, "w").write(_CONF)
        url = "https://github.com/foo/bar/releases/download/v1/x.tgz"
        r = _run([url, "--dry-run"], cp)
        lines = [l for l in r.stdout.strip().splitlines() if l]
        assert lines[0] == url
        assert lines[1] == "https://ghfast.top/" + url
        assert lines[2] == "https://gh-proxy.com/" + url
        assert len(lines) == 3

def test_fetch_dryrun_no_conf_only_direct():
    url = "https://github.com/foo/bar.tgz"
    r = _run([url, "--dry-run"], "/nonexistent/mirrors.conf")
    lines = [l for l in r.stdout.strip().splitlines() if l]
    assert lines == [url]

def test_shim_rewrites_shortname_to_ghcr_mirrors():
    with tempfile.TemporaryDirectory() as t:
        cp = os.path.join(t, "mirrors.conf")
        open(cp, "w").write("GHCR_MIRRORS=ghcr.m.daocloud.io ghcr.nju.edu.cn\n")
        env = dict(os.environ, MIRRORS_CONF=cp)
        r = subprocess.run(["bash", SHIM, "install", "wechat", "--dry-run"],
                           env=env, capture_output=True, text=True)
        lines = [l for l in r.stdout.strip().splitlines() if l]
        assert lines == [
            "ghcr.m.daocloud.io/linuxserver/proot-apps:wechat",
            "ghcr.nju.edu.cn/linuxserver/proot-apps:wechat",
            "wechat",
        ]
