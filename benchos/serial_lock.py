"""Cooperate across BenchOS processes sharing a USB serial port."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from .protocol import BenchError


class SerialPortLock:
    def __init__(self, port: str, timeout_s: float = 3.0):
        digest = hashlib.sha256(port.encode("utf-8")).hexdigest()[:16]
        self.path = Path(tempfile.gettempdir()) / f"benchos-serial-{digest}.lock"
        self.port = port
        self.timeout_s = timeout_s
        self._fd: int | None = None

    def acquire(self) -> None:
        if self._fd is not None:
            return
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        # msvcrt.locking locks a byte range, so ensure byte zero exists.
        if os.name == "nt" and os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")
            os.lseek(fd, 0, os.SEEK_SET)
        deadline = time.monotonic() + self.timeout_s
        while True:
            try:
                if os.name == "nt":
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fd = fd
                return
            except (BlockingIOError, OSError) as exc:
                contended = isinstance(exc, BlockingIOError)
                if os.name == "nt" and isinstance(exc, OSError):
                    contended = exc.errno in (13, 36) or getattr(exc, "winerror", None) == 33
                if not contended:
                    os.close(fd)
                    raise
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise BenchError(f"Serial port {self.port} is busy; retry shortly")
                time.sleep(0.05)
            except OSError:
                os.close(fd)
                raise

    def release(self) -> None:
        if self._fd is not None:
            if os.name == "nt":
                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> SerialPortLock:
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()
