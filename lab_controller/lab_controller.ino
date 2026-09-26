#include "config.h"
#include <ctype.h>
#include <stdlib.h>
#include <string.h>

static char line[MAX_COMMAND_LENGTH + 1];
static size_t lineLength = 0;
static bool overflow = false;
static volatile uint32_t risingEdges = 0;
static volatile uint32_t sdaTransitions = 0;
static volatile uint32_t sclTransitions = 0;
static volatile uint32_t tapTransitions[DIGITAL_TAP_COUNT] = {};

void IRAM_ATTR countRisingEdge() { risingEdges++; }
void IRAM_ATTR countSdaTransition() { sdaTransitions++; }
void IRAM_ATTR countSclTransition() { sclTransitions++; }
void IRAM_ATTR countTapTransition(void *index) {
  tapTransitions[reinterpret_cast<uintptr_t>(index)]++;
}

const ProbeConfig *findProbe(const char *name) {
  for (size_t i = 0; i < PROBE_COUNT; ++i) {
    if (strcmp(name, PROBES[i].name) == 0) return &PROBES[i];
  }
  return nullptr;
}

// Arduino-ESP32's analogReadMilliVolts applies chip calibration where available.
// It is still an approximate instrument reading, especially near the rails.
void measureVoltage(const ProbeConfig &probe) {
  uint32_t rawSum = 0;
  uint32_t mvSum = 0;
  for (uint16_t i = 0; i < ADC_SAMPLES; ++i) {
    rawSum += analogRead(probe.adcPin);
    mvSum += analogReadMilliVolts(probe.adcPin);
    delayMicroseconds(150);
  }
  const float volts = static_cast<float>(mvSum) / ADC_SAMPLES / 1000.0f * probe.adcScale;
  const uint32_t raw = (rawSum + ADC_SAMPLES / 2) / ADC_SAMPLES;
  Serial.printf("OK VOLTAGE %s %.3f RAW %lu SAMPLES %u\n", probe.name,
                volts, static_cast<unsigned long>(raw), ADC_SAMPLES);
}

void measureFrequencyPin(const char *name, uint8_t pin, uint32_t windowMs) {
  // Local interrupt counting avoids asking the host/agent to time edges.
  noInterrupts();
  risingEdges = 0;
  interrupts();
  attachInterrupt(digitalPinToInterrupt(pin), countRisingEdge, RISING);
  const uint32_t start = millis();
  delay(windowMs);
  const uint32_t elapsed = millis() - start;
  detachInterrupt(digitalPinToInterrupt(pin));
  noInterrupts();
  const uint32_t edges = risingEdges;
  interrupts();
  const float hz = elapsed ? (1000.0f * edges / elapsed) : 0.0f;
  // Pulse width is diagnostic only. A missing pulse returns zero.
  const uint32_t pulseUs = pulseIn(pin, HIGH, 60000UL);
  Serial.printf("OK FREQUENCY %s %.2f EDGES %lu WINDOW_MS %lu PULSE_US %lu\n",
                name, hz, static_cast<unsigned long>(edges),
                static_cast<unsigned long>(elapsed),
                static_cast<unsigned long>(pulseUs));
}

void measureDigitalTaps(uint32_t windowMs) {
  bool starts[DIGITAL_TAP_COUNT], ends[DIGITAL_TAP_COUNT];
  uint32_t counts[DIGITAL_TAP_COUNT];
  for (size_t i = 0; i < DIGITAL_TAP_COUNT; ++i) {
    starts[i] = digitalRead(DIGITAL_TAPS[i].pin);
    tapTransitions[i] = 0;
    attachInterruptArg(digitalPinToInterrupt(DIGITAL_TAPS[i].pin), countTapTransition,
                       reinterpret_cast<void *>(i), CHANGE);
  }
  const uint32_t start = millis();
  delay(windowMs);
  const uint32_t elapsed = millis() - start;
  for (size_t i = 0; i < DIGITAL_TAP_COUNT; ++i) {
    detachInterrupt(digitalPinToInterrupt(DIGITAL_TAPS[i].pin));
    counts[i] = tapTransitions[i];
    ends[i] = digitalRead(DIGITAL_TAPS[i].pin);
  }
  Serial.printf("OK TAPS WINDOW_MS %lu", static_cast<unsigned long>(elapsed));
  for (size_t i = 0; i < DIGITAL_TAP_COUNT; ++i) {
    Serial.printf(" %s %s %s %lu", DIGITAL_TAPS[i].name, starts[i] ? "HIGH" : "LOW",
                  ends[i] ? "HIGH" : "LOW", static_cast<unsigned long>(counts[i]));
  }
  Serial.println();
}

void measureBusActivity(uint32_t windowMs) {
  // These interrupt counts reveal activity or a static line. They are not a
  // logic-analyzer trace and can undercount fast edges at high bus rates.
  const bool sdaStart = digitalRead(BUS_SDA_GPIO);
  const bool sclStart = digitalRead(BUS_SCL_GPIO);
  noInterrupts();
  sdaTransitions = 0;
  sclTransitions = 0;
  interrupts();
  attachInterrupt(digitalPinToInterrupt(BUS_SDA_GPIO), countSdaTransition, CHANGE);
  attachInterrupt(digitalPinToInterrupt(BUS_SCL_GPIO), countSclTransition, CHANGE);
  const uint32_t start = millis();
  delay(windowMs);
  const uint32_t elapsed = millis() - start;
  detachInterrupt(digitalPinToInterrupt(BUS_SDA_GPIO));
  detachInterrupt(digitalPinToInterrupt(BUS_SCL_GPIO));
  noInterrupts();
  const uint32_t sdaCount = sdaTransitions;
  const uint32_t sclCount = sclTransitions;
  interrupts();
  const bool sdaEnd = digitalRead(BUS_SDA_GPIO);
  const bool sclEnd = digitalRead(BUS_SCL_GPIO);
  Serial.printf("OK BUS SDA %s %s EDGES %lu SCL %s %s EDGES %lu WINDOW_MS %lu\n",
                sdaStart ? "HIGH" : "LOW", sdaEnd ? "HIGH" : "LOW",
                static_cast<unsigned long>(sdaCount),
                sclStart ? "HIGH" : "LOW", sclEnd ? "HIGH" : "LOW",
                static_cast<unsigned long>(sclCount), static_cast<unsigned long>(elapsed));
}

void processLine(char *command) {
  char *save = nullptr;
  char *verb = strtok_r(command, " \t", &save);
  char *probeName = strtok_r(nullptr, " \t", &save);
  char *arg = strtok_r(nullptr, " \t", &save);
  char *extra = strtok_r(nullptr, " \t", &save);
  if (!verb) return;
  for (char *p = verb; *p; ++p) *p = toupper(static_cast<unsigned char>(*p));
  if (strcmp(verb, "PING") == 0 && !probeName) { Serial.println("OK PONG"); return; }
  if (strcmp(verb, "HELP") == 0 && !probeName) {
    Serial.println("OK HELP PING|INFO|READ_ADC <probe>|READ_DIGITAL <probe-or-D1-D5>|MEASURE_FREQ <probe-or-D1-D5> <10-2000ms>|MEASURE_BUS <10-2000ms>|MEASURE_TAPS <10-2000ms>|HELP");
    return;
  }
  if (strcmp(verb, "INFO") == 0 && !probeName) {
    Serial.printf("OK INFO BenchOS-S3 v0.3 PROBES %u ADC_SAMPLES %u PROFILE %s\n",
                  static_cast<unsigned>(PROBE_COUNT), ADC_SAMPLES, LAB_PROFILE);
    return;
  }
  if (strcmp(verb, "MEASURE_BUS") == 0 || strcmp(verb, "MEASURE_TAPS") == 0) {
    if (!probeName || arg || extra) { Serial.println("ERR BAD_ARGUMENTS"); return; }
    char *end = nullptr;
    const unsigned long ms = strtoul(probeName, &end, 10);
    if (*end || ms < 10 || ms > MAX_FREQUENCY_WINDOW_MS) {
      Serial.println("ERR BAD_WINDOW"); return;
    }
    if (strcmp(verb, "MEASURE_TAPS") == 0) measureDigitalTaps(ms);
    else measureBusActivity(ms);
    return;
  }
  if (!probeName || extra) { Serial.println("ERR BAD_ARGUMENTS"); return; }
  const ProbeConfig *probe = findProbe(probeName);
  int digitalPin = probe ? probe->digitalPin : -1;
  for (const auto &tap : DIGITAL_TAPS) {
    if (strcmp(probeName, tap.name) == 0) digitalPin = tap.pin;
  }
  if (digitalPin < 0) { Serial.println("ERR UNKNOWN_PROBE"); return; }
  if (strcmp(verb, "READ_ADC") == 0 && !arg) {
    if (!probe) { Serial.println("ERR DIGITAL_ONLY"); return; }
    measureVoltage(*probe); return;
  }
  if (strcmp(verb, "READ_DIGITAL") == 0 && !arg) {
    Serial.printf("OK DIGITAL %s %s\n", probeName,
                  digitalRead(digitalPin) ? "HIGH" : "LOW");
    return;
  }
  if (strcmp(verb, "MEASURE_FREQ") == 0) {
    if (!arg) { Serial.println("ERR BAD_ARGUMENTS"); return; }
    char *end = nullptr;
    const unsigned long ms = strtoul(arg, &end, 10);
    if (*end || ms < 10 || ms > MAX_FREQUENCY_WINDOW_MS) {
      Serial.println("ERR BAD_WINDOW"); return;
    }
    measureFrequencyPin(probeName, digitalPin, ms);
    return;
  }
  Serial.println("ERR UNKNOWN_COMMAND");
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  analogReadResolution(12);
  for (size_t i = 0; i < PROBE_COUNT; ++i) {
    pinMode(PROBES[i].adcPin, INPUT);
    pinMode(PROBES[i].digitalPin, INPUT);  // Never drive measurement probes.
    analogSetPinAttenuation(PROBES[i].adcPin, ADC_11db);
  }
  pinMode(BUS_SDA_GPIO, INPUT);  // No internal pullups; observe only.
  pinMode(BUS_SCL_GPIO, INPUT);
  for (const auto &tap : DIGITAL_TAPS) pinMode(tap.pin, INPUT);
}

void loop() {
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\r') continue;
    if (c == '\n') {
      if (overflow) Serial.println("ERR LINE_TOO_LONG");
      else { line[lineLength] = '\0'; processLine(line); }
      lineLength = 0;
      overflow = false;
    } else if (!overflow) {
      if (lineLength < MAX_COMMAND_LENGTH) line[lineLength++] = c;
      else overflow = true;
    }
  }
}
