"""Cooperate across BenchOS processes sharing a USB serial port on macOS/Linux."""

from __future__ import annotations

import fcntl
import hashlib
import os
import tempfile
import time
from pathlib import Path

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
        deadline = time.monotonic() + self.timeout_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fd = fd
                return
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise BenchError(f"Serial port {self.port} is busy; retry shortly")
                time.sleep(0.05)
            except OSError:
                os.close(fd)
                raise

    def release(self) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> SerialPortLock:
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()
