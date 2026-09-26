#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WORKSPACE_DIR=$(CDPATH= cd -- "$PROJECT_DIR/../.." && pwd)
if [ -n "${BENCHOS_PYTHON:-}" ]; then
  exec "$BENCHOS_PYTHON" "$@"
fi
if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
  exec "$PROJECT_DIR/.venv/bin/python" "$@"
fi
if [ -x "$WORKSPACE_DIR/work/benchos-venv/bin/python" ]; then
  exec "$WORKSPACE_DIR/work/benchos-venv/bin/python" "$@"
fi
echo "No BenchOS Python environment found. Run: python3 -m venv .venv" >&2
exit 1
