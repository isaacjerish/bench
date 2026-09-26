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
    assert parse_response("OK BUS SDA HIGH HIGH EDGES 24 SCL HIGH HIGH EDGES 160 WINDOW_MS 1001") == {
        "kind": "bus_activity", "window_ms": 1001, "edge_counts_approximate": True,
        "sda": {"start": "HIGH", "end": "HIGH", "edges": 24},
        "scl": {"start": "HIGH", "end": "HIGH", "edges": 160}
    }


@pytest.mark.parametrize("line", [
    "OK VOLTAGE P1 nan RAW 100 SAMPLES 32",
    "OK VOLTAGE P1 1.2 RAW -1 SAMPLES 32",
    "OK DIGITAL P1 MAYBE",
    "OK FREQUENCY P1 50 EDGES xx WINDOW_MS 250 PULSE_US 1500",
    "OK BUS SDA HIGH HIGH EDGES xx SCL HIGH HIGH EDGES 160 WINDOW_MS 1000",
    "OK BUS SDA HIGH HIGH EDGES 24 SCL MAYBE HIGH EDGES 160 WINDOW_MS 1000",
    "OK TAPS WINDOW_MS 1000 D1 HIGH HIGH 4 D1 LOW LOW 2",
    "OK TAPS WINDOW_MS 1000 D1 MAYBE HIGH 4",
    "OK TAPS WINDOW_MS 1000 D1 HIGH HIGH -4",
    "OK TAPS WINDOW_MS 0 D1 HIGH HIGH 4",
    "OK TAPS WINDOW_MS 1000 D1 HIGH HIGH",
])
def test_malformed_measurement_is_rejected(line):
    with pytest.raises(BenchProtocolError):
        parse_response(line)


def test_device_error_and_command_validation():
    with pytest.raises(BenchDeviceError, match="UNKNOWN_PROBE"):
        parse_response("ERR UNKNOWN_PROBE")
    with pytest.raises(ValueError):
        validate_probe("P1\nREAD_ADC P2")


def test_taps_keep_each_endpoint_and_explicit_capture_limits():
    result = parse_response("OK TAPS WINDOW_MS 1001 D1 HIGH HIGH 32 D2 HIGH HIGH 190 D3 HIGH HIGH 30 D4 HIGH HIGH 0 D5 LOW HIGH 3")
    assert result["kind"] == "digital_taps"
    assert result["taps"]["D4"]["edges"] == 0
    assert result["taps"]["D5"] == {"start": "LOW", "end": "HIGH", "edges": 3}
    assert result["capture_windows_overlap"] is True
    assert result["decoded_transactions"] is False
