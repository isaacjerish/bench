#pragma once
#include <Arduino.h>

// Change these if IO6/IO7 are unavailable on the ESP32-C6 board.
static constexpr int IMU_SDA_GPIO = 6;
static constexpr int IMU_SCL_GPIO = 7;
static constexpr uint32_t IMU_I2C_HZ = 100000;
static constexpr uint32_t IMU_REPORT_MS = 250;

// 0 = report actual acceleration. 1 = falsely report a fixed, level pose.
static constexpr uint8_t DEMO_FAULT = 0;
