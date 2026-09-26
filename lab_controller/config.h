#pragma once
#include <Arduino.h>

// ESP32-S3 defaults: GPIO1 is ADC1_CH0; GPIO2 is a digital input.
// Confirm both pins are exposed and free on your particular board.
// The probe TIP connects directly to GPIO2 and through an equal-resistor
// divider to GPIO1 (TIP--10k--GPIO1--10k--GND). Never put >3.3V on TIP.
struct ProbeConfig {
  const char *name;
  uint8_t adcPin;
  uint8_t digitalPin;
  float adcScale;
};

static const ProbeConfig PROBES[] = {{"P1", 1, 2, 2.0f}};
static constexpr size_t PROBE_COUNT = sizeof(PROBES) / sizeof(PROBES[0]);
static constexpr uint32_t SERIAL_BAUD = 115200;
static constexpr uint16_t ADC_SAMPLES = 32;
static constexpr size_t MAX_COMMAND_LENGTH = 96;
static constexpr uint32_t MAX_FREQUENCY_WINDOW_MS = 2000;
