# ESP32-C6 servo signal demo

Edit [`config.h`](config.h) to match the GPIO exposed on your exact C6 board.
The default wire is GPIO20. Firmware emits a steady 50 Hz control signal with a
1,500 µs high pulse, which centers many hobby servos. It uses Arduino-ESP32 3.x
LEDC APIs and does not need a servo library.

The three fault modes are selected by `DEMO_FAULT` in `config.h`:

1. `1`: firmware drives GPIO21 while the servo and BenchOS remain on GPIO20.
2. `2`: configured output has zero duty, so the line stays LOW.
3. `3`: 312 Hz output, far outside the 45–55 Hz physical test.

For visible movement after safe external power is connected, set
`DEMO_SWEEP = true` in `config.h` and reflash. The C6 then alternates 1000 and
2000 µs pulses every two seconds, while hardware LEDC maintains the 50 Hz
signal. Leave it `false` for a stable 1500 µs physical timing test.

**Electrical hookup:** C6 GPIO20 to servo signal and the BenchOS P1 tip.
Connect C6 GND, S3 GND, and external servo supply GND together. Power the
servo from a suitable **separate 5 V source**. Do not power it from an ESP32
GPIO or the ESP32 3.3 V rail. Keep the P1 tip on 0–3.3 V logic only.
