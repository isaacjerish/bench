"""USB serial client for the ESP32-S3 lab controller."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import serial

from . import config, ports
from .harness import describe_harness
from .protocol import BenchError, BenchProtocolError, parse_response, validate_probe
from .serial_lock import SerialPortLock

LOGGER = logging.getLogger(__name__)


class BenchClient:
    def __init__(self, port: str | None = None, *, timeout: float = config.TIMEOUT_S,
                 startup_delay: float = config.STARTUP_S, verbose: bool = False,
                 log_path: str | None = None):
        self._requested_port = port or config.configured_port()
        self.port = self._requested_port
        self.timeout = timeout
        self.startup_delay = startup_delay
        self.verbose = verbose
        self.log_path = log_path or config.configured_log()
        self._serial: serial.Serial | None = None
        self._port_lock: SerialPortLock | None = None
        if verbose:
            logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    def __enter__(self) -> BenchClient:
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def connect(self) -> BenchClient:
        if self._serial and self._serial.is_open:
            return self
        candidates = [self._requested_port] if self._requested_port else ports.candidate_ports()
        if not candidates:
            raise BenchError("No serial ports found. Connect the ESP32-S3 using a data USB cable.")
        failures: list[str] = []
        for candidate in candidates:
            try:
                self._port_lock = SerialPortLock(candidate)
                self._port_lock.acquire()
                transport = serial.Serial(candidate, config.BAUD, timeout=self.timeout,
                                          write_timeout=self.timeout)
                self._serial = transport
                time.sleep(self.startup_delay)  # ESP32 may reboot when serial opens.
                transport.reset_input_buffer()
                response = self._exchange("PING")
                if response["kind"] != "pong":
                    raise BenchProtocolError(f"{candidate} did not answer PING")
                self.port = candidate
                if self.verbose:
                    LOGGER.info("Connected to BenchOS on %s", candidate)
                return self
            except (serial.SerialException, OSError, BenchError) as exc:
                failures.append(f"{candidate}: {exc}")
                self.close()
        raise BenchError("No BenchOS controller responded. " + "; ".join(failures))

    def close(self) -> None:
        try:
            if self._serial:
                self._serial.close()
        finally:
            self._serial = None
            if self._port_lock:
                self._port_lock.release()
            self._port_lock = None

    def _exchange(self, command: str) -> dict:
        if not self._serial or not self._serial.is_open:
            raise BenchError("Not connected")
        if self.verbose:
            LOGGER.info("TX %s", command)
        try:
            self._serial.write((command + "\n").encode("ascii"))
            self._serial.flush()
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                raw = self._serial.readline()
                if not raw:
                    continue
                line = raw.decode("ascii", errors="replace").strip()
                if self.verbose:
                    LOGGER.info("RX %s", line)
                if not line.startswith(("OK ", "ERR ")):
                    continue  # Ignore ESP boot messages or other unrelated text.
                return parse_response(line)
        except (serial.SerialException, OSError) as exc:
            self.close()
            raise BenchError(f"Serial connection lost: {exc}") from exc
        failed_port = self.port
        self.close()
        raise BenchError(f"Timed out waiting for reply to {command!r} on {failed_port}")

    def _request(self, command: str, expected: str) -> dict:
        if not self._serial or not self._serial.is_open:
            self.connect()
        result = self._exchange(command)
        if result["kind"] != expected:
            raise BenchProtocolError(f"Expected {expected}, got {result['kind']}")
        if "probe" in result:
            expected_probe = command.split()[1]
            if result["probe"] != expected_probe:
                raise BenchProtocolError(f"Reply probe mismatch: {result['probe']}")
        self._log(result)
        return result

    def _log(self, result: dict) -> None:
        if self.log_path and result["kind"] in ("voltage", "digital", "frequency", "bus_activity"):
            record = {"timestamp": datetime.now(timezone.utc).isoformat(), **result}
            with Path(self.log_path).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record) + "\n")

    def ping(self) -> dict:
        return self._request("PING", "pong")

    def info(self) -> dict:
        return self._request("INFO", "info")

    def measure_voltage(self, probe: str) -> dict:
        return self._request(f"READ_ADC {validate_probe(probe)}", "voltage")

    def measure_voltage_pair(self, probe_a: str = "P1", probe_b: str = "P2") -> dict:
        """Read two input probes in order; these are close in time, not simultaneous."""
        names = (validate_probe(probe_a), validate_probe(probe_b))
        if names[0] == names[1] or set(names) != {"P1", "P2"}:
            raise ValueError("Choose distinct P1 and P2 probes")
        first_at = datetime.now(timezone.utc).isoformat()
        start = time.monotonic()
        first = self.measure_voltage(names[0])
        second_at = datetime.now(timezone.utc).isoformat()
        second = self.measure_voltage(names[1])
        declared = describe_harness()["probes"]
        def metadata(name: str) -> dict:
            item = declared[name]
            return {"declared_state": item["state"],
                    "declared_net": item["net"] if item["state"] == "connected" else None}
        return {"simultaneous": False, "elapsed_ms": round((time.monotonic() - start) * 1000, 1),
                "wiring_source": "user_declared",
                "readings": [{"timestamp": first_at, **metadata(names[0]), **first},
                             {"timestamp": second_at, **metadata(names[1]), **second}]}

    def read_digital(self, probe: str) -> dict:
        return self._request(f"READ_DIGITAL {validate_probe(probe)}", "digital")

    def measure_frequency(self, probe: str, duration_ms: int = 1000) -> dict:
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or not 10 <= duration_ms <= 2000:
            raise ValueError("duration_ms must be an integer from 10 to 2000")
        return self._request(f"MEASURE_FREQ {validate_probe(probe)} {duration_ms}", "frequency")

    def measure_bus_activity(self, duration_ms: int = 1000) -> dict:
        """Observe declared read-only SDA/SCL inputs; edge counts are approximate."""
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or not 10 <= duration_ms <= 2000:
            raise ValueError("duration_ms must be an integer from 10 to 2000")
        monitor = describe_harness()["bus_monitor"]
        if monitor["state"] != "connected":
            raise BenchError("Bus monitor is not declared connected; check wiring and harness/current.yaml")
        result = self._request(f"MEASURE_BUS {duration_ms}", "bus_activity")
        return {**result, "wiring_source": "user_declared",
                "sda_net": monitor["sda_net"], "scl_net": monitor["scl_net"]}
