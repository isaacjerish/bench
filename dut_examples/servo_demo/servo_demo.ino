#include "config.h"

uint8_t outputPin() {
  return DEMO_FAULT == 1 ? WRONG_PIN_GPIO : SERVO_SIGNAL_GPIO;
}

uint32_t outputFrequency() {
  return DEMO_FAULT == 3 ? 312 : NORMAL_FREQUENCY_HZ;
}

uint32_t pulseToDuty(uint32_t pulseUs, uint32_t frequencyHz) {
  // At 14-bit resolution, 50 Hz and 1500 us is about 7.5% duty.
  return static_cast<uint32_t>((static_cast<uint64_t>(pulseUs) * frequencyHz
                                * (1UL << PWM_RESOLUTION_BITS) + 500000ULL) / 1000000ULL);
}

void setup() {
  Serial.begin(115200);
  delay(300);
  const uint8_t pin = outputPin();
  const uint32_t frequency = outputFrequency();
  if (!ledcAttach(pin, frequency, PWM_RESOLUTION_BITS)) {
    Serial.println("ERROR LEDC attach failed");
    return;
  }
  const uint32_t duty = DEMO_FAULT == 2 ? 0 : pulseToDuty(NORMAL_PULSE_US, frequency);
  if (!ledcWrite(pin, duty)) {
    Serial.println("ERROR LEDC write failed");
    return;
  }
  Serial.printf("Servo demo configured: GPIO%u, %lu Hz, duty=%lu, fault=%u\n",
                pin, static_cast<unsigned long>(frequency),
                static_cast<unsigned long>(duty), DEMO_FAULT);
  Serial.println("Software configured output; verify the actual signal with BenchOS.");
}

void loop() {
  delay(2000);
  if (DEMO_SWEEP && DEMO_FAULT != 2) {
    static bool right = false;
    right = !right;
    const uint32_t pulseUs = right ? 2000 : 1000;
    ledcWrite(outputPin(), pulseToDuty(pulseUs, outputFrequency()));
    Serial.printf("Servo pulse set to %lu us; verify physical output with BenchOS.\n",
                  static_cast<unsigned long>(pulseUs));
  } else {
    Serial.println("Servo demo alive; physical output still needs measurement.");
  }
}
