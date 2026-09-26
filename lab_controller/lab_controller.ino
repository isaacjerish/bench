#include "config.h"
#include <ctype.h>
#include <stdlib.h>
#include <string.h>

static char line[MAX_COMMAND_LENGTH + 1];
static size_t lineLength = 0;
static bool overflow = false;
static volatile uint32_t risingEdges = 0;

void IRAM_ATTR countRisingEdge() { risingEdges++; }

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

void measureFrequency(const ProbeConfig &probe, uint32_t windowMs) {
  // Local interrupt counting avoids asking the host/agent to time edges.
  noInterrupts();
  risingEdges = 0;
  interrupts();
  attachInterrupt(digitalPinToInterrupt(probe.digitalPin), countRisingEdge, RISING);
  const uint32_t start = millis();
  delay(windowMs);
  const uint32_t elapsed = millis() - start;
  detachInterrupt(digitalPinToInterrupt(probe.digitalPin));
  noInterrupts();
  const uint32_t edges = risingEdges;
  interrupts();
  const float hz = elapsed ? (1000.0f * edges / elapsed) : 0.0f;
  // Pulse width is diagnostic only. A missing pulse returns zero.
  const uint32_t pulseUs = pulseIn(probe.digitalPin, HIGH, 60000UL);
  Serial.printf("OK FREQUENCY %s %.2f EDGES %lu WINDOW_MS %lu PULSE_US %lu\n",
                probe.name, hz, static_cast<unsigned long>(edges),
                static_cast<unsigned long>(elapsed),
                static_cast<unsigned long>(pulseUs));
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
    Serial.println("OK HELP PING|INFO|READ_ADC <probe>|READ_DIGITAL <probe>|MEASURE_FREQ <probe> <10-2000ms>|HELP");
    return;
  }
  if (strcmp(verb, "INFO") == 0 && !probeName) {
    Serial.printf("OK INFO BenchOS-S3 v0.1 PROBES %u ADC_SAMPLES %u\n",
                  static_cast<unsigned>(PROBE_COUNT), ADC_SAMPLES);
    return;
  }
  if (!probeName || extra) { Serial.println("ERR BAD_ARGUMENTS"); return; }
  const ProbeConfig *probe = findProbe(probeName);
  if (!probe) { Serial.println("ERR UNKNOWN_PROBE"); return; }
  if (strcmp(verb, "READ_ADC") == 0 && !arg) { measureVoltage(*probe); return; }
  if (strcmp(verb, "READ_DIGITAL") == 0 && !arg) {
    Serial.printf("OK DIGITAL %s %s\n", probe->name,
                  digitalRead(probe->digitalPin) ? "HIGH" : "LOW");
    return;
  }
  if (strcmp(verb, "MEASURE_FREQ") == 0) {
    if (!arg) { Serial.println("ERR BAD_ARGUMENTS"); return; }
    char *end = nullptr;
    const unsigned long ms = strtoul(arg, &end, 10);
    if (*end || ms < 10 || ms > MAX_FREQUENCY_WINDOW_MS) {
      Serial.println("ERR BAD_WINDOW"); return;
    }
    measureFrequency(*probe, ms);
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
