# MPU family motion demo

The blue breakout in the supplied photos is marked `MPU-9250/6500/9255`.
That is a family marking, not a confirmed chip ID. The serial log reports its
I²C address and `WHO_AM_I` value, then includes the ID with every acceleration
reading in g so the dashboard can identify it even after startup.

With both boards disconnected from USB, wire the MPU breakout to the C6:

| MPU pin | Connect to |
| --- | --- |
| VCC | C6 3V3 |
| GND | Shared GND rail |
| SDA/SDI | C6 GPIO5 / IO5 (current build; IO6 is obstructed) |
| SCL/SCLK | C6 GPIO7 / IO7 |
| ADO/SDO | Shared GND rail (address 0x68) |
| NCS | C6 3V3 (select I²C) |

Leave EDA, ECL, INT, and FSYNC unconnected. **Use 3.3 V only**: the exact
breakout input rating is not known, and the MPU-9250 chip's VDD maximum is
3.6 V. Do not connect the Elegoo 5 V or 9 V power to this board. The current
photoresistor circuit may stay wired to C6 GPIO1 and BenchOS P1 while trying
the IMU. Do not move P1 to an I²C wire while it is still connected to the
photoresistor divider.

GPIO5 is a C6 boot strapping pin. This particular board booted and answered
over I²C with SDA on IO5, but if a later boot fails, move SDA to another free
exposed GPIO and update `config.h` before reflashing.

After confirming the C6 exposes GPIO5 and GPIO7, compile and flash:

```sh
./scripts/flash_dut.sh imu_demo /dev/cu.usbmodemYYYY
```

Open C6 serial at 115200 baud. `IMU_FOUND` followed by changing `IMU_ACCEL_G`
values is the initial check. At rest, the vector magnitude should be roughly
1 g; tilting the module should change the axis values. Set `DEMO_FAULT=1` in
`config.h` and reflash to demonstrate a false fixed pose; return it to zero to
repair. Once the breakout is communicating, BenchOS can independently observe
SDA/SCL electrical activity with P1 after isolating T from the light sensor.

If `IMU_ERROR no_device_at_0x68_or_0x69` appears, first check VCC, GND,
SDA/SCL orientation, NCS, and ADO. I²C also requires pullups to 3.3 V; we
can add suitable resistors if the breakout does not already provide them.

The **first** physical module returned `WHO_AM_I=0x70`, consistent with an
MPU-6500, but its Z register repeatedly returned `0x7FFF` (+2.000 g) even
after a software reset and full USB power cycle. The firmware prints
`IMU_RAW` and the accelerometer configuration readback to expose such faults;
the dashboard flags a saturated axis. The user swapped in a second module on
the same C6 pins. It read about (0, 0.013, 1.086) g while still and
(-0.988, 0.017, 0.133) g held on edge, a plausible gravity-vector change.
The dashboard still labels this a DUT stream until S3 physically probes the
I²C lines.
