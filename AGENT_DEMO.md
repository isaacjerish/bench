# Live agent demo

## Preparation

1. Flash the S3 lab controller and validate `PING`, 3.3 V, and ground through
   the plain CLI using the README steps.
2. Register the local MCP server with Codex and start a fresh Codex task.
3. Flash the C6 servo example with `DEMO_FAULT = 0`. Connect the C6 GPIO20
   signal to P1 tip, share ground, and connect servo power only to a suitable
   separate 5 V source.
4. Run `./scripts/python.sh -m benchos.cli --log measurements.jsonl test physical_tests/servo_signal.yaml`.
   The frequency must be 45–55 Hz and the high pulse 900–2100 µs.

## Blind fault demonstration

Set `DEMO_FAULT` in `dut_examples/servo_demo/config.h` to 1, 2, or 3, flash,
and avoid telling Codex the number. Leave physical wiring unchanged. Then ask:

> The servo is not working. Diagnose the system and fix anything you can in
> software. Use BenchOS tools to verify hypotheses against the real circuit.
> Do not assume a software command succeeded physically; measure the result.
> Run the physical servo signal test after each important change.

Expected observations:

| Fault | Physical evidence | Likely fix |
|---|---|---|
| Wrong software pin | P1 has 0 Hz even though serial says GPIO21 configured | Drive wired GPIO20 |
| Silent output | P1 is LOW and 0 Hz even though LEDC initialized | Restore nonzero duty |
| Wrong frequency | P1 reads about 312 Hz | Restore 50 Hz |

Record each attempt in `measurements.jsonl`. The meaningful finish line is a
physical PASS, including a measured pulse width, after the last flash.

If no suitable separate servo supply is available, this remains a complete
**electrical signal** demo: leave the signal on P1 without attaching a motor
and ask Codex to debug
the failed physical PWM test. A two-wire DC motor needs an H-bridge and a
separate, driver-specific wiring plan; it must never be wired to the servo
signal or to an ESP32 GPIO directly.
