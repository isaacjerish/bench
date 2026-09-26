#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 servo_demo|led_demo|light_sensor_demo /dev/cu.usbmodemXXXX" >&2
  exit 2
fi

case "$1" in
  servo_demo|led_demo|light_sensor_demo) DEMO=$1 ;;
  *) echo "Unknown DUT demo: $1" >&2; exit 2 ;;
esac

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SKETCH="$PROJECT_DIR/dut_examples/$DEMO"
CONFIG="$PROJECT_DIR/scripts/arduino-cli.yaml"
FQBN=esp32:esp32:esp32c6:CDCOnBoot=cdc

arduino-cli compile --config-file "$CONFIG" --fqbn "$FQBN" "$SKETCH"
arduino-cli upload --config-file "$CONFIG" --fqbn "$FQBN" -p "$2" "$SKETCH"
