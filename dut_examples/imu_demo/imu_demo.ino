#include <Wire.h>
#include "config.h"

static constexpr uint8_t WHO_AM_I = 0x75;
static constexpr uint8_t PWR_MGMT_1 = 0x6B;
static constexpr uint8_t ACCEL_CONFIG = 0x1C;
static constexpr uint8_t ACCEL_XOUT_H = 0x3B;
static uint8_t imuAddress = 0;
static uint8_t imuId = 0;
static bool i2cReady = false;

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

bool detectImu() {
  imuAddress = 0;
  for (uint8_t address : {uint8_t(0x68), uint8_t(0x69)}) {
    uint8_t id = 0;
    if (readRegisters(address, WHO_AM_I, &id, 1)) {
      imuAddress = address;
      imuId = id;
      Serial.printf("IMU_FOUND addr=0x%02X who_am_i=0x%02X\n", address, id);
      break;
    }
  }
  if (!imuAddress) {
    Serial.println("IMU_ERROR no_device_at_0x68_or_0x69");
    return false;
  }
  if (!writeRegister(imuAddress, PWR_MGMT_1, 0x80)) {
    Serial.println("IMU_ERROR reset_failed");
    imuAddress = 0;
    return false;
  }
  delay(150);
  if (!writeRegister(imuAddress, PWR_MGMT_1, 0x01) ||
      !writeRegister(imuAddress, ACCEL_CONFIG, 0x00)) {
    Serial.println("IMU_ERROR configuration_failed");
    imuAddress = 0;
    return false;
  }
  uint8_t accelConfig = 0xFF;
  if (!readRegisters(imuAddress, ACCEL_CONFIG, &accelConfig, 1)) {
    Serial.println("IMU_ERROR config_readback_failed");
    imuAddress = 0;
    return false;
  }
  Serial.printf("IMU_CONFIG accel=0x%02X expected=0x00\n", accelConfig);
  delay(100);
  return true;
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.printf("IMU demo: SDA=GPIO%d SCL=GPIO%d fault=%u\n",
                IMU_SDA_GPIO, IMU_SCL_GPIO, DEMO_FAULT);
  i2cReady = Wire.begin(IMU_SDA_GPIO, IMU_SCL_GPIO, IMU_I2C_HZ);
  if (!i2cReady) Serial.println("IMU_ERROR i2c_init");
  else detectImu();
}

void loop() {
  if (!i2cReady) {
    delay(1000);
    return;
  }
  if (!imuAddress) {
    detectImu();
    delay(1000);
    return;
  }
  uint8_t data[6];
  if (!readRegisters(imuAddress, ACCEL_XOUT_H, data, sizeof(data))) {
    Serial.println("IMU_ERROR read_failed");
    imuAddress = 0;
    delay(1000);
    return;
  }
  const int16_t x = static_cast<int16_t>((data[0] << 8) | data[1]);
  const int16_t y = static_cast<int16_t>((data[2] << 8) | data[3]);
  const int16_t z = static_cast<int16_t>((data[4] << 8) | data[5]);
  uint8_t accelConfig = 0xFF;
  if (!readRegisters(imuAddress, ACCEL_CONFIG, &accelConfig, 1)) {
    Serial.println("IMU_ERROR config_readback_failed");
    imuAddress = 0;
    delay(1000);
    return;
  }
  Serial.printf("IMU_RAW x=%d y=%d z=%d bytes=%02X%02X_%02X%02X_%02X%02X accel_config=0x%02X\n",
                x, y, z, data[0], data[1], data[2], data[3], data[4], data[5], accelConfig);
  // MPU-9250/6500 default accelerometer range is +/-2 g (16384 LSB/g).
  const float ax = DEMO_FAULT == 1 ? 0.0f : x / 16384.0f;
  const float ay = DEMO_FAULT == 1 ? 0.0f : y / 16384.0f;
  const float az = DEMO_FAULT == 1 ? 1.0f : z / 16384.0f;
  Serial.printf("IMU_ACCEL_G x=%.3f y=%.3f z=%.3f id=0x%02X\n", ax, ay, az, imuId);
  delay(IMU_REPORT_MS);
}
