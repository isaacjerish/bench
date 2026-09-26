# Benchy

The Python package and firmware still use `benchos` identifiers for
compatibility. See [the instrument roadmap](BENCHY_ROADMAP.md) and
[the agent-operated lab plan](AUTONOMY_PLAN.md) for the next hardware and
software capabilities.

Benchy lets Codex inspect **real voltages and signal timing** while it debugs
firmware. The ESP32-S3 is a small, input-only lab instrument; the ESP32-C6 is a
separate device under test (DUT). No cloud, API key, frontend, or separate LLM
runner is required.

```text
Codex --local MCP--> Python Benchy --USB serial--> ESP32-S3 --P1/P2--> circuit
Codex --Arduino CLI/USB---------------------------> ESP32-C6 --> servo signal
```

## The first physical hookup: S3 only

The default P1 probe uses **two S3 inputs** to observe one test point. Check
your exact S3 dev board pin labels before wiring: GPIO1 (or IO1) must be
exposed and ADC-capable, and GPIO2 (IO2) must be free. Edit
[`lab_controller/config.h`](lab_controller/config.h) if either pin differs.

With the S3 unplugged, place two **10 kΩ resistors** on a breadboard:

```text
                       +---- S3 GPIO2 (digital input)
                       |
P1 TIP / test row T ---+---[10 kΩ]--- row M ---[10 kΩ]--- GND rail
                                      |
                                      +---- S3 GPIO1 (ADC input)

S3 GND ------------------------------- GND rail
S3 USB ------------------------------- MacBook (data cable)
```

The measured voltage is the voltage at **T**, reconstructed from the half
voltage at M. The direct GPIO2 branch lets the same named probe read digital
states and count edges. Both pins are configured as `INPUT`, with no pullups.
**Only connect known 0–3.3 V signals to T.** The divider does not protect
GPIO2 from overvoltage. Never connect 5 V, a negative voltage, or an unknown
voltage to T. A voltage above 3.3 V requires a redesigned divider **and**
protection or disconnection of the digital branch. The two 10 kΩ resistors
are for the ADC divider; do not substitute a single resistor.

For the first reading, connect S3 **3V3** to T after checking there is no
ground jumper on T. Expect approximately 3.3 V from `voltage P1`. Remove
the 3V3-to-T jumper, then connect **GND to T**; expect approximately 0 V.
Never connect 3V3 and GND to T at the same time. T is the single movable
probe point for later DUT tests.

## Second input probe, P2

The current S3 firmware also defines P2 on S3 IO4 (ADC) and IO5 (digital).
On a separate pair of empty breadboard rows U and N, wire two additional
10 kΩ resistors as `U --10k-- N --10k-- shared GND`. Connect S3 IO4 to N and
S3 IO5 to U. Do not join U to P1's row T or midpoint M. This is another
**input-only, known 0–3.3 V** probe; S3 IO5 is directly connected to U and
has no protection for 5 V or unknown voltages. The C6's IO5 is separately
used for MPU SDA and must not be moved when adding P2.

Run `./scripts/python.sh -m benchos.cli harness` to see the **declared**
wiring. It is not automatic breadboard discovery. After physical validation,
`voltage P2`, `digital P2`, and `pair-voltage` can inspect both test points.
The pair command reads P1 then P2 in order and reports timestamps; it does
not sample them simultaneously.

## Install software

Run from this repository directory. Create a local virtual environment with:

```sh
python3 -m venv .venv
./scripts/python.sh -m pip install -e '.[mcp,dev]'
```

Install [Arduino CLI](https://arduino.github.io/arduino-cli/latest/installation/)
and Espressif's Arduino core 3.x if absent. On the original Mac, an isolated
Arduino CLI config exists at `scripts/arduino-cli.yaml`; its absolute paths are
machine-specific and intentionally excluded from Git. On a fresh clone, copy
`scripts/arduino-cli.example.yaml` to `scripts/arduino-cli.yaml` first. From
this repository directory:

```sh
arduino-cli core update-index --config-file scripts/arduino-cli.yaml
arduino-cli core install esp32:esp32 --config-file scripts/arduino-cli.yaml
arduino-cli board list --config-file scripts/arduino-cli.yaml
```

## Flash and test the S3

`arduino-cli board list` should show the Espressif USB serial port. Identify
which board is connected before flashing. The generic S3 board FQBN is
`esp32:esp32:esp32s3:CDCOnBoot=cdc`. The `CDCOnBoot=cdc` option is required
for `Serial` to answer over this board's native USB port. Use your specific
FQBN if known, with USB serial enabled.

```sh
arduino-cli compile --config-file scripts/arduino-cli.yaml --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc lab_controller
arduino-cli upload --config-file scripts/arduino-cli.yaml --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc -p /dev/cu.usbmodemXXXX lab_controller
```

After flashing, from this repository directory:

```sh
./scripts/python.sh -m benchos.cli list
./scripts/python.sh -m benchos.cli ping
./scripts/python.sh -m benchos.cli info
./scripts/python.sh -m benchos.cli voltage P1
./scripts/python.sh -m benchos.cli digital P1
./scripts/python.sh -m benchos.cli frequency P1 --duration-ms 1000
./scripts/python.sh -m benchos.cli test physical_tests/rail_3v3.yaml
```

Use `--port /dev/cu.usbmodemXXXX` **before** the subcommand to select a
specific port, or set `BENCHOS_PORT`. `--verbose` logs serial commands and
replies. `--log measurements.jsonl` records timestamped physical readings and
pass/fail checks. The port name is discovered at runtime; do not copy a stale
one from an example.

## Connect Benchy to Codex

The server is a local stdio process using the current Python MCP SDK. It is
already registered on this Mac. To recreate the registration, use absolute
paths to the runtime and source directory:

```sh
codex mcp add benchos --env PYTHONPATH="$(pwd)" -- "$(pwd)/.venv/bin/python" -m mcp_server.server
codex mcp list
```

`PYTHONPATH` lets the server find this code from any working directory. Set
`BENCHOS_PORT` with another `--env` flag
if several USB serial devices are connected. `BENCHOS_LOG` sets a JSONL file
for MCP measurements. Restart the Codex task after registration so the tools appear.
Ask: **“Use Benchy to measure the voltage on P1.”**
The MCP server also exposes `check_circuit` for the named physical test
profiles and `read_imu_stream` for the C6 motion report. IMU serial values are
labeled as DUT claims until the S3 independently observes the bus.

## Local dashboard

The monochrome dashboard is a generic workspace for the **current declared
design**. Its overhead breadboard map is illustrative: P1/P2 net labels come
from `harness/current.yaml`, not a camera or automatic wiring discovery. The
page reads both S3 probes in order, displays their physical voltages and
digital levels, and checks optional declared 0–3.3 V target ranges. The
connection editor saves probe net names, states, and target ranges to the local
harness file; saving a declaration does not verify or move a wire. The
**Preview** switch uses clearly marked sample readings without hardware;
preview values are never reported as live measurements.

The investigation panel shows evidence, uncertainty, a suggested next check,
and a local timeline export. The read-only DUT serial monitor samples bounded
windows with filtering, pause, clear, and export controls. There may be gaps
while another tool uses the port. The code inspector shows the S3 source,
harness, and source files listed under `source_files` in the current harness,
along with hashes, the Git revision, and local modifications. The declared DUT
firmware is a label; source on disk does not prove which binary was flashed.
Subtle motion is disabled when the browser requests reduced motion. The server
listens on the Mac's loopback interface only and exposes no firmware-flashing
endpoint.

From this repository, start it with the current serial ports (detect them again
if either board was unplugged):

```sh
./scripts/python.sh -m benchos.dashboard --lab-port /dev/cu.usbmodem1201 --dut-port /dev/cu.usbmodem1101
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). You can also select the
ports in the page. The dashboard releases the S3 serial port after each
sample; BenchOS uses a short cross-process lock to share its serial ports with
the Codex MCP server and CLI. The dashboard has no demo-specific circuit tabs.
Named demo checks remain available through the CLI and MCP tools. Edit
`harness/current.yaml` after changing the design's DUT metadata or source
files; use the page's connection editor for P1/P2 declarations.

The visual direction draws on the [shadcn/ui dashboard examples](https://ui.shadcn.com/examples/dashboard),
[Anthropic's frontend-design skill](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md),
and [Vercel's interface guidelines](https://github.com/vercel-labs/web-interface-guidelines).
The dashboard uses its own small HTML/CSS/JS interface, with no React or
template runtime dependency. Its reduced-motion setting follows the
[MDN guidance](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion).

## C6 servo demo

This example validates a **servo-style control signal**. A two-wire DC motor
cannot be connected to that signal or powered by an ESP32 GPIO. A DC motor
requires a suitable H-bridge driver and power supply, with wiring matched to
the exact driver model and motor rating.

If no separate servo supply is available, use the
[`LED fallback demo`](dut_examples/led_demo/README.md) instead. It runs from
the C6's USB power, uses one LED plus a 220–330 Ω series resistor, and has a
2 Hz physical check in `physical_tests/led_blink.yaml`.

Once the S3 rail/ground test passes, connect the C6 with a *second data USB
cable* and identify its new serial port. Confirm the GPIO20 label on your C6
board before wiring or change `dut_examples/servo_demo/config.h`. **Remove the
direct T-to-GND or T-to-3V3 test jumper before attaching C6 GPIO20.** Leave
the M-to-GND resistor and the shared ground rail in place.

```text
C6 GPIO20 --------- servo SIGNAL wire ---------- P1 tip T
C6 GND ------------ common GND rail ------------- S3 GND
external 5 V + ---- servo POWER wire only
external 5 V GND -- common GND rail
```

For a yellow/red/brown SG90, **yellow is signal**, **red is the separate
5 V power lead**, and **brown is ground**. The yellow lead joins C6 GPIO20
and P1 tip T; brown joins the shared GND rail. Connect red only after the
external supply's 5 V output and input power have been positively identified.

Power the servo only from a suitable separate 5 V supply, never from an ESP32
GPIO or ESP32 3.3 V rail. Do not connect the S3 and C6 outputs together; the
S3 pins are inputs. Connect only a 3.3 V servo control line to P1 tip.

For the SG90 movement test, obtain a **regulated 5 V source rated for at least
2 A** with accessible +5 V and GND connections (for example, a USB power bank
with a USB power breakout). Keep the servo unplugged until those two terminals
are positively identified. The Elegoo breadboard power module cannot be used
without an appropriate input source, and its output current capability has
not been verified for this particular module. If it is labeled **MB-V2**, its
[datasheet](https://pgccphy.net/1020/datasheets/ELEGOO%20Breadboard%20Power%20Supply%20Module.pdf)
limits output to 700 mA, below the SG90 maker's stated possible 2 A draw; do
not use that module for SG90 power. A 5 V header on an ESP32 dev
board is part of its board power path; do not treat it as the separate servo
supply. With power disconnected, remove whichever DUT branch is presently on T
(currently the photoresistor, its extra 10 kΩ pull-down, and C6 GPIO1). Keep
the S3's two-resistor divider. Then connect C6 GPIO20 and SG90 yellow to T,
brown to the common GND rail, and red
to the separate +5 V terminal. Connect the supply GND to the common rail.
After wiring has been checked, flash `servo_demo`, power the supply, and run
`./scripts/physical_check.sh servo_signal <S3-port>` before enabling
`DEMO_SWEEP` for visible motion.
The [SG90 maker's specifications](https://towerpro.com.tw/product/sg90-7/)
state a 4.8–6 V operating range and up to about 2 A operating current; the
[ESP32-C6 board guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c6/esp32-c6-devkitc-1/user_guide.html)
describes its 5 V header as a board power connection.

```sh
arduino-cli compile --config-file scripts/arduino-cli.yaml --fqbn esp32:esp32:esp32c6:CDCOnBoot=cdc dut_examples/servo_demo
arduino-cli upload --config-file scripts/arduino-cli.yaml --fqbn esp32:esp32:esp32c6:CDCOnBoot=cdc -p /dev/cu.usbmodemYYYY dut_examples/servo_demo
```

From this repository directory run:

```sh
./scripts/python.sh -m benchos.cli --log measurements.jsonl test physical_tests/servo_signal.yaml
```

For repeated demos, the wrappers accept an explicit C6 or S3 port:

```sh
./scripts/flash_dut.sh servo_demo /dev/cu.usbmodemYYYY
./scripts/physical_check.sh servo_signal /dev/cu.usbmodemXXXX
```

The physical PASS requires 45–55 Hz, at least one transition, and a high pulse
of 900–2100 µs. See [`AGENT_DEMO.md`](AGENT_DEMO.md) for the three fault modes.

## Light sensor cross-check

The optional [photoresistor demo](dut_examples/light_sensor_demo/README.md)
uses a kit photoresistor and a spare 10 kΩ resistor, powered at 3.3 V from the
C6. The C6 reports its ADC reading over USB; the S3 independently measures the
same physical sensor node at P1. The CLI command `light-compare --dut-port
<C6-port>` and MCP tool `compare_light_sensor(dut_port)` compare the two
readings and can expose a firmware fault that falsely reports zero. Remove the
LED branch and C6 GPIO20-to-T wire before wiring the photoresistor as shown
in the demo README. A difference test needs enough light to bring the sensor
node above 0.3 V. This demo was physically validated: a false zero report
failed against a real 2.207 V reading, and the repaired firmware passed.

## MPU motion sensor

The optional [MPU family demo](dut_examples/imu_demo/README.md) uses the blue
`MPU-9250/6500/9255` board from the kit. It identifies the chip over I²C and
reports live three-axis acceleration. Use only C6 3.3 V for its VCC; see its
README for the exact wiring. The IMU can be added while the light sensor
circuit remains in place.

## Limits and common failures

- The ESP32 ADC is approximate, and resistor tolerance adds error. It is a
  debugging instrument, not a calibrated multimeter. Arduino's
  `analogReadMilliVolts()` applies chip calibration where available, but
  readings should be checked against a known reference.
- S3 GPIO1/2 can differ on a particular board; inspect pin labels. Some boards
  repurpose pins for onboard peripherals.
- A 50 Hz servo signal may show `LOW` in one instantaneous `digital` read;
  use `frequency` and `pulse_us` to judge it.
- A floating probe can show random digital transitions. Tie T to GND or a
  known signal for tests.
- `No BenchOS controller responded` means the wrong port, a charge-only cable,
  firmware not flashed, or a board still rebooting. Run `list`, then `ping`.
- `0 Hz` with a live C6 serial log means a wrong pin, missing common ground,
  or no physical PWM. Inspect wiring and measure before changing code.
- If uploading fails, close any program holding the serial port. Some boards
  require holding BOOT while tapping RESET to enter download mode.

Arduino APIs used here: [ADC](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/adc.html)
and [LEDC](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html).
