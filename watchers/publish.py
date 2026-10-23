"""One immutable generation, then one manifest rename.

The input scripts rename three shared .tmp files. Those are three snapshots.
A reader here follows manifest.json only. Generations are not rewritten.
Cleanup removes directories the current manifest does not name.
"""
import hashlib
import json
import os
import uuid


class Incomplete(Exception):
    pass


class PublishError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class PublishCrash(Exception):
    def __init__(self, stage):
        self.stage = stage
        super().__init__(stage)


def _lock_blocking(fd):
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        return
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_EX)


def _unlock(fd):
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        return
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_UN)


def allocate_generation(root):
    """Short lock on the counter only. This is not the output-set lock."""
    path = os.path.join(root, "generation.counter")
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        _lock_blocking(fd)
        raw = b""
        while True:
            chunk = os.read(fd, 64)
            if not chunk:
                break
            raw += chunk
        try:
            current = int((raw or b"0").strip() or b"0")
        except ValueError:
            current = 0
        nxt = current + 1
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, str(nxt).encode("ascii"))
        os.fsync(fd)
        return nxt
    finally:
        try:
            _unlock(fd)
        finally:
            os.close(fd)


def _atomic_bytes(directory, final_name, data, stage, crash_after, hard_crash):
    tmp = os.path.join(directory, f".{final_name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except OSError as exc:
        raise PublishError("publish_failed") from exc
    try:
        view = data if isinstance(data, (bytes, bytearray)) else bytes(data)
        os.write(fd, view)
        os.fsync(fd)
    except OSError as exc:
        os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        if getattr(exc, "errno", None) == 28:
            raise PublishError("disk_full") from exc
        raise PublishError("publish_failed") from exc
    os.close(fd)
    os.replace(tmp, os.path.join(directory, final_name))
    if crash_after == stage:
        if hard_crash:
            os._exit(86)
        raise PublishCrash(stage)


def publish(root, full_bytes, display_bytes, meta, crash_after=None, hard_crash=False, mirrors=()):
    root = os.fspath(root)
    os.makedirs(os.path.join(root, "generations"), exist_ok=True)
    generation = allocate_generation(root)
    folder = os.path.join(root, "generations", f"{generation:08d}")
    os.makedirs(folder)
    body = dict(meta)
    body["observation_generation"] = generation
    _atomic_bytes(folder, "full.png", full_bytes, "full", crash_after, hard_crash)
    _atomic_bytes(folder, "display.png", display_bytes, "display", crash_after, hard_crash)
    _atomic_bytes(
        folder, "meta.json", json.dumps(body, sort_keys=True).encode("utf-8"),
        "meta", crash_after, hard_crash,
    )
    manifest = {
        "generation": generation,
        "full": f"generations/{generation:08d}/full.png",
        "display": f"generations/{generation:08d}/display.png",
        "metadata": f"generations/{generation:08d}/meta.json",
        "full_sha256": hashlib.sha256(full_bytes).hexdigest(),
        "display_sha256": hashlib.sha256(display_bytes).hexdigest(),
        "published_at": body.get("epoch"),
    }
    if not _commit_manifest(root, manifest, crash_after, hard_crash):
        return None
    for name, payload in mirrors:
        _atomic_bytes(root, name, payload, "mirror", None, False)
    return manifest


def _current_generation(root):
    path = os.path.join(root, "manifest.json")
    try:
        manifest = json.loads(open(path, "r", encoding="utf-8").read())
        return int(manifest["generation"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return 0


def _commit_manifest(root, manifest, crash_after, hard_crash):
    """Move the pointer forward only. A slower publisher must not uncover a deleted generation."""
    fd = os.open(os.path.join(root, "generation.counter"), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        _lock_blocking(fd)
        if int(manifest["generation"]) < _current_generation(root):
            return False
        _atomic_bytes(
            root, "manifest.json", json.dumps(manifest, sort_keys=True).encode("utf-8"),
            "manifest", crash_after, hard_crash,
        )
        _cleanup_older(root, manifest["generation"])
        return True
    finally:
        try:
            _unlock(fd)
        finally:
            os.close(fd)


def _cleanup_older(root, keep):
    base = os.path.join(root, "generations")
    if not os.path.isdir(base):
        return
    for name in os.listdir(base):
        if not name.isdigit() or int(name) >= int(keep):
            continue
        path = os.path.join(base, name)
        if not os.path.isdir(path):
            continue
        for child in os.listdir(path):
            child_path = os.path.join(path, child)
            try:
                if os.path.isfile(child_path):
                    os.unlink(child_path)
            except OSError:
                return
        try:
            os.rmdir(path)
        except OSError:
            return


def read_published(root):
    path = os.path.join(root, "manifest.json")
    try:
        manifest = json.loads(open(path, "r", encoding="utf-8").read())
        full = open(os.path.join(root, manifest["full"]), "rb").read()
        display = open(os.path.join(root, manifest["display"]), "rb").read()
        meta = json.loads(open(os.path.join(root, manifest["metadata"]), "r", encoding="utf-8").read())
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise Incomplete("unreadable generation") from exc
    if hashlib.sha256(full).hexdigest() != manifest.get("full_sha256"):
        raise Incomplete("full hash")
    if hashlib.sha256(display).hexdigest() != manifest.get("display_sha256"):
        raise Incomplete("display hash")
    if meta.get("observation_generation") != manifest.get("generation"):
        raise Incomplete("mixed generation")
    return {"manifest": manifest, "full": full, "display": display, "meta": meta}
