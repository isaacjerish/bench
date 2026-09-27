"""Visual inspection stays a hypothesis until an allowlisted probe measurement."""

import io
import json
import threading
import time
import urllib.error
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import http.client
import pytest

from benchos.dashboard import DashboardServer, DashboardState
from benchos.harness import describe_harness
from benchos.visual_inspection import (
    GeminiRestProvider, SessionStore, VisualError, analyze_dut_image, build_inspection_context,
    execute_check, findings_document, is_phone_capture_path, local_dashboard_allowed,
    public_base_url, read_latest_findings, resolve_check, summarize_physical, validate_analysis,
    validate_image, write_latest_findings, SYSTEM_PROMPT, get_provider,
    availability, unreachable_host_warning,
)

JPEG = b"\xff\xd8\xff\xe0BENCHY-JPEG-MARKER!!"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
WEBP = b"RIFF" + b"\x24\x00\x00\x00" + b"WEBP" + b"payload"
VALID = {
    "observed_hardware": [{"item": "ESP32-C6 development board", "confidence": "HIGH"}],
    "observations": [{"observation": "A signal jumper appears adjacent to a GPIO label", "confidence": "MEDIUM"}],
    "possible_issues": [{"issue": "Signal wire may not match the declared GPIO",
                         "evidence": ["Expected harness uses a different pin", "Visible jumper is nearby"],
                         "confidence": "LOW"}],
    "recommended_checks": [
        {"measurement": "measure_frequency", "target": "P1", "reason": "Confirm whether PWM reaches the declared net"},
        {"measurement": "os.system", "target": "P1", "reason": "Do not run this"},
    ],
    "limitations": ["GPIO silkscreen is partially obscured"],
    "voltage_v": 3.3,
    "continuity": True,
}


def test_prompt_refuses_electrical_facts_from_appearance():
    assert "VISUAL OBSERVATION" in SYSTEM_PROMPT
    assert "Never infer voltage" in SYSTEM_PROMPT
    assert "probes determine what is electrically true" in SYSTEM_PROMPT


def test_public_url_rejects_localhost_and_missing_values(monkeypatch):
    monkeypatch.delenv("BENCHY_PUBLIC_BASE_URL", raising=False)
    assert public_base_url() is None
    for blocked in ("http://127.0.0.1:8765", "http://localhost:8765", "http://10.0.0.8:8765/bench"):
        monkeypatch.setenv("BENCHY_PUBLIC_BASE_URL", blocked)
        assert public_base_url() is None
    monkeypatch.setenv("BENCHY_PUBLIC_BASE_URL", "http://10.0.0.8:8765")
    assert public_base_url() == "http://10.0.0.8:8765"


def test_qr_target_that_is_not_this_computer_is_called_out(monkeypatch):
    monkeypatch.setattr("benchos.visual_inspection.local_ipv4_addresses",
                        lambda: {"10.90.238.177"})
    warning = unreachable_host_warning("http://192.168.1.50:8765")
    assert "192.168.1.50" in warning and "10.90.238.177" in warning
    assert unreachable_host_warning("http://10.90.238.177:8765") is None
    assert unreachable_host_warning("https://benchy.ngrok.app") is None

    monkeypatch.setattr("benchos.visual_inspection.local_ipv4_addresses", set)
    assert unreachable_host_warning("http://192.168.1.50:8765") is None

    monkeypatch.setenv("BENCHY_PUBLIC_BASE_URL", "http://192.168.1.50:8765")
    monkeypatch.setattr("benchos.visual_inspection.local_ipv4_addresses",
                        lambda: {"10.90.238.177"})
    reachable = availability()
    assert reachable["available"] is True
    assert "will not reach" in reachable["warning"]


def test_dashboard_routes_stay_local_while_capture_does_not():
    assert local_dashboard_allowed("127.0.0.1", "127.0.0.1:8765") is True
    assert local_dashboard_allowed("127.0.0.1", "tunnel.example") is False
    assert local_dashboard_allowed("192.168.1.20", "192.168.1.20:8765") is False
    assert is_phone_capture_path("/app.css") is True
    assert is_phone_capture_path("/api/probes") is False
    assert is_phone_capture_path("/capture/" + "a" * 24) is True


def test_session_expires_and_rejects_unknown_tokens(monkeypatch):
    monkeypatch.setenv("BENCHY_PUBLIC_BASE_URL", "http://10.1.1.1:8765")
    store = SessionStore()
    opened = datetime(2026, 9, 26, 18, tzinfo=timezone.utc)
    view = store.start(now=opened)
    assert view["qr_svg"].startswith("<svg")
    assert "127.0.0.1" not in view["qr_svg"]
    token = view["capture_url"].rsplit("/", 1)[-1]
    assert store.phone_state(token, now=opened)["status"] == "waiting"
    with pytest.raises(VisualError, match="expired"):
        store.store_image(token, JPEG, "image/jpeg", now=opened + timedelta(minutes=11))
    assert store.phone_state(token, now=opened + timedelta(minutes=11))["status"] == "expired"
    with pytest.raises(VisualError) as missing:
        store.phone_state("not-a-real-token")
    assert missing.value.status == HTTPStatus.NOT_FOUND


def test_image_type_and_size_are_rejected():
    assert validate_image(JPEG, "image/jpeg") == "image/jpeg"
    assert validate_image(PNG, "image/png") == "image/png"
    assert validate_image(WEBP, "image/webp") == "image/webp"
    with pytest.raises(VisualError, match="JPEG, PNG, or WEBP"):
        validate_image(b"GIF89a" + b"\x00" * 16, "image/gif")
    with pytest.raises(VisualError, match="do not match"):
        validate_image(JPEG, "image/png")
    with pytest.raises(VisualError, match="5 MB"):
        validate_image(JPEG + b"0" * (5 * 1024 * 1024), "image/jpeg")


def test_analysis_drops_electrical_claims_and_unsupported_checks():
    clean = validate_analysis(VALID)
    assert "voltage_v" not in clean
    assert "continuity" not in clean
    assert clean["evidence_class"] == "visual_hypothesis"
    assert clean["possible_issues"][0]["electrically_verified"] is False
    assert clean["possible_issues"][0]["kind"] == "hypothesis"
    supported = [item for item in clean["recommended_checks"] if item["supported"]]
    blocked = [item for item in clean["recommended_checks"] if not item["supported"]]
    assert supported[0]["measurement"] == "measure_frequency"
    assert supported[0]["target"] == "P1"
    assert blocked[0]["measurement"] == "os.system"
    with pytest.raises(VisualError, match="could not validate"):
        validate_analysis({"observed_hardware": "board"})
    with pytest.raises(VisualError, match="could not validate"):
        validate_analysis([])


def test_allowlist_fixes_probe_window_and_rejects_other_commands():
    spec = resolve_check("measure_frequency", "P1")
    assert spec == {"measurement": "measure_frequency", "probe": "P1", "duration_ms": 1000}
    assert resolve_check("check_circuit", "servo_signal")["profile"] == "servo_signal"
    assert resolve_check("measure_voltage_pair", "P9") == {"measurement": "measure_voltage_pair"}
    for measurement, target in (("os.system", "P1"), ("measure_frequency", "P9"),
                                ("check_circuit", "../../somewhere"), ("build_and_flash_dut", "")):
        with pytest.raises(VisualError):
            resolve_check(measurement, target)

    class Fake:
        def __getattr__(self, name):
            raise AssertionError(name)

        def measure_frequency(self, probe, duration_ms):
            return {"probe": probe, "frequency_hz": 49.98, "pulse_us": 1501, "edges": 50}

    reading = execute_check(Fake(), spec)
    assert "49.98" in summarize_physical(spec, reading)
    assert "1501" in summarize_physical(spec, reading)
    with pytest.raises(VisualError):
        execute_check(Fake(), {"measurement": "os.system"})


def test_context_uses_the_harness_and_omits_usb_identity():
    harness = describe_harness()
    context = build_inspection_context(
        harness,
        {"timestamp": "t", "digital_states": {"P1": "LOW"},
         "readings": [{"probe": "P1", "voltage_v": 0.03, "declared_net": "LIGHT_SENSE"}]},
        None,
        ["light_mv=12"],
    )
    encoded = json.dumps(context)
    assert harness["dut"]["usb_serial_number"] not in encoded
    assert context["dut"]["board"] == "ESP32-C6"
    assert context["source"] == "user_declared"
    assert context["physically_verified"] is False
    assert context["latest_measurements"]["probes"]["readings"][0]["voltage_v"] == 0.03
    assert context["expected_harness"]["probes"]["P1"]["net"] == "LIGHT_SENSE"
    assert "light_mv=12" in context["latest_measurements"]["recent_serial_lines"]


def test_gemini_errors_do_not_switch_models():
    calls = {"count": 0}

    def unavailable(request, timeout=30):
        calls["count"] += 1
        raise urllib.error.HTTPError(
            request.full_url, 404, "Not Found", hdrs=None,
            fp=io.BytesIO(b'{"error":{"message":"models/gemini-robotics-er-2-preview is not found"}}'))

    provider = GeminiRestProvider("test-key", "gemini-robotics-er-2-preview", unavailable)
    with pytest.raises(VisualError, match="will not switch models") as failure:
        provider.analyze(JPEG, "image/jpeg", {"dut": {"board": "ESP32-C6"}})
    assert failure.value.status == HTTPStatus.SERVICE_UNAVAILABLE
    assert calls["count"] == 1

    def quota(request, timeout=30):
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many", hdrs=None,
                                     fp=io.BytesIO(b'{"error":{"message":"Resource exhausted"}}'))

    with pytest.raises(VisualError, match="quota or rate limit"):
        GeminiRestProvider("test-key", "gemini-robotics-er-2-preview", quota).analyze(JPEG, "image/jpeg", {})

    def timed_out(request, timeout=30):
        raise TimeoutError()

    with pytest.raises(VisualError, match="timed out"):
        GeminiRestProvider("test-key", "gemini-robotics-er-2-preview", timed_out).analyze(JPEG, "image/jpeg", {})

    def opener(*_args, **_kwargs):
        raise AssertionError("network")

    with pytest.raises(VisualError, match="GEMINI_API_KEY"):
        GeminiRestProvider("", "gemini-robotics-er-2-preview", opener).analyze(JPEG, "image/jpeg", {})


def test_gemini_success_is_validated_structured_output():
    def succeed(request, timeout=30):
        assert "gemini-robotics-er-2-preview" in request.full_url
        assert request.get_header("X-goog-api-key") == "test-key"
        body = json.loads(request.data.decode())
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["systemInstruction"]["parts"][0]["text"] == SYSTEM_PROMPT
        assert "inlineData" in body["contents"][0]["parts"][1]
        payload = {"candidates": [{"content": {"parts": [{"text": json.dumps(VALID)}]}}]}
        response = io.BytesIO(json.dumps(payload).encode())
        response.status = 200

        class Handle:
            def read(self, _limit=-1):
                return response.getvalue()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        return Handle()

    analysis = analyze_dut_image(JPEG, "image/jpeg", {"dut": {"board": "ESP32-C6"}},
                                 GeminiRestProvider("test-key", "gemini-robotics-er-2-preview", succeed))
    assert analysis["observed_hardware"][0]["item"].startswith("ESP32-C6")
    assert "voltage_v" not in analysis

    def malformed(request, timeout=30):
        payload = {"candidates": [{"content": {"parts": [{"text": "not-json"}]}}]}

        class Handle:
            def read(self, _limit=-1):
                return json.dumps(payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        return Handle()

    with pytest.raises(VisualError, match="valid JSON"):
        GeminiRestProvider("test-key", "gemini-robotics-er-2-preview", malformed).analyze(JPEG, "image/jpeg", {})


def test_truncated_and_empty_answers_name_their_own_cause():
    def responder(payload):
        def opener(request, timeout=30):
            class Handle:
                def read(self, _limit=-1):
                    return json.dumps(payload).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

            return Handle()

        return opener

    truncated = responder({"candidates": [{"finishReason": "MAX_TOKENS",
                                           "content": {"parts": [{"text": '{"observed_hardware": [{"it'}]}}]})
    with pytest.raises(VisualError, match="token output limit"):
        GeminiRestProvider("test-key", "m", truncated).analyze(JPEG, "image/jpeg", {})

    silent = responder({"candidates": [{"finishReason": "OTHER", "content": {"role": "model"}}]})
    with pytest.raises(VisualError, match="no text to read"):
        GeminiRestProvider("test-key", "m", silent).analyze(JPEG, "image/jpeg", {})

    blocked = responder({"candidates": [{"finishReason": "SAFETY"}]})
    with pytest.raises(VisualError, match="declined to analyze"):
        GeminiRestProvider("test-key", "m", blocked).analyze(JPEG, "image/jpeg", {})

    empty = responder({"candidates": []})
    with pytest.raises(VisualError, match="no answer"):
        GeminiRestProvider("test-key", "m", empty).analyze(JPEG, "image/jpeg", {})


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("BENCHY_VISION_PROVIDER", "openai")
    with pytest.raises(VisualError, match="must be gemini"):
        get_provider()
    monkeypatch.setenv("BENCHY_VISION_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "present")
    monkeypatch.delenv("BENCHY_VISION_MODEL", raising=False)
    assert get_provider().model == "gemini-robotics-er-2-preview"


def test_latest_findings_file_has_no_photo(monkeypatch, tmp_path):
    path = tmp_path / "latest.json"
    monkeypatch.setenv("BENCHY_VISUAL_FINDINGS", str(path))
    assert read_latest_findings()["ok"] is False
    write_latest_findings(findings_document(validate_analysis(VALID), {"dut": {"board": "ESP32-C6"}},
                                            "gemini-robotics-er-2-preview"))
    document = read_latest_findings()
    assert document["ok"] is True
    assert document["physically_verified"] is False
    assert b"BENCHY-JPEG-MARKER" not in path.read_bytes()
    from mcp_server.server import latest_visual_inspection
    assert latest_visual_inspection()["analysis"]["possible_issues"][0]["electrically_verified"] is False


def test_phone_upload_reaches_the_desktop_without_opening_probes(monkeypatch, tmp_path):
    monkeypatch.setenv("BENCHY_VISUAL_FINDINGS", str(tmp_path / "latest.json"))
    state = DashboardState()
    seen = {}

    def analyzer(image, mime, context):
        seen["image"] = image
        seen["mime"] = mime
        seen["context"] = context
        return VALID

    state.vision_analyzer = analyzer
    try:
        server = DashboardServer(("127.0.0.1", 0), state)
    except PermissionError:
        pytest.skip("Local socket binding is disabled by this sandbox")
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    port = server.server_address[1]
    base = f"http://127.0.0.1:{port}"
    monkeypatch.setenv("BENCHY_PUBLIC_BASE_URL", f"http://10.4.4.4:{port}")
    try:
        with urlopen(base + "/") as response:
            page = response.read()
            assert b"PHOTO CONTEXT" in page
            assert b"visual-start" in page
        with pytest.raises(HTTPError) as blocked:
            urlopen(Request(base + "/api/visual/session", data=b"{}",
                            headers={"Content-Type": "application/json"}, method="POST"))
        assert blocked.value.code == 403
        with urlopen(Request(base + "/api/visual/session", data=b"{}",
                             headers={"Content-Type": "application/json", "X-Benchy-Local": "1"},
                             method="POST")) as response:
            assert response.status == 201
            started = json.load(response)
        assert started["status"] == "waiting"
        assert started["qr_svg"].startswith("<svg")
        assert "127.0.0.1" not in started["capture_url"]
        token = started["capture_url"].rsplit("/", 1)[-1]
        remote = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        remote.request("GET", "/api/probes", headers={"Host": "tunnel.example"})
        denied = remote.getresponse()
        assert denied.status == 403
        denied.read()
        remote.request("GET", "/capture/" + token, headers={"Host": "10.4.4.4"})
        phone = remote.getresponse()
        phone_page = phone.read()
        assert phone.status == 200
        assert b'capture="environment"' in phone_page
        assert token.encode() in phone_page
        assert b"Take Photo" in phone_page
        remote.request("POST", "/capture/" + token, body=JPEG, headers={
            "Host": "10.4.4.4", "Content-Type": "image/jpeg"})
        accepted = remote.getresponse()
        assert accepted.status == 202
        accepted.read()
        deadline = time.time() + 3
        view = {}
        while time.time() < deadline:
            with urlopen(base + "/api/visual/session") as response:
                view = json.load(response)
            if view["status"] in {"complete", "error"}:
                break
            time.sleep(0.05)
        assert view["status"] == "complete"
        assert b"BENCHY-JPEG-MARKER" not in json.dumps(view).encode()
        assert seen == {}  # Upload alone never calls a model or opens probes.
        assert view["analysis"] is None
        assert view["photo_count"] == 1
        assert state.visual.images() == [(JPEG, "image/jpeg")]
        assert view["context"]["electrical_analysis"] is False
        with urlopen(base + "/api/visual/session/image") as response:
            assert response.headers["Content-Type"] == "image/jpeg"
            assert response.read().startswith(b"\xff\xd8\xff")
        remote.request("POST", "/capture/" + token, body=b"x", headers={
            "Host": "10.4.4.4", "Content-Type": "image/jpeg", "Content-Length": "6000000"})
        too_big = remote.getresponse()
        assert too_big.status == 400
        too_big.read()
    finally:
        server.shutdown()
        server.server_close()
        state.close()
        worker.join(timeout=2)


def test_recommended_check_uses_the_client_allowlist(monkeypatch, tmp_path):
    monkeypatch.setenv("BENCHY_PUBLIC_BASE_URL", "http://10.8.8.8:8765")
    monkeypatch.setenv("BENCHY_VISUAL_FINDINGS", str(tmp_path / "latest.json"))
    calls = []

    class FakeClient:
        def __init__(self, port, **_kwargs):
            self.port = port

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def measure_frequency(self, probe, duration_ms):
            calls.append((self.port, probe, duration_ms))
            return {"kind": "frequency", "probe": probe, "frequency_hz": 49.98,
                    "edges": 50, "window_ms": duration_ms, "pulse_us": 1501}

    monkeypatch.setattr("benchos.dashboard.candidate_ports", lambda: ["COM5"])
    monkeypatch.setattr("benchos.dashboard.BenchClient", FakeClient)
    state = DashboardState()
    state.visual.start()
    with pytest.raises(VisualError):
        state.run_visual_check("COM5", "os.system", "P1")
    assert calls == []
    result = state.run_visual_check("COM5", "measure_frequency", "P1")
    assert calls == [("COM5", "P1", 1000)]
    assert result["check"]["source"] == "s3_physical"
    assert result["check"]["evidence"] == "physical"
    assert "49.98" in result["check"]["summary"]
    assert result["session"]["physical_checks"][0]["summary"] == result["check"]["summary"]
