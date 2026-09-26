#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
"$PROJECT_DIR/scripts/python.sh" -m benchos.cli list
arduino-cli board list --config-file "$PROJECT_DIR/scripts/arduino-cli.yaml"
