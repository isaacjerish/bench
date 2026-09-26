# ParcelGuard: proposed clean demo build

Status: **planned, not wired or flashed**. User stepped away and requested
website work before receiving the full wiring batch. Current firmware and
`harness/current.yaml` still describe the earlier multi-sensor circuit.

## Behavior

A parcel box monitors light intrusion and water leaks. A covered light sensor
represents a closed lid. Opening it or wetting only the water-sensor comb
causes an LED alarm. Benchy observes all three used C6 GPIOs: light input IO1,
water input IO2, and LED output IO20.

## Planned wiring

Power off both USB boards before rebuilding. Use C6 3V3 for the sensor supply
rail and a single shared ground rail connected to C6 and S3 GND. The S3 remains
USB powered; do not join the boards' 3V3 outputs. Set the MPU aside for this
smaller build. All measured nodes are known 0–3.3 V.

| Signal row | Circuit | Permanent sensing branch |
| --- | --- | --- |
| L | Photoresistor from C6 3V3 to L; existing 10 kΩ from L to GND; C6 IO1 to L | L → 6.8 kΩ → separate LS row; S3 IO1 and IO8 both to LS |
| W | Water `+` to C6 3V3, `-` to GND, `S` to W; C6 IO2 to W | W → 6.8 kΩ → separate WS row; S3 IO4 and IO9 both to WS |
| A | C6 IO20 to A; A → 220–330 Ω → LED anode; LED cathode to GND | A → 6.8 kΩ → separate AS row; S3 IO6 and IO10 both to AS |

Use separate connected five-hole groups for L, LS, W, WS, A, AS, and each
LED leg. No sense-row resistor goes to GND: these are series taps, **not
voltage dividers**. Reuse the existing three 6.8 kΩ resistors, one 10 kΩ
photoresistor resistor, and the LED's 220–330 Ω resistor. Mark the three
signal rows so the sensor branch, DUT wire, and probe tap are easy to identify.

## Software prerequisites

- Add and compile a named S3 series-tap profile: P1 ADC IO1/digital IO8,
  P2 ADC IO4/digital IO9, P3 ADC IO6/digital IO10; ADC scale **1**, no divider.
  Preserve the earlier profile for reproducing past tests.
- Add C6 `parcel_guard` firmware with bounded light/water sampling and LED
  alert timing. Confirm thresholds from a real dark/bright and dry/wet baseline.
- Add a separate harness profile with all three new connections pending.
  Set current wiring only after user confirmation and flash the correct S3
  profile before interpreting readings.
- Direct ESP32 ADC measurements can saturate near the top of the rail; do
  not use this simple setup to claim calibrated supply measurements.

## Intended demo

1. Normal dark/dry box: reports agree with independent readings.
2. Light intrusion or leak: S3 observes the changed sensor voltage and LED
   drive transitions; the user observes the actual LED.
3. An intentionally false sensor report disagrees with the physical probe.
4. Agent repairs the code, flashes the enrolled C6, and repeats the same check.

Fixed taps cover these declared nodes. They do not discover arbitrary wiring,
measure current, or prove that the LED emits light merely from an output pin.
