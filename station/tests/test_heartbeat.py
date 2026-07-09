"""node-id 是 app-manager 序列号激活的指纹锚点，station 与 app-manager 并行首启会抢它。

这些用例锁住「出现即完整」的创建语义。回归成 read→write 或裸 O_EXCL 都会在这里红。
"""
import threading
from pathlib import Path

from station import heartbeat


def _point_at(tmp_path, monkeypatch):
    monkeypatch.setattr(heartbeat, "_HID_FILE", Path(tmp_path) / "node-id")


def test_hid_created_and_persisted(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch)
    hid = heartbeat._hid()
    assert heartbeat._valid_hid(hid)
    assert heartbeat._HID_FILE.read_text().strip() == hid


def test_hid_is_stable_across_calls(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch)
    assert heartbeat._hid() == heartbeat._hid()


def test_hid_reuses_existing_file(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch)
    heartbeat._HID_FILE.write_text("deadbeef-0000-1111-2222-333344445555\n")
    assert heartbeat._hid() == "deadbeef-0000-1111-2222-333344445555"


def test_hid_ignores_garbage_file(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch)
    heartbeat._HID_FILE.write_text("!!! not an id !!!")
    hid = heartbeat._hid()
    assert heartbeat._valid_hid(hid)


def test_concurrent_hid_converges_to_one_uuid(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch)
    seen = []
    barrier = threading.Barrier(16)

    def worker():
        barrier.wait()
        seen.append(heartbeat._hid())

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(set(seen)) == 1
    assert heartbeat._HID_FILE.read_text().strip() == seen[0]


def test_no_tmp_files_left_behind(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch)
    heartbeat._hid()
    assert list(Path(tmp_path).glob("*.tmp")) == []
