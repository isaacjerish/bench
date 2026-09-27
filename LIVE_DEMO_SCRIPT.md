# Benchy live pitch — one wiring error, one software error

**Plan for 3–5 minutes, including upload time.** The faults are deliberately
seeded and labeled in source; every measurement and repair is real.

## Before the audience arrives

- Timing fault 3 is currently loaded; its 10 Hz output was measured. The
  combined wiring swap has **not been confirmed or measured yet**. Each
  fault and repair has already been rehearsed separately.
- For the combined setup: light uncovered, water dry. Unplug both USB cables;
  swap only the C6 IO1/IO2 jumper ends (light to IO2, water S to IO1). Leave
  every colored S3 branch, resistor, and the LED wiring in place. Reconnect.
  Have the agent capture both mismatches and the timing fault before filming.
- Expand the browser panel. Preview off, Live on, correct S3/C6 selected.
  Keep conditions steady for fresh readings. Start on **Design map**.
- The headline shows one issue at a time; **Signal taps** can show another
  failing check at the same time. Do not promise a two-item issue dashboard.

## Opening — 20 seconds

> “Your code compiles, the LED blinks, and your project is still wrong.
> Benchy gives an AI debugging agent access to measurements from the actual
> circuit, alongside its firmware and serial output. This parcel monitor
> detects an open lid or a leak. I've deliberately introduced one wiring
> mistake and one software bug. Let's find both and verify the repairs.”

Say this after the two-fault setup has actually been confirmed.

## Live walkthrough

| Where to go | What to do / say |
| --- | --- |
| **Design map + coverage + Assessment** | Point to S3 as the measuring board and C6 as the project. “These three permanent probe connections cover the signals this project uses. This is our declared wiring map; Benchy checks the signals at those connections.” |
| **Probes** | Show light voltage and dry-water voltage. “These values come from the independent S3 measurements.” Briefly point to the trends; hold the light steady during diagnosis. |
| **Serial monitor** | Show `light_mv`, `water_mv`, and raw output; optionally filter `PARCEL`. “This is what the controller says it sees. Compare that with the measurements: the light and water reports are reversed.” Use the actual values currently on screen. |
| **Signal taps** | Show D3 and the failing rate. “There's a second problem: 40 transitions in two seconds. That's ten full blinks per second; we intended two.” Ask the agent for its separate frequency measurement. |
| **Source** | Select `dut_examples/parcel_guard/config.h`, click **Refresh**. Show the intended IO1/IO2 assignments and the `SOFTWARE BUG DEMO` comment. Then select `parcel_guard.ino` to show the annotated 50 ms versus 250 ms half-cycle. “One fix belongs in the wiring. The other belongs in firmware.” |
| **Investigation** | Point to observed evidence, next check, and the timeline; click **Capture note** if useful. “We keep the evidence and the proposed next check together, so we can verify whether a change helped.” |
| **Saved captures** | Save `Both faults present`. Each save takes fresh measurements; wait for confirmation. “This records the physical readings, device output, wiring declaration, and local source hashes.” |

## The agent prompt

> “This circuit has more than one problem. Before changing anything, compare
> both sensor voltages with the device reports, measure the alarm frequency,
> and inspect the pin assignments and timing code. Report each independent
> issue with its evidence. Then guide the wiring repair, fix and flash the
> firmware, and remeasure every check.”

Run this in the connected Codex task. The source inspector is read-only;
the agent performs the code edit, build, and flash through its tools.

## Repair sequence — the strongest moment

1. **Fix the wiring first.** Unplug both USB cables; restore light to C6 IO1
   and water S to C6 IO2; reconnect. Agent remeasures. Save `Wiring repaired`.
   Show **Assessment + Signal taps** and say:
   > “The sensor readings now agree, but the alarm timing still fails.
   > Fixing one problem hasn't hidden the other.”
2. **Fix the software.** Agent selects fault 0, builds, and flashes the C6.
   Refresh **Source** to show the change. During compilation, briefly revisit
   **Investigation** and explain: “The measurements tell us what failed;
   the source helps explain why. The next measurement will test the repair.”
3. **Verify.** Agent measures the alarm at 2 Hz and checks both sensor reports.
   Show the fresh passing assessment and **8 transitions in two seconds**.
   Save `Both repaired`. Only announce success after those checks pass.
4. **Show the proof.** In **Saved captures**, choose `Both faults present`
   Before and `Both repaired` After. Highlight D3 **20/s → 4/s** and expand
   **Device output saved with these captures** for the sensor-report repair.
   Use `Wiring repaired` as the intermediate capture if useful. Point to
   **Inspect saved context** for source hashes; exports preserve evidence.

P3 voltage is a snapshot of a blinking signal: HIGH/LOW differences between
captures can be phase, not a fault. Use D3 rate and the frequency measurement.

## Closing — 10 seconds

> “One wiring mistake, one firmware bug, and measured proof of both repairs.
> Benchy connects the agent's code understanding to the signals on the bench.”

## Voice and scope

The **Talk through the fault** panel is optional and currently disabled on
this dashboard because its xAI key is not configured. Do not make voice the
critical path of the demo. Its tools are read-only; Codex handles firmware
changes. This prototype checks declared 0–3.3 V probe connections; it does
not automatically trace all wiring or prove that an LED emits light.

The existing captures `02 Inputs swapped` / `03 Inputs repaired` and
`04 Timing fault` / `05 Timing repaired` document the earlier **separate**
rehearsals. Label them as recorded evidence if you use them as a fallback;
do not present them as the new combined live run.
