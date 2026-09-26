# Permanent digital taps

Latest hardware checkpoint: S3 v0.2 uploaded and verified; both SDA/SCL
endpoint pairs show activity. D5 initially showed excessive transitions despite a DUT
report of no alert; after reseating, it reads LOW with zero edges. Covered-light input triggered a C6 alert and eight
D5 transitions in two seconds with DUT serial open. The user still sees a
dark LED; the LED branch and standalone blink timing need checking. Raw results live in
`validation_runs/2026-09-26-taps/`. All locations below are user declarations.

## Current setup and wiring batch

Keep the existing MPU, light sensor, water sensor, LED, P1/P2/P3, shared ground,
and S3 IO8/IO9 bus branches. Add three branches using **6.8 kΩ** resistors
(the user ran out of 10 kΩ; 1–10 kΩ is acceptable for this known 3.3 V setup).
Disconnect both USB cables before moving wires. Do not connect these inputs
to 5 V or unknown nodes; a series resistor does not provide level shifting.

| Tap | S3 input | Observed point | Series resistor | Status |
| --- | --- | --- | --- | --- |
| D1 | IO8 | MPU-side SDA row | existing 10 kΩ | Previously connected and tested |
| D2 | IO9 | MPU-side SCL row | existing 10 kΩ | Previously connected and tested |
| D3 | IO10 | C6 IO5 source junction | new 6.8 kΩ | User reported connected |
| D4 | IO11 | C6 IO7 source junction | new 6.8 kΩ | User reported connected |
| D5 | IO12 | C6 IO20 before LED resistor | new 6.8 kΩ | Connected; idle LOW validated after reseating |

For each new tap, use two unused, separate breadboard rows:

1. Move only the C6 end of the existing signal jumper to the first row.
   Leave the other end attached to its sensor or LED circuit.
2. Add a jumper from the same C6 GPIO to that first row, restoring the
   original signal path through this new source junction.
3. Put a 6.8 kΩ resistor from that junction row to a second isolated row.
4. Connect the designated S3 input to the second row.

```text
C6 signal pin ── source junction ── original wire ── sensor / LED circuit
                       |
                     6.8 kΩ
                       |
                  sense row ── designated S3 input
```

Use independent rows for all three signals. Add no connection from a sense
row to power or ground. On IO20 retain the existing 220–330 Ω LED resistor
and LED-to-ground path. Existing S3 IO8/IO9 stay at the **MPU-side** rows.
Keep the unlabeled DHT11, buzzer, and servo disconnected.

Reconnect both USB cables and confirm completion before declaring D3–D5
connected in `harness/current.yaml`. Input mode is fixed in S3 firmware;
the host does not expose drive or pull-resistor commands.

## Software

S3 v0.2 adds `MEASURE_TAPS 1000`, with five approximate CHANGE-interrupt
counts collected over overlapping windows. Example format (illustrative):

```text
OK TAPS WINDOW_MS 1000 D1 HIGH HIGH 20 D2 HIGH HIGH 180 D3 HIGH HIGH 19 D4 HIGH HIGH 179 D5 LOW LOW 0
```

`READ_DIGITAL D1` through `D5` and `MEASURE_FREQ D5 1000` also work.
`READ_ADC D5` returns `ERR DIGITAL_ONLY`; P1/P2/P3 ADC support remains.

```sh
./scripts/python.sh -m benchos.cli digital-taps --duration-ms 1000
./scripts/python.sh -m benchos.cli digital D5
./scripts/python.sh -m benchos.cli frequency D5 --duration-ms 2000
```

MCP: `measure_digital_taps(duration_ms=1000)`. Dashboard: “Sample bus” calls
`/api/taps` when taps are declared, keeps the DUT serial stream open during
capture, and displays all declared endpoints. The net names and locations
come from the harness, so they can describe another known 3.3 V design.

Only taps declared `connected` can contribute to comparisons. Pending raw
inputs may float; they are returned as unusable for diagnosis and hidden
from the displayed measurements. Two declared endpoints on the same net are
compared for activity at both, one, or neither endpoint. A difference suggests
a check of the link and the two sensing branches; it does not locate a broken
contact by itself.

An optional `max_transitions_per_s` declaration checks an upper bound on
CHANGE edges per second. For the current LED drive the bound is 8/s, allowing
its intended 2 Hz blink (4 transitions/s) and boundary changes. This catches
large excess activity without claiming a cause. It does not require blinking
when an alert is active, and passing an upper bound cannot prove an LED works.

## Acceptance sequence after wiring

1. Confirm physical placement and USB identities. Upload compiled S3 v0.2
   using the S3 port lock, then verify `INFO` and `HELP`.
2. Recheck P1/P2/P3 and C6 telemetry to detect a wiring regression.
3. Capture D1–D5 together during C6 MPU traffic. Both ends of SDA/SCL should
   show activity; do not require exact counts to match.
4. Trigger an alert with a covered photoresistor or wet water-sensor comb;
   measure D5 at 2 Hz and obtain a visual LED observation. Voltage/timing at
   IO20 does not prove current through the LED or that it emits light.
5. For an open-link demonstration, disconnect a source-junction-to-MPU
   jumper while leaving both endpoint taps attached. Compare source activity,
   sensor-side activity, sensor supply, and DUT errors; restore and remeasure.

## Limits

These are approximate digital counts, not a logic analyzer or I²C decoder.
The five inputs have small start/stop skew; fast transitions may be missed.
Coincident activity does not prove matching bytes, ACK, or electrical
continuity. A tap at the source junction cannot distinguish a break in the
short C6-pin-to-junction stub without another measurement. Light and water
remain instrumented at their existing sensor nodes; this expansion is not
dual-ended coverage of every wire or a measurement of LED current.
