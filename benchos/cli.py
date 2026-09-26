"""Manual CLI, independent of MCP and Codex."""

import argparse
import json
import sys

from .checks import run_suite
from .client import BenchClient
from .ports import available_ports
from .protocol import BenchError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="benchos", description="BenchOS physical measurements")
    parser.add_argument("--port", help="Explicit serial port; otherwise auto-discover")
    parser.add_argument("--verbose", action="store_true", help="Log serial TX/RX to stderr")
    parser.add_argument("--log", help="Append measurements and tests to a JSONL file")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("list", "ping", "info"):
        sub.add_parser(name)
    for name in ("voltage", "digital"):
        sub.add_parser(name).add_argument("probe")
    frequency = sub.add_parser("frequency")
    frequency.add_argument("probe")
    frequency.add_argument("--duration-ms", type=int, default=1000)
    test = sub.add_parser("test")
    test.add_argument("file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list":
        print(json.dumps(available_ports(), indent=2))
        return 0
    try:
        with BenchClient(args.port, verbose=args.verbose, log_path=args.log) as client:
            if args.command == "ping":
                result = client.ping()
            elif args.command == "info":
                result = client.info()
            elif args.command == "voltage":
                result = client.measure_voltage(args.probe)
            elif args.command == "digital":
                result = client.read_digital(args.probe)
            elif args.command == "frequency":
                result = client.measure_frequency(args.probe, args.duration_ms)
            else:
                result = run_suite(client, args.file, log_path=args.log)
    except (BenchError, OSError, ValueError, TypeError) as exc:
        print(f"BenchOS error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 1 if args.command == "test" and not result["pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
