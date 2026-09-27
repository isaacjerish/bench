# Benchy — story-led, four-person demo video

**Target: 3–4 minutes edited.** Allow extra time when recording for real AI
responses and firmware builds. The story is: **a familiar hardware disaster →
meet Benchy → describe a broken project → investigate together → fix → prove it.**
All software actions stay in the website. Keep technical details in the crew
notes below; the spoken demo should sound like someone asking for help.

## Cast

| Person | Job |
| --- | --- |
| 1 — Builder | LED/explosion hook, introduce Benchy, closing line. |
| 2 — Student / TA | Explain the problem and example project; handle the wire repair. |
| 3 — Operator | Add photos, talk/type to Benchy, review and upload the code change. |
| 4 — Narrator / verifier | Explain what Benchy is doing and show that the repair works. |

The actual ECE 4180 TA should deliver the TA sentence. Otherwise say “One of
our teammates is an ECE 4180 TA.”

## 1. Project overview / intro — about 45–55 seconds

### Hook — Person 1, about 8 seconds

**Picture:** Use the existing clip of someone connecting an LED, followed by
the exaggerated explosion edit. The explosion is a visual/sound effect.

> “It's one LED. How hard could it be?”

**Explosion. Beat. Cut to the builder looking at the laptop.**

> “Maybe it's the code.”

**Title card: BENCHY.**

### The problem — Person 2, about 20 seconds

**Picture:** A real breadboard, tangled jumpers, code on a laptop, someone
following a wire with their finger.

> “We're ECE students. We've spent hours tracing jumper wires, checking
> connections, and changing code—just to figure out where a problem starts.
> As an ECE 4180 TA, I see students lose that same time. If I could diagnose
> their circuits faster, I could help a lot more of them.”

### What Benchy does — Person 1, about 20 seconds

**Picture:** Benchy beside the project; close-up of its probe connections;
then the website with real readings.

> “Meet Benchy: an AI debugging partner connected to your circuit. Tell it
> what you're building, show it the board, and connect probes to the signals
> you want checked. Benchy can measure those signals, investigate the code,
> and help you get the project working. Our prototype focuses on low-voltage
> breadboard projects like this one.”

**On-screen line:** “Describe → Measure → Repair → Verify”

This establishes who it serves, the debugging problem, why it matters, what
it does, and the prototype's scope before the example begins.

## 2. Example demo — about 2–2½ minutes, with waits trimmed

### A. Describe the project and add a photo — Persons 2 and 3

**Picture:** The parcel monitor and its rapidly blinking LED. Show the water
sensor is dry. Keep the light sensor uncovered throughout the investigation.

**Person 2:**

> “This is a parcel monitor. It should alert us if the box opens or water
> gets in. Right now it's reporting a leak even though the sensor is dry,
> and the alarm is blinking too fast. We've planted one wiring mistake and
> one software bug. Let's ask Benchy to find them.”

**UI:** Open **Debug with Benchy → Add photos / use camera**. Choose a clear
photo of the current board, with a second close-up if needed. Show the image
thumbnail. Paste this description and click **Send to Benchy ↗**:

```text
This is our parcel monitor. The light sensor detects an open lid, the water
sensor detects a leak, and the LED should blink twice per second whenever
either happens. The water sensor is dry and the light sensor is uncovered,
but it reports a leak and the LED flashes too fast. I've attached the board
photo. The probes are connected as recorded in the workspace, at the sensor
signals and alarm output. Use fresh measurements and the code to find what's
wrong. Explain it simply, and don't change anything yet.
```

**Person 4, over the upload / investigation:**

> “We describe the project in normal language and add photos for context.
> Gemini Robotics ER describes what's visible in those photos. Benchy's
> probes supply the electrical measurements, and Codex uses that evidence
> alongside the firmware to investigate.”

**Optional shot:** Use **Visual → Start phone photo link** and scan the QR to
send the photo from a phone. Choose this route only after rehearsing that
phone on the actual Wi-Fi; direct image attachment is the shorter sequence.
Use an image of the real current setup.

### B. Have a conversation — Person 3

**UI:** After the first answer finishes, click **Start voice conversation**.
Allow the microphone if prompted. Ask:

> “Can you check the sensor signals and the alarm, and tell me what I should
> fix first?”

**Person 4:**

> “You can type to Benchy or talk it through. Grok powers the voice
> conversation, while the debugging agent checks the project and takes
> measurements through the probes.”

**Picture:** Let the actual response play. Briefly cut to **Probes** and
**Signal taps** while it works, then return to the conversation. Use the real
answer; do not script a fabricated model response.

**Person 4, only after the findings are established:**

> “It found two separate problems: the sensor inputs are swapped, and the
> firmware is driving the alarm too fast.”

The audience only needs the meaning. “Ten blinks a second instead of two” is
plenty; don't narrate GPIO numbers, edge counts, or ADC details.

### C. Correct the wiring — Person 2

**Picture:** A short close-up of Person 2 unplugging power, restoring the two
sensor jumpers at the project board, then reconnecting. Exact order is in the
crew notes below. The colored Benchy probes stay attached.

**Person 2:**

> “Benchy tells us which connections to correct. We move the two sensor
> wires; the probes stay in place.”

**Person 3, through voice or chat:**

> “I've corrected the sensor connections. Check them again, and see whether
> the alarm still needs fixing. Don't change the code yet.”

**Picture:** Real follow-up result; the false leak is gone, but the LED still
blinks too quickly. Save the intermediate capture if useful for the edit.

### D. Let Benchy repair the firmware — Persons 3 and 4

**Person 3, through voice or chat:**

> “Fix the firmware so the alarm blinks twice per second. Keep the sensor
> connections unchanged, and show me the code change before uploading.”

**UI:** Stop voice after the response so filming doesn't capture room chatter.
Open **Review local code changes → Refresh diff**. Briefly show the change
and the clearly labeled demo bug in **Source**. Return to **Build & flash…**,
review the project board, check the wiring confirmation, type **FLASH**, and
click **Build and upload firmware**.

**Person 4:**

> “Benchy prepares the firmware fix. We review it and approve the upload,
> and it builds and flashes the project board from the same website.”

**Picture:** Actual upload progress and result. Trim the wait with a visible
“Build and upload — sped up” label if needed. During the wait, a quick cut to
**Serial monitor** can show that the device's own reports are also available.

### E. Verify the repair — Persons 3 and 4

**UI:** Click **Ask Benchy to review the result ↗**. Ask:

> “Check the real circuit again. Do the sensor readings agree now, and is
> the alarm blinking twice per second?”

**Picture:** Actual measured response, visibly slower LED, then
**Saved captures** showing the before/after evidence.

**Person 4, after fresh verification passes:**

> “The sensor reports now match the measurements, and the alarm is back to
> two blinks a second. Benchy checked the physical result after the upload.”

**Physical payoff:** With the water sensor dry, cover the light sensor with
an opaque object. The LED stops. Uncover it; the slower blink returns.
Keep this shot if it behaves as verified.

## 3. Closing — Persons 2 and 1, about 15 seconds

**Person 2:**

> “For students, that's less time lost tracing wires. For a TA, it means
> getting to the next student sooner.”

**Person 1:**

> “Benchy: an AI debugging partner that can measure what it's trying to fix.”

**End card:** BENCHY · Describe. Measure. Repair. Verify.

---

## Crew notes — do not read these aloud

### Current starting state

At the last verified rehearsal, both faults were already in place:

- The photoresistor goes to **C6 IO2**, and water **S goes to C6 IO1**.
- The source and running C6 use `PARCEL_GUARD_FAULT 3`: an intentional
  10 Hz timing fault. Healthy behavior is 2 Hz.
- Keep yellow/blue/orange S3 probes, their resistors, grounds, and LED wiring
  untouched. Leave light uncovered and water dry to expose both faults.
- Last saved baseline: **01 Both faults verified**, September 26 at 22:43
  local; light 2.337 V, water 0 V, alarm 20 transitions/s (10 full cycles/s).
  This is historical evidence. Take a new capture for each actual recording.

### Exact physical repair during scene C

1. Unplug **both ESP32 USB cables**.
2. At the **C6 board only**, put the **photoresistor signal jumper into IO1**.
3. Put the **water sensor S jumper into IO2**.
4. Leave all S3 probe branches and the LED connection in place.
5. Reconnect both USB cables. Keep light uncovered and water dry. Wait five
   seconds, then refresh the website's ports if necessary.

The person fixes the physical wires. Benchy diagnoses and guides that action;
it cannot physically move a jumper.

### Firmware and upload specifics for the operator

- The intended small demo repair is `PARCEL_GUARD_FAULT 3 → 0` in
  `dut_examples/parcel_guard/config.h`, preserving LIGHT_GPIO 1,
  WATER_GPIO 2, and ALERT_LED_GPIO 20. The code explicitly labels this as a
  seeded demonstration bug. Do not hide that if the code appears on screen.
- Review **Source** and **Review local code changes** before the upload.
- The flash target must be the enrolled **ESP32-C6**, profile containing
  `esp32c6`, sketch `dut_examples/parcel_guard`; never the S3 instrument.
- The dialog requires a reviewed wiring declaration and typed `FLASH`.
  Scene C restores the real wiring to that declaration before this step.
- Flashing success alone does not establish repair. Ask for fresh sensor
  comparisons and a 2000 ms alarm-frequency measurement afterward.
- Dry water should report near zero. Light varies with the room.
  Healthy alarm: about 2 Hz or 8 digital transitions in two seconds.

### Before/after captures and screen coverage

Save **01 Both faults verified**, **02 Wiring repaired**, and
**03 Both repaired** at the corresponding stages. In **Saved captures**, select
01 as Before and 03 as After. Expand **Device output saved with these captures**
if useful. Use actual readings; don't use an old healthy capture as the live
result of this recording.

The story naturally covers the main UI: Visual/attachments, chat, voice,
probes, signal taps, source/diff, upload, and saved evidence. Show Assessment
and pin coverage in the opening workspace shot. Use Serial monitor and the
Investigation evidence as short supporting shots during real waits. No need
to explain every panel.

### Recording checks and honest product wording

- **Preview off; real boards selected; Live on.** Keep the browser wide and
  `.env`/credentials out of frame. Don't change wiring with power connected.
- Voice and real measurement delegation were verified. In a noisy room,
  **Mute microphone** while the answer plays; **Unmute microphone** for the
  next question. Stop voice to return typed messages directly to Codex.
- Gemini image description worked in an API check; the actual circuit-photo
  upload path still needs rehearsal with the chosen picture. A photo gives
  visual context, not proof of continuity, voltage, or an exhaustive schematic.
- Call it **Gemini Robotics ER for visual context**, not a custom model trained
  specifically on our circuit. Grok provides voice; typed debugging normally
  goes to Codex. A typed message during a live voice session goes through that
  voice conversation.
- The latest website flash dialog's target and confirmation handling were
  checked. A real repair upload through that new dialog still needs rehearsal.
  Earlier uploads and the individually repaired 2 Hz circuit were verified.
- Cut waiting time, with a label when speeding up. Keep the actual answers,
  failures, approval, and successful measurements from this run.
- If a check fails, keep investigating before filming a success claim. The
  goal is a clear real repair, not a promise that Benchy can debug every circuit.
