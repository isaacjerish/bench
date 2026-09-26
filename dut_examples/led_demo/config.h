#pragma once
#include <Arduino.h>

// ESP32-C6 GPIO20 is exposed on common DevKitC boards and is not a boot
// strapping pin. Change here if your exact board uses this pin elsewhere.
static constexpr uint8_t LED_SIGNAL_GPIO = 20;
static constexpr uint32_t HALF_PERIOD_MS = 250;  // 2 Hz, easy to see.
