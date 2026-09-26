"""Local stdio MCP tools backed by real ESP32-S3 serial measurements."""

from typing import Any

from mcp.server.mcpserver import MCPServer

from benchos import BenchClient
from benchos.light import compare_light
from benchos.protocol import BenchError

mcp = MCPServer("benchos", instructions=(
    "These tools read physical circuits through the ESP32-S3. "
    "A firmware log is not evidence of physical output. "
    "Never connect P1 to a signal outside 0–3.3 V."
))


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
def measure_voltage(probe: str) -> dict[str, Any]:
    """Measure approximate physical voltage on a 0–3.3 V probe tip."""
    return _measure("measure_voltage", probe)


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


if __name__ == "__main__":
    mcp.run("stdio")
