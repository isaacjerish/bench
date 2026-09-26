#pragma once
#include <Arduino.h>

static constexpr uint8_t LIGHT_GPIO = 1;
static constexpr uint8_t WATER_GPIO = 2;
static constexpr uint8_t ALERT_LED_GPIO = 20;
static constexpr uint16_t LID_OPEN_MV = 1400;
static constexpr uint16_t LID_CLOSED_MV = 900;
static constexpr uint16_t WATER_WET_MV = 500;
static constexpr uint16_t WATER_DRY_MV = 300;
static constexpr uint32_t SAMPLE_MS = 100;
static constexpr uint32_t REPORT_MS = 500;
static constexpr char BUILD_ID[] = "parcel-guard-v1";

// Deliberate, disclosed debugging exercises. 0 = correct firmware;
// 1 = water ADC/report forced to zero (leak ignored);
// 2 = alarm output disabled despite alert; 3 = wrong blink frequency (10 Hz).
#ifndef PARCEL_GUARD_FAULT
#define PARCEL_GUARD_FAULT 0
#endif
static constexpr uint8_t DEMO_FAULT = PARCEL_GUARD_FAULT;
static_assert(DEMO_FAULT <= 3, "Unknown demonstration fault");
