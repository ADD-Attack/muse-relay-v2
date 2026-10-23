"""W06, W07, and the local half of W08, on both watcher variants."""
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "watchers"))
from consumer import Consumer
from live_watch import ABRAHAM, LAPTOP, poll_once

SCRIPTS = {"abraham": ROOT / "watchers" / "watch-live.py", "laptop": ROOT / "watchers" / "watch-live-laptop.py"}
VARIANTS = {"abraham": ABRAHAM, "laptop": LAPTOP}


def png(color):
    buf = BytesIO()
    Image.new("RGB", (6, 6), color).save(buf, format="PNG")
    return buf.getvalue()


class Clock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


def serve(payload):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1/screen"


@pytest.mark.parametrize("name", ["abraham", "laptop"])
def test_w06_clock_restart_reset_and_two_consumers(tmp_path, name):
    config = VARIANTS[name]
    clock = Clock(1000.0)
    image = png((1, 2, 3))
    poll_once(config, str(tmp_path), "token", lambda *_a: image, clock, beat=lambda *_a: None)
    first = Consumer()
    second = Consumer()
    status = str(tmp_path / config["status"])
    left = first.check(str(tmp_path), status, 1000.0, 10)
    right = second.check(str(tmp_path), status, 1000.0, 10)
    assert left["label"] == "fresh" and right["label"] == "fresh"
    assert left["published"]["full"] == right["published"]["full"]
    assert left["published"]["display"] == right["published"]["display"]

    restarted = Consumer()
    assert restarted.check(str(tmp_path), status, 1000.0, 10)["label"] == "fresh"
    assert first.check(str(tmp_path), status, 1000.0 - 5, 10)["label"] == "unknown"
    assert first.check(str(tmp_path), status, 1000.0 + 10, 10)["label"] == "stale"

    clock.value = 1003.0
    poll_once(config, str(tmp_path), "token", lambda *_a: image, clock, beat=lambda *_a: None)
    seen = first.check(str(tmp_path), status, 1003.0, 10)
    assert seen["generation"] == 2
    rolled = Consumer()
    rolled.high_water = 5
    reset = rolled.check(str(tmp_path), status, 1003.0, 10)
    assert reset["label"] == "unknown"
    assert reset["reason"] == "generation_reset"


@pytest.mark.parametrize("name", ["abraham", "laptop"])
def test_w07_pause_and_resume_the_launched_script(tmp_path, name):
    server, url = serve(png((0, 0, 255)))
    env = os.environ.copy()
    env.update({
        "WATCH_HOME": str(tmp_path),
        "WATCH_URL": url,
        "WATCH_PROXY": "direct",
        "WATCH_POLL_S": "0.2",
        "WATCH_DEADLINE_S": "2",
        "WATCH_STALE_S": "10",
    })
    process = subprocess.Popen(
        [sys.executable, str(SCRIPTS[name]), "token"],
        cwd=str(ROOT), env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    status_path = tmp_path / VARIANTS[name]["status"]
    pause_path = tmp_path / VARIANTS[name]["pause"]
    try:
        fresh = _wait_label(tmp_path, status_path, "fresh")
        assert fresh
        pause_path.write_text("paused")
        assert _wait_label(tmp_path, status_path, "paused")
        pause_path.unlink()
        assert _wait_label(tmp_path, status_path, "fresh")
    finally:
        process.kill()
        process.wait(timeout=5)
        server.shutdown()


def _wait_label(root, status_path, label):
    deadline = time.time() + 8
    while time.time() < deadline:
        if status_path.exists():
            view = Consumer().check(str(root), str(status_path), time.time(), 10)
            if view["label"] == label:
                return True
        time.sleep(0.05)
    return False


@pytest.mark.parametrize("name", ["abraham", "laptop"])
def test_w08_needs_advancing_application_evidence(tmp_path, name):
    config = VARIANTS[name]
    clock = Clock(3000.0)
    evidence = tmp_path / "application.log"
    evidence.write_text("closed dialog\n")
    mark = evidence.stat().st_size
    image = png((9, 9, 9))
    poll_once(config, str(tmp_path), "token", lambda *_a: image, clock, beat=lambda *_a: None)
    consumer = Consumer()
    status = str(tmp_path / config["status"])
    screen_only = consumer.check(str(tmp_path), status, 3000.0, 10, str(evidence), mark)
    assert screen_only["label"] == "fresh"
    assert screen_only["accepted"] is False
    clock.value = 3003.0
    evidence.write_text("closed dialog\nlog line advanced\n")
    poll_once(config, str(tmp_path), "token", lambda *_a: png((8, 8, 8)), clock, beat=lambda *_a: None)
    accepted = consumer.check(str(tmp_path), status, 3003.0, 10, str(evidence), mark)
    assert accepted["generation"] == 2
    assert accepted["evidence"] == "advanced"
    assert accepted["accepted"] is True
    assert 3003.0 - 3000.0 >= 3
