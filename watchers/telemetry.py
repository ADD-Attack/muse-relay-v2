"""Clocks for one watcher. A heartbeat does not move a successful observation."""
import json
import os
import uuid


def empty_status():
    return {
        "last_attempt_at": None,
        "last_success_at": None,
        "last_published_at": None,
        "process_heartbeat_at": None,
        "content_changed_at": None,
        "content_hash": None,
        "consecutive_failures": 0,
        "last_error": None,
        "last_fetch_ok": None,
        "observation_generation": 0,
        "paused": False,
        "poll_s": 3.0,
        "deadline_s": 5.0,
        "stale_s": 10.0,
    }


def _finite(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == value
        and value not in (float("inf"), float("-inf"))
    )


def load_status(path):
    status = empty_status()
    try:
        loaded = json.loads(open(path, "r", encoding="utf-8").read())
    except (OSError, ValueError, TypeError):
        return status
    if not isinstance(loaded, dict):
        return status
    for key in status:
        if key in loaded:
            status[key] = loaded[key]
    return status


def store_status(path, status):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = os.path.join(folder or ".", f".status.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    payload = json.dumps(status, sort_keys=True).encode("utf-8")
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def note_heartbeat(status, now):
    status["process_heartbeat_at"] = now
    return status


def note_failure(status, now, code):
    status["last_attempt_at"] = now
    status["last_fetch_ok"] = False
    status["consecutive_failures"] = int(status.get("consecutive_failures") or 0) + 1
    status["last_error"] = code
    return status


def note_success(status, now, content_hash, published_at):
    previous = status.get("content_hash")
    status["last_attempt_at"] = now
    status["last_fetch_ok"] = True
    status["last_error"] = None
    status["consecutive_failures"] = 0
    status["last_success_at"] = now
    status["observation_generation"] = int(status.get("observation_generation") or 0) + 1
    if content_hash != previous:
        status["content_hash"] = content_hash
        status["content_changed_at"] = now
    if published_at is not None:
        status["last_published_at"] = published_at
    return status


def observation_label(status, now, stale_s):
    """Return (label, stale). Paused is never fresh. Error is immediate."""
    if status.get("paused") is True:
        return "paused", False
    success = status.get("last_success_at")
    future = _finite(success) and float(success) > float(now)
    if status.get("last_fetch_ok") is False:
        if future or not _finite(success):
            return "error", False
        return "error", (float(now) - float(success)) >= float(stale_s)
    if not _finite(success) or future:
        return "unknown", False
    stale = (float(now) - float(success)) >= float(stale_s)
    return ("stale" if stale else "fresh"), stale
