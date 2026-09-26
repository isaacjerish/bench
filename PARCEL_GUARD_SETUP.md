# ParcelGuard — clean wiring batch

Status (2026-09-26): instructions issued; user confirmation and upload still
pending. `harness/current.yaml` selects this design with pending connections.
The S3 and C6 sketches compile. Do not mark the new circuit physically verified
until the user confirms wiring and the independent checks pass.

## What it does

A parcel box detects light entering through an open lid and water reaching its
leak sensor. Either event flashes an LED at 2 Hz. Benchy observes all three
used C6 signals permanently. Covering the photoresistor represents closing the
lid; an opaque cup or small box works. No special enclosure is required.

## Parts

- ESP32-C6 DUT and ESP32-S3 Benchy, each with its USB data cable
- Photoresistor, water sensor labeled `+`, `-`, `S`, one LED
- Three 6.8 kΩ resistors, one 10 kΩ resistor, one 220–330 Ω resistor
- Breadboard and jumper wires

## 1. Start clean, with both USB cables unplugged

Remove the previous MPU and all old probe wiring/dividers. Power the sensor
rail from **C6 3V3**, and connect **C6 GND and S3 GND** to the same ground rail.
Do not connect the two 3V3 outputs. Use one continuous section of the power
rails; many breadboards split them halfway along their length.

## 2. Build the three circuits and their permanent taps

Each named row below is one connected five-hole group (a–e), not both sides of
the breadboard center gap. Suggested rows can be changed if clearly labeled.

| Row/group | Wires and component legs in that connected group |
| --- | --- |
| **L / row 10** | C6 IO1, photoresistor leg, 10 kΩ resistor end, first 6.8 kΩ resistor end |
| **LS / row 14** | Other end of L's 6.8 kΩ resistor, S3 IO1, S3 IO8 |
| **W / row 20** | C6 IO2, water sensor S, second 6.8 kΩ resistor end |
| **WS / row 24** | Other end of W's 6.8 kΩ resistor, S3 IO4, S3 IO9 |
| **A / row 30** | C6 IO20, 220–330 Ω LED resistor end, third 6.8 kΩ resistor end |
| **AS / row 34** | Other end of A's 6.8 kΩ resistor, S3 IO6, S3 IO10 |

Remaining component connections:

- Photoresistor other leg → C6 3V3 rail.
- The 10 kΩ resistor other end → shared GND rail.
- Water sensor `+` → C6 3V3; `-` → shared GND.
- LED resistor other end → LED long leg/anode, in its own empty row.
- LED short leg/flat side/cathode → shared GND; its legs must occupy different
  connected groups.

**No LS/WS/AS resistor goes to GND.** Each probe uses a single 6.8 kΩ series
resistor, shared by its ADC and digital input. These are only for known
0–3.3 V nodes; the resistor does not make an input safe for 5 V.

Reconnect both USB cables. Leave the water sensor dry and photoresistor
uncovered. Reply **“ParcelGuard wired”** so the agent can activate the confirmed
connections, flash the matching S3 profile and C6 sketch, and measure them.

## Firmware mapping

| Probe | Analog pin | Digital pin / tap | ADC scale |
| --- | --- | --- | --- |
| P1 LIGHT_SENSE | S3 IO1 | S3 IO8 / D1 | 1 |
| P2 WATER_SENSE | S3 IO4 | S3 IO9 / D2 | 1 |
| P3 ALARM_DRIVE | S3 IO6 | S3 IO10 / D3 | 1 |

D4/IO11 and D5/IO12 remain disconnected. This design has no I²C bus.
The S3 requires `series-taps-v1`; the Python client rejects the old divider
firmware. Compile S3 with `compiler.cpp.extra_flags=-DBENCHY_PROFILE_SERIES=1`.
The unmodified default build retains `legacy-dividers-v1` for older wiring.

ADC readings near the top of the rail may saturate. P3 voltage readings sample
individual moments of the blinking signal; use its digital frequency/counts to
check the blink rate. Measuring the output pin does not prove light emission.

See `PARCEL_GUARD_DEMO.md` for the short demonstration and deliberate faults.
