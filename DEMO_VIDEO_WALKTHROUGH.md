# Benchy: a three-minute debugging demo

Use the real connected boards with **Preview off** and **Live: on**. Expand
the browser panel for filming so the design map and assessment fit together.
These are deliberately seeded faults; measurements and repairs are real.
The agent uses Benchy's tools. The webpage displays evidence and local source;
its source inspector does not edit or flash firmware.

## Opening — 20 seconds

1. Keep the light sensor uncovered and water sensor dry.
2. Open **Design map**: show the breadboard illustration, probe coverage, and
   assessment. Say: “This parcel monitor detects an open lid or a leak.
   Benchy independently measures each signal used by the controller.”
3. Open **Probes**: light should be high, water near zero. Open **Signal taps**:
   D3 should count about **8 transitions in 2 seconds**, a 2 Hz square wave.
4. In **Saved captures**, name a capture `01 Healthy` and click
   **Save new capture**. Keep the scene steady until it finishes.

## Fault 1 — sensors connected to the wrong inputs

This common wiring mistake can hide behind an LED that still blinks.

1. Unplug **both ESP32 USB cables**. At the **C6 only**, swap the two jumper
   ends plugged into **IO1 and IO2**. Keep their sensor ends and all colored
   S3 wires/resistors in place. Reconnect USB and wait for fresh readings.
2. Leave light uncovered and water dry. In **Design map**, show the mismatch.
   In **Serial monitor**, compare `light_mv` and `water_mv` with **Probes**:
   Benchy's light voltage should be high and water low, with the DUT reversed.
3. Save `02 Inputs swapped`. Ask the agent:
   > Compare Benchy's physical light and water measurements with the DUT's
   > reports and pin configuration. What explains the disagreement, and what
   > should I reconnect? Verify after I fix it.
4. Open **Source**, choose `dut_examples/parcel_guard/config.h`, and click
   **Refresh**. It declares light on IO1 and water on IO2. This narrows the
   mismatch; the agent does not automatically trace wires through a breadboard.
5. Unplug both USB cables. Restore **photoresistor → C6 IO1**,
   **water sensor S → C6 IO2**. Reconnect and wait for fresh passing evidence.
6. Save `03 Inputs repaired`. In **Saved captures**, choose `02 Inputs swapped`
   as **Before** and `03 Inputs repaired` as **After**. Expand
   **Device output saved with these captures** to show the reports too.

## Fault 2 — wrong alarm timing; agent fixes firmware

No wire moves. Leave the light uncovered so the alarm stays requested.

1. Ask the agent to seed the existing **fault 3** timing exercise and flash
   the C6. It changes the alarm from 2 Hz to 10 Hz. Wait for upload and fresh
   measurements; do not use upload success as proof of circuit behavior.
2. Show **Signal taps**: approximately **40 transitions in 2 seconds**, against
   the declared 3–5 transitions/s operating range. Show the failing assessment.
   Save `04 Timing fault`.
3. Ask:
   > Measure the alarm frequency, inspect its timing code, restore the intended
   > 2 Hz behavior, flash the C6, and prove the repair with a new measurement.
4. **Source** → `dut_examples/parcel_guard/parcel_guard.ino` → **Refresh**:
   50 ms per half-cycle produces 10 Hz; 250 ms produces 2 Hz. The agent restores
   fault 0 and flashes. The serial fault marker discloses the exercise.
5. Show the fresh **Signal taps** pass (about 8 transitions/2 seconds) and
   the agent's separate **2 Hz frequency measurement**. Confirm visible LED
   blinking. Save `05 Timing repaired`; compare captures 04 and 05.

## What makes this convincing

- Film the real board beside the UI; hold each condition steady for 10 seconds.
- Show **symptom → independent measurement → source/wiring explanation →
  repair → new measurement**, with one fault at a time.
- If time permits only one fault, use timing: it demonstrates measurement,
  code inspection, flashing, and physical verification without rewiring.
- The illustration is a declared map, not a camera reconstruction. Saved
  comparisons are historical; return to **Design map** for the live result.
- Seeded faults and declared expected behavior are appropriate demo setup.
  Do not describe a scripted exercise as blind discovery or replace readings
  with synthetic values. Leave the final circuit and C6 at fault 0.

## Rehearsal status

After the color rewire, the live dashboard and a saved capture agree: light
**2.697 V**, dry-water baseline **0 V**, D3 **8 transitions/2 seconds**,
stable DUT `alert=1`, conditional output check **pass**. This validates the
new live conditional-check path. Covered/wet stimulus checks after this rewire
and the two full fault/repair sequences remain pending.

Color reminder: **yellow S3 IO1+IO8 = light**, **blue IO4+IO9 = water**,
**orange IO6+IO10 = alarm drive**, **black GND = common ground**. Each signal
pair shares its own 6.8 kΩ series resistor; those resistors do not go to GND.
