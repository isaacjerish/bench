import asyncio

from mcp_server.server import mcp


def test_mcp_exposes_explicit_structured_tools():
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    assert set(tools) == {
        "lab_ping", "lab_info", "measure_voltage", "read_digital", "measure_frequency"
    }
    assert tools["measure_voltage"].output_schema is not None
    assert tools["measure_frequency"].input_schema["properties"]["duration_ms"]["default"] == 250
