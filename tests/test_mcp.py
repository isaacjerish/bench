import asyncio

from mcp_server.server import mcp


def test_mcp_exposes_explicit_structured_tools():
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    assert set(tools) == {
        "lab_ping", "lab_info", "describe_harness", "plan_dut_flash", "measure_voltage", "measure_voltage_pair", "measure_bus_activity", "read_digital", "measure_frequency",
        "compare_light_sensor", "check_circuit", "read_imu_stream"
    }
    assert tools["measure_voltage"].output_schema is not None
    assert tools["measure_frequency"].input_schema["properties"]["duration_ms"]["default"] == 250


def test_check_circuit_rejects_unknown_profile_without_opening_serial():
    from mcp_server.server import check_circuit

    result = check_circuit("../../somewhere")
    assert result["ok"] is False
    assert "Unknown profile" in result["error"]
