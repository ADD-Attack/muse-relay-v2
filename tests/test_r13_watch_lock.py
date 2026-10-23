"""W01: one OS lock per output set, on both watcher variants."""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = {
    "abraham": ROOT / "watchers" / "watch-live.py",
    "laptop": ROOT / "watchers" / "watch-live-laptop.py",
}


def _start(script, home):
    env = os.environ.copy()
    env["WATCH_HOME"] = str(home)
    env["WATCH_URL"] = "http://127.0.0.1:9"
    env["WATCH_PROXY"] = "direct"
    env["WATCH_POLL_S"] = "30"
    env["WATCH_DEADLINE_S"] = "0.2"
    env["WATCH_STALE_S"] = "10"
    return subprocess.Popen(
        [sys.executable, str(script), "token"],
        cwd=str(ROOT),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _wait_held(home, lock_name):
    path = home / lock_name
    deadline = time.time() + 5
    while time.time() < deadline:
        if path.exists():
            from watchers.lock import LockHeld, OutputLock
            try:
                OutputLock(path).acquire().release()
            except LockHeld:
                return path
        time.sleep(0.05)
    raise AssertionError(f"lock was not held: {path}")


@pytest.mark.parametrize("variant,lock_name", [("abraham", "screen-live.lock"), ("laptop", "screen-laptop-live.lock")])
def test_w01_second_process_loses_and_relaunch_keeps_the_lock_file(tmp_path, variant, lock_name):
    script = SCRIPTS[variant]
    first = _start(script, tmp_path)
    try:
        path = _wait_held(tmp_path, lock_name)
        inode = path.stat().st_ino
        second = _start(script, tmp_path)
        stderr = second.stderr.read()
        assert second.wait(timeout=5) == 1
        assert "another watcher holds the output lock" in stderr
        assert path.stat().st_ino == inode
    finally:
        first.kill()
        first.wait(timeout=5)
    relaunch = _start(script, tmp_path)
    try:
        again = _wait_held(tmp_path, lock_name)
        assert again.stat().st_ino == inode
    finally:
        relaunch.kill()
        relaunch.wait(timeout=5)
