# ParcelGuard demo: observe → diagnose → repair → verify

Status: matching firmware is uploaded. Initial light readings agree and the
LED drive passes at 2.000 Hz. Covered/dry reads 0.686 V light and alarm off;
the user confirms visible on/off response. The water-only alarm response
remains pending; the complete demo is not yet validated. Seeded faults are
intentional exercises, not a claim of discovering an unknown fault unaided.

## Before showing friends

1. Complete `PARCEL_GUARD_SETUP.md` and confirm “ParcelGuard wired.”
2. Agent flashes S3 `series-taps-v1`, then the correct C6 sketch, and checks
   independent light/water voltages plus the LED drive frequency.
3. User confirms the LED actually lights. Hold an opaque cover over the
   photoresistor and keep water sensor dry: LED should stop after startup.
4. Remove the cover: LED should blink twice per second. Replace the cover.
5. Touch only the sensor's comb/traces with a damp fingertip or a small drop
   of tap water. Keep the header, USB boards, and main breadboard dry. LED
   should blink while the sensor is wet. Wipe the comb dry afterward.

Initial thresholds: light opens at 1.4 V and closes at 0.9 V; water detects at
0.5 V and clears at 0.3 V. Confirm dark/bright and dry/wet levels from real
readings; adjust thresholds if this lighting/sensor needs it.

## Three-minute main demo

- **Show the project:** “This box detects an open lid and a leak. Every used
  signal is permanently connected to Benchy's independent measurement inputs.”
- **Show healthy behavior:** open/close the light cover; show the physical
  voltage and LED drive activity. The serial values are claims from the DUT.
- **Introduce a disclosed software bug:** ask the agent to enable fault 3
  (10 Hz LED alarm). Keep the photoresistor uncovered so `alert=1` remains stable.
- **Ask for diagnosis:** “The alarm is flashing wrong. Use Benchy to measure it,
  inspect the source, fix the code, flash the C6, and verify the result.”
- **Show evidence:** D3 should exceed its 6 transitions/s upper bound, and
  P3 frequency should measure about 10 Hz. Save a “Before repair” capture.
- **Repair and verify:** agent sets fault 0, flashes the C6, checks P3 frequency
  at 2 Hz (1.5–2.5 Hz range over 2 s), and checks sensor telemetry agreement.
  Save “After repair” and compare the physical readings and source state.

No wire moves are required during this main demonstration. A passing drive
frequency check establishes the electrical signal; the user verifies the LED
actually emits light.

## Optional second exercise: hidden water reading

Keep the light sensor covered. Wet only the comb. Confirm both the C6 and S3
show the changed water voltage, then enable fault 1. The C6 reports water=0 and
ignores the leak; S3 P2 should still measure the real wet-sensor voltage.
Benchy should flag their disagreement. Agent restores fault 0, reflashes, and
remeasures while the sensor remains wet. A report mismatch can have firmware
or wiring causes; independent readings and source inspection narrow it down.

## Operator / agent commands

Use the enrolled USB identities in the current harness. Do not guess ports.
Keep the source inspector honest: change `PARCEL_GUARD_FAULT` in
`dut_examples/parcel_guard/config.h` to 0, 1, 2, or 3 before using the regular
build/flash command. A compile-time override is useful for development but
would not appear as that source change in the inspector.

```sh
./scripts/python.sh -m benchos.cli flash-plan
./scripts/python.sh -m benchos.cli flash-dut
./scripts/python.sh -m benchos.cli check-telemetry
./scripts/python.sh -m benchos.cli frequency P3 --duration-ms 2000
./scripts/python.sh -m benchos.cli digital-taps --duration-ms 2000
```

The physical suite is `physical_tests/parcel_alarm.yaml`. Run it only while the
lid is open or the water sensor is wet and the expected mode is the healthy
2 Hz alarm. The client refuses incompatible S3 profiles. After deliberate
fault tests, leave the source and flashed C6 at fault 0.

## Capability boundaries

Three fixed taps cover these declared signal nodes. They do not automatically
discover wiring, measure LED current/light, or locate every broken contact.
Captured voltages and transition windows are sequential, with timestamps.
