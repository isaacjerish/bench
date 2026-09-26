# Benchy handoff

## Where the code is

This repository is the complete Benchy project. The Python package remains
`benchos` for compatibility. Start with `README.md` for
wiring and setup, `AGENT_DEMO.md` for the judging demo, and `VALIDATION.md` for
real hardware results. The key directories are:

- `lab_controller/`: ESP32-S3 input-only measurement firmware; pins in `config.h`.
- `benchos/`: Python serial client, CLI, response parsing, and physical checks.
- `mcp_server/`: local Codex MCP tools backed by the S3.
- `dut_examples/servo_demo/`: ESP32-C6 servo PWM and three selectable faults.
- `dut_examples/led_demo/`: tested 2 Hz visible LED demo.
- `dut_examples/light_sensor_demo/`: photoresistor cross-check demo, available to reflash.
- `dut_examples/imu_demo/`: currently flashed MPU-family I²C motion demo.
- `harness/current.yaml`: user-declared live wiring map; update after any wire move.
- `benchos/dashboard.py` and `benchos/dashboard_ui/`: generic local design
  workspace with a declared-net overhead map, paired physical probes, target
  checks, serial monitor, investigation timeline, and code inspector. Start
  with `./scripts/python.sh -m benchos.dashboard`. The map is illustrative;
  it cannot discover the real breadboard layout.
- `physical_tests/`: YAML pass/fail checks.
- `scripts/`: board detection, flashing, and test commands.
- `tests/`: Python unit tests.

## Current physical state (2026-09-26, US Eastern)

- S3 lab controller: `/dev/cu.usbmodem1101` at the latest check, USB serial
  `94:A9:90:DB:BA:64` (chip identified as ESP32-S3).
- C6 DUT: `/dev/cu.usbmodem5` at the latest check, USB serial
  `A0:85:E3:DA:BD:80` (chip identified as ESP32-C6). Port names have changed
  before; the dashboard now selects by these declared stable identities.
- S3 GPIO1 measures divider midpoint M. Two 10 kΩ resistors connect test row T
  to M to GND. S3 GPIO2 directly observes T. S3 and C6 GND share a rail.
- A second input probe P2 is wired on separate rows U (tip) and N (midpoint):
  `U --10 kΩ-- N --10 kΩ-- shared GND`, S3 IO4 to N, S3 IO5 directly to U.
  U is currently attached to the sensor-side MPU VCC pin/row. Do not confuse
  S3 IO5 with C6 IO5, which carries MPU SDA. Both probes are 0–3.3 V only.
- C6 GPIO20 and the LED/resistor branch have been removed from T. A
  photoresistor connects C6 3V3 to T; a separate 10 kΩ resistor connects T to
  shared GND; C6 GPIO1 also measures T. The S3 P1 divider remains in place.
- C6 currently runs `imu_demo` with `DEMO_FAULT=0`, SDA on IO5 and SCL on IO7.
  The user swapped in a second MPU breakout on the same reported wiring.
  The photoresistor circuit remains wired, but `light-compare` needs
  `light_sensor_demo` reflashed before it can pass again.
- Both USB boards were present on 2026-09-26. Before the C6 was switched to
  `imu_demo`, the live `light-compare` check
  passed: S3 P1 measured 2.177 V, C6 reported 2.249 V, a 0.072 V difference
  against the configured 0.45 V tolerance. The dashboard server was listening
  on `127.0.0.1:8765` at that time; check whether it is still running before
  opening the URL. These are point-in-time observations;
  re-run the command below after changing wiring or restarting the computer.
- SG90 is **not connected**. It needs a separate regulated 5 V supply rated for
  at least 2 A with accessible +5 V and GND. The Elegoo breadboard module has
  a newly located barrel wall plug. Its front is marked `Vin: 6.5V-9V` with
  selectable 3.3 V/5 V rails; the plug's output rating, module model, and
  module output-current rating still need inspection. If the module is MB-V2,
  its 700 mA output rating is below the SG90 maker's possible 2 A draw. Do not
  use an ESP32 GPIO,
  3.3 V pin, or board 5 V header to power the servo.

## What has been validated

- S3 firmware compiles, flashes, and responds to CLI `PING`.
- Real P1 readings: about 3.26 V on S3 3V3 and 0.000 V on GND.
- MCP stdio tools returned real voltage and PWM measurements. MCP registration
  exists on the original Mac; a new Codex task or new computer must register
  the server again using the README instructions.
- Normal C6 servo firmware produced about 50 Hz and 1500 µs high pulses,
  passing the physical servo signal check without connecting the servo motor.
- All three deliberate faults were physically detected: wrong pin 0 Hz,
  stuck-low 0 Hz/0 V/LOW, wrong frequency 312 Hz. Repaired PWM passed.
- LED firmware was restored after fault testing and remeasured at 2.0 Hz PASS.
- Photoresistor cross-check: normal 2.274 V reported / 2.192 V physical PASS;
  false-zero 0.000 V reported / 2.207 V physical FAIL; repaired 2.261 V
  reported / 2.207 V physical PASS. With the sensor covered, C6 reported
  0.595 V while S3 measured 0.557 V, proving a real light response.
- Python tests: run `./scripts/python.sh -m pytest -q` for the current count.
- Local dashboard live light comparison passed with C6 2.255 V vs S3 2.191 V.
  It remains available at `http://127.0.0.1:8765` while the local server runs;
  reopen with the command in README if needed. The preview switch is sample
  data, not a hardware result.
- The S3 CLI worked while the dashboard was running using a shared serial lock.
  MCP now has named `check_circuit` profiles and `read_imu_stream` (DUT claim
  only until the I²C bus is physically probed).
- S3 firmware now reports two probes. P2 read 3.265 V/HIGH on S3 3V3 and
  0.002 V/LOW on GND; the independent `imu_vcc` profile then passed at
  3.231 V/HIGH on the MPU VCC connection. P1 remained near 2.16 V on the light
  node during the P2 tests. `pair-voltage` / `measure_voltage_pair` read the
  channels in order with timestamps; they are not simultaneous samples.
- `harness/current.yaml` records user-declared connections, and the CLI/MCP
  `harness` / `describe_harness` tools expose them. The `imu_vcc` profile
  requires P2 to be declared connected to `MPU_VCC` before running. A declaration is not a
  physical measurement. The named IMU check combines S3 P2 supply evidence
  with the C6 motion stream without calling the bus independently verified.
- Deliberately opening only the C6 IO7 → MPU SCL wire left P2's `imu_vcc`
  check passing at 3.228 V/HIGH while the C6 reported
  `IMU_ERROR no_device_at_0x68_or_0x69`. The combined diagnosis was
  **“Power present; IMU link failed”**; it did not claim which bus wire was
  wrong. After SCL was restored, P2 passed at 3.246 V/HIGH and the C6 again
  reported a plausible 1.096 g acceleration magnitude. The C6 firmware now
  retries discovery after a sensor read failure; retry behavior was compiled
  and flashed, while the observed recovery included a USB reconnect.
- The dashboard's `/api/serial` endpoint captured real C6 `IMU_RAW` and
  `IMU_ACCEL_G` lines in bounded windows without disturbing the live IMU
  snapshot. `/api/code` reports the local Git revision, modified files, hashes,
  and declared DUT firmware; it explicitly does not verify the flashed binary.
  The GUI can render in Preview without boards. Session notes are stored in the
  browser's local storage and can be exported as JSON.
- The current dashboard has no built-in demo circuit tabs. It reads P1 and P2
  as generic physical inputs, shows their user-declared net names on an
  illustrative overhead map, and evaluates optional 0–3.3 V target ranges.
  Its editor writes only P1/P2 connection declarations to `harness/current.yaml`.
  The source viewer uses that file's `source_files` list for the current DUT.
  This generic interface and paired-probe HTTP endpoint have host tests and
  a browser preview check; no new physical acceptance run was performed for
  this redesign. The earlier physical measurements above remain the evidence.
- The S3 now runs the bus-activity firmware; live `HELP` lists `MEASURE_BUS`,
  and P1/P2 continued reading normally after upload. The user attached IO8
  through a 10 kΩ series resistor to MPU SDA and IO9 through another 10 kΩ
  resistor to SCL. The harness records this **user-declared** wiring. Initial
  zero-edge samples were inconclusive. IO8 read LOW when grounded through its
  resistor; both IO8 and IO9 counted 241 transitions when temporarily sensing
  the same SCL row. Once IO8 was restored to SDA and the C6 serial stream was
  held open during capture, both lines showed activity (508/1,935 transitions
  over 2 s). Arduino CLI reported a serial-stream verification error after
  writing the image; the subsequent live command and probe checks prove that
  the new firmware booted, but do not prove binary readback verification.
- The dashboard now opens in Live mode, selects the S3 and C6 by USB serial
  identity, and shows P1/P2, read-only bus activity, sampled C6 serial output,
  and current local source. Live APIs returned P1 2.548 V, P2 3.220 V,
  SDA/SCL activity, and `IMU_RAW`/`IMU_ACCEL_G` lines on the current wiring.
  The bus panel labels zero edges inconclusive when the DUT is idle.
- The new generic `build-dut` and `flash-dut` CLI commands and MCP
  `build_and_flash_dut` tool use the declared sketch and stable C6 USB serial.
  A real build and flash of `imu_demo` completed with Arduino's verified hash
  report. After reboot the C6 produced fresh IMU data; S3 read MPU VCC at
  3.217 V and later measured SDA/SCL at 502/1,936 edges over 2 s. Evidence
  logs and binary hashes are under `work/flash-runs/` outside this repo.
  Running-build identity and whole-circuit function remain unverified.

## What Benchy can diagnose today

Benchy has **two physical test points, P1 and P2**, each with an approximate
0–3.3 V ADC measurement, an instantaneous HIGH/LOW read, a rising-edge frequency count,
and one high-pulse-width measurement. The agent can run named rail, ground,
LED, and servo-signal pass/fail checks and compare a C6 light-sensor claim
against S3's independent measurement. This is a working electrical-debugging
MVP for known nodes, not an automatic scan of a breadboard.

| Symptom / deliberate fault | What P1 can establish | What still needs checking |
| --- | --- | --- |
| C6 says the LED should blink, but P1 sees 0 edges | The selected physical node is not toggling | Probe the intended GPIO, wire, and shared ground to distinguish wrong pin from disconnection |
| Servo firmware claims 50 Hz, but P1 reads about 312 Hz | The physical PWM timing fails the servo profile | Correct the PWM configuration and remeasure; motor motion remains untested |
| PWM node is held near 0 V and `LOW` | The output is stuck low at that node | Check firmware duty/output enable and then the connection |
| C6 light reading says 0 V, but S3 sees about 2.2 V | The reported sensor value disagrees with the physical node | Inspect C6 ADC pin/configuration and report path |
| P1 reads about 3.26 V on a 3V3 rail or 0 V on GND | The probed rail/node passes its configured voltage check | This does not measure current, ripple, or behavior under servo load |

The wrong-pin, stuck-low, wrong-frequency, false-zero light reading, power-present
SCL-open link fault, and
repaired cases above were physically demonstrated; see `VALIDATION.md` for
recorded measurements. A zero-edge reading alone does not identify a unique
root cause. BenchOS cannot yet map unknown wiring, capture/decode I²C, inspect
multiple nodes simultaneously, measure current or 5 V directly, or confirm
SG90 shaft movement. `read_imu_stream` is a C6 report, not independent S3
confirmation of the I²C lines. The P1 ADC is approximate,
and neither probe must touch a node above 3.3 V. The 10 kΩ/10 kΩ divider
loads a probed net; do not attach it to SDA/SCL without checking the bus
pullups. It is not a high-impedance logic-analyzer front end.

## Current MPU wiring and validation

The MPU board photographed by the user is marked `MPU-9250/6500/9255`;
both tested modules returned I²C `WHO_AM_I=0x70`, consistent with MPU-6500.
The user wired SDA to **C6 IO5** because a wire is stuck in IO6; SCL is on
IO7. The photoresistor, test row T, and P1 divider remain untouched.
`config.h` matches this wiring. The first module returned a fixed Z raw value
of `7FFF` (+2.000 g) even at rest, after a software reset, and after USB power
cycling. Its accelerometer range register correctly read `0x00` (±2 g).

The user swapped in a **second module** without changing C6 pins or firmware.
At rest, it reported about X=0.000 g, Y=0.013 g, Z=1.086 g. Held on its edge,
it reported about X=-0.988 g, Y=0.017 g, Z=0.133 g, magnitude=0.997 g.
This is a plausible gravity-vector shift and no axis is saturated. The same
wiring working with the replacement strongly implicates the first module,
though swapping also reseated the physical contacts. The dashboard now shows
the second module as an **unverified DUT stream** rather than a physical S3
pass; P1 has not probed the I²C bus. The current wiring is:

| MPU pin | C6 / breadboard connection |
| --- | --- |
| VCC | C6 3V3 |
| GND | Shared GND rail |
| SDA/SDI | C6 GPIO5/IO5 |
| SCL/SCLK | C6 GPIO7/IO7 |
| ADO/SDO | Shared GND rail |
| NCS | C6 3V3 |

Leave EDA, ECL, INT, and FSYNC open. Do not feed this breakout 5 V or the 9 V
barrel input. GPIO5 is an
ESP32-C6 strapping pin, so if the C6 fails to boot with the MPU attached,
unplug USB, move SDA to another exposed free GPIO, update `config.h`, and
retry. Full procedure and failure cases are in `dut_examples/imu_demo/README.md`.
The first module can be kept as a known bad sensor for a failure-detection
demo. To restore the proven light demo, flash
`light_sensor_demo` on the C6 without changing the current photoresistor wiring.

For the SG90 motion demo, obtain a separately regulated 5 V supply with
accessible +5 V and GND and adequate servo current. The found Elegoo module
and 9 V barrel adapter have not been verified as suitable. Do not connect the
servo red wire yet. The previously tested PWM-only demo can be restored at
any time by clearing T of the light sensor branch and moving C6 GPIO20 to T.

## Fast commands on the original Mac

Run in the repository directory:

```sh
./scripts/detect_boards.sh
./scripts/python.sh -m benchos.cli harness
./scripts/python.sh -m benchos.cli --port /dev/cu.usbmodem1101 pair-voltage
./scripts/python.sh -m benchos.cli --port /dev/cu.usbmodem1101 test physical_tests/imu_vcc.yaml
./scripts/python.sh -m benchos.cli --port /dev/cu.usbmodem1101 bus-activity --duration-ms 1000
./scripts/python.sh -m benchos.cli flash-plan
./scripts/python.sh -m pytest -q
```

The C6 currently runs `imu_demo`; use the dashboard's generic serial monitor
or `read_imu_stream` MCP tool for its output. Reflash `light_sensor_demo`
before running `light-compare` again. To open the dashboard:

```sh
./scripts/python.sh -m benchos.dashboard --lab-port /dev/cu.usbmodem1101 --dut-port /dev/cu.usbmodem5
```

Open `http://127.0.0.1:8765/`. Detect ports again if they have changed. The
design map follows the harness declaration; the connection editor is only a
record of user-checked wiring. Change `dut`, `source_files`, and other design
metadata directly in `harness/current.yaml` when switching to a fresh design.

To switch the C6 to the servo signal demo, disconnect the photoresistor and
its additional 10 kΩ pull-down from T, remove C6 GPIO1 from T, then connect
C6 GPIO20 to T. Confirm the SG90 supply and wiring before attaching the motor:

```sh
./scripts/flash_dut.sh servo_demo /dev/cu.usbmodem5
./scripts/physical_check.sh servo_signal /dev/cu.usbmodem1101
```

`dut_examples/servo_demo/config.h` has `DEMO_FAULT=0` and `DEMO_SWEEP=false`.
Once servo power is safely connected and PWM passes, set `DEMO_SWEEP=true`,
reflash, and confirm physical motion. `AGENT_DEMO.md` explains the blind fault
challenge. The exact servo wiring and safety sequence are in `README.md`.

## Fresh computer setup

Create a venv, install the package, copy the portable Arduino config, and
install the ESP32 Arduino core:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[mcp,dev]'
cp scripts/arduino-cli.example.yaml scripts/arduino-cli.yaml
arduino-cli core update-index --config-file scripts/arduino-cli.yaml
arduino-cli core install esp32:esp32 --config-file scripts/arduino-cli.yaml
```

Set `BENCHOS_PORT` to the S3 port and `PYTHONPATH` to this repository when
registering the MCP server. `README.md` has the complete `codex mcp add`
command. The original Mac's venv and Arduino core live outside this repository
and are not included in Git.

## Remaining work

1. When hardware work resumes, inspect the IO8/IO9 series-resistor contacts
   and confirm they land on the actual SDA/SCL rows. The S3 currently counts
   zero edges despite healthy C6 MPU output, so transition capture remains
   unvalidated. The P1/P2 10 kΩ/10 kΩ probes load the bus and must not be
   assumed suitable for SDA/SCL.
2. For a new design, update the harness's DUT metadata and source-file list,
   verify each probe connection by hand, and add bounded physical test
   expectations. The GUI does not infer connectivity or flashed code.
3. If testing SG90 motion, identify a separate regulated 5 V supply with
   adequate current first. Then wire its ground to the shared rail, SG90 yellow
   to C6 GPIO20/T, brown to ground, and red to that supply's +5 V.
4. Flash normal servo firmware, run the physical signal check, enable sweep,
   and verify actual SG90 movement. Record the result in `VALIDATION.md`.
