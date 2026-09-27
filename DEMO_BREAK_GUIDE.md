# Benchy demo — what to break

For the current light + water + LED circuit. Healthy behavior is tested;
**rehearse these deliberate wiring faults once before filming.**

For the recommended two-fault video and exact UI sequence, use
[the video walkthrough](DEMO_VIDEO_WALKTHROUGH.md).

## Before every change

**Unplug BOTH ESP32 USB cables before breaking or restoring wiring.** Reconnect
both afterward and wait 5 seconds. Do **one fault at a time**, restoring it
before the next. Keep all S3 probe wires and 6.8 kΩ resistors in place.
Never join power to ground or move anything to 5 V.

Start with the water sensor dry and photoresistor uncovered: LED should blink.
Cover the photoresistor: LED should stop. Uncover it again.

## 1. Swap the sensor inputs — best main demo

- **Break:** At the **C6 board only**, swap the two jumper ends plugged into
  **IO1 and IO2**. The photoresistor now goes to IO2; water sensor S goes to IO1.
  Keep the other ends, sensor power, and all Benchy connections untouched.
- **Show:** Leave light uncovered and water dry. The LED may still blink;
  the bug is that the C6 is interpreting the sensors backward.
- **Benchy evidence:** Its light probe should stay high and water probe near
  zero, while C6 serial reports low `light_mv` and high `water_mv`. Two
  mismatches point toward swapped inputs or incorrect firmware pin mapping;
  source inspection helps distinguish them.
- **Restore:** Photoresistor jumper → **C6 IO1**; water S jumper → **C6 IO2**.
  Remeasure: both sensor reports should agree with Benchy again.

## 2. Disconnect the LED's ground — output versus actual load

- **Break:** Disconnect only the **LED short leg / flat-side connection to
  the blue ground rail**. If its leg goes directly into the rail, lift that
  leg out. Keep the loose end isolated.
- **Show:** Light uncovered, water dry, but the LED stays dark. Tell the agent
  “The LED is physically off.”
- **Benchy evidence:** The C6 should still request an alarm and Benchy should
  measure about **2 Hz** at IO20. That narrows the issue to the LED/resistor/
  return path. **Benchy cannot see emitted light or pinpoint the open contact;
  the dashboard may still show passing electrical checks.**
- **Restore:** Reconnect the LED's short-leg connection to blue ground.

## 3. Remove power from just the photoresistor

- **Break:** Disconnect only the photoresistor's connection to the **red 3V3
  rail**; lift that leg if directly inserted. Keep its other leg, the 10 kΩ
  resistor, and all sensor/probe wires connected. Isolate the loose end.
- **Show:** Water dry, photoresistor uncovered, but the LED stays off.
- **Benchy evidence:** The light reading should remain near zero even in
  light. Both boards can agree on that wrong physical condition, so a green
  comparison alone does not establish a working sensor. Tell the agent the
  sensor is uncovered; it should investigate the light sensor's power/path.
- **Restore:** Reconnect that photoresistor connection to red 3V3.

## Film this sequence

**Working → friend introduces fault → ask Benchy → show measurements → restore
the wire → remeasure.** Save “Broken” and “Repaired” captures in the dashboard.

Prompt: “This circuit is behaving incorrectly. Use Benchy's live measurements,
serial output, and source to diagnose it. Tell me the next physical fix, then
verify after I make it.” Report the visible symptom without revealing the
deliberately moved wire. These wiring faults need a physical repair, not a reflash.
