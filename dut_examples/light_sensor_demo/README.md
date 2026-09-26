# Light sensor cross-check demo

This demo uses a kit photoresistor and one **additional 10 kΩ resistor**. It
runs at 3.3 V from the C6's USB-powered board and needs no servo supply. Do
not wire it until you identify the C6's GPIO1/IO1, 3V3, and GND labels.

```text
C6 3V3 --- photoresistor --- sensor row S --- 10 kΩ --- common GND rail
                                  |
                                  +--- C6 GPIO1 / IO1 (ADC input)
                                  +--- S3 P1 tip T / test row T

S3 GND ------------------------------- common GND rail --- C6 GND
```

Remove the LED and series resistor from T and disconnect C6 GPIO20 from T
before connecting the sensor row S to T. Keep the S3's original two-resistor
P1 ADC divider in place: T → 10 kΩ → M → 10 kΩ → GND. This adds a 20 kΩ
load to the sensor node, so this is a debugging demonstration, not a
calibrated light meter. C6 GPIO1 and S3 GPIO1 are pins on *different boards*;
the S3 GPIO1 remains connected only to divider midpoint M.

The C6 prints `LIGHT_MV <millivolts>` over USB. BenchOS compares that software
claim with the independently measured physical voltage at P1. Cover the
photoresistor and shine a light on it to change the signal. With this divider
orientation, brighter light should raise the sensor voltage. `DEMO_FAULT=1`
forces a false zero report while the real voltage can still change.

From the repository root, after wiring:

```sh
./scripts/flash_dut.sh light_sensor_demo <C6-port>
./scripts/python.sh -m benchos.cli --port <S3-port> light-compare --dut-port <C6-port>
```

Both boards stay USB-powered. Only known 0–3.3 V signals may reach P1.
Elegoo's [kit parts list](https://eu.elegoo.com/en-fr/products/elegoo-mega-2560-the-most-complete-starter-kit)
lists a photoresistor and 10 kΩ resistors. Espressif's
[C6 board pin table](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c6/esp32-c6-devkitc-1/user_guide.html)
identifies GPIO1 as ADC1_CH1; check the label on your actual C6 board.
