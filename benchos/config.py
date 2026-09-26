"""Host settings. Override with CLI flags or environment variables."""

import os

BAUD = 115200
TIMEOUT_S = 3.0
STARTUP_S = 1.5


def configured_port() -> str | None:
    return os.environ.get("BENCHOS_PORT") or None


def configured_log() -> str | None:
    return os.environ.get("BENCHOS_LOG") or None
