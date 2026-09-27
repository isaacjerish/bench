# Benchy instructions for Codex

Benchy provides real physical readings through an ESP32-S3. Firmware logs,
successful flashing, and serial messages do not prove the circuit works.

When debugging hardware:

1. State a hypothesis.
2. Choose the smallest physical measurement that tests it.
3. Call `measure_voltage`, `read_digital`, or `measure_frequency`.
4. Interpret the reading, including noise and measurement limits.
5. Change firmware only when evidence supports the change.
6. Reflash only when necessary, then remeasure.
7. Run the physical check and report the measured values.

Never turn a measurement probe into an output. P1 and P2 accept only known
0–3.3 V logic with common ground. Do not connect 5 V or unknown voltages to
either branch. The two 10 kΩ divider resistors load the measured net, so do
not assume they are safe to attach to a weakly pulled I²C line. Read the
declared `harness/current.yaml` before selecting a probe, and confirm physical
placement with the user when it could have changed. The servo uses a separate
5 V supply and common ground.
Avoid repeatedly flashing a board when one measurement could test the current
hypothesis. Prefer deterministic physical tests over visual guesses. A 250 ms
frequency window is only a quick estimate at 50 Hz; use 1000 ms for pass/fail.

## Dashboard agent boundary

For Codex conversations started from the local dashboard, never run a command
that uploads firmware to a device. The website exposes read-only physical
measurement tools to the agent. If an upload is needed, explain why and direct
the user to review the diff and use the dashboard's separate, explicitly
confirmed Build & flash action. Do not change physical wiring from software.
