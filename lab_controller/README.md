# Lab controller

Flash this sketch to an **ESP32-S3** with Arduino-ESP32 3.x. Edit
[`config.h`](config.h) for your board before wiring. P1 uses GPIO1 for ADC
through two equal 10 kΩ resistors, and GPIO2 for direct digital observation.
P2 repeats the same circuit with GPIO4 for ADC and GPIO5 for digital input.
Both probes are always unpulled inputs. On each probe, the ADC divider and
digital branch meet at its own tip. Supply only a known, common-ground,
0–3.3 V signal to P1 or P2; never attach 5 V,
a negative voltage, or an unknown voltage directly. If larger voltages must
be measured in the future, **both** branches need appropriate protection and
the direct digital branch must be disconnected.

The protocol is newline-delimited ASCII at 115200 baud. `HELP` lists commands.
`READ_ADC P1` returns approximate volts, average raw ADC code, and sample count.
`MEASURE_FREQ P1 1000` counts rising edges in a one-second window and reports
an optional high pulse width. Low frequencies need a longer window; very short
pulses may be missed. No reading is a calibrated voltmeter measurement.

Firmware v0.2 also supports P3 (ADC IO6 and digital IO7, each connected to
the known 0–3.3 V node through its own series resistor, without a divider)
and passive digital taps D1–D5 on IO8–IO12. `MEASURE_TAPS 1000` counts all
five inputs over overlapping windows, while `READ_DIGITAL D5` and
`MEASURE_FREQ D5 2000` inspect an individual tap. The original `MEASURE_BUS`
command still observes IO8/IO9. No command enables drive mode or internal
pulls. See `../PERMANENT_TAPS.md` for wiring, protocol, and capture limits.
