#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 ground|rail_3v3|servo_signal|led_blink /dev/cu.usbmodemXXXX" >&2
  exit 2
fi

case "$1" in
  ground|rail_3v3|servo_signal|led_blink) TEST=$1 ;;
  *) echo "Unknown physical test: $1" >&2; exit 2 ;;
esac

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_DIR"
exec ./scripts/python.sh -m benchos.cli --port "$2" \
  --log measurements.jsonl test "physical_tests/$TEST.yaml"
