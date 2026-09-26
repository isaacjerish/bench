"""A flash plan must identify one enrolled DUT and stay inside the project."""

import pytest

from benchos.flash import plan_dut_flash


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
