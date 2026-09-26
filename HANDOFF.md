# Benchy handoff

## Latest: dashboard readiness pass (2026-09-26)

- Completed conditional output checks in `benchos/activity.py`, enabled through
  generic `activity_checks` declarations. For the current circuit, `alert=1`
  requires 3–5 transitions/s at D3; `alert=0` requires zero. A silent requested
  alarm and excessive activity fail. Missing serial reports, changed states,
  delayed captures, or unconfirmed taps remain unverified.
- Digital samples collect complete serial lines before and after a 2 s
  counter window. Rules and evidence are included in the response/capture.
  Reports are still DUT claims; output checks do not prove LED light emission.
- Dashboard shows these bounded verdicts and requires them before giving a
  passing assessment. Analog comparisons use the closest nearby report and
  report changing inputs as inconclusive rather than a misleading mismatch.
- Automatic browser sampling now sequences serial/probe/tap requests to reduce
  contention. Port changes clear old DUT context; in-flight tap results from
  a different selected DUT are discarded. Tap condition reports appear in
  the serial monitor without waiting for another poll.
- Identical saved files share one menu entry while all files/IDs remain
  readable. Selection aliases preserve existing saved references. The current
  library now shows 9 unique captures instead of 12 duplicate entries.
- Signal navigation targets the permanent taps when no I²C bus is declared.
  Preview/offline labels and save availability update correctly.
- Verification before remote integration: **103 Python tests + 9 Node UI tests passed**, including local
  HTTP routes, malformed/stale/changed conditions, serial-fragment assembly,
  missing required output checks, and record deduplication. Browser checked
  source config, saved comparisons, serial filtering in labeled Preview, and
  correct Offline state; restored real-data mode afterward.
- Both ESP32s disappeared from USB discovery before this website pass. The
  new conditional capture path is host-tested, **not yet revalidated live**.
  Healthy physical light/water/LED evidence below remains historical. Firmware
  was not changed during this pass. Dashboard restarted on localhost:8765.
- Integrated remote commit `2ca270b` (Grok voice debugging), preserving its
  microphone controls, endpoints, worklet, docs, and tests alongside the
  dashboard fixes. Corrected the voice wrapper to use the installed MCP SDK's
  `structured_content` and `is_error` attributes. Voice transport itself has
  not been exercised; it requires a configured xAI key and user-started audio.
- Final merged regression gate: **110 Python tests and 9 Node UI tests pass**;
  JavaScript syntax checks pass. The merged browser shows Offline correctly,
  displays the dry/wet comparison, reads the current source, and has no browser
  console errors. Voice is disabled with an explicit missing-key message on
  this dashboard process. Last dashboard exec session: 31571; verify before
  any later restart. No USB boards were detected at this final check.

## Active: ParcelGuard wiring checks pass (2026-09-26)

User requested a concise document for friends introducing wiring faults on
camera. `DEMO_BREAK_GUIDE.md` covers swapping the C6 IO1/IO2 sensor leads,
opening the LED ground, and disconnecting only photoresistor 3V3, with exact
restoration instructions. These fault procedures are **not yet rehearsed**;
only the healthy circuit has been physically validated. The guide explicitly
states that an LED-path break can leave electrical checks passing and requires
the user's visual observation. Do not promise automatic exact-wire localization.

User requested “check wiring” after the clean batch. Both enrolled USB boards
were discovered and uploaded with verification. S3 now responds as v0.3,
`series-taps-v1`; C6 emits `build=parcel-guard-v1`, fault 0. Port names swapped:
S3 was `/dev/cu.usbmodem5`, C6 `/dev/cu.usbmodem1101`; always rediscover by serial.
Current connections are declared connected, not automatically traced/proven.

- Initial S3 light reading **2.700 V**, C6 report **2.725 V** (25 mV difference).
- Water S3 **0.000 V**, C6 **0.002 V**. A zero baseline does not verify the
  water sensor's power or response; the wet test is still required.
- LED drive: **8 CHANGE edges / 2000 ms** and a separate **2.000 Hz** frequency
  check (4 rising edges / 2 s), passing the 1.5–2.5 Hz suite. High ADC snapshot
  was 3.159 V / raw 4095, at the ADC limit; do not interpret as an exact rail.
- User confirms the LED blinks with light and stops covered (they corrected
  their initial “keeps blinking” report). Covered/dry capture: S3 light
  **0.686 V**, water **0 V**, LED drive **0 V**, zero alarm edges in 1 s;
  DUT reports light roughly 0.700–0.792 V, `lid_open=0 wet=0 alert=0`.
- First wet attempt was captured during movement: light **2.186 V**, water
  **0.003 V**, then DUT water rose from 0.023 V to 0.834 V across later
  messages. Do not treat those sequential observations as simultaneous or
  claim water-alone activation: the DUT also reported `lid_open=1`.
- Stable dark/wet follow-up **passed**: S3 light **0.534 V**, water **0.965 V**;
  C6 light 0.532–0.551 V and water 0.993–1.055 V, consistently reporting
  `lid_open=0 wet=1 alert=1 fault=0`. Alarm tap counted **4 CHANGE edges in
  1000 ms**, consistent with the previously measured 2 Hz drive. User confirms
  visible LED blinking. Both independent sensor stimuli and LED behavior now
  work without moving wiring. User was told they can wipe the comb dry.
- Physical sensor/LED checks are complete for this wiring. The deliberate
  fault → agent diagnosis → repair demonstration still needs execution; do
  not call that sequence validated yet. No fault firmware was uploaded here.
- Evidence: `validation_runs/2026-09-26-parcel-s3-upload.json`,
  `2026-09-26-parcel-c6-upload.json`, `2026-09-26-parcel-baseline.json`,
  `2026-09-26-parcel-covered-dry.json`, `2026-09-26-parcel-covered-wet.json`,
  `2026-09-26-parcel-dark-wet-steady.json` (the decisive water-only capture).
  The first covered capture's human annotation was corrected with an audit
  note; raw measurements and timestamps remain unchanged.
- Dashboard restarted and live browser refreshed with the new declarations.
  Host verification: 15 targeted profile/capture/postflash tests passed.
- Conditional-activity comparison was completed in the later website pass
  above. It is enabled and host-tested; a new live run is still required.

## Previous preparation: ParcelGuard wiring batch issued (2026-09-26)

User is back and requested the final quick demo. The complete clean wiring
batch was delivered in chat and is in `PARCEL_GUARD_SETUP.md`: the photoresistor,
water sensor, and LED output each have a shared 6.8 kΩ ADC/digital tap.
Await **“wired” / “ParcelGuard wired.”** No need to request more parts.
User explicitly requests component-by-component instructions in wiring order:
use board names and pin labels, never invented row letters or node names.
The setup guide follows power → photoresistor → water sensor → LED → USB.

- Current harness now selects `parcel_guard` with P1/P2/P3 and D1/D2/D3
  **pending**. Prior map is preserved in
  `harness/profiles/plant_sentinel_legacy.yaml`. Keep pending until confirmed.
- S3 series build requires `-DBENCHY_PROFILE_SERIES=1`; INFO v0.3 identifies
  `series-taps-v1`. Host refuses readings if that required profile is missing
  or different. Default S3 compilation retains the legacy divider map.
- S3 new mapping: P1 ADC1/digital8, P2 ADC4/digital9, P3 ADC6/digital10;
  all ADC scales 1. The series build counts only D1–D3 so unused floating
  inputs do not consume interrupts. All measurement pins remain inputs.
- C6 `dut_examples/parcel_guard` uses IO1 light, IO2 water, IO20 LED. Serial
  reports run in a separate task, while sensing and 2 Hz LED timing run in
  loop(). It reports every 500 ms, with light/water hysteresis. Fault 0 is
  healthy, 1 is false-zero water, 2 disables the LED drive, 3 makes it 10 Hz.
  Initial light thresholds: open 1.4 V / closed 0.9 V; water wet 0.5 V /
  dry 0.3 V. These need the rebuilt circuit's physical baseline.
- Both sketches compiled before upload. Build directories under workspace
  `work/parcel-s3` and `work/parcel-c6`. No new firmware uploaded yet.
- Dashboard supports connected digital taps without requiring an I²C bus;
  ParcelGuard hides the unrelated bus panel and offers “Sample taps.”
- Demo script: `PARCEL_GUARD_DEMO.md`. Main exercise uses a disclosed 10 Hz
  alarm fault, then repair to 2 Hz and physical verification. Optional water
  false-zero exercise compares C6 report with S3 P2 while the comb is wet.
- After confirmation: stop dashboard polling for uploads, identify USB serials,
  upload S3 with verification, activate connected declarations, then flash C6.
  Check physical light/water readings and P3 2 Hz while uncovered. Ask for the
  combined dark/dry → bright → dark/wet user action batch and visible LED check.
  Do not declare the rebuilt demo finished before those tests pass.
- Tests now read a private copy of the legacy fixture, independent of the
  user's current map. Explicit ParcelGuard profile tests verify pending state
  and rejection of incompatible S3 firmware.

## Latest work: website while user is AFK (2026-09-26)

- Follow-up: **Save new capture** now collects fresh server-side physical
  readings, a frozen harness, nearby selected-DUT serial output, a user note,
  and local source inventories before/after. It stores a persistent JSON file
  and selects it in the comparison panel. Automatically saved runtime records
  in `validation_runs/dashboard/` are ignored by Git.
- One real browser save succeeded: P1 2.436 V, P2 3.165 V, P3 0 V;
  D1/D3 42/42 transitions, D2/D4 166/166, D5 0 in a 1 s digital window.
  **Those voltage and digital windows were ~119 seconds apart**, so they must
  not be interpreted as concurrent observations. The raw record is retained in
  `validation_runs/2026-09-26-dashboard-capture.json`. The UI now displays
  per-reading timestamps and capture spans, and new long gaps get a warning.
- Added bounded queue waits and a reservation so automatic polling cannot
  overtake a saved capture. Also bound serial events to their originating port.
  The subsequent live retry could not run: both ESP32s disappeared from USB
  discovery. Only system/Bluetooth ports were listed. The queue reservation
  is host-tested, but a successful live repeat with the final reservation fix
  remains pending. Do not claim its timing is physically validated.
- Website still works offline for source inspection and saved comparisons.
  The save action is disabled until an S3 is identified. User is AFK; do not
  restart the deferred wiring sequence.
- Final capture-feature verification: **79 Python tests and 4 Node UI tests
  passed**, including loopback HTTP routes, server-originated measurement
  capture, frozen declarations, source changes, partial failures, queue
  reservation, and timing warnings. Browser checked the saved context,
  individual timestamps, and disabled save action while boards are absent.
- User postponed the clean wiring rebuild and asked for website work. No
  firmware was changed or new wiring requested during this website pass.
- Added declared DUT pin coverage (`dut_pins` in the harness), showing the
  connected analog/digital channels and their latest fresh evidence. The
  existing circuit declares five used pins, all covered. This is a declaration,
  not automatic discovery or continuity verification.
- Added rolling two-minute voltage trends. Old physical readings lose their
  current verdict after 15 seconds; the page labels stale captures explicitly.
  Pausing live sampling was checked in the browser: the assessment changed to
  “Fresh evidence needed” and the coverage table stopped showing old readings.
- Added read-only saved-capture comparison, backed by bounded JSON files in
  `validation_runs/`. Original net labels are retained; missing measurements
  stay blank. Deltas require the same channel, net, metric, and unit. Browser
  check: the saved noisy D5 capture showed 4,988.006 transitions/s, versus 0
  after reseating. This is historical evidence, not a new physical test.
- Session timeline entries open an inspectable snapshot with the original
  measurement, harness declaration, nearby serial output, and recent taps.
  Escape closes the viewer. Legacy records without wiring snapshots say so.
- Host verification: **71 Python tests passed**, including loopback API and
  asset serving; **4 Node UI logic tests passed**. JS syntax and whitespace
  checks passed. Dashboard running at `http://127.0.0.1:8765/`; check process
  before restarting. Live sampling was restored after the browser check.
- Untracked `video/node_modules/` belongs to separate video work; do not stage it.

## Earlier plan: clean ParcelGuard rebuild (superseded by batch above)

User requested a clean, simpler test project for a quick friends demo, with
Benchy permanently observing every used DUT GPIO. Stop the earlier LED repair
sequence; the historical observations below remain useful evidence.

New project: light intrusion + water leak → blinking LED alarm. C6 uses only
IO1 (light), IO2 (water), IO20 (LED). Wiring is in `PARCEL_GUARD_SETUP.md`.
Each signal branches through a 6.8 kΩ resistor into a sense row shared by an
S3 ADC and a digital input: P1 IO1/IO8, P2 IO4/IO9, P3 IO6/IO10. These are
known 0–3.3 V nodes with no ADC divider. Existing firmware/manifest still
describe the prior circuit. **Do not measure the rebuilt circuit under the
old mapping or scale.** The full inline wiring batch has not yet been delivered
and the user has not confirmed rebuilding it. When they return to wiring,
prepare a named S3 series-tap profile (ADC scale 1), C6 `parcel_guard` sketch,
and its harness, then deliver the complete batch. Keep all new connections
pending until confirmed. Preserve the old profile and historical evidence.
No Git history reset/rebase is requested.

## Latest checkpoint: permanent taps (2026-09-26, 19:35 UTC)

- User reported completing three **6.8 kΩ** branches: C6 IO5 source junction
  to S3 IO10, C6 IO7 source junction to S3 IO11, and C6 IO20 before the LED
  resistor to S3 IO12. All are declared connected; declarations are not
  automatic connectivity verification. Full wiring: `PERMANENT_TAPS.md`.
- S3 v0.2 compiled and uploaded to USB serial `94:A9:90:DB:BA:64` while
  holding its port lock. Arduino verified flash hashes; live `INFO` says
  v0.2 and `HELP` lists `MEASURE_TAPS`. C6 firmware was not changed.
- After upload: P1 2.457 V, P2 3.219 V, P3 0.000 V. C6 light 2.522 V and
  water 0.020 V both match their independent probes within 0.45 V. C6
  reports MPU healthy, Z 1.086 g, `alert=0`, `fault=0`.
- New bus endpoint taps show activity in the same 2 s window: SDA D1/D3
  82/82 edges; SCL D2/D4 332/331. Repeated SDA 86/86 and 86/85, SCL
  332/332 and 332/331. This supports working observations at both ends;
  approximate counts do not prove matching transactions or continuity.
- **LED tap reseating resolved the excess activity.** Before reseating,
  D5 counted 6,015 / 10,714 / 9,981 CHANGE edges in ~2 s while C6 reported
  no alert. After the user checked the C6 IO20 → 6.8 kΩ → S3 IO12 branch,
  D5 measured LOW, zero edges, and 0 Hz; SDA was 81/81 and SCL 332/332 at
  the two endpoints. P1 2.468 V, P2 3.199 V, P3 0.000 V; telemetry passed.
  This supports a corrected sense connection, without identifying the exact
  original bad contact. Saved after-check: `led-reseated.json`.
- Covered-light test: P1 fell to 0.316 V; C6 reported 0.355 V,
  `low_light=1`, `alert=1`. D5 counted eight CHANGE edges in 2 s with DUT
  serial held open. **User reports LED still dark.** User was asked to
  unplug both boards, check LED polarity (long leg/anode toward the
  220–330 Ω resistor, short leg/flat side to shared GND), ensure legs occupy
  separate connected groups and correct resistor value, then reconnect with
  light still covered and report whether it flashes. That request was later
  superseded by the clean rebuild; do not resume the old one-wire sequence.
- A separate D5 frequency window without explicitly holding DUT serial open
  read 1 Hz (two rising edges in 2 s), so consistent standalone 2 Hz timing
  is not yet proved. The covered-light record contains both results. Keep
  the DUT stream open for the next comparison and investigate before
  declaring precise timing validated. `pulse_us=0` at this slow rate is
  inconclusive because the firmware's pulse timeout is only 60 ms.
- Saved raw hardware evidence: `validation_runs/2026-09-26-taps/`.
  `reassessed-led-repeat.json` applies the new generic declared transition
  bound to a saved capture; it is not an additional live sample.
- Dashboard `/api/taps`, CLI `digital-taps`, and MCP `measure_digital_taps`
  support five counts, endpoint comparisons, and optional
  `max_transitions_per_s` targets. D5's 8/s upper bound catches the excessive
  activity. This is only an upper bound; idle LOW passing it does not prove
  the LED works. GUI net names and expectations come from the harness.
- Host telemetry checks require every declared field, allow separate serial
  lines, and reject stale/malformed newest values. Upload now holds a serial
  lock and rechecks identity afterward. Optional postflash marker, telemetry,
  and voltage targets are implemented with tests, but the complete automatic
  upload-to-postcheck sequence remains unvalidated on hardware.
- Latest host run: 67 passed, 1 sandbox socket test skipped. The preceding
  64-test suite passed with loopback access. JS syntax and whitespace checks
  passed. Firmware program size: 315,258 bytes; globals: 23,336 bytes.
- Software checkpoint `5000912` was pushed to GitHub before the live tests.
  Resume by reading current Git state and these saved results. The dashboard
  was restarted after flashing at `http://127.0.0.1:8765/`; check its process
  before reuse.

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
- `dut_examples/imu_demo/`: earlier MPU-family I²C motion demo.
- `dut_examples/plant_sentinel/`: currently flashed combined light, water,
  motion, and LED demo; see `PLANT_SENTINEL_PLAN.md`.
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
- C6 currently runs `plant_sentinel` with `DEMO_FAULT=0`; SDA is IO5 and SCL
  IO7. It also samples light on IO1 and water on IO2, and drives an LED on IO20.
  The user swapped in a second MPU breakout on the same reported wiring.
  The photoresistor circuit remains wired, but the old `light-compare` profile needs
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

## Multi-sensor checkpoint (later on 2026-09-26)

- User connected a 3-pin water sensor (`+` to C6 3V3, `-` to shared GND,
  `S` to C6 IO2) and two separate 10 kΩ S3 sense branches from `S` to
  P3 ADC IO6 and digital IO7. S3 firmware with P3 compiled and uploaded with
  Arduino flash verification. P3 measured 0.000 V dry and 0.897/0.833 V wet.
- User wired an LED from C6 IO20 through a 220–330 Ω resistor to the LED
  anode, with cathode to shared GND. LED operation during an alert still needs
  observation. The unmarked passive buzzer and unlabeled DHT11 stay disconnected.
- `plant_sentinel` compiled and flashed to the enrolled C6 with verified flash
  hashes after pausing dashboard serial polling. A first upload attempt failed
  before verification due to a serial disconnect and must not be counted.
  Fresh C6 serial identified `plant-sentinel-v1` and reported light 2.52 V,
  water 0.016–0.033 V dry, IMU ID `0x70`, Z about 1.08 g, and no alert.
  S3 independently measured P1 2.464 V, P2 3.226 V, P3 0.003 V dry.
- The dashboard's generic telemetry cards parse numeric `key=value` serial
  output. `harness/current.yaml` declares P1/light and P3/water comparisons,
  each with a 0.45 V tolerance. The live page showed “Independent readings
  agree” for the dry baseline. This checks reported analog values against S3
  readings near in time; it does not verify unprobed LED current or decode I²C.
- Agents can call MCP `check_telemetry_against_probes` or run CLI
  `check-telemetry`. Both discover enrolled S3/C6 USB identities, sample
  overlapping windows, and compare only harness-declared fields and tips.
  A live dry check passed: P1 2.443 V versus C6 2.489 V, P3 0.000 V versus
  C6 0.019 V. Missing or stale reports return `unverified`.
- The full host suite now passes 42 tests with loopback access, including
  asset serving, MCP registration, false-zero detection, and stale-report
  handling.
- A second reversible SCL-open test before the combined sketch showed MPU
  VCC at 3.191 V, SDA 36 edges and SCL 0 edges in a 2 s S3 capture while
  C6 serial reported `IMU_ERROR no_device_at_0x68_or_0x69`. After restoring
  SCL, S3 counted SDA 492 and SCL 1,929 edges and the IMU stream recovered.
- Current host tests: 39 passed, 1 sandbox socket test skipped. JS syntax and
  whitespace checks passed. The dashboard is served at `127.0.0.1:8765` when
  its local process is running.

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
./scripts/python.sh -m benchos.cli check-telemetry
./scripts/python.sh -m benchos.cli flash-plan
./scripts/python.sh -m pytest -q
```

The C6 currently runs `plant_sentinel`; use the dashboard's generic serial
monitor for its output. Reflash `light_sensor_demo`
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

1. Complete and validate the permanent tap batch above. The original IO8/IO9
   paths already passed grounded/common-SCL tests and an SCL-open/restored
   fault test. The new five-input capture still needs live validation. The
   P1/P2 dividers load nets and must not be moved onto I²C lines.
2. For a new design, update the harness's DUT metadata and source-file list,
   verify each probe connection by hand, and add bounded physical test
   expectations. The GUI does not infer connectivity or flashed code.
3. If testing SG90 motion, identify a separate regulated 5 V supply with
   adequate current first. Then wire its ground to the shared rail, SG90 yellow
   to C6 GPIO20/T, brown to ground, and red to that supply's +5 V.
4. Flash normal servo firmware, run the physical signal check, enable sweep,
   and verify actual SG90 movement. Record the result in `VALIDATION.md`.
