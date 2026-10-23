"""W04 and W05: failure clocks, static frames, and the B17 heartbeat."""
import importlib.util
import io
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "watchers"))
from live_watch import ABRAHAM, FetchError, LAPTOP, poll_once
from publish import PublishError
from telemetry import load_status, observation_label

VARIANTS = {"abraham": ABRAHAM, "laptop": LAPTOP}


def png(color=(10, 20, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, format="PNG")
    return buf.getvalue()


class Clock:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value

    def time(self):
        return self.value

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


def status_of(home, config):
    return load_status(str(home / config["status"]))


@pytest.mark.parametrize("name", ["abraham", "laptop"])
def test_w04_failures_do_not_move_success_or_publication(tmp_path, monkeypatch, name):
    config = VARIANTS[name]
    clock = Clock()
    image = png()

    def fetch(*_args):
        return image

    poll_once(config, str(tmp_path), "token", fetch, clock, beat=lambda *_a: None)
    first = status_of(tmp_path, config)
    assert first["last_fetch_ok"] is True
    assert first["last_success_at"] == 1000.0
    assert first["last_published_at"] == 1000.0
    assert first["consecutive_failures"] == 0
    assert first["poll_s"] == 3.0 and first["deadline_s"] == 5.0 and first["stale_s"] == 10.0

    def fail(code):
        def fetch_fail(*_args):
            raise FetchError(code)
        return fetch_fail

    for stamp, code in ((1001.0, "http_502"), (1002.0, "timeout"), (1003.0, "invalid_png")):
        clock.value = stamp
        poll_once(config, str(tmp_path), "token", fail(code), clock, beat=lambda *_a: None)
        row = status_of(tmp_path, config)
        assert row["last_error"] == code
        assert row["last_success_at"] == 1000.0
        assert row["last_published_at"] == 1000.0
        assert row["last_attempt_at"] == stamp
        assert row["process_heartbeat_at"] == stamp
        assert observation_label(row, stamp, 10)[0] == "error"

    def boom(*_args, **_kwargs):
        raise PublishError("disk_full")

    import live_watch
    monkeypatch.setattr(live_watch, "publish", boom)
    clock.value = 1004.0
    poll_once(config, str(tmp_path), "token", fetch, clock, beat=lambda *_a: None)
    row = status_of(tmp_path, config)
    assert row["last_error"] == "disk_full"
    assert row["consecutive_failures"] == 4
    assert row["last_success_at"] == 1000.0
    assert row["last_published_at"] == 1000.0
    assert "FAIL" in (tmp_path / config["log"]).read_text()


@pytest.mark.parametrize("name", ["abraham", "laptop"])
def test_w05_static_frames_then_failures_go_stale(tmp_path, name):
    config = VARIANTS[name]
    clock = Clock(1000.0)
    image = png((0, 128, 0))

    def fetch(*_args):
        return image

    for step in range(11):
        clock.value = 1000.0 + step * 3
        poll_once(config, str(tmp_path), "token", fetch, clock, beat=lambda *_a: None)
    row = status_of(tmp_path, config)
    assert row["observation_generation"] == 11
    assert row["content_changed_at"] == 1000.0
    assert row["last_success_at"] == 1030.0
    assert observation_label(row, 1030.0, 10) == ("fresh", False)
    log = (tmp_path / config["log"]).read_text().strip().splitlines()
    assert "changed=0" in log[-1]

    def fail(*_args):
        raise FetchError("http_502")

    clock.value = 1031.0
    poll_once(config, str(tmp_path), "token", fail, clock, beat=lambda *_a: None)
    row = status_of(tmp_path, config)
    assert observation_label(row, 1031.0, 10) == ("error", False)
    assert row["last_success_at"] == 1030.0
    clock.value = 1040.0
    poll_once(config, str(tmp_path), "token", fail, clock, beat=lambda *_a: None)
    row = status_of(tmp_path, config)
    assert row["process_heartbeat_at"] == 1040.0
    assert row["last_published_at"] == 1030.0
    assert observation_label(row, 1040.0, 10) == ("error", True)


def test_b17_heartbeat_does_not_advance_gateway_success(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("b18_gateway", ROOT / "services/gateway/app.py")
    gateway = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gateway)
    gateway.TOKEN = "token"
    gateway.HANDS_SECRET = "secret"
    clock = Clock(2000.0)
    monkeypatch.setattr(gateway, "time", clock)
    image = png((255, 0, 0))
    monkeypatch.setattr(gateway, "_fetch_screenshot", lambda **_kw: (image, "image/png", None))
    client = gateway.app.test_client()

    def fetch(url, token, timeout, proxy):
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        response = client.get(parts.path + "?" + parts.query, headers={"X-Relay-Token": token})
        if response.status_code != 200:
            raise FetchError(f"http_{response.status_code}")
        return response.data

    def beat(origin, holder, token, timeout):
        response = client.post("/v1/watch", json={"holder": holder}, headers={"X-Relay-Token": token})
        assert response.status_code == 200

    poll_once(ABRAHAM, str(tmp_path), "token", fetch, clock.time, beat=beat)
    row = gateway._current_watchers()[0]
    assert row["holder"] == "abraham"
    assert row["last_fetch_ok"] is True
    success = row["last_success_at"]
    local = status_of(tmp_path, ABRAHAM)
    published = local["last_published_at"]
    clock.value = 2001.0
    (tmp_path / ABRAHAM["pause"]).write_text("1")
    poll_once(ABRAHAM, str(tmp_path), "token", fetch, clock.time, beat=beat)
    again = gateway._current_watchers()[0]
    assert again["last_success_at"] == success
    local = status_of(tmp_path, ABRAHAM)
    assert local["paused"] is True
    assert local["last_published_at"] == published
    assert local["process_heartbeat_at"] == 2001.0
    assert observation_label(local, 2001.0, 10)[0] == "paused"
