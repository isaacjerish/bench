# Benchy — four-person live demo

**Aim for 4–6 minutes, with extra room for the AI response and firmware build.**
All software actions happen in the website. No terminal or separate Codex
window is needed; Person 2 handles the two physical jumper corrections.
This is a disclosed two-fault exercise: one physical sensor-wire swap and one
firmware timing bug. Measurements, code correction, upload, and remeasurement
are real. Do not announce a result until fresh evidence supports it.

## Roles

| Person | Role | Hands-on job |
| --- | --- | --- |
| 1 — Story | The ECE student / TA problem and opening | Introduce the problem; keep the story moving during waits. |
| 2 — Hardware | Explain the two boards and handle wiring | Keep sensors steady; restore the two C6 input jumpers. |
| 3 — Investigator | Drive the website and ask Benchy | Type prompts, show source/diff, run the confirmed upload. |
| 4 — Verifier | Explain independent evidence and close | Save captures, show serial/tap comparisons, verify the repair. |

## Before recording — do this off camera

1. Open `http://127.0.0.1:8765/` on the laptop. **Preview off**, **Live on**,
   correct S3 and C6 selected. Keep both USB cables connected.
2. Software fault: `dut_examples/parcel_guard/config.h` must set
   `PARCEL_GUARD_FAULT 3`, and the C6 must actually be running that build.
   The latest verified setup already does. Local source alone is not proof:
   Benchy measured the alarm at **10 Hz**; healthy target is **2 Hz**.
3. **Current setup: the inputs are already swapped and both faults are measured.
   Leave the wires as they are for filming.** To recreate this setup later: uncover the photoresistor; dry the water sensor.
   Unplug **both USB cables**. At the **C6 board only**, swap the jumper ends
   in **IO1 and IO2**: photoresistor to **IO2**, water sensor **S to IO1**.
   Leave all yellow/blue/orange S3 wires, resistors, grounds, and LED wiring
   exactly as they are. Reconnect USB and wait at least five seconds.
4. In **Debug with Benchy**, use the diagnosis prompt below. Confirm it has
   fresh evidence for the reversed sensor readings **and** wrong alarm rate.
   If one is absent, resolve that before saying there are two faults.
5. A website capture named **`01 Both faults verified`** is already saved
   (22:43 local: P1 2.337 V, P2 0 V, D3 20 transitions/s). For a new recording,
   in **Saved captures**, name a fresh capture `01 Both faults verified` and
   click **Save new capture ↗**. Wait for success. Do not replace fresh
   evidence with an old capture during filming.
6. Voice has been checked in this browser. In a noisy room, click **Mute
   microphone** after your question while Benchy investigates and reads back
   the result. Click **Unmute microphone** for a follow-up. Typed chat is the
   fallback. Stop voice before switching to typed prompts; otherwise
   typed messages route through the voice conversation. Keep `.env` and keys
   off screen. Use a wide browser view so tables and code fit.

## 1. Opening — Person 1 (about 30 seconds)

**Screen:** Top of the workspace, hardware connections and Assessment.

> “We're ECE students. We've all spent hours staring into a forest of jumper
> wires, trying to work out whether a bug lives in our code or our circuit.
> As an ECE 4180 TA, I see how much time that takes from helping students.
> Benchy gives an AI debugging agent physical measurements alongside the
> firmware and serial output. Today, we've deliberately planted one wiring
> mistake and one software bug. Let's find both and prove the repairs.”

The actual TA should speak that sentence; otherwise say “One of our teammates
is an ECE 4180 TA.”

## 2. What is being measured — Person 2 (about 35 seconds)

**Physical:** Point to the C6, S3, photoresistor, water sensor, and LED.
**Clicks:** Show the pin-coverage table, then **Probes**.

> “This is a parcel monitor: light means the lid is open, water means a leak,
> and the LED signals an alert. The C6 runs the project. The separate S3
> measures its signals through permanent input probes. Yellow follows light,
> blue follows water, and orange follows the alarm output. We can inspect
> those signals without moving the probes between tests.”

Keep the light uncovered and water dry through diagnosis. Explain that the
coverage table is a wiring declaration, not automatic wire recognition.

## 3. Let the agent investigate — Person 3 (about 45–75 seconds)

**Click:** **Debug with Benchy**. Paste and send:

```text
This parcel monitor should alert when the lid is open or water is detected,
with a 2 Hz LED blink. Its behavior is wrong. The S3 sensor-side taps and alarm
tap have stayed in place. Read the declared harness, take fresh independent
measurements, compare both sensor voltages with the C6 reports, and measure
the alarm frequency over 2000 ms. Inspect the source and report every
independent issue with its evidence. Do not edit or flash anything yet.
```

> “We give it the intended behavior and a way to measure. It compares what
> the controller reports against a separate instrument, then checks the
> relevant code. We'll fix the problems one at a time so neither can hide
> the other.”

**While it works:** Visit **Serial monitor** and point to `light_mv` and
`water_mv`. Return to chat for the measured explanation. If using voice, speak
an equivalent request and wait for its investigation to finish.

## 4. Show both failures — Person 4 (about 40 seconds)

**Clicks:** **Probes → Serial monitor → Signal taps → Source**.

> “The real light signal and water signal don't match their reported sensor
> names. That is evidence for the input wiring problem. Separately, the alarm
> is switching at ten cycles per second when it should be two.”

- Use **actual live numbers**; ambient light changes. Dry water is normally
  near zero. With the input swap, the high light voltage appears under the
  water report. One sensor swap is one wiring mistake.
- D3 counts **both edges**: roughly **40 transitions in 2 seconds = 20/s**,
  which corresponds to **10 full cycles/s**. Healthy: roughly **8 in 2 s**.
- **Source:** choose `dut_examples/parcel_guard/config.h`. Show the correct
  IO1/IO2 assignments and the explicit `SOFTWARE BUG DEMO` comment.
  The sketch's timing line explains 50 ms versus 250 ms per half-cycle.
- **Investigation** keeps the evidence/next-check/timeline. The main headline
  may show just one failing check; read the separate taps and chat results.

## 5. Repair only the wiring — Person 2 (about 30–45 seconds)

**Physical sequence:**

1. Unplug **both USB cables**.
2. At the C6, put the **photoresistor jumper back into IO1**.
3. Put the **water sensor S jumper back into IO2**.
4. Leave every S3 probe/resistor and the LED connection untouched.
5. Reconnect both USB cables. Keep light uncovered and water dry; wait five
   seconds. Click **Refresh ports and source** if a port changed.

Person 3 sends:

```text
I restored photoresistor to C6 IO1 and water sensor S to C6 IO2. Both boards
are powered again; the S3 taps are unchanged. Remeasure both sensor comparisons
and the alarm frequency. Do not edit or flash yet.
```

Person 4 saves **`02 Wiring repaired`** in Saved captures.

> “Now the sensor readings agree, but the alarm timing still fails. Correcting
> the wiring hasn't hidden the software bug.”

Only say this after measurements establish both parts.

## 6. Repair firmware from the website — Person 3 (about 45–90 seconds)

**Click:** **Debug with Benchy**. Send:

```text
Prepare the smallest firmware correction for the remaining timing fault.
Set PARCEL_GUARD_FAULT to 0 in dut_examples/parcel_guard/config.h, keeping the
correct pin assignments. Explain the change and leave it ready for my review.
Do not upload firmware; I will use Build & flash.
```

1. Expand **Review local code changes**; click **Refresh diff**. Show `3 → 0`.
2. In **Source**, choose `config.h` and click **Refresh** if needed.
3. Back in chat, click **Build & flash…**. Check the target says **ESP32-C6**
   via its `esp32c6` board profile, sketch `dut_examples/parcel_guard`, and
   enrolled DUT identity. It must not be the S3.
4. Confirm the restored wiring matches the declaration, check the review box,
   type **`FLASH`**, and click **Build and upload firmware**.
5. Wait for the result. Click **Ask Benchy to review the result ↗**. Ask:

```text
Verify the repair now using fresh S3 measurements: compare both sensor inputs
with the DUT reports and measure the alarm frequency over 2000 ms. An upload
message is not proof. Report anything that still fails.
```

**Person 1 fills build time:**

> “The agent can prepare a correction, and the operator reviews the change
> and upload target. The interesting part is what comes next: we measure
> again, because a successful upload doesn't prove the circuit works.”

## 7. Prove it and close — Person 4 (about 40 seconds)

**Clicks:** **Signal taps → Saved captures**.

1. Confirm fresh **2 Hz** measurement, matching sensor reports, and about
   **8 transitions / 2 seconds** on D3 while the alert is active.
2. Save **`03 Both repaired`**.
3. Select **Before: `01 Both faults verified`**, **After: `03 Both repaired`**.
4. Show D3 changing **20 transitions/s → 4 transitions/s**. Expand
   **Device output saved with these captures** to show corrected reports.
   Use `02 Wiring repaired` to explain the intermediate state if useful.

> “One wiring mistake, one firmware bug, and independent measurements showing
> both repairs. Benchy brings the agent's code understanding to the signals
> on the bench—so a student or TA can spend less time guessing and more time
> building.”

**Optional physical ending:** With water still dry, cover the photoresistor
fully with an opaque object. The LED should stop. Uncover it; it should resume
at 2 Hz. Only add this after the main verification passes.

## Optional photo moment — 15–30 seconds

Use **Visual → Start phone photo link**, scan the QR from the same Wi-Fi, and
send a clear board photo. Ask a question in chat to include it. Gemini makes a
visual description for Codex; the probes establish electrical facts. The
phone session expires after ten minutes. Test actual phone Wi-Fi access before
filming. Skip this segment if it interrupts the main story.

## Recovery cues

- **Room conversation interrupts voice:** click **Mute microphone**. You can
  still type into the voice conversation and hear its answer. Benchy also
  pauses microphone input during tool work and the measured readback.
- **Voice stalls:** stop voice and use the typed prompts above.
- **A port disappears:** reseat its data cable, then refresh ports. Never flash
  a guessed device. Pause narration until both selected identities are right.
- **Reading says stale/unverified:** hold light/water steady, keep serial
  running, and sample again. This is not a passing result.
- **No timing fault:** check live frequency and actual firmware before setup;
  fault 3 may already have been repaired. Do not seed it mid-demo silently.
- **Upload fails:** inspect the result; don't repeatedly click upload. Source
  state and running firmware can differ until upload and remeasurement pass.
- **Past captures:** `02 Inputs swapped`/`03 Inputs repaired` and
  `04 Timing fault`/`05 Timing repaired` are recorded separate rehearsals.
  Clearly label them as past evidence if used as fallback.
- **P3 voltage jumps between high and low:** normal snapshot phase for a
  blinking signal. Compare frequency/edge rate instead.

## Ready check

- [x] Updated website and typed Codex → MCP → real S3 measurements verified.
- [x] Live sensor comparisons, serial, source, and saved captures working.
- [x] Deliberate 10 Hz fault measured; fresh preflight capture saved.
- [x] Flash target review resolves the enrolled C6; prior upload path rehearsed.
- [x] xAI session token and Gemini image-description API verified.
- [x] User exercised microphone/audio. Final website voice → Codex → physical
  tools → spoken response checked with microphone muted and a typed question;
  it reported both swapped inputs and the approximately 10 Hz alarm. Readable
  transcript, caption coalescing, mute control, and stop control verified.
- [ ] Actual phone upload checked, if included in the video.
- [x] Both faults measured together after the physical input swap and reseating.
  Saved `Reseated input swap — combined rehearsal`: light 2.299 V vs reported
  ~0.002 V; dry water 0 V vs reported ~2.340 V; D3 40 transitions / 2 s.
- [ ] End-to-end repair through the new website flash dialog rehearsed.

The unchecked items still need a human rehearsal if included. The new flash
dialog and its target/confirmation handling were checked, but a real upload
through that dialog was not repeated in this session; the deliberately faulty
firmware and swapped inputs remain ready for filming. The underlying upload
and repaired 2 Hz circuit were verified in earlier individual rehearsals.
