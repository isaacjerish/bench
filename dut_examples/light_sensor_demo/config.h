#pragma once
#include <Arduino.h>

// GPIO1 is ADC1_CH1 on ESP32-C6. Confirm IO1 is exposed on your board.
static constexpr uint8_t LIGHT_SENSOR_GPIO = 1;
static constexpr uint8_t LIGHT_SAMPLES = 16;
static constexpr uint32_t REPORT_INTERVAL_MS = 500;

// 0 = correct report, 1 = firmware falsely reports zero millivolts.
static constexpr uint8_t DEMO_FAULT = 0;
