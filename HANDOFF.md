# BenchOS handoff

## Where the code is

This repository is the complete BenchOS project. Start with `README.md` for
wiring and setup, `AGENT_DEMO.md` for the judging demo, and `VALIDATION.md` for
real hardware results. The key directories are:

- `lab_controller/`: ESP32-S3 input-only measurement firmware; pins in `config.h`.
- `benchos/`: Python serial client, CLI, response parsing, and physical checks.
- `mcp_server/`: local Codex MCP tools backed by the S3.
- `dut_examples/servo_demo/`: ESP32-C6 servo PWM and three selectable faults.
- `dut_examples/led_demo/`: tested 2 Hz visible LED demo.
- `dut_examples/light_sensor_demo/`: photoresistor cross-check demo, currently flashed.
- `dut_examples/imu_demo/`: new MPU-family I²C motion demo; wiring pending.
- `benchos/dashboard.py` and `benchos/dashboard_ui/`: local dashboard and live
  measurement view; start with `./scripts/python.sh -m benchos.dashboard`.
- `physical_tests/`: YAML pass/fail checks.
- `scripts/`: board detection, flashing, and test commands.
- `tests/`: Python unit tests.

## Current physical state (2026-09-25, US Eastern)

- S3 lab controller: `/dev/cu.usbmodem1201` on the original Mac.
- C6 DUT: `/dev/cu.usbmodem1101` on the original Mac. These port names can change.
- S3 GPIO1 measures divider midpoint M. Two 10 kΩ resistors connect test row T
  to M to GND. S3 GPIO2 directly observes T. S3 and C6 GND share a rail.
- C6 GPIO20 and the LED/resistor branch have been removed from T. A
  photoresistor connects C6 3V3 to T; a separate 10 kΩ resistor connects T to
  shared GND; C6 GPIO1 also measures T. The S3 P1 divider remains in place.
- C6 currently runs `light_sensor_demo` with `DEMO_FAULT=0`.
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

## Fast commands on the original Mac

Run in the repository directory:

```sh
./scripts/detect_boards.sh
./scripts/python.sh -m benchos.cli --port /dev/cu.usbmodem1201 light-compare --dut-port /dev/cu.usbmodem1101
./scripts/python.sh -m pytest -q
```

To switch the C6 to the servo signal demo, disconnect the photoresistor and
its additional 10 kΩ pull-down from T, remove C6 GPIO1 from T, then connect
C6 GPIO20 to T. Confirm the SG90 supply and wiring before attaching the motor:

```sh
./scripts/flash_dut.sh servo_demo /dev/cu.usbmodem1101
./scripts/physical_check.sh servo_signal /dev/cu.usbmodem1201
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

0. Confirm C6 GPIO6/IO6 and GPIO7/IO7 are exposed; wire and validate the MPU
   as described in `dut_examples/imu_demo/README.md`.
1. Obtain and identify the separate 5 V servo supply.
2. Disconnect the photoresistor circuit, wire SG90 yellow to C6 GPIO20/T, brown to the
   shared GND rail, red to the separate +5 V, and supply GND to the shared rail.
3. Flash normal servo firmware, run the physical signal check, enable sweep,
   and verify actual SG90 movement. Record the result in `VALIDATION.md`.
