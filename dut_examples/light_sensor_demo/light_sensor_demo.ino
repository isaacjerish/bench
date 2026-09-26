#include "config.h"

void setup() {
  Serial.begin(115200);
  pinMode(LIGHT_SENSOR_GPIO, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(LIGHT_SENSOR_GPIO, ADC_11db);
  Serial.printf("Light demo ready: GPIO%u, fault=%u\n", LIGHT_SENSOR_GPIO, DEMO_FAULT);
}

void loop() {
  uint32_t millivolts = 0;
  for (uint8_t i = 0; i < LIGHT_SAMPLES; ++i) {
    millivolts += analogReadMilliVolts(LIGHT_SENSOR_GPIO);
    delayMicroseconds(150);
  }
  millivolts = (millivolts + LIGHT_SAMPLES / 2) / LIGHT_SAMPLES;
  const uint32_t reported = DEMO_FAULT == 1 ? 0 : millivolts;
  Serial.printf("LIGHT_MV %lu\n", static_cast<unsigned long>(reported));
  delay(REPORT_INTERVAL_MS);
}
