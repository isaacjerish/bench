# Benchy: from two probes to an agent-operated lab

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

Two probes cannot scan an uninstrumented breadboard automatically. Initially,
the agent will guide a person to move a probe. Later, fixed leads or a guarded
switch matrix can let it visit several declared nets unattended. A diagram or
photo may help propose hypotheses, but electrical readings remain the proof.

## Current baseline and gaps

| Capability | Current evidence | Missing for a new design |
| --- | --- | --- |
| P1/P2 DC voltage, digital level, edge count, pulse width | Live 3.3 V/GND, LED, PWM, light, and MPU-supply readings in `VALIDATION.md` | More points, better input protection and calibration; current probes only accept known 0–3.3 V nodes and load the net |
| C6 serial output and source view | Live MPU serial lines; local file hashes and Git revision | Reliable mapping from source/build to flashed binary; protocol-independent capture and parsing |
| I²C observation | Staged S3 IO8/IO9 edge-count firmware compiles | Physical wiring/validation; edge count is not transaction decode |
| DUT flashing | `scripts/flash_dut.sh` compiles and uploads one of four demos | Agent tool for an arbitrary declared sketch, board/port identity, bounded logs, postflash identity and regression test |
| Physical checks | Named fixed demo profiles | User-defined expectations tied to net names, design version, and measured evidence |
| Active tests, current, 5 V, unknown nodes | None | Separate protected hardware; existing S3 inputs must not be repurposed as outputs |

## Build order

### 1. Agent-controlled DUT flashing and evidence records (software first)

Add a typed `build_and_flash_dut` tool and CLI command. The design manifest
declares the sketch path, board FQBN, unique USB identity when available,
expected boot marker, and physical checks. The tool will:

- Reject paths outside the selected project and refuse the S3 instrument port.
- Discover the DUT again immediately before upload and check board/chip identity
  when the transport supports it; refuse ambiguity after port renumbering.
- Record source Git revision and dirty-file hashes, compile to an isolated build
  directory, retain build/upload logs and artifact hashes, then upload.
- Observe the DUT after reboot and run the same bounded physical check used
  before flashing. Report compile, upload, boot, and electrical outcomes
  separately. A successful upload is not proof that the circuit works.
- If the DUT cannot identify its running build, label flashed identity
  **unverified** rather than equating it with source on disk.

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

The user has a multimeter, **not** a USB logic analyzer. Start with the staged
S3 IO8/IO9 read-only edge monitor after checking the exact pins, common
ground, and bus voltage with the meter. This can report idle levels and
approximate edge counts; it is **not** an I²C decoder and has not yet been
physically validated. Use the known 3.3 V MPU bus only. Series resistors do
not make an S3 input tolerant of 5 V or unknown voltages.

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

1. Confirm current S3/C6 USB identities and rerun P1/P2 rail checks; ports may
   have changed. Do not assume the breadboard matches a prior session.
2. S3 IO8/IO9, spare 10 kΩ resistors, and a multimeter are available. Confirm
   the exact S3 pin labels and the meter's DC voltage mode.
3. Check MPU VCC, SDA, and SCL against shared ground with the meter, then wire
   the two S3 read-only inputs only to confirmed 3.3 V bus lines. Keep P1/P2
   on their existing nodes until that plan is checked.
4. In parallel, implement phase 1 without wiring changes; it yields the
   largest immediate gain in agent autonomy.

## Scope boundary

Benchy can become an effective autonomous debugging harness for circuits
whose test points are exposed and whose voltage/power domains are known. It
cannot safely attach raw S3 inputs to an unknown rail, measure every node
through two physical wires, or prove a flashed program from a source-file
hash alone. Each added hardware path must earn its claimed range and timing
with physical acceptance measurements.
