from benchos.checks import FrequencyRangeCheck, VoltageRangeCheck


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
