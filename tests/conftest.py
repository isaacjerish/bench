"""Host tests use a private fixture circuit, never the user's active wiring map."""
from pathlib import Path

import pytest

from benchos import harness


@pytest.fixture(autouse=True)
def harness_file(tmp_path, monkeypatch):
    reference = Path(__file__).resolve().parents[1] / 'harness/profiles/plant_sentinel_legacy.yaml'
    path = tmp_path / 'harness.yaml'
    path.write_text(reference.read_text())
    # Imported aliases retain the same function object. Changing only its
    # default path covers those aliases while explicit profile paths still work.
    monkeypatch.setattr(harness.describe_harness, '__defaults__', (path,))
    monkeypatch.setattr(harness.update_probe_declarations, '__defaults__', (path,))
    return path
