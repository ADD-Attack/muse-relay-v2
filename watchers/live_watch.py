"""Repaired latest-frame watchers.

Inputs, not this implementation:
  v3-r13-spec 5bf44ec
  docs/r13-inputs/watchers/watch-live.py
  docs/r13-inputs/watchers/watch-live-laptop.py

Those loops have fetch() and three shared .tmp renames. They have no lock,
no failure line, no heartbeat, and no consumer. The symbols below are the
repair. Defaults preserve each variant's URL, directory, and file names.
"""
import io
import os
import subprocess
import sys
import time

from PIL import Image

from lock import LockHeld, OutputLock
from publish import PublishError, publish

POLL_S = 3.0
DEADLINE_S = 5.0
STALE_S = 10.0
PROXY = "http://hatch-egress-proxy:3130"

ABRAHAM = {
    "name": "abraham",
    "holder": "abraham",
    "url": "http://100.119.30.72:5010/v1/screen",
    "home": "~/workspace",
    "live": "screen-live.png",
    "full": "screen-live-full.png",
    "epoch": "screen-live.txt",
    "log": "screen-live.log",
    "lock": "screen-live.lock",
}
LAPTOP = {
    "name": "laptop",
    "holder": "laptop",
    "url": "http://100.76.253.71:5010/v1/screen",
    "home": "~/workspace/miata-logs",
    "live": "screen-laptop-live.png",
    "full": "screen-laptop-live-full.png",
    "epoch": "screen-laptop-live.txt",
    "log": "screen-laptop-live.log",
    "lock": "screen-laptop-live.lock",
}


class FetchError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _env_float(name, default):
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    value = float(raw)
    if value != value or value <= 0 or value == float("inf"):
        raise SystemExit(f"{name} must be a finite positive number")
    return value


def append_log(path, line):
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def fetch_curl(url, token, timeout, proxy):
    command = ["curl", "-sS", "--max-time", str(timeout)]
    if proxy and proxy != "direct":
        command += ["--proxytunnel", "-x", proxy]
    command += ["-H", "X-Relay-Token: " + token, "-w", "\nWATCH_HTTP:%{http_code}", url]
    try:
        result = subprocess.run(command, capture_output=True, timeout=float(timeout) + 1.0)
    except subprocess.TimeoutExpired as exc:
        raise FetchError("timeout") from exc
    except FileNotFoundError as exc:
        raise FetchError("fetch_unavailable") from exc
    if result.returncode != 0:
        err = (result.stderr or b"").decode("utf-8", "replace").lower()
        if result.returncode == 28 or "timed out" in err:
            raise FetchError("timeout")
        raise FetchError("fetch_failed")
    marker = b"\nWATCH_HTTP:"
    body, sep, tail = result.stdout.rpartition(marker)
    if not sep:
        raise FetchError("invalid_png")
    try:
        code = int(tail.strip() or b"0")
    except ValueError as exc:
        raise FetchError("invalid_png") from exc
    if code == 502:
        raise FetchError("http_502")
    if code != 200:
        raise FetchError(f"http_{code}")
    if not body.startswith(b"\x89PNG"):
        raise FetchError("invalid_png")
    return body


def decode_image(png_bytes):
    try:
        image = Image.open(io.BytesIO(png_bytes))
        image.load()
        return image.convert("RGB")
    except Exception as exc:
        raise FetchError("invalid_png") from exc


def png_bytes(image):
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def display_image(image):
    width, height = image.size
    if width <= 0 or height <= 0:
        raise FetchError("invalid_png")
    return image.resize((1440, max(1, int(1440 * height / width))))


def masked_hash(image):
    width, height = image.size
    cropped = image.crop((0, 0, width, height - 80)) if height > 80 else image
    import hashlib
    return hashlib.sha256(cropped.tobytes()).hexdigest()


def with_watcher(url, holder):
    if "watcher=" in url:
        return url
    return url + ("&" if "?" in url else "?") + "watcher=" + holder


def poll_once(config, home, token, fetch, now):
    url = with_watcher(os.environ.get("WATCH_URL", config["url"]), config["holder"])
    deadline = _env_float("WATCH_DEADLINE_S", DEADLINE_S)
    proxy = os.environ.get("WATCH_PROXY", PROXY)
    log_path = os.path.join(home, config["log"])
    try:
        png = fetch(url, token, deadline, proxy)
        image = decode_image(png)
        epoch = now()
        meta = {
            "epoch": epoch,
            "variant": config["name"],
            "content_hash": masked_hash(image),
            "width": image.size[0],
            "height": image.size[1],
        }
        full = png_bytes(image)
        shown = png_bytes(display_image(image))
        epoch_text = str(epoch).encode("ascii")
        manifest = publish(
            home, full, shown, meta,
            crash_after=os.environ.get("WATCH_CRASH_AFTER") or None,
            hard_crash=os.environ.get("WATCH_CRASH_EXIT") == "1",
            mirrors=(
                (config["full"], full),
                (config["live"], shown),
                (config["epoch"], epoch_text),
            ),
        )
        if manifest is None:
            return None
        short = meta["content_hash"][:12]
        append_log(log_path, "%f %s changed=%d\n" % (epoch, short, 0))
        return manifest
    except FetchError as exc:
        append_log(log_path, "FAIL %f %s\n" % (now(), exc.code))
        return None
    except PublishError as exc:
        append_log(log_path, "FAIL %f %s\n" % (now(), exc.code))
        return None


def main(config, argv=None):
    argv = list(sys.argv if argv is None else argv)
    if len(argv) < 2:
        print(f"usage: {config['name']} watcher <gateway-token>", file=sys.stderr)
        return 2
    home = os.path.expanduser(os.environ.get("WATCH_HOME") or config["home"])
    os.makedirs(home, exist_ok=True)
    lock_path = os.path.join(home, config["lock"])
    lock = None
    if os.environ.get("WATCH_DISABLE_LOCK") != "1":
        lock = OutputLock(lock_path)
        try:
            lock.acquire()
        except LockHeld as exc:
            print(str(exc), file=sys.stderr)
            return 1
    print(f"lock acquired: {lock_path}", file=sys.stderr)
    token = argv[1]
    poll_s = _env_float("WATCH_POLL_S", POLL_S)
    try:
        while True:
            poll_once(config, home, token, fetch_curl, time.time)
            if os.environ.get("WATCH_ONCE") == "1":
                return 0
            time.sleep(poll_s)
    finally:
        if lock is not None:
            lock.release()
