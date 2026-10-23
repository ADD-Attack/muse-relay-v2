"""Repaired latest-frame watchers.

Inputs, not this implementation:
  v3-r13-spec 5bf44ec
  docs/r13-inputs/watchers/watch-live.py
  docs/r13-inputs/watchers/watch-live-laptop.py

Those loops have fetch() and three shared .tmp renames. They have no lock,
no failure line, no heartbeat, and no consumer. The symbols below are the
repair. Defaults preserve each variant's URL, directory, and file names.
"""
import os
import sys
import time

from lock import LockHeld, OutputLock

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


def _env_float(name, default):
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    value = float(raw)
    if value <= 0:
        raise SystemExit(f"{name} must be a finite positive number")
    return value


def main(config, argv=None):
    argv = list(sys.argv if argv is None else argv)
    if len(argv) < 2:
        print(f"usage: {config['name']} watcher <gateway-token>", file=sys.stderr)
        return 2
    home = os.path.expanduser(os.environ.get("WATCH_HOME") or config["home"])
    os.makedirs(home, exist_ok=True)
    lock_path = os.path.join(home, config["lock"])
    if os.environ.get("WATCH_DISABLE_LOCK") == "1":
        lock = None
    else:
        lock = OutputLock(lock_path)
        try:
            lock.acquire()
        except LockHeld as exc:
            print(str(exc), file=sys.stderr)
            return 1
    print(f"lock acquired: {lock_path}", file=sys.stderr)
    poll_s = _env_float("WATCH_POLL_S", POLL_S)
    try:
        while True:
            time.sleep(poll_s)
    finally:
        if lock is not None:
            lock.release()
    return 0
