#pragma once
#include <Arduino.h>

// Current user-declared C6 wiring. Change only after updating the harness.
static constexpr uint8_t LIGHT_GPIO = 1;
static constexpr uint8_t WATER_GPIO = 2;
static constexpr uint8_t IMU_SDA_GPIO = 5;
static constexpr uint8_t IMU_SCL_GPIO = 7;
static constexpr uint8_t ALERT_LED_GPIO = 20;
static constexpr uint32_t I2C_HZ = 100000;
static constexpr uint32_t REPORT_MS = 1000;
static constexpr uint16_t LIGHT_LOW_MV = 700;
static constexpr uint16_t WATER_WET_MV = 500;  // S3 P3: dry 0 mV; wet 833–897 mV on this sensor.
static constexpr float TILT_Z_MAX_G = 0.65f;   // Board's Z axis points up when planter is upright.
static constexpr char BUILD_ID[] = "plant-sentinel-v1";

// 0 = physical readings; 1 = falsely report water=0; 2 = falsely report light=0;
// 3 = leave alarm LED off despite an alert. Faults alter reports/output, not rails.
static constexpr uint8_t DEMO_FAULT = 0;
