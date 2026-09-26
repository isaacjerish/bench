#include "config.h"

static bool high = false;
static uint32_t lastToggle = 0;

void setup() {
  Serial.begin(115200);
  pinMode(LED_SIGNAL_GPIO, OUTPUT);
  digitalWrite(LED_SIGNAL_GPIO, LOW);
  lastToggle = millis();
  Serial.printf("LED demo configured on GPIO%u at about 2 Hz.\n", LED_SIGNAL_GPIO);
  Serial.println("Verify the physical line with BenchOS; serial output alone is not proof.");
}

void loop() {
  const uint32_t now = millis();
  if (now - lastToggle >= HALF_PERIOD_MS) {
    lastToggle += HALF_PERIOD_MS;
    high = !high;
    digitalWrite(LED_SIGNAL_GPIO, high ? HIGH : LOW);
  }
}
