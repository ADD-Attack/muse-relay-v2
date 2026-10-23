"""OS lifetime lock for one watcher output set.

The supplied scripts do not lock. Their comments mention a launcher PID file.
A PID file is not this lock. The fd stays open for the process; the kernel
releases it on exit or kill. The file itself is never removed.
"""
import os


class LockHeld(Exception):
    def __init__(self, path):
        self.path = path
        super().__init__(f"another watcher holds the output lock: {path}")


class OutputLock:
    def __init__(self, path):
        self.path = os.fspath(path)
        self._fd = None

    def acquire(self):
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            _lock_fd(fd)
        except (BlockingIOError, OSError):
            os.close(fd)
            raise LockHeld(self.path) from None
        self._fd = fd
        return self

    def release(self):
        fd = self._fd
        self._fd = None
        if fd is not None:
            os.close(fd)

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_exc):
        self.release()


def _lock_fd(fd):
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
