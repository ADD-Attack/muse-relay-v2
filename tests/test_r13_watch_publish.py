"""W02 and W03: unique temps, one manifest, no mixed generation."""
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "watchers"))
from publish import Incomplete, PublishCrash, publish, read_published

SCRIPTS = {
    "abraham": ROOT / "watchers" / "watch-live.py",
    "laptop": ROOT / "watchers" / "watch-live-laptop.py",
}


def png(color, size=(8, 8)):
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def serve(payload):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1/screen"


def run_script(script, home, url, extra):
    env = os.environ.copy()
    env.update({
        "WATCH_HOME": str(home),
        "WATCH_URL": url,
        "WATCH_PROXY": "direct",
        "WATCH_POLL_S": "30",
        "WATCH_DEADLINE_S": "2",
        "WATCH_ONCE": "1",
    })
    env.update(extra)
    return subprocess.run(
        [sys.executable, str(script), "token"],
        cwd=str(ROOT),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
    )


def test_publish_reader_rejects_a_partial_generation(tmp_path):
    red = png((255, 0, 0))
    publish(tmp_path, red, red, {"epoch": 1.0, "content_hash": "a"})
    try:
        publish(tmp_path, png((0, 255, 0)), png((0, 255, 0)), {"epoch": 2.0}, crash_after="display")
    except PublishCrash as exc:
        assert exc.stage == "display"
    got = read_published(tmp_path)
    assert got["manifest"]["generation"] == 1
    assert got["full"] == red
    assert got["display"] == red
    assert got["meta"]["observation_generation"] == 1


def test_concurrent_publishes_never_mix(tmp_path):
    errors = []
    gate = threading.Barrier(2)

    def once(color):
        gate.wait()
        publish(tmp_path, png(color), png(color), {"epoch": 1.0, "content_hash": "c"})

    threads = [threading.Thread(target=once, args=(color,)) for color in ((1, 2, 3), (4, 5, 6))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    got = read_published(tmp_path)
    assert got["full"] == got["display"]
    assert got["meta"]["observation_generation"] == got["manifest"]["generation"]
    temps = [path.name for path in tmp_path.rglob("*") if path.name.endswith(".tmp") or path.name.endswith("png.tmp")]
    assert temps == []
    assert errors == []


@pytest.mark.parametrize("variant", ["abraham", "laptop"])
def test_w02_unlocked_processes_leave_one_complete_generation(tmp_path, variant):
    server, url = serve(png((0, 128, 0)))
    seen = []
    stop = threading.Event()

    def watch():
        while not stop.is_set():
            try:
                got = read_published(tmp_path)
            except Incomplete:
                continue
            if got["meta"]["observation_generation"] != got["manifest"]["generation"]:
                seen.append("mixed")

    thread = threading.Thread(target=watch)
    thread.start()
    try:
        first = threading.Thread(target=run_script, args=(SCRIPTS[variant], tmp_path, url, {"WATCH_DISABLE_LOCK": "1"}))
        second = threading.Thread(target=run_script, args=(SCRIPTS[variant], tmp_path, url, {"WATCH_DISABLE_LOCK": "1"}))
        first.start()
        second.start()
        first.join()
        second.join()
    finally:
        stop.set()
        thread.join()
        server.shutdown()
    got = read_published(tmp_path)
    assert got["meta"]["variant"] == variant
    assert seen == []
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize("variant", ["abraham", "laptop"])
@pytest.mark.parametrize("stage", ["full", "display", "meta", "manifest"])
def test_w03_crash_after_each_stage_stays_on_a_complete_generation(tmp_path, variant, stage):
    red = png((255, 0, 0))
    publish(tmp_path, red, red, {"epoch": 1.0, "variant": variant, "content_hash": "red"})
    server, url = serve(png((0, 0, 255)))
    try:
        result = run_script(SCRIPTS[variant], tmp_path, url, {
            "WATCH_CRASH_AFTER": stage,
            "WATCH_CRASH_EXIT": "1",
        })
    finally:
        server.shutdown()
    assert result.returncode == 86
    got = read_published(tmp_path)
    if stage == "manifest":
        assert got["manifest"]["generation"] == 2
        assert got["meta"]["observation_generation"] == 2
    else:
        assert got["manifest"]["generation"] == 1
        assert got["full"] == red
        assert got["display"] == red
