import pytest

from benchos.protocol import BenchError
from benchos.serial_lock import SerialPortLock


def test_same_port_is_serialized_and_released(tmp_path, monkeypatch):
    monkeypatch.setattr("benchos.serial_lock.tempfile.gettempdir", lambda: str(tmp_path))
    first = SerialPortLock("/dev/cu.test", timeout_s=0)
    second = SerialPortLock("/dev/cu.test", timeout_s=0)
    with first:
        with pytest.raises(BenchError, match="busy"):
            second.acquire()
    with second:
        assert second._fd is not None
