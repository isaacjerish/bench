#include <Wire.h>
#include "config.h"

static constexpr uint8_t WHO_AM_I = 0x75;
static constexpr uint8_t PWR_MGMT_1 = 0x6B;
static constexpr uint8_t ACCEL_CONFIG = 0x1C;
static constexpr uint8_t ACCEL_XOUT_H = 0x3B;
static uint8_t imuAddress = 0;
static uint8_t imuId = 0;
static bool i2cReady = false;
static uint32_t lastReport = 0;
static bool currentAlert = false;

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
      break;
    }
  }
  if (!imuAddress) return false;
  if (!writeRegister(imuAddress, PWR_MGMT_1, 0x80)) { imuAddress = 0; return false; }
  delay(150);
  if (!writeRegister(imuAddress, PWR_MGMT_1, 0x01) ||
      !writeRegister(imuAddress, ACCEL_CONFIG, 0x00)) { imuAddress = 0; return false; }
  return true;
}

uint16_t sampleMillivolts(uint8_t pin) {
  uint32_t sum = 0;
  for (uint8_t i = 0; i < 16; ++i) {
    sum += analogReadMilliVolts(pin);
    delayMicroseconds(120);
  }
  return static_cast<uint16_t>((sum + 8) / 16);
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  analogSetPinAttenuation(LIGHT_GPIO, ADC_11db);
  analogSetPinAttenuation(WATER_GPIO, ADC_11db);
  pinMode(ALERT_LED_GPIO, OUTPUT);
  digitalWrite(ALERT_LED_GPIO, LOW);
  i2cReady = Wire.begin(IMU_SDA_GPIO, IMU_SCL_GPIO, I2C_HZ);
  if (i2cReady) detectImu();
}

void loop() {
  const uint32_t now = millis();
  digitalWrite(ALERT_LED_GPIO, DEMO_FAULT == 3 ? LOW :
               (currentAlert && (now / 250) % 2 == 0 ? HIGH : LOW));
  if (now - lastReport < REPORT_MS) { delay(1); return; }
  lastReport = now;

  const uint16_t lightPhysicalMv = sampleMillivolts(LIGHT_GPIO);
  const uint16_t waterPhysicalMv = sampleMillivolts(WATER_GPIO);
  const uint16_t lightReportedMv = DEMO_FAULT == 2 ? 0 : lightPhysicalMv;
  const uint16_t waterReportedMv = DEMO_FAULT == 1 ? 0 : waterPhysicalMv;

  bool imuOk = false;
  float ax = 0, ay = 0, az = 0;
  if (i2cReady) {
    if (!imuAddress) detectImu();
    uint8_t data[6];
    if (imuAddress && readRegisters(imuAddress, ACCEL_XOUT_H, data, sizeof(data))) {
      const int16_t x = static_cast<int16_t>((data[0] << 8) | data[1]);
      const int16_t y = static_cast<int16_t>((data[2] << 8) | data[3]);
      const int16_t z = static_cast<int16_t>((data[4] << 8) | data[5]);
      ax = x / 16384.0f;
      ay = y / 16384.0f;
      az = z / 16384.0f;
      imuOk = true;
    } else imuAddress = 0;
  }

  // Decisions use physical reads, while faults corrupt only a report or LED.
  const bool lowLight = lightPhysicalMv < LIGHT_LOW_MV;
  const bool waterDetected = waterPhysicalMv >= WATER_WET_MV;
  const bool tilted = imuOk && az < TILT_Z_MAX_G;
  const bool alert = lowLight || waterDetected || tilted || !imuOk;
  currentAlert = alert;

  if (Serial) {
    Serial.printf("SENTINEL build=%s light_mv=%u water_mv=%u imu_ok=%u ax_g=%.3f ay_g=%.3f az_g=%.3f imu_id=0x%02X low_light=%u water_detected=%u tilted=%u alert=%u fault=%u\n",
                  BUILD_ID, lightReportedMv, waterReportedMv, imuOk ? 1 : 0,
                  ax, ay, az, imuId, lowLight ? 1 : 0, waterDetected ? 1 : 0,
                  tilted ? 1 : 0, alert ? 1 : 0, DEMO_FAULT);
    if (!imuOk) Serial.println("SENTINEL_ERROR imu_unavailable");
  }
}
