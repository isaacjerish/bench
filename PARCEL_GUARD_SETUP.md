# ParcelGuard — clean wiring batch

Status (2026-09-26): user reported wiring ready for checking; both boards have
the matching firmware and the current connections are declared connected.
Initial light readings agree (S3 2.700 V / C6 2.725 V) and the LED drive measures
2.000 Hz. Covered light measured 0.686 V with LED drive 0 V / zero transitions;
the user confirms the LED blinks in light and stops covered. The water-only
alarm response still needs validation. These steps document the complete wiring.

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

## 1. Unplug and clear the old circuit

Unplug both ESP32 USB cables. Remove the old MPU and previous sensor/probe
wiring so it cannot remain accidentally connected. Reuse the parts below.

When these steps say to connect several things together, put their wire ends
in the same connected five-hole group on one side of the breadboard's middle
gap. Put a resistor's two ends in different groups, so it is not bypassed.

## 2. Connect power and ground

1. C6 **3V3** → red **+** power rail.
2. C6 **GND** → blue **−** ground rail.
3. S3 **GND** → that same blue ground rail.

Leave S3 3V3 unconnected. Use one continuous section of each rail; many
breadboards split their rails halfway along the length. This circuit uses 3.3 V.

## 3. Connect the photoresistor, then its Benchy wires

1. One photoresistor leg → red power rail.
2. Other photoresistor leg → C6 **IO1**.
3. Connect a **10 kΩ** resistor between that second leg and the blue ground rail.
4. Connect one end of a **6.8 kΩ** resistor alongside that second leg.
5. Put the free end of the 6.8 kΩ resistor in an unused connected group.
6. Connect **S3 IO1 and S3 IO8** to that free end, together.

## 4. Connect the water sensor, then its Benchy wires

1. Water sensor **+** → red power rail.
2. Water sensor **−** → blue ground rail.
3. Water sensor **S** → C6 **IO2**.
4. Connect one end of a second **6.8 kΩ** resistor alongside the sensor's S wire.
5. Put its free end in a different unused connected group.
6. Connect **S3 IO4 and S3 IO9** to that free end, together.

## 5. Connect the LED, then its Benchy wires

1. C6 **IO20** → one end of a **220–330 Ω** resistor.
2. Other end of that resistor → LED **long leg** (anode).
3. LED **short leg / flat side** (cathode) → blue ground rail.
4. Connect one end of the third **6.8 kΩ** resistor alongside the C6 IO20 wire,
   **before** the LED's 220–330 Ω resistor.
5. Put its free end in another unused connected group.
6. Connect **S3 IO6 and S3 IO10** to that free end, together.

The three 6.8 kΩ resistors do not connect to ground. Keep their S3 ends
separate from each other. They are for known 0–3.3 V signals and do not make
an input safe for 5 V.

## 6. Reconnect USB

Reconnect both USB data cables. Leave the water sensor dry and photoresistor
uncovered. Reply **“wired”** and leave both boards connected. The agent will
activate the confirmed connections, upload the matching S3 and C6 firmware,
and take physical readings before declaring the demo ready.

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
