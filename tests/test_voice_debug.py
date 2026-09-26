"""Voice endpoints keep credentials local and tool access read-only."""

import io
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from benchos.dashboard import (DashboardServer, DashboardState, create_voice_token,
                               invoke_voice_tool, voice_tool_specs)


def test_voice_tool_schemas_exclude_firmware_write_tools():
    names = {tool["name"] for tool in voice_tool_specs()}
    assert "describe_harness" in names
    assert "measure_voltage" in names
    assert "read_source_file" in names
    assert "build_and_flash_dut" not in names
    assert "flash_dut" not in names


def test_voice_tool_execution_rejects_write_and_unlisted_source(monkeypatch):
    with pytest.raises(ValueError, match="not enabled"):
        invoke_voice_tool("build_and_flash_dut", {})
    monkeypatch.setattr("benchos.dashboard.viewable_source_files", lambda: ("benchos/client.py",))
    with pytest.raises(ValueError, match="allowlist"):
        invoke_voice_tool("read_source_file", {"path": "../.env"})


def test_missing_voice_key_is_clear_and_never_returns_a_secret(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="XAI_API_KEY is not set"):
        create_voice_token()


def test_xai_token_error_does_not_echo_credentials(monkeypatch):
    key = "example-secret-that-must-not-leak"
    monkeypatch.setenv("XAI_API_KEY", key)

    def fail_request(*_args, **_kwargs):
        raise HTTPError("https://api.x.ai", 401, "Unauthorized", {}, io.BytesIO(key.encode()))

    monkeypatch.setattr("benchos.dashboard.urllib.request.urlopen", fail_request)
    with pytest.raises(RuntimeError) as error:
        create_voice_token()
    assert key not in str(error.value)


def test_voice_endpoints_require_local_origin_and_block_write_calls(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    state = DashboardState()
    try:
        server = DashboardServer(("127.0.0.1", 0), state)
    except PermissionError:
        pytest.skip("Local socket binding is disabled by this sandbox")
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(base + "/api/voice/status") as response:
            assert json.load(response)["configured"] is False
        with urlopen(base + "/api/voice/tools") as response:
            exposed = {tool["name"] for tool in json.load(response)["tools"]}
            assert "describe_harness" in exposed
            assert "build_and_flash_dut" not in exposed
        body = json.dumps({"name": "build_and_flash_dut", "arguments": {}}).encode()
        request = Request(base + "/api/voice/tool", data=body,
                          headers={"Content-Type": "application/json", "X-Benchy-Local": "1",
                                   "Origin": "http://attacker.example"}, method="POST")
        with pytest.raises(HTTPError) as blocked:
            urlopen(request)
        assert blocked.value.code == 403
        request = Request(base + "/api/voice/tool", data=body,
                          headers={"Content-Type": "application/json", "X-Benchy-Local": "1",
                                   "Origin": base}, method="POST")
        with pytest.raises(HTTPError) as blocked:
            urlopen(request)
        assert blocked.value.code == 403
        assert json.load(blocked.value)["error"] == "Tool is not enabled in voice mode"
        request = Request(base + "/api/voice/session", data=b"{}",
                          headers={"Content-Type": "application/json", "X-Benchy-Local": "1",
                                   "Origin": base}, method="POST")
        with pytest.raises(HTTPError) as unavailable:
            urlopen(request)
        assert unavailable.value.code == 503
        assert "XAI_API_KEY is not set" in json.load(unavailable.value)["error"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
