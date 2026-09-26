#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WORKSPACE_DIR=$(CDPATH= cd -- "$PROJECT_DIR/../.." && pwd)
exec "$WORKSPACE_DIR/work/benchos-venv/bin/python" "$@"
