"""Manual CLI, independent of MCP and Codex."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .checks import run_suite
from .client import BenchClient
from .light import compare_light
from .harness import describe_harness
from .flash import plan_dut_flash, build_dut_firmware, flash_result_ok
from .telemetry import check_live_declared_telemetry
from .ports import available_ports
from .protocol import BenchError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="benchos", description="Benchy physical measurements")
    parser.add_argument("--port", help="Explicit serial port; otherwise auto-discover")
    parser.add_argument("--verbose", action="store_true", help="Log serial TX/RX to stderr")
    parser.add_argument("--log", help="Append measurements and tests to a JSONL file")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("list", "ping", "info", "harness", "flash-plan"):
        sub.add_parser(name)
    sub.add_parser("build-dut", help="Compile the declared DUT sketch into an evidence directory")
    sub.add_parser("flash-dut", help="Compile and upload only to the enrolled DUT USB identity")
    sub.add_parser("check-telemetry", help="Compare declared DUT serial fields with fresh S3 probe readings")
    for name in ("voltage", "digital"):
        sub.add_parser(name).add_argument("probe")
    sub.add_parser("pair-voltage", help="Read P1 then P2, close in time but not simultaneously")
    bus = sub.add_parser("bus-activity", help="Observe declared SDA/SCL read-only monitor inputs")
    bus.add_argument("--duration-ms", type=int, default=1000)
    taps = sub.add_parser("digital-taps", help="Observe fixed input taps and compare declared endpoints")
    taps.add_argument("--duration-ms", type=int, default=1000)
    frequency = sub.add_parser("frequency")
    frequency.add_argument("probe")
    frequency.add_argument("--duration-ms", type=int, default=1000)
    test = sub.add_parser("test")
    test.add_argument("file")
    light = sub.add_parser("light-compare", help="Compare C6 light report with physical P1 voltage")
    light.add_argument("--dut-port", required=True, help="C6 USB serial port")
    light.add_argument("--tolerance-v", type=float, default=0.45)
    light.add_argument("--min-physical-v", type=float, default=0.3)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list":
        print(json.dumps(available_ports(), indent=2))
        return 0
    if args.command == "harness":
        try:
            print(json.dumps(describe_harness(), indent=2, default=str))
            return 0
        except (OSError, ValueError) as exc:
            print(f"Benchy error: {exc}", file=sys.stderr)
            return 2
    if args.command == "flash-plan":
        try:
            print(json.dumps(plan_dut_flash(), indent=2))
            return 0
        except (OSError, ValueError) as exc:
            print(f"Benchy error: {exc}", file=sys.stderr)
            return 2
    if args.command in ("build-dut", "flash-dut"):
        try:
            result = build_dut_firmware(flash=args.command == "flash-dut")
            print(json.dumps(result, indent=2))
            ok = result["compile"]["ok"] if args.command == "build-dut" else flash_result_ok(result)
            return 0 if ok else 1
        except (OSError, ValueError) as exc:
            print(f"Benchy error: {exc}", file=sys.stderr)
            return 2
    if args.command == "check-telemetry":
        try:
            result = check_live_declared_telemetry()
            print(json.dumps(result, indent=2))
            return 0 if result["state"] == "pass" else 1
        except (BenchError, OSError, ValueError) as exc:
            print(f"Benchy error: {exc}", file=sys.stderr)
            return 2
    try:
        with BenchClient(args.port, verbose=args.verbose, log_path=args.log) as client:
            if args.command == "ping":
                result = client.ping()
            elif args.command == "info":
                result = client.info()
            elif args.command == "voltage":
                result = client.measure_voltage(args.probe)
            elif args.command == "pair-voltage":
                result = client.measure_voltage_pair()
            elif args.command == "bus-activity":
                result = client.measure_bus_activity(args.duration_ms)
            elif args.command == "digital-taps":
                result = client.measure_digital_taps(args.duration_ms)
            elif args.command == "digital":
                result = client.read_digital(args.probe)
            elif args.command == "frequency":
                result = client.measure_frequency(args.probe, args.duration_ms)
            elif args.command == "light-compare":
                result = compare_light(client, args.dut_port,
                                       tolerance_v=args.tolerance_v,
                                       min_physical_v=args.min_physical_v)
                if args.log:
                    record = {"timestamp": datetime.now(timezone.utc).isoformat(), **result}
                    with Path(args.log).open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(record) + "\n")
            else:
                result = run_suite(client, args.file, log_path=args.log)
    except (BenchError, OSError, ValueError, TypeError) as exc:
        print(f"Benchy error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 1 if args.command in ("test", "light-compare") and not result["pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
