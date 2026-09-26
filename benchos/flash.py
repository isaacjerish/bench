"""Identity-checked build and upload of a user-declared DUT sketch."""

from __future__ import annotations

import re
import hashlib
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .harness import describe_harness
from .ports import available_ports

REPO_ROOT = Path(__file__).resolve().parent.parent
FQBN_RE = re.compile(r"[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+(?::[A-Za-z0-9_,=.-]+)?\Z")
CONFIG = REPO_ROOT / "scripts" / "arduino-cli.yaml"
FLASH_RUNS = REPO_ROOT.parents[1] / "work" / "flash-runs"


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


def _source_hash(sketch: Path) -> str:
    """Hash sketch content, including headers, in stable relative-path order."""
    files = sorted(path for path in sketch.rglob("*") if path.is_file())
    if len(files) > 128 or any(path.is_symlink() or not path.resolve().is_relative_to(sketch)
                               for path in files):
        raise ValueError("Sketch contains too many files or a symlink outside its directory")
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(sketch)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _git_state(root: Path, sketch_name: str) -> dict:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                                text=True, timeout=3, check=True).stdout.strip()
        changed = subprocess.run(["git", "status", "--porcelain", "--", sketch_name], cwd=root,
                                 capture_output=True, text=True, timeout=3, check=True).stdout.splitlines()
        return {"commit": commit, "sketch_dirty": bool(changed)}
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return {"commit": None, "sketch_dirty": None}


def _command(argv: list[str], log: Path, timeout_s: int) -> dict:
    try:
        completed = subprocess.run(argv, capture_output=True, text=True,
                                   timeout=timeout_s, check=False)
        output = (completed.stdout or "") + "\n" + (completed.stderr or "")
        log.write_text(output[-200_000:], encoding="utf-8")
        return {"ok": completed.returncode == 0, "exit_code": completed.returncode,
                "log": str(log), "tail": output[-3000:]}
    except subprocess.TimeoutExpired as exc:
        output = f"Timed out after {timeout_s}s.\n{exc.stdout or ''}\n{exc.stderr or ''}"
        log.write_text(output[-200_000:], encoding="utf-8")
        return {"ok": False, "timed_out": True, "log": str(log), "tail": output[-3000:]}


def build_dut_firmware(*, flash: bool = False, harness: dict | None = None,
                       ports_provider=None, root: Path = REPO_ROOT,
                       runs_dir: Path = FLASH_RUNS) -> dict:
    """Compile a declared sketch; optionally upload only to the rechecked DUT.

    A successful upload is transport evidence. The running firmware and circuit
    remain unverified until a separate boot observation and physical check.
    """
    ports_provider = available_ports if ports_provider is None else ports_provider
    harness = describe_harness() if harness is None else harness
    plan = plan_dut_flash(harness, ports_provider(), root)
    sketch = (root.resolve() / plan["sketch_path"]).resolve()
    source_hash = _source_hash(sketch)
    if shutil.which("arduino-cli") is None:
        raise ValueError("arduino-cli is not installed")
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="dut-", dir=runs_dir))
    build_dir = run_dir / "build"
    build_dir.mkdir()
    result = {"source": "declared_sketch_and_usb_identity", "timestamp": datetime.now(timezone.utc).isoformat(),
              "run_dir": str(run_dir), "device": plan["device"], "usb_serial_number": plan["usb_serial_number"],
              "sketch_path": plan["sketch_path"], "fqbn": plan["fqbn"], "source_sha256": source_hash,
              "git": _git_state(root, plan["sketch_path"]),
              "compile": None, "upload": None, "artifact_sha256": {},
              "flashed_firmware_verified": False, "physical_circuit_verified": False}
    compile_argv = ["arduino-cli", "compile", "--config-file", str(CONFIG), "--fqbn", plan["fqbn"],
                    "--build-path", str(build_dir), str(sketch)]
    result["compile"] = _command(compile_argv, run_dir / "compile.log", 300)
    if result["compile"]["ok"]:
        result["artifact_sha256"] = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(build_dir.glob("*.bin"))
        }
        if not result["artifact_sha256"]:
            result["compile"]["ok"] = False
            result["compile"]["tail"] += "\nNo compiled .bin artifact was produced."
    if flash and result["compile"]["ok"]:
        if _source_hash(sketch) != source_hash:
            raise ValueError("DUT source changed during compilation; upload refused")
        # Port names may change during compilation. Re-resolve immediately
        # before upload and reject loss or replacement of the enrolled board.
        fresh = plan_dut_flash(harness, ports_provider(), root)
        if (fresh["usb_serial_number"] != plan["usb_serial_number"]
                or fresh["vid"] != plan["vid"] or fresh["pid"] != plan["pid"]):
            raise ValueError("DUT USB identity changed before upload")
        result["device"] = fresh["device"]
        upload_argv = ["arduino-cli", "upload", "--config-file", str(CONFIG), "--fqbn", plan["fqbn"],
                       "--input-dir", str(build_dir), "--port", fresh["device"], "--verify", str(sketch)]
        result["upload"] = _command(upload_argv, run_dir / "upload.log", 180)
        result["upload"]["status"] = ("reported_success" if result["upload"]["ok"]
                                      else "uncertain_or_failed")
    (run_dir / "evidence.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
