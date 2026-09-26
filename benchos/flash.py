"""Read-only preflight for a declared DUT build and USB target."""

from __future__ import annotations

import re
from pathlib import Path

from .harness import describe_harness
from .ports import available_ports

REPO_ROOT = Path(__file__).resolve().parent.parent
FQBN_RE = re.compile(r"[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+(?::[A-Za-z0-9_,=.-]+)?\Z")


def plan_dut_flash(harness: dict | None = None, ports: list[dict] | None = None,
                   root: Path = REPO_ROOT) -> dict:
    """Resolve source and the one USB device enrolled as DUT; write nothing."""
    harness = describe_harness() if harness is None else harness
    ports = available_ports() if ports is None else ports
    dut = harness.get("dut", {})
    lab = harness.get("lab", {})
    serial = dut.get("usb_serial_number")
    if not isinstance(serial, str) or not serial.strip():
        raise ValueError("DUT needs an enrolled USB serial number")
    lab_serial = lab.get("usb_serial_number")
    if lab_serial and serial.casefold() == str(lab_serial).casefold():
        raise ValueError("DUT USB identity matches the lab controller")
    matches = [port for port in ports if port.get("serial_number")
               and str(port["serial_number"]).casefold() == serial.casefold()]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one connected DUT with USB serial {serial}; found {len(matches)}")
    port = matches[0]
    if not isinstance(port.get("device"), str) or not port["device"]:
        raise ValueError("DUT USB device has no usable serial port")
    fqbn = dut.get("fqbn")
    if not isinstance(fqbn, str) or not FQBN_RE.fullmatch(fqbn):
        raise ValueError("DUT needs a valid declared Arduino FQBN")
    sketch_name = dut.get("sketch_path")
    if not isinstance(sketch_name, str) or not sketch_name:
        raise ValueError("DUT needs a declared sketch_path")
    relative = Path(sketch_name)
    if relative.is_absolute() or ".." in relative.parts or any(part.startswith(".") for part in relative.parts):
        raise ValueError("DUT sketch_path must be a project-relative directory")
    project_root = root.resolve()
    sketch = (project_root / relative).resolve()
    if not sketch.is_relative_to(project_root) or not sketch.is_dir() or not (sketch / f"{sketch.name}.ino").is_file():
        raise ValueError("DUT sketch_path must contain a matching .ino file inside this project")
    return {"source": "user_declared_plus_usb_discovery", "device": port["device"],
            "usb_serial_number": serial, "vid": port.get("vid"), "pid": port.get("pid"),
            "sketch_path": sketch_name, "fqbn": fqbn,
            "lab_usb_serial_number": lab_serial, "flashed_firmware_verified": False}
