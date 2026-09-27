"""Read-only Benchy MCP surface for the website's Codex agent."""

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from mcp_server import server as full_server

mcp = MCPServer("benchy-readonly", instructions=(
    "These tools read physical circuits through the ESP32-S3. A firmware log "
    "is not evidence of physical output. Read describe_harness before choosing "
    "a probe. P1/P2/P3 accept only known 0–3.3 V signals with common ground. "
    "Never suggest connecting a probe to 5 V or an unknown voltage."
))

READ_ONLY_TOOLS = (
    "lab_ping", "lab_info", "describe_harness", "measure_voltage",
    "measure_voltage_pair", "check_telemetry_against_probes",
    "measure_bus_activity", "measure_digital_taps", "read_digital",
    "measure_frequency", "compare_light_sensor", "check_circuit",
    "read_imu_stream",
)

for tool_name in READ_ONLY_TOOLS:
    mcp.tool(structured_output=True, annotations=ToolAnnotations(
        read_only_hint=True, destructive_hint=False, open_world_hint=False,
    ))(getattr(full_server, tool_name))


if __name__ == "__main__":
    mcp.run("stdio")
