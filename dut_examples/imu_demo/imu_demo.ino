#include <Wire.h>
#include "config.h"

static constexpr uint8_t WHO_AM_I = 0x75;
static constexpr uint8_t PWR_MGMT_1 = 0x6B;
static constexpr uint8_t ACCEL_CONFIG = 0x1C;
static constexpr uint8_t ACCEL_XOUT_H = 0x3B;
static uint8_t imuAddress = 0;

bool readRegisters(uint8_t address, uint8_t reg, uint8_t *data, size_t length) {
  Wire.beginTransmission(address);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(address, static_cast<uint8_t>(length)) != length) return false;
  for (size_t i = 0; i < length; ++i) data[i] = Wire.read();
  return true;
}

bool writeRegister(uint8_t address, uint8_t reg, uint8_t value) {
  Wire.beginTransmission(address);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.printf("IMU demo: SDA=GPIO%d SCL=GPIO%d fault=%u\n",
                IMU_SDA_GPIO, IMU_SCL_GPIO, DEMO_FAULT);
  if (!Wire.begin(IMU_SDA_GPIO, IMU_SCL_GPIO, IMU_I2C_HZ)) {
    Serial.println("IMU_ERROR i2c_init");
    return;
  }
  for (uint8_t address : {uint8_t(0x68), uint8_t(0x69)}) {
    uint8_t id = 0;
    if (readRegisters(address, WHO_AM_I, &id, 1)) {
      imuAddress = address;
      Serial.printf("IMU_FOUND addr=0x%02X who_am_i=0x%02X\n", address, id);
      break;
    }
  }
  if (!imuAddress) {
    Serial.println("IMU_ERROR no_device_at_0x68_or_0x69");
    return;
  }
  if (!writeRegister(imuAddress, PWR_MGMT_1, 0x00) ||
      !writeRegister(imuAddress, ACCEL_CONFIG, 0x00)) {
    Serial.println("IMU_ERROR configuration_failed");
    imuAddress = 0;
    return;
  }
  delay(100);
}

void loop() {
  if (!imuAddress) {
    delay(1000);
    return;
  }
  uint8_t data[6];
  if (!readRegisters(imuAddress, ACCEL_XOUT_H, data, sizeof(data))) {
    Serial.println("IMU_ERROR read_failed");
    delay(IMU_REPORT_MS);
    return;
  }
  const int16_t x = static_cast<int16_t>((data[0] << 8) | data[1]);
  const int16_t y = static_cast<int16_t>((data[2] << 8) | data[3]);
  const int16_t z = static_cast<int16_t>((data[4] << 8) | data[5]);
  // MPU-9250/6500 default accelerometer range is +/-2 g (16384 LSB/g).
  const float ax = DEMO_FAULT == 1 ? 0.0f : x / 16384.0f;
  const float ay = DEMO_FAULT == 1 ? 0.0f : y / 16384.0f;
  const float az = DEMO_FAULT == 1 ? 1.0f : z / 16384.0f;
  Serial.printf("IMU_ACCEL_G x=%.3f y=%.3f z=%.3f\n", ax, ay, az);
  delay(IMU_REPORT_MS);
}
