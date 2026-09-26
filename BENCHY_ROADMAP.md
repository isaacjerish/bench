# Benchy: instrument roadmap

Benchy is the agent's physical bench. The Python package and firmware still
use `benchos` identifiers for compatibility; the product name is Benchy.

## Current baseline

An ESP32-S3 reads two known 0–3.3 V test points (P1/P2), each through an ADC divider and
a separate digital input. The host exposes voltage, level, edge frequency, and
pulse width through CLI and MCP. The ESP32-C6 can be flashed and read over USB.
Physical LED/PWM/light checks have passed. A replacement MPU-6500 reports a
plausible gravity vector while still and when tilted. Its I²C connection has
not been independently observed by the S3. See `VALIDATION.md` for evidence.

## Next build: two passive probes and named nets

1. Add P2 on ESP32-S3 IO4 (ADC1) and IO5 (digital). **Done:** P2 read 3.265 V
   and HIGH on 3V3, 0.002 V and LOW on ground, and 3.231 V and HIGH on the
   MPU VCC connection. Both probes remain restricted to known 0–3.3 V nodes
   and share ground.
2. Add one host command that takes a short, ordered snapshot of P1 and P2.
   **Done:** `pair-voltage` and `measure_voltage_pair` return readings,
   including timestamps and the configured physical node names. Explicitly
   mark a node name as **declared wiring**, never inferred wiring.
3. Add a per-build circuit manifest with declared board pins and net names.
   **Done for the current build:** `harness/current.yaml`, CLI `harness`, MCP
   `describe_harness`, and the dashboard's IMU wiring text use the same
   user-declared map. The pair-voltage result labels each reading with its
   declared net. The dashboard omits the P2 power check if P2 is not declared
   connected to `MPU_VCC`.
4. Demonstrate an MPU link fault with P1 still on the light node and P2 on
   the sensor-side VCC connection. **Done:** opening SCL left P2 at 3.228 V
   while C6 reported no I²C device; restoring SCL returned normal readings.
   This rules out lost sensor power in that run. It does not independently
   distinguish SCL from SDA faults.

Acceptance achieved so far: P2 passed 3V3 and GND checks, P1 retained its
photoresistor reading, and Benchy separated a measured-good sensor supply
from a failed I²C report without flashing first. The exact failed I²C line
was known because the user injected that fault; Benchy cannot discover that
line on its own yet. No GUI verdict calls a DUT-only reading a physical pass.

## Next instrument capabilities, in dependency order

| Capability | What it would let the agent do | Required engineering |
| --- | --- | --- |
| Protected input front end | Probe 5 V and accidental out-of-range nodes without exposing S3 pins | Proper input protection, level shifting/attenuation, labeled voltage ranges, calibration, and bench verification; the current direct digital branch is strictly 0–3.3 V |
| High-impedance bus inputs | Observe SDA/SCL without loading their pullups or making the S3 an I²C master | Dedicated buffered digital inputs or a known-safe high-impedance front end; the present 10 kΩ/10 kΩ divider draws current and is not suitable for every I²C bus |
| Timed digital capture | Capture edges on several nets and decode UART, I²C, SPI, and PWM transactions | MCU peripheral or dedicated logic-analyzer capture, timestamps, bounded buffers, decoders, and a measured bandwidth specification |
| Current and power sensing | Separate “firmware stopped” from “rail collapsed under load” | Rated shunt/monitor or bench supply; choose range and isolation for each power domain |
| Dedicated stimulus outputs | Pulse reset, emulate a button, generate PWM, or stimulate an input | Output pins/driver hardware physically separate from probes, series impedance, explicit target-net allowlist, and default high impedance |
| Controlled power | Power-cycle a DUT or vary a known supply while recording response | Suitable switch/supply, current limit, common-ground design, and interlocks; the current breadboard supply is not verified for this |
| Visual feedback | Verify LED state or servo motion beyond the control signal | Camera mount, image capture, calibration, and comparison to the electrical trace |

## Software behavior that makes this an engineering tool

- Every measurement carries source (S3 physical probe or DUT report), probe,
  declared net, units, range, timestamp, sample window, and confidence limits.
- A debug run records hypothesis, smallest discriminating measurement, result,
  firmware/wiring change, and before/after physical checks.
- Agent tools expose bounded typed operations rather than arbitrary raw serial
  commands. Time-critical sampling stays on the microcontroller.
- The UI shows the actual declared net connections and the evidence behind a
  verdict. If a wire is moved, the manifest is updated before the next run.
- Tests cover parsing and interlocks; physical acceptance checks establish
  capability. A compiled sketch or plausible serial report is not a physical
  test.

## What needs to be on the table next

P2 is built and on the MPU VCC connection. For the next electrical capability,
choose a protected, buffered input circuit and verify its loading before
touching SDA/SCL or any unknown node. The DHT11, water-level board, ultrasonic
module, and motor can provide later DUTs after the harness can observe their
relevant electrical nodes safely.
