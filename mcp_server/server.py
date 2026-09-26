"""Local stdio MCP tools backed by real ESP32-S3 serial measurements."""

from typing import Any
from pathlib import Path

import yaml
from mcp.server.mcpserver import MCPServer

from benchos import BenchClient
from benchos.light import compare_light
from benchos.checks import run_suite
from benchos.dashboard import read_imu_report
from benchos.harness import describe_harness as read_harness
from benchos.flash import plan_dut_flash as read_flash_plan, build_dut_firmware, flash_result_ok
from benchos.telemetry import check_live_declared_telemetry
from benchos.protocol import BenchError

mcp = MCPServer("benchos", instructions=(
    "These tools read physical circuits through the ESP32-S3. "
    "A firmware log is not evidence of physical output. "
    "Never connect P1 to a signal outside 0–3.3 V. "
    "The circuit must match the selected check profile; software cannot rewire it."
))

PROFILES = {"rail_3v3", "ground", "led_blink", "servo_signal", "imu_vcc"}
PROFILE_DIR = Path(__file__).resolve().parent.parent / "physical_tests"


def _measure(method: str, *args, timeout: float = 3.0) -> dict[str, Any]:
    try:
        with BenchClient(timeout=timeout) as client:
            return {"ok": True, **getattr(client, method)(*args)}
    except (BenchError, OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool(structured_output=True)
def lab_ping() -> dict[str, Any]:
    """Check that the physical ESP32-S3 lab controller responds."""
    return _measure("ping")


@mcp.tool(structured_output=True)
def lab_info() -> dict[str, Any]:
    """Read firmware identity and available probe count."""
    return _measure("info")


@mcp.tool(structured_output=True)
def describe_harness() -> dict[str, Any]:
    """Return declared P1/P2/P3 wiring and voltage limits; declarations are not proof."""
    try:
        return {"ok": True, **read_harness()}
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool(structured_output=True)
def plan_dut_flash() -> dict[str, Any]:
    """Identify the declared DUT by stable USB serial and source path; does not flash."""
    try:
        return {"ok": True, **read_flash_plan()}
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool(structured_output=True)
def build_and_flash_dut() -> dict[str, Any]:
    """Compile and upload the declared sketch to its unique enrolled DUT USB device.

    Returns separate compile/upload evidence. Neither a successful upload nor
    local source identity proves the running code or physical circuit.
    """
    try:
        result = build_dut_firmware(flash=True)
        return {"ok": flash_result_ok(result), **result}
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool(structured_output=True)
def measure_voltage(probe: str) -> dict[str, Any]:
    """Measure approximate physical voltage on a 0–3.3 V probe tip."""
    return _measure("measure_voltage", probe)


@mcp.tool(structured_output=True)
def measure_voltage_pair() -> dict[str, Any]:
    """Read P1 then P2 over one S3 connection; timestamps show they are not simultaneous."""
    return _measure("measure_voltage_pair")


@mcp.tool(structured_output=True)
def check_telemetry_against_probes() -> dict[str, Any]:
    """Compare declared numeric DUT serial fields with fresh physical S3 probes.

    Discovers the enrolled boards by USB identity; checks only declared fields
    and nodes, and reports missing/stale serial data as unverified.
    """
    try:
        result = check_live_declared_telemetry()
        return {"ok": result["state"] == "pass", **result}
    except (BenchError, OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        return {"ok": False, "state": "error", "error": str(exc)}


@mcp.tool(structured_output=True)
def measure_bus_activity(duration_ms: int = 1000) -> dict[str, Any]:
    """Count approximate SDA/SCL transitions on declared 3.3 V read-only inputs; does not decode I²C."""
    return _measure("measure_bus_activity", duration_ms)


@mcp.tool(structured_output=True)
def measure_digital_taps(duration_ms: int = 1000) -> dict[str, Any]:
    """Count D1–D5 input transitions over overlapping windows and compare declared endpoints.

    Unconfirmed connections cannot support a diagnosis. Counts are approximate;
    this does not decode protocols or establish continuity between endpoints.
    """
    return _measure("measure_digital_taps", duration_ms, timeout=5.0)


@mcp.tool(structured_output=True)
def read_digital(probe: str) -> dict[str, Any]:
    """Read the current physical HIGH or LOW level of a probe."""
    return _measure("read_digital", probe)


@mcp.tool(structured_output=True)
def measure_frequency(probe: str, duration_ms: int = 250) -> dict[str, Any]:
    """Count physical rising edges locally; also report one high pulse width."""
    return _measure("measure_frequency", probe, duration_ms, timeout=5.0)


@mcp.tool(structured_output=True)
def compare_light_sensor(dut_port: str) -> dict[str, Any]:
    """Compare C6-reported light voltage with the real voltage measured by S3 P1."""
    try:
        with BenchClient(timeout=3.0) as client:
            return {"ok": True, **compare_light(client, dut_port)}
    except (BenchError, OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool(structured_output=True)
def check_circuit(profile: str) -> dict[str, Any]:
    """Run a named physical check: rail_3v3, ground, led_blink, servo_signal, or imu_vcc."""
    if profile not in PROFILES:
        return {"ok": False, "error": "Unknown profile. Choose rail_3v3, ground, led_blink, servo_signal, or imu_vcc."}
    try:
        with BenchClient(timeout=3.0) as client:
            return {"ok": True, **run_suite(client, PROFILE_DIR / f"{profile}.yaml")}
    except (BenchError, OSError, ValueError, TypeError) as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool(structured_output=True)
def read_imu_stream(dut_port: str) -> dict[str, Any]:
    """Read one C6 MPU acceleration report; this is a DUT claim, not independent physical proof."""
    try:
        return {"ok": True, "verified_by_probe": False, **read_imu_report(dut_port)}
    except (BenchError, OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}


if __name__ == "__main__":
    mcp.run("stdio")
