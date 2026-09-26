# Benchy: toward an agent-operated lab

Status: proposed build plan, 2026-09-26. This document separates capabilities
already measured on hardware from work that still needs wiring and validation.

## Target behavior

Given a new breadboard design, its source code, and a small description of the
intended nets and behavior, the agent should be able to:

1. Identify the DUT board and its current firmware, then record a baseline.
2. Select a measurement that separates plausible fault causes.
3. Acquire voltage, timing, digital traffic, and power evidence from declared
   test points without claiming to have discovered wiring it cannot see.
4. Change local DUT firmware, compile it, flash the **identified DUT**, observe
   its restart, and repeat the same physical check.
5. Preserve the evidence chain: hypothesis, probe location, raw result,
   limits, firmware revision, action, and before/after result.

Three analog probes cannot scan an uninstrumented breadboard automatically.
The current expansion adds fixed digital taps at both ends of critical signal
wires and at the LED control node; see `PERMANENT_TAPS.md`. A later guarded
switch matrix could visit more declared nets unattended. A diagram or
photo may help propose hypotheses, but electrical readings remain the proof.

## Current baseline and gaps

| Capability | Current evidence | Missing for a new design |
| --- | --- | --- |
| P1/P2 DC voltage, digital level, edge count, pulse width | Live 3.3 V/GND, LED, PWM, light, and MPU-supply readings in `VALIDATION.md` | More points, better input protection and calibration; current probes only accept known 0–3.3 V nodes and load the net |
| C6 serial output and source view | Live MPU serial lines; local file hashes and Git revision | Reliable mapping from source/build to flashed binary; protocol-independent capture and parsing |
| I²C observation | IO8/IO9 grounded and common-SCL checks passed; restored SDA/SCL counted 508/1,935 transitions in 2 s with C6 serial open | Timed capture and I²C address/ACK decode; better input protection |
| DUT flashing | Generic build/flash CLI and MCP physically exercised; upload locking and optional marker/telemetry/range postchecks now implemented with host tests | Live acceptance of automatic postchecks; binary identity remains unverified |
| Permanent digital taps | S3 v0.2 uploaded; both SDA/SCL endpoint pairs show activity; generic host/MCP/dashboard comparison implemented | D5 idle LOW recovered after reseating; validate LED alert response and open-link comparison |
| Physical checks | Named fixed demo profiles | User-defined expectations tied to net names, design version, and measured evidence |
| Active tests, current, 5 V, unknown nodes | None | Separate protected hardware; existing S3 inputs must not be repurposed as outputs |

## Build order

### 1. Agent-controlled DUT flashing and evidence records (software first)

The typed `build_and_flash_dut` MCP tool and CLI build/flash commands are
implemented and physically exercised. The design manifest declares the sketch
path, board FQBN, and unique USB identity. Current implementation:

- Reject paths outside the selected project and refuse the S3 instrument port.
- Rediscovers the DUT USB serial and VID/PID immediately before upload and
  refuses ambiguous or missing identities after port renumbering.
- Records source Git revision, sketch dirty state, source hash, build/upload
  logs, and artifact hashes in an isolated evidence directory.
- Reports compilation and upload separately; flashed firmware identity and
  whole-circuit function remain explicitly **unverified**.

Implemented: optional per-design serial marker and bounded telemetry/voltage
postchecks stored in the same evidence record, plus a serial lock for upload
and another USB identity check after lock acquisition. Next: exercise the
complete automatic sequence on hardware. Earlier manual after-upload checks
showed fresh IMU data, 3.217 V sensor supply, and SDA/SCL activity, recorded in
`VALIDATION.md`. Current C6 firmware is the combined `plant_sentinel`.

Acceptance: intentionally wrong DUT port is refused; a compile failure leaves
the current firmware running; a known-good C6 sketch flashes, reports its build
marker, and passes a before/after S3 physical check. No GUI button needs to
expose unrestricted shell execution.

### 2. Guided investigation of arbitrary nets (existing P1/P2)

Extend the manifest from two probe labels to a design-specific table of nets,
expected states/ranges, stimuli, firmware claims, and allowed probe locations.
The agent chooses one discriminating check at a time, asks the operator to place
P1/P2 on known safe nodes, records that placement, and performs a fresh reading.
The GUI shows the declared topology, each measurement's source, and unresolved
hypotheses. Checks must remain generic data, not hardcoded demo modes.

Acceptance: load a new LED-plus-button circuit description without editing
Python; diagnose at least an open signal wire, wrong output pin, and bad
firmware timing by physical readings and a repair flash. Deliberate faults are
opened wires or firmware changes, never a deliberate supply short.

### 3. Observe two digital bus lines without driving them

The user has a multimeter, **not** a USB logic analyzer, and wants Benchy to
avoid depending on the meter for routine diagnosis. The S3 P2 probe measured
3.227 V at the MPU supply before connecting IO8/IO9. The user then connected
IO8/IO9 through separate 10 kΩ series resistors to the known 3.3 V MPU bus.
Initial captures showed zero edges. Grounded-input and common-SCL checks
subsequently passed, and the restored leads counted SDA/SCL activity with
the DUT serial stream held open. An SCL-open test showed sensor-side clock
inactivity with VCC still present and a DUT communication error; restoring
the jumper restored activity and motion reports. This is **not** an I²C
decoder. Series resistors do not make an S3 input tolerant of 5 V or unknown
voltages. The five-tap capture now observes activity at both SDA/SCL endpoints; its noisy D5 branch and open-link comparison still need validation.

Next, investigate a bounded two-channel capture on the S3, using a peripheral
such as RMT rather than relying on host USB timing. Decode START/STOP,
address, ACK/NACK, and stuck-low conditions, retaining raw capture evidence.
Measure the maximum reliable bus rate and label captures that overflow or miss
edges. Its two-channel timing and buffer behavior require validation before
calling it a logic analyzer. If reliable capture is not achievable at the
target bus rate, a supported USB logic analyzer becomes an optional hardware
addition. [Espressif's RMT
documentation](https://docs.espressif.com/projects/esp-idf/en/v4.4.6/esp32s3/api-reference/peripherals/rmt.html)
describes pulse-duration receive; it does not establish our achievable I²C
decode rate.

Acceptance: with MPU power still measured by P2, Benchy independently
distinguishes normal transactions, an open SCL jumper, an open SDA jumper,
and a stuck-low line where safely reproducible. Diagnosis identifies the
observed line state and traffic; it does not infer a specific broken contact
without another measurement.

### 4. Expand electrical reach with a protected measurement module

Design a separate input board with defined impedance, protected 3.3 V/5 V
ranges, overvoltage indication, and calibration points. Keep direct S3 GPIOs
behind the front end. Add current/power sensing as another isolated, rated
module on a *known* supply path; do not put an unknown load through a bare
microcontroller pin. ESP32-S3 ADC readings need range-aware calibration;
Espressif documents both [ADC operating modes](https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/api-reference/peripherals/adc/index.html)
and [calibration](https://docs.espressif.com/projects/esp-idf/en/v5.0/esp32s3/api-reference/peripherals/adc_calibration.html).

Acceptance: compare each protected range against a reference meter at low,
mid, and high points; verify out-of-range reporting and that a 5 V node cannot
reach a raw S3 GPIO. Only then advertise 5 V support in software.

### 5. Controlled stimulus and unattended multi-net access

Add output hardware physically separate from measurement inputs. Start with
one current-limited, default-off button/reset emulator; later add selectable
stimulus and a guarded analog/digital switch matrix for prewired test points.
Each action names an allowed net, drive mode, duration, and recovery state.
Firmware resets, watchdogs, or USB disconnects return outputs to high
impedance. Use a real current-limited supply/switch if power cycling or load
testing is needed.

Acceptance: the agent can observe a baseline, stimulate a button input,
capture the resulting output/serial behavior, and return to its prior state.
Unmapped nets and output-on-output connections are refused.

## First session with the hardware

1. USB identities were confirmed by chip type: S3 `94:A9:90:DB:BA:64`, C6
   `A0:85:E3:DA:BD:80`. The current `/dev/cu` ports are in `HANDOFF.md`.
2. SDA/SCL endpoint activity is observed on S3 v0.2; D5 is now quiet after
   reseating. Await covered-photoresistor confirmation and measure the alert.
3. Keep P1/P2/P3 on their present nodes. Do not use the meter as an ongoing
   Benchy dependency; a reference meter is optional for calibrating future
   protected voltage ranges.
4. On the next necessary C6 firmware change, validate the automatic postflash
   marker, telemetry, and voltage-target observations end to end.

## Scope boundary

Benchy can become an effective autonomous debugging harness for circuits
whose test points are exposed and whose voltage/power domains are known. It
cannot safely attach raw S3 inputs to an unknown rail, measure every node
through two physical wires, or prove a flashed program from a source-file
hash alone. Each added hardware path must earn its claimed range and timing
with physical acceptance measurements.
