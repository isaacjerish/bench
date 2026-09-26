import pytest

from benchos.protocol import BenchDeviceError, BenchProtocolError, parse_response, validate_probe


def test_measurement_lines_are_structured():
    assert parse_response("OK INFO BenchOS-S3 v0.1 PROBES 2 ADC_SAMPLES 32") == {
        "kind": "info", "device": "BenchOS-S3", "version": "v0.1",
        "probe_count": 2, "adc_samples": 32,
        "text": "BenchOS-S3 v0.1 PROBES 2 ADC_SAMPLES 32"
    }
    assert parse_response("OK VOLTAGE P1 3.271 RAW 2030 SAMPLES 32") == {
        "kind": "voltage", "probe": "P1", "voltage_v": 3.271, "raw": 2030, "samples": 32
    }
    assert parse_response("OK FREQUENCY P1 50.00 EDGES 50 WINDOW_MS 1000 PULSE_US 1500") == {
        "kind": "frequency", "probe": "P1", "frequency_hz": 50.0,
        "edges": 50, "window_ms": 1000, "pulse_us": 1500
    }


@pytest.mark.parametrize("line", [
    "OK VOLTAGE P1 nan RAW 100 SAMPLES 32",
    "OK VOLTAGE P1 1.2 RAW -1 SAMPLES 32",
    "OK DIGITAL P1 MAYBE",
    "OK FREQUENCY P1 50 EDGES xx WINDOW_MS 250 PULSE_US 1500",
])
def test_malformed_measurement_is_rejected(line):
    with pytest.raises(BenchProtocolError):
        parse_response(line)


def test_device_error_and_command_validation():
    with pytest.raises(BenchDeviceError, match="UNKNOWN_PROBE"):
        parse_response("ERR UNKNOWN_PROBE")
    with pytest.raises(ValueError):
        validate_probe("P1\nREAD_ADC P2")
