"""A flash plan must identify one enrolled DUT and stay inside the project."""

import pytest

from benchos.flash import plan_dut_flash, build_dut_firmware


def fixture(tmp_path):
    sketch = tmp_path / "custom_design"
    sketch.mkdir()
    (sketch / "custom_design.ino").write_text("void setup() {}\nvoid loop() {}\n")
    harness = {"lab": {"usb_serial_number": "LAB-1"},
               "dut": {"usb_serial_number": "DUT-2", "sketch_path": "custom_design",
                       "fqbn": "esp32:esp32:esp32c6:CDCOnBoot=cdc"}}
    ports = [{"device": "/dev/lab", "serial_number": "LAB-1", "vid": 12346, "pid": 4097},
             {"device": "/dev/dut", "serial_number": "DUT-2", "vid": 12346, "pid": 4097}]
    return harness, ports


def test_flash_plan_selects_enrolled_dut_after_port_change(tmp_path):
    harness, ports = fixture(tmp_path)
    result = plan_dut_flash(harness, ports, tmp_path)
    assert result["device"] == "/dev/dut"
    assert result["flashed_firmware_verified"] is False


def test_flash_plan_rejects_lab_identity_and_ambiguous_dut(tmp_path):
    harness, ports = fixture(tmp_path)
    harness["dut"]["usb_serial_number"] = "LAB-1"
    with pytest.raises(ValueError, match="lab controller"):
        plan_dut_flash(harness, ports, tmp_path)
    harness["dut"]["usb_serial_number"] = "DUT-2"
    with pytest.raises(ValueError, match="exactly one"):
        plan_dut_flash(harness, ports + [ports[1]], tmp_path)


def test_flash_plan_rejects_escape_from_project(tmp_path):
    harness, ports = fixture(tmp_path)
    harness["dut"]["sketch_path"] = "../other"
    with pytest.raises(ValueError, match="project-relative"):
        plan_dut_flash(harness, ports, tmp_path)


def test_compile_failure_never_uploads(tmp_path, monkeypatch):
    harness, ports = fixture(tmp_path)
    calls = []
    def fail_compile(argv, log, timeout_s):
        calls.append(argv)
        return {"ok": False, "exit_code": 1, "log": str(log), "tail": "compile failed"}
    monkeypatch.setattr("benchos.flash._command", fail_compile)
    monkeypatch.setattr("benchos.flash.shutil.which", lambda _: "/usr/bin/arduino-cli")
    result = build_dut_firmware(flash=True, harness=harness, ports_provider=lambda: ports,
                                root=tmp_path, runs_dir=tmp_path / "runs")
    assert result["compile"]["ok"] is False
    assert result["upload"] is None
    assert len(calls) == 1


def test_upload_rechecks_identity_and_records_artifact(tmp_path, monkeypatch):
    harness, ports = fixture(tmp_path)
    commands = []
    def fake_command(argv, log, timeout_s):
        commands.append(argv)
        if argv[1] == "compile":
            build_dir = Path(argv[argv.index("--build-path") + 1])
            (build_dir / "custom_design.ino.bin").write_bytes(b"firmware")
        return {"ok": True, "exit_code": 0, "log": str(log), "tail": "done"}
    from pathlib import Path
    monkeypatch.setattr("benchos.flash._command", fake_command)
    monkeypatch.setattr("benchos.flash.shutil.which", lambda _: "/usr/bin/arduino-cli")
    seen = 0
    def discover():
        nonlocal seen
        seen += 1
        return ports
    result = build_dut_firmware(flash=True, harness=harness, ports_provider=discover,
                                root=tmp_path, runs_dir=tmp_path / "runs")
    assert seen == 2
    assert commands[1][1] == "upload"
    assert commands[1][commands[1].index("--port") + 1] == "/dev/dut"
    assert "custom_design.ino.bin" in result["artifact_sha256"]
    assert result["upload"]["status"] == "reported_success"
    assert result["flashed_firmware_verified"] is False
    assert (Path(result["run_dir"]) / "evidence.json").is_file()
