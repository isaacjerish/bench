# BenchOS validation log

Validation performed on the user's Mac with an ESP32-S3 lab controller and
an ESP32-C6 target. Hardware measurements are from the real S3 ADC/GPIO,
not mocked values.

| Check | Result |
|---|---|
| Python host/MCP tests | 12 passed |
| S3 Arduino compile and flash | Passed, USB CDC enabled |
| C6 Arduino compile and flash | Passed, GPIO20 output |
| S3 USB serial `PING` | `OK PONG` |
| P1 tip on S3 3V3, CLI | 3.261 V, 32 samples |
| P1 tip on S3 3V3, MCP stdio | structured `voltage_v: 3.256`, `ok: true` |
| Automated 3.3 V rail check | PASS, 3.258 V |
| P1 tip on GND | PASS, 0.000 V and `LOW` |
| C6 GPIO20 to P1 physical PWM | 50.00 Hz, 50 edges/1000 ms, 1500 µs pulse |
| Automated servo signal check | PASS |
| MCP `measure_frequency(P1, 1000)` | Structured 50.0 Hz / 1500 µs result, no error |
| Fault 3, wrong frequency | 312.0 Hz / 1499 µs, physical FAIL |
| Repaired C6 firmware | 49.95 Hz / 1500 µs, physical PASS |
| Fault 1, wrong software pin (GPIO21) | P1 measured 0 Hz, 0 edges, physical FAIL |
| Fault 2, stuck-low GPIO20 | P1 measured 0 Hz, 0 edges, 0.000 V and `LOW`, physical FAIL |
| C6 LED fallback on GPIO20 | 2.0 Hz, 4 edges/2000 ms, physical PASS |
| C6 LED fallback with LED and resistor attached | User confirmed visible blinking; P1 remeasured 2.0 Hz, 4 edges/2000 ms, physical PASS |
| LED firmware restored after fault checks | P1 measured 2.0 Hz, 4 edges/2000 ms, physical PASS |

The resistor divider is nominally 1:2. These values show a working physical
measurement loop, but the ADC and resistor tolerances do not make it a
calibrated voltmeter.

The user later found an SG90 hobby servo. Servo motion is pending confirmation
of the Elegoo module's exact input/output labels and power source. The
three-wire SG90 needs no external H-bridge; its red power lead must go to an
appropriate separate 5 V source, not an ESP32 rail.

The C6 currently runs the LED fallback sketch with a visibly blinking LED.
The servo sketch remains in `dut_examples/servo_demo` and can be reflashed
when a suitable servo power source is available.
