"""B12: exclusive gateway epoch lock, crash, and fail-closed rollback."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

STORE = Path(__file__).resolve().parents[1] / "services/gateway/epoch_store.py"
PY = sys.executable
CHILD = r"""
import importlib.util, sys, time
spec = importlib.util.spec_from_file_location("epoch_store", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
store = mod.EpochStore(sys.argv[2])
try:
    ok = store.acquire()
except mod.SyncError as exc:
    print(f"ERROR {exc}", flush=True)
    sys.exit(2)
print(f"RESULT {int(bool(ok))} {store.epoch or 0}", flush=True)
if ok and len(sys.argv) > 3 and sys.argv[3] == "hold":
    time.sleep(30)
"""

def load():
    spec = importlib.util.spec_from_file_location("epoch_store_test", STORE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def run_child(directory, *args):
    return subprocess.Popen(
        [PY, "-c", CHILD, str(STORE), str(directory), *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def read_result(proc):
    line = proc.stdout.readline().strip()
    if not line.startswith("RESULT"):
        err = proc.stderr.read()
        raise AssertionError(f"child failed: {line!r} {err}")
    _tag, ok, epoch = line.split()
    return ok == "1", int(epoch)

def test_one_live_process_owns_the_lock_and_a_killed_one_yields_a_higher_epoch(tmp_path):
    holder = run_child(tmp_path, "hold")
    try:
        held, first = read_result(holder)
        assert held is True and first == 1
        rival = run_child(tmp_path)
        denied, epoch = read_result(rival)
        assert denied is False and epoch == 0
        rival.wait(timeout=5)
    finally:
        holder.kill()
        holder.wait(timeout=5)
    successor = run_child(tmp_path)
    try:
        held, second = read_result(successor)
        assert held is True and second > first
    finally:
        successor.kill()
        successor.wait(timeout=5)

def test_disk_failure_and_rollback_fail_closed_until_explicit_recovery(tmp_path, monkeypatch):
    module = load()
    store = module.EpochStore(tmp_path)
    assert store.acquire() is True
    assert store.epoch == 1
    store.release()

    real = module.os.replace
    def fail(src, dst):
        raise OSError("disk full")
    monkeypatch.setattr(module.os, "replace", fail)
    broken = module.EpochStore(tmp_path)
    with pytest.raises(module.SyncError):
        broken.acquire()
    assert broken.serving is False
    monkeypatch.setattr(module.os, "replace", real)

    restored = module.EpochStore(tmp_path)
    assert restored.acquire() is True
    epoch_path = Path(tmp_path) / "epoch.json"
    record = json.loads(epoch_path.read_text())
    record["epoch"] = 1
    epoch_path.write_text(json.dumps(record))
    with pytest.raises(module.SyncError):
        restored.recheck()
    assert restored.serving is False
    with pytest.raises(module.SyncError):
        restored.recover("please")
    assert restored.recover("reset-pairing") == 1
    assert restored.serving is True
    restored.release()

def test_corrupt_store_and_one_step_crash_do_not_reset_to_zero(tmp_path):
    module = load()
    (tmp_path / "epoch.json").write_text("{")
    (tmp_path / "high-water.json").write_text(json.dumps({"high_water": 1, "pairing": "p"}))
    with pytest.raises(module.SyncError):
        module.EpochStore(tmp_path).acquire()

    clean = tmp_path / "clean"
    clean.mkdir()
    pairing = "11111111-1111-1111-1111-111111111111"
    (clean / "high-water.json").write_text(json.dumps({"high_water": 4, "pairing": pairing}))
    (clean / "epoch.json").write_text(json.dumps({"epoch": 5, "pairing": pairing}))
    store = module.EpochStore(clean)
    assert store.acquire() is True
    assert store.epoch == 6
    store.release()
    again = module.EpochStore(clean)
    assert again.acquire() is True
    assert again.epoch == 7
    again.release()
