# BenchOS validation log

Validation performed on the user's Mac with an ESP32-S3 lab controller and
an ESP32-C6 target. Hardware measurements are from the real S3 ADC/GPIO,
not mocked values.

| Check | Result |
|---|---|
| Python host/MCP/dashboard tests | 21 passed with local socket access |
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
| Photoresistor normal C6/S3 agreement | C6 reported 2.274 V; S3 measured 2.192 V; difference 0.082 V, PASS |
| Photoresistor false-zero firmware fault | C6 reported 0.000 V; S3 measured 2.207 V; difference 2.207 V, FAIL as intended |
| Photoresistor repaired C6/S3 agreement | C6 reported 2.261 V; S3 measured 2.207 V; difference 0.054 V, PASS |
| Photoresistor covered response | User covered sensor; S3 voltage fell to 0.557 V, C6 reported 0.595 V; difference 0.038 V, PASS |
| Local dashboard live light view | C6 reported 2.255 V; S3 measured 2.191 V; UI showed physical PASS |
| CLI while dashboard runs | S3 measured 2.192 V; shared serial lock allowed both processes to use the port |
| Dashboard preview fault | Clearly marked sample values 0.000 V vs 2.207 V showed FAIL; no hardware read represented as live |
| Monochrome dashboard redesign | Four generated overhead breadboard scenes served locally; live light view showed S3 2.180 V vs C6 2.245 V, PASS |
| 2026-09-26 live light comparison before IMU flash | C6 reported 2.249 V, S3 measured 2.177 V, difference 0.072 V, PASS |
| First MPU on C6 SDA=IO5, SCL=IO7 | C6 booted and I²C `WHO_AM_I=0x70` (consistent with MPU-6500); X/Y values changed during user tilt |
| First MPU Z-axis raw check | Repeated `7FFF` / +2.000 g, including after sensor reset and full C6 USB power cycle; accelerometer config readback `0x00`; clipped-axis fault, **not** a healthy 3-axis stream |
| First MPU live dashboard diagnosis | `fail`, “Accelerometer axis clipped”, `saturated_axes: ["z"]`; source marked as C6 report, not S3 physical proof |
| Replacement MPU still | X near 0 g, Y about 0.013 g, Z about 1.086 g; no saturated axis, plausible static gravity reading |
| Replacement MPU held on edge by user | X about -0.988 g, Y about 0.017 g, Z about 0.133 g; magnitude about 0.997 g, plausible 90° gravity shift |
| Replacement MPU dashboard | DUT stream detected, `saturated_axes: []`, state `unverified` because S3 P1 has not probed the I²C lines |
| Host tests after clipped-axis dashboard check | 22 passed |
| S3 firmware P2 probe | S3 `INFO` reported `PROBES 2`; existing P1 still read about 2.16 V |
| P2 on known S3 3V3 | 3.265 V and HIGH; P1 simultaneously reported 2.170 V on separate light node |
| P2 on known GND | 0.002 V and LOW; P1 reported 2.155 V |
| P2 on MPU sensor-side VCC | `imu_vcc` physical profile PASS at 3.231 V and HIGH; C6 MPU stream remained healthy after USB reconnection |
| Live two-source IMU dashboard | S3 P2 measured 3.234 V; C6 reported magnitude 0.996 g; verdict explicitly says power verified and I²C bus unverified |
| Deliberate SCL open fault | P2 `imu_vcc` PASS at 3.228 V/HIGH while C6 reported `IMU_ERROR no_device_at_0x68_or_0x69`; Benchy diagnosed power present with IMU link failure |
| SCL restored | P2 `imu_vcc` PASS at 3.246 V/HIGH; C6 returned `WHO_AM_I=0x70` and 1.096 g magnitude |
| Current host suite after P2, harness, and IMU link diagnostics | 28 passed with local loopback access |
| Live dashboard after SCL restoration and software restart | P2 measured 3.225 V; C6 reported 1.087 g, no clipped axes; state `unverified` because bus traffic is not independently decoded |
| Dashboard serial monitor API with connected C6 | Captured eight real `IMU_RAW` and `IMU_ACCEL_G` lines in a 1200 ms bounded window; this is sampled output, not continuous capture |
| Dashboard after serial monitor added | P2 measured 3.225 V; C6 reported 1.088 g with no clipped axes; existing IMU verdict preserved |
| Host tests with serial and code APIs | 31 passed, including source-file allowlist and invalid-port rejection |
| Generic dashboard software checkpoint, 2026-09-26 | 34 host tests passed with loopback access; JavaScript syntax and Git whitespace checks passed |
| Generic dashboard browser preview | Illustrative overhead map loaded current P1/P2 net labels and target range from the harness; preview readings stayed labeled as sample data |
| Current-design source inventory | Listed S3 source, harness, and only the declared IMU DUT source files; unrelated demo sketches were excluded |
| USB role identification after port renumbering | Read-only esptool identified `/dev/cu.usbmodem1101` as ESP32-S3 (USB serial `94:A9:90:DB:BA:64`) and `/dev/cu.usbmodem5` as ESP32-C6 (`A0:85:E3:DA:BD:80`) |
| S3 bus-monitor firmware upload | Arduino CLI wrote the new application but returned a serial-stream error during `--verify`; after reset, live `HELP` listed `MEASURE_BUS` and P1/P2 still measured 2.538 V / 3.227 V. Runtime verified; binary readback was not verified. |
| New IO8/IO9 wiring, first read-only test | User connected each input through a separate 10 kΩ series resistor to MPU SDA/SCL. S3 reported both lines HIGH and 0 edges in 1 s and 2 s windows; physical transition capture remains **unvalidated**. |
| Concurrent C6 behavior | C6 reported `WHO_AM_I=0x70` and about 1.088 g while S3 bus inputs counted zero edges. This shows the DUT still communicates with its MPU, but does not identify why the sense inputs were static. |
| Live generic dashboard API and browser | Auto-selected boards by stable USB serial; API returned P1 2.548 V, P2 3.220 V, S3 bus HIGH/HIGH with zero edges, and real `IMU_RAW`/`IMU_ACCEL_G` lines. Browser showed those as live physical/serial evidence with bus result marked inconclusive. |
| Host tests after live bus dashboard | 38 passed with local loopback access |
| IO8 grounded-input isolation | With IO8 connected to GND through its 10 kΩ sense resistor, S3 read SDA LOW; IO9 simultaneously counted 242 SCL transitions in 1 s. The firmware input and IO9 clock path respond. |
| Both inputs temporarily on SCL | Concurrent C6 serial plus S3 bus capture counted 241 transitions on both IO8 and IO9 in 2 s. This confirmed IO8 edge counting. |
| Restored SDA/SCL, synchronized capture | Dashboard held the C6 serial stream open while S3 captured 508 SDA and 1,935 SCL transitions in 2 s. The sense branches now show physical activity, without decoding transactions. |
| Generic declared-sketch build | `build-dut` compiled `imu_demo` into an isolated evidence directory; source hash, Git revision, compile log, and binary hashes were recorded. No upload in this step. |
| Generic enrolled-DUT flash | `flash-dut` compiled, rediscovered C6 USB serial `A0:85:E3:DA:BD:80`, uploaded only to `/dev/cu.usbmodem5`, and Arduino reported verified flash hashes. C6 then produced fresh IMU data. |
| Independent postflash checks | S3 measured MPU VCC at 3.217 V, then counted 502 SDA and 1,936 SCL transitions in 2 s while the C6 serial stream was open. This proves power and bus activity at the declared nodes, not the exact running binary or full circuit behavior. |
| Host tests after flash and synchronized capture | 39 passed, 1 sandbox socket test skipped; JavaScript syntax and Git whitespace checks passed. |
| Second SCL-open fault and restoration | With MPU VCC 3.191 V, S3 counted SDA 36/SCL 0 edges in 2 s while C6 reported `IMU_ERROR no_device_at_0x68_or_0x69`. Restored SCL yielded SDA 492/SCL 1,929 edges and a fresh motion stream. |
| S3 third-probe firmware | P3 on S3 IO6 ADC/IO7 digital compiled, uploaded with Arduino verification, and appeared in S3 `INFO` as a third probe. |
| Water-sensor dry/wet response | P3 measured 0.000 V dry, then 0.897 V and 0.833 V in separate samples with only the sensor comb wet; this supports a 0.5 V provisional wet threshold. |
| Combined DUT firmware | `plant_sentinel` compiled and uploaded to enrolled C6 serial `A0:85:E3:DA:BD:80`; verified flash hashes on the successful second attempt. Fresh serial showed build ID `plant-sentinel-v1`, light about 2.52 V, water 0.016–0.033 V dry, IMU ID `0x70`, no active alert. The first upload attempt lost the serial connection before verification. |
| Combined dry baseline cross-check | S3 independently measured P1 2.464 V, P2 3.226 V and P3 0.003 V while C6 reported light ~2.52 V and water ~0.02 V. The dashboard reported agreement under harness-declared 0.45 V tolerances. LED output and wet C6 report remain to be checked. |
| Agent-facing generic telemetry check | Enrolled USB identities were rediscovered. S3 P1 2.443 V vs C6 2.489 V and S3 P3 0.000 V vs C6 0.019 V both passed declared 0.45 V tolerances. A stale-report unit check returns `unverified`; a false-zero wet claim is unit-tested as `fail`. |

The resistor divider is nominally 1:2. These values show a working physical
measurement loop, but the ADC and resistor tolerances do not make it a
calibrated voltmeter.

The user later found an SG90 hobby servo. Servo motion is pending confirmation
of the Elegoo module's exact input/output labels and power source. The
three-wire SG90 needs no external H-bridge; its red power lead must go to an
appropriate separate 5 V source, not an ESP32 rail.

The C6 currently runs `plant_sentinel` with `DEMO_FAULT=0`: light on IO1,
water on IO2, MPU SDA/SCL on IO5/IO7, and an LED/resistor on IO20. The generic
`check-telemetry` compares its light/water reports with P1/P3; the older
`light-compare` requires the separate `light_sensor_demo` sketch. The servo
sketch remains available when an appropriate separate power source is ready.

The replacement MPU is wired and responds over I²C with plausible still and
tilted values. The first module had a saturated Z axis. The stream is not
independently confirmed by the S3, but its VCC supply is now measured by P2.
The dashboard server is
available via `./scripts/python.sh -m benchos.dashboard` when started; do not
assume the previous process is still running. `read_imu_stream` returns the
C6's claim rather than physical proof from P1.

The generic dashboard now has live physical P1/P2 and bus-input samples.
The IO8/IO9 path passed grounded-input and common-SCL checks, then counted
transitions on the restored SDA/SCL branches. The read-only bus monitor does
not decode I²C traffic. Its capture should keep the DUT serial stream open
for sketches that pause their I/O loop without a serial reader.

## Permanent-tap software checkpoint (2026-09-26)

- S3 v0.2 compiled for `esp32:esp32:esp32s3:CDCOnBoot=cdc`: 315,258 bytes
  program, 23,336 bytes globals. The new IO8–IO12 capture is **not yet
  uploaded or physically validated**. D3–D5 wiring confirmation is pending.
- Host tests: 64 passed with local loopback access;
  JS syntax and whitespace checks passed. Coverage includes malformed tap
  responses, unconfirmed inputs, endpoint activity mismatch, missing telemetry
  fields, upload locking, exact serial markers, and missing postflash evidence.
- Dashboard inspected with both boards absent: no invented measurements,
  new taps marked pending, and current local source visible. API is restarted
  with `/api/taps`; live data requires the new S3 firmware and connected boards.
- These checks establish software behavior and compilation only. The next
  physical acceptance is the sequence in `PERMANENT_TAPS.md`.
