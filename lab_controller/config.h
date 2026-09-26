#pragma once
#include <Arduino.h>

// Current ESP32-S3 bench: P1 uses GPIO1 ADC + GPIO2 digital; P2 uses
// GPIO4 ADC + GPIO5 digital. P3 uses GPIO6 ADC + GPIO7 digital, with
// separate 10k series resistors from its known 0-3.3V tip to each input.
// All are INPUT only. P1/P2 TIP connects directly to its digital pin and
// through an equal-resistor divider to its ADC pin (TIP--10k--ADC--10k--GND).
// Never put >3.3V on any TIP; P3 has no voltage-divider protection.
struct ProbeConfig {
  const char *name;
  uint8_t adcPin;
  uint8_t digitalPin;
  float adcScale;
};

static const ProbeConfig PROBES[] = {
    {"P1", 1, 2, 2.0f},
    {"P2", 4, 5, 2.0f},
    {"P3", 6, 7, 1.0f},
};
static constexpr size_t PROBE_COUNT = sizeof(PROBES) / sizeof(PROBES[0]);
// Dedicated read-only logic inputs. Wire only after confirming these pins are
// exposed and the observed bus is 0–3.3 V; these pins are not 5 V tolerant.
static constexpr uint8_t BUS_SDA_GPIO = 8;
static constexpr uint8_t BUS_SCL_GPIO = 9;
struct DigitalTapConfig { const char *name; uint8_t pin; };
// Passive 0–3.3 V taps. No pullups, pulldowns, or drive mode are enabled.
static const DigitalTapConfig DIGITAL_TAPS[] = {
    {"D1", 8}, {"D2", 9}, {"D3", 10}, {"D4", 11}, {"D5", 12},
};
static constexpr size_t DIGITAL_TAP_COUNT = sizeof(DIGITAL_TAPS) / sizeof(DIGITAL_TAPS[0]);
static constexpr uint32_t SERIAL_BAUD = 115200;
static constexpr uint16_t ADC_SAMPLES = 32;
static constexpr size_t MAX_COMMAND_LENGTH = 96;
static constexpr uint32_t MAX_FREQUENCY_WINDOW_MS = 2000;
