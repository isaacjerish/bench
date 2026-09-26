#pragma once
#include <Arduino.h>

// Confirm GPIO20 is exposed and unused on your ESP32-C6 dev board.
// Avoid GPIO4/5: they are boot strapping pins on ESP32-C6.
static constexpr uint8_t SERVO_SIGNAL_GPIO = 20;
static constexpr uint8_t WRONG_PIN_GPIO = 21;
static constexpr uint32_t NORMAL_FREQUENCY_HZ = 50;
static constexpr uint32_t NORMAL_PULSE_US = 1500;
static constexpr uint8_t PWM_RESOLUTION_BITS = 14;

// 0 = working, 1 = wrong software pin, 2 = silent/stuck-low signal,
// 3 = wrong frequency (312 Hz). Set one fault at a time for the demo.
static constexpr uint8_t DEMO_FAULT = 0;

// Turn on only for a visible, unloaded servo motion demo after external 5 V
// power and common ground are connected. Default stays at 1500 us for tests.
static constexpr bool DEMO_SWEEP = false;
