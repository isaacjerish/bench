#include "config.h"
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>

struct Reading {
  uint32_t uptime;
  uint16_t lightMv;
  uint16_t waterMv;
  bool lidOpen;
  bool wet;
  bool alert;
};
static QueueHandle_t reportQueue;
static bool lidOpen = false, wet = false, alert = false;
static uint32_t lastSample = 0, lastReport = 0;
static uint16_t lightMv = 0, waterMv = 0;

uint16_t sampleMillivolts(uint8_t pin) {
  uint32_t sum = 0;
  for (unsigned i = 0; i < 16; ++i) {
    sum += analogReadMilliVolts(pin);
    delayMicroseconds(100);
  }
  return static_cast<uint16_t>((sum + 8) / 16);
}

void reportTask(void *) {
  Reading reading;
  for (;;) {
    if (xQueueReceive(reportQueue, &reading, portMAX_DELAY) != pdTRUE) continue;
    // USB logging has its own task. A disconnected or slow reader cannot stop
    // sensor decisions and the alarm output in loop(). Old pending snapshots
    // are overwritten in the one-element queue rather than replayed in bulk.
    if (!Serial) continue;
    char line[240];
    const int length = snprintf(line, sizeof(line),
        "PARCEL build=%s uptime_ms=%lu light_mv=%u water_mv=%u lid_open=%u wet=%u alert=%u fault=%u\n",
        BUILD_ID, static_cast<unsigned long>(reading.uptime), reading.lightMv,
        reading.waterMv, reading.lidOpen, reading.wet, reading.alert, DEMO_FAULT);
    if (length > 0 && length < static_cast<int>(sizeof(line)) && Serial.availableForWrite() >= length)
      Serial.write(reinterpret_cast<const uint8_t *>(line), length);
  }
}

void setup() {
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);
  analogReadResolution(12);
  pinMode(LIGHT_GPIO, INPUT);
  pinMode(WATER_GPIO, INPUT);
  analogSetPinAttenuation(LIGHT_GPIO, ADC_11db);
  analogSetPinAttenuation(WATER_GPIO, ADC_11db);
  pinMode(ALERT_LED_GPIO, OUTPUT);
  digitalWrite(ALERT_LED_GPIO, LOW);
  reportQueue = xQueueCreate(1, sizeof(Reading));
  if (reportQueue) xTaskCreate(reportTask, "parcel-report", 4096, nullptr, 1, nullptr);
}

void loop() {
  const uint32_t now = millis();
  if (now - lastSample >= SAMPLE_MS) {
    lastSample = now;
    lightMv = sampleMillivolts(LIGHT_GPIO);
    waterMv = DEMO_FAULT == 1 ? 0 : sampleMillivolts(WATER_GPIO);
    // Hysteresis prevents threshold chatter as a lid moves or water dries.
    if (lightMv >= LID_OPEN_MV) lidOpen = true;
    else if (lightMv <= LID_CLOSED_MV) lidOpen = false;
    if (waterMv >= WATER_WET_MV) wet = true;
    else if (waterMv <= WATER_DRY_MV) wet = false;
    alert = lidOpen || wet;
  }
  const uint32_t halfPeriodMs = DEMO_FAULT == 3 ? 50 : 250;
  const bool startupCheck = now < 1500;
  const bool shouldBlink = startupCheck || alert;
  const bool outputHigh = DEMO_FAULT != 2 && shouldBlink && (now / halfPeriodMs) % 2 == 0;
  digitalWrite(ALERT_LED_GPIO, outputHigh ? HIGH : LOW);
  if (reportQueue && now - lastReport >= REPORT_MS) {
    lastReport = now;
    Reading reading{now, lightMv, waterMv, lidOpen, wet, alert};
    xQueueOverwrite(reportQueue, &reading);
  }
  delay(1);
}
