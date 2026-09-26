# Plant Sentinel: multi-sensor Benchy demonstration

## Product behavior

A tabletop planter monitor combines four independent observations:

| Input | Why it belongs in the design | Current connection |
| --- | --- | --- |
| Photoresistor | Tracks whether the plant receives light | C6 IO1 and S3 P1 on `LIGHT_SENSE` |
| MPU-family motion sensor | Detects a tipped or knocked-over planter | C6 IO5/IO7 I²C; S3 P2 on VCC and IO8/IO9 on SDA/SCL |
| DHT11 | Reports ambient temperature and humidity | Planned C6 digital input; exact module labels to verify |
| Water-level/leak sensor | Detects water in the saucer or a reservoir | C6 IO2 ADC; S3 P3 independently samples the output |

An LED gives a visible alert for a dry/overfull saucer, poor light, or a
tipped planter. Firmware emits one structured `SENTINEL` report per cycle:
measured values, sensor health, active alerts, and its build identity. A
sensor read failure must remain distinct from a valid dry/level reading.

## Benchy evidence

The dashboard stays design-neutral. The harness declares which nets the
probes touch and their safe ranges. This demonstration uses independent S3
measurements to check claims from the C6:

- P1 measures the real light-sense voltage while C6 reports its ADC value.
- P2 measures MPU VCC; IO8/IO9 count real SDA/SCL transitions.
- P3 measures the water sensor's analog output through its own 10 kΩ sense
  branch. It measured 0.000 V dry and 0.833–0.897 V with the comb wet.
- The C6 serial monitor captures sensor errors and reports; source and flash
  evidence identify local files and build artifacts separately.

## Fault story for judging

1. **Water reads dry while the tray is wet.** The C6 report is wrong; an S3
   voltage probe on the sensor output shows a changed electrical level. This
   separates software scaling/reporting from sensor power or wiring.
2. **Motion sensor disappears while its 3.3 V supply is present.** The C6
   reports an I²C error, P2 confirms supply, and IO8/IO9 show which declared
   bus branch has stopped moving. Benchy asks for a specific contact check.
3. **The alarm LED stays dark despite an alert.** This is visible to a person;
   Benchy needs a probe moved to the LED drive net before it can claim to
   measure the output timing independently.
4. **DHT11 times out or returns a bad checksum.** Firmware distinguishes this
   from a real humidity value; a movable S3 digital probe can check whether
   data pulses reach the C6 pin. A failure at the sensor and a missing wire
   may need additional placement measurements to distinguish.

Faults should be introduced as reversible open wires or selectable firmware
faults. Do not short supply rails. Restore every fault and demonstrate
recovery with fresh measurements.

## Current wiring and next expansion

The photoresistor, MPU, water sensor, and C6 IO20 LED branch are user-declared
connected. The two-pin unmarked buzzer remains disconnected. The 3-pin DHT11
breakout remains disconnected until its pin order is identified from clear
front/back photos. The current three-sensor design is enough to validate
cross-source measurements and deliberate faults before adding DHT11.

The wet threshold in the current sketch is 500 mV, between the observed dry
and wet P3 values. Confirm it against the C6's own IO2 ADC report after flash;
the S3 and C6 ADCs may disagree in absolute calibration.
Do not connect the SG90 or HC-SR04 yet: their 5 V power and echo/servo paths
need a separate, verified supply and level shifting before they join this
3.3 V breadboard.
