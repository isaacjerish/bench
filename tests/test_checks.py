from benchos.checks import FrequencyRangeCheck, VoltageRangeCheck
from benchos import light
from benchos.light import parse_light_line


class FakeClient:
    def measure_voltage(self, _probe):
        return {"voltage_v": 0.0}

    def measure_frequency(self, _probe, _duration):
        return {"frequency_hz": 50.1, "edges": 50, "pulse_us": 300}


def test_physical_check_catches_wrong_servo_pulse_even_with_good_frequency():
    result = FrequencyRangeCheck("P1", 45, 55, pulse_min_us=900,
                                 pulse_max_us=2100).run(FakeClient())
    assert result["value"] == 50.1
    assert result["pass"] is False


def test_ground_check_passes_at_zero():
    assert VoltageRangeCheck("P1", 0, 0.15).run(FakeClient())["pass"]


def test_light_report_parser_ignores_boot_logs_and_reads_millivolts():
    assert parse_light_line("Light demo ready: GPIO1, fault=0") is None
    assert parse_light_line("LIGHT_MV 1234\n") == 1.234


def test_light_cross_check_detects_false_dut_report(monkeypatch):
    class Probe:
        port = "/dev/s3"

        def measure_voltage(self, _probe):
            return {"voltage_v": 1.4}

    monkeypatch.setattr(light, "read_light_report", lambda _port: 0.0)
    result = light.compare_light(Probe(), "/dev/c6")
    assert result["enough_signal"]
    assert result["difference_v"] == 1.4
    assert not result["pass"]
