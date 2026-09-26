# Lab controller

Flash this sketch to an **ESP32-S3** with Arduino-ESP32 3.x. Edit
[`config.h`](config.h) for your board before wiring. P1 uses GPIO1 for ADC
through two equal 10 kΩ resistors, and GPIO2 for direct digital observation.
The probe is always an unpulled input. Both branches meet at the probe tip.
Supply only a known, common-ground, 0–3.3 V signal to P1; never attach 5 V,
a negative voltage, or an unknown voltage directly. If larger voltages must
be measured in the future, **both** branches need appropriate protection and
the direct digital branch must be disconnected.

The protocol is newline-delimited ASCII at 115200 baud. `HELP` lists commands.
`READ_ADC P1` returns approximate volts, average raw ADC code, and sample count.
`MEASURE_FREQ P1 1000` counts rising edges in a one-second window and reports
an optional high pulse width. Low frequencies need a longer window; very short
pulses may be missed. No reading is a calibrated voltmeter measurement.
