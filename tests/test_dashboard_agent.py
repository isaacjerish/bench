"""Regression coverage for the dashboard's local Codex measurement bridge."""
import asyncio
import io
import json
import os
import subprocess
import sys
import tomllib
from urllib.error import HTTPError

import pytest

from benchos.dashboard import agent_mcp_config, codex_event_error, safe_agent_diagnostic
from benchos.visual_inspection import GeminiRestProvider, VisualError


def test_mcp_command_keeps_venv_interpreter_and_imports_tools():
    config = tomllib.loads('\n'.join(agent_mcp_config()))['mcp_servers']['benchy']
    assert config['command'] == sys.executable
    result = subprocess.run([config['command'], '-c',
        'from mcp_server.agent_readonly import mcp; print(mcp.name)'],
        capture_output=True, text=True, timeout=15, env={**os.environ,
        **config['env']})
    assert result.returncode == 0, result.stderr
    assert 'benchy-readonly' in result.stdout


def test_dashboard_mcp_exposes_measurements_without_firmware_writes():
    from mcp_server.agent_readonly import mcp
    tools = asyncio.run(mcp.list_tools())
    assert all(tool.annotations.read_only_hint is True for tool in tools)
    names = {tool.name for tool in tools}
    assert {'measure_voltage', 'measure_frequency', 'describe_harness',
            'check_telemetry_against_probes', 'measure_digital_taps'} <= names
    assert not any('flash' in name or 'upload' in name for name in names)


def test_photo_context_provider_http_error_is_sanitized():
    def fail(request, timeout):
        raise HTTPError(request.full_url, 401, 'Unauthorized', {},
                        io.BytesIO(b'{"error":{"message":"private-key"}}'))
    with pytest.raises(VisualError, match='Visual analysis failed') as error:
        GeminiRestProvider('private-key', 'test-model', fail).describe_images([
            (b'\xff\xd8\xfftest-photo', 'image/jpeg')])
    assert 'private-key' not in str(error.value)


def test_photo_context_describes_all_images_without_diagnosis_schema():
    def succeed(request, timeout):
        body = json.loads(request.data)
        parts = body['contents'][0]['parts']
        assert sum('inlineData' in part for part in parts) == 2
        assert 'responseSchema' not in body['generationConfig']
        return io.BytesIO(json.dumps({'candidates': [{'content': {'parts': [
            {'text': 'A board and two visible wires; pin labels are uncertain.'}]}}]}).encode())
    answer = GeminiRestProvider('test-key', 'test-model', succeed).describe_images([
        (b'photo1', 'image/jpeg'), (b'photo2', 'image/png')])
    assert 'pin labels are uncertain' in answer


def test_structured_agent_errors_are_readable_and_credentials_are_redacted(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'sample-secret-for-regression')
    detail = codex_event_error({'type': 'turn.failed', 'error': {
        'message': '\x1b[31mAuthentication failed: sample-secret-for-regression\x1b[0m'}})
    assert detail == 'Authentication failed: [redacted]'
    assert codex_event_error({'type': 'error', 'message': 'Usage limit reached'}) == 'Usage limit reached'
    assert codex_event_error({'type': 'item.completed', 'item': {'error': 'not a turn failure'}}) == ''
    assert safe_agent_diagnostic('Authorization: Bearer abc.def.ghi') == 'Authorization: Bearer [redacted]'


@pytest.mark.parametrize('events,return_code,expected', [
    ([{'type': 'error', 'message': 'Reconnecting...'},
      {'type': 'turn.failed', 'error': {'message': 'Usage limit reached. Try again at 11:30 PM.'}}],
     1, 'Usage limit reached. Try again at 11:30 PM.'),
    ([{'type': 'turn.failed', 'error': {'message': 'Model access unavailable.'}}],
     0, 'Model access unavailable.'),
    ([{'type': 'error', 'message': 'Reconnecting...'},
      {'type': 'turn.completed'}], 0, None),
])
def test_chat_surfaces_json_failure_without_stderr(monkeypatch, events, return_code, expected):
    import threading
    from urllib.request import Request, urlopen
    from benchos.dashboard import DashboardServer, DashboardState

    class FakeProcess:
        def __init__(self, *args, **kwargs):
            self.stdin = io.StringIO()
            self.stdout = io.StringIO('\n'.join(json.dumps(event) for event in events))
        def wait(self):
            return return_code
        def poll(self):
            return return_code

    monkeypatch.setattr('benchos.dashboard.find_codex_cli', lambda: 'test-codex')
    monkeypatch.setattr('benchos.dashboard.subprocess.Popen', FakeProcess)
    state = DashboardState()
    server = DashboardServer(('127.0.0.1', 0), state)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{server.server_address[1]}'
    try:
        request = Request(base + '/api/agent/chat',
            data=json.dumps({'message': 'Test the connection'}).encode(),
            headers={'Content-Type': 'application/json', 'X-Benchy-Local': '1', 'Origin': base})
        with urlopen(request, timeout=5) as response:
            frames = [json.loads(line[6:]) for line in response.read().decode().splitlines()
                      if line.startswith('data: ')]
        failures = [frame['message'] for frame in frames if frame['kind'] == 'error']
        assert failures == ([expected] if expected else [])
        assert any(frame['kind'] == 'complete' for frame in frames) is (expected is None)
    finally:
        server.shutdown()
        server.server_close()
        state.close()
        worker.join(timeout=2)


def test_web_flash_confirmation_and_upload_failure_remain_separate(monkeypatch):
    import threading
    from urllib.request import Request, urlopen
    from benchos.dashboard import DashboardServer, DashboardState
    calls=[]
    def fake_build(*, flash):
        calls.append(flash)
        return {'compile': {'ok': True}, 'upload': {'ok': False}, 'postflash': None}
    monkeypatch.setattr('benchos.flash.build_dut_firmware',fake_build)
    state=DashboardState()
    server=DashboardServer(('127.0.0.1',0),state)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    base=f'http://127.0.0.1:{server.server_address[1]}'
    def request(payload,origin=base):
        return urlopen(Request(base+'/api/agent/flash',data=json.dumps(payload).encode(),
            headers={'Content-Type':'application/json','X-Benchy-Local':'1','Origin':origin}),timeout=5)
    try:
        for payload,origin,expected in [({},base,400),
            ({'confirmation':'FLASH_DECLARED_DUT','wiring_confirmed':False},base,400),
            ({'confirmation':'FLASH_DECLARED_DUT','wiring_confirmed':True},'http://other.invalid',403)]:
            with pytest.raises(HTTPError) as error: request(payload,origin)
            assert error.value.code==expected
        assert calls==[]
        with pytest.raises(HTTPError) as failure:
            request({'confirmation':'FLASH_DECLARED_DUT','wiring_confirmed':True})
        assert failure.value.code==409
        assert json.load(failure.value)['ok'] is False
        assert calls==[True]
    finally:
        server.shutdown();server.server_close();state.close();worker.join(timeout=2)
