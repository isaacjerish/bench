# BenchOS build checklist

- [x] Inspect Python, Arduino CLI, serial ports, and workspace.
- [x] Build, compile, and flash the ESP32-S3 lab controller firmware.
- [x] Build and test the Python serial client and CLI; live `PING` passed.
- [x] Verify P1 at 3.261 V and 0.000 V through the CLI; both physical checks passed.
- [x] Expose the tested client through local MCP and register it with Codex.
- [x] Build and compile the ESP32-C6 servo example.
- [x] Flash C6 and verify a real 50 Hz, 1500 µs signal through P1 and MCP.
- [x] Demonstrate a physical fault/repair cycle (312 Hz FAIL → 49.95 Hz PASS).
- [x] Build and physically verify a 2 Hz LED fallback without external power.
- [x] Confirm the LED is visibly blinking and remeasure with it attached: 2.0 Hz PASS.
- [x] Physically exercise all three fault variants; each produced a failing P1 reading.
- [x] Prepare and compile a 3.3 V photoresistor DUT and C6/S3 voltage comparison.
- [ ] Wire the photoresistor demo and validate normal and faulty readings.
- [ ] Hook up the SG90 and verify physical motion after identifying the Elegoo
      power module input/output labels and power source.
