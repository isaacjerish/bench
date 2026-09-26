#pragma once
#include <Arduino.h>

// The current breadboard uses IO5 because a wire is stuck in C6 IO6.
static constexpr int IMU_SDA_GPIO = 5;
static constexpr int IMU_SCL_GPIO = 7;
static constexpr uint32_t IMU_I2C_HZ = 100000;
static constexpr uint32_t IMU_REPORT_MS = 250;

// 0 = report actual acceleration. 1 = falsely report a fixed, level pose.
static constexpr uint8_t DEMO_FAULT = 0;
