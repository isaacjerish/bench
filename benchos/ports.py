"""Serial-port discovery without fixed /dev names."""

from serial.tools import list_ports


def available_ports() -> list[dict]:
    return [
        {
            "device": port.device,
            "description": port.description,
            "vid": port.vid,
            "pid": port.pid,
            "manufacturer": port.manufacturer,
        }
        for port in list_ports.comports()
    ]


def candidate_ports() -> list[str]:
    ports = available_ports()

    def is_usb(port: dict) -> bool:
        combined = " ".join(
            str(port.get(key) or "") for key in ("device", "description", "manufacturer")
        ).lower()
        return port["vid"] is not None or any(
            token in combined for token in ("usb", "jtag", "wch", "cp210")
        )

    # Avoid opening unrelated Bluetooth and system console ports automatically.
    # Users with an unusual adapter can pass --port or BENCHOS_PORT explicitly.
    return sorted(port["device"] for port in ports if is_usb(port))
