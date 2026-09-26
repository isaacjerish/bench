# LED fallback demo

This gives BenchOS an easily visible DUT without a separate power supply.
The C6 stays powered over USB. It blinks an LED from GPIO20 at about 2 Hz.

```text
C6 GPIO20 ---- row T / BenchOS P1 tip ----[330 Ω]---- LED anode (+, long leg)
LED cathode (-, short leg/flat side) ------------------- common GND rail
C6 GND and S3 GND ------------------------------------ common GND rail
```

The resistor **must** be in series with the LED. The S3 P1 ADC divider remains
connected to T. Remove the servo signal lead before adding the LED, or leave
the unpowered servo disconnected entirely. Do not connect T directly to 3V3
or GND. `physical_tests/led_blink.yaml` checks for a roughly 2 Hz physical
signal. A successful serial log does not prove the LED or wire is connected.
The firmware's optional `pulse_us` diagnostic will report 0 for this slow
blink because its 60 ms pulse timeout is tuned for servo pulses; the 2 Hz
edge-count test is the relevant measurement here.

From the workspace root, compile and upload with your detected C6 port:

```sh
arduino-cli compile --config-file outputs/benchos/scripts/arduino-cli.yaml --fqbn esp32:esp32:esp32c6:CDCOnBoot=cdc outputs/benchos/dut_examples/led_demo
arduino-cli upload --config-file outputs/benchos/scripts/arduino-cli.yaml --fqbn esp32:esp32:esp32c6:CDCOnBoot=cdc -p /dev/cu.usbmodemYYYY outputs/benchos/dut_examples/led_demo
```

From `outputs/benchos`, run:

```sh
./scripts/python.sh -m benchos.cli test physical_tests/led_blink.yaml
```
