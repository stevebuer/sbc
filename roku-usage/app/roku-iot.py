#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Sequence

from roku_ecp import RokuDevice, discover_roku_devices, ensure_database, poll_roku_device, store_usage_sample


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Continuously log Roku usage to SQLite.")
	parser.add_argument("--database", default="roku-usage.sqlite3", help="SQLite database path.")
	parser.add_argument("--interval", type=float, default=30.0, help="Seconds between polling rounds.")
	parser.add_argument("--timeout", type=float, default=2.0, help="Seconds to wait for device discovery.")
	parser.add_argument("--retries", type=int, default=1, help="Number of discovery retries.")
	parser.add_argument("--host", action="append", default=[], help="Poll a specific Roku host. Repeatable.")
	parser.add_argument("--once", action="store_true", help="Run a single polling round and exit.")
	parser.add_argument("--json", action="store_true", help="Print each collected sample as JSON.")
	return parser


def _build_devices(args: argparse.Namespace) -> list[RokuDevice]:
	devices = [RokuDevice(host=host.strip()) for host in args.host if host.strip()]
	if devices:
		return devices
	return discover_roku_devices(timeout=args.timeout, retries=args.retries)


def main(argv: Sequence[str] | None = None) -> int:
	args = build_parser().parse_args(argv)
	database_path = Path(args.database)
	connection = ensure_database(database_path)

	while True:
		devices = _build_devices(args)
		if not devices:
			print("No Roku devices available.")
			return 0

		for device in devices:
			status = poll_roku_device(device)
			if not status:
				continue
			store_usage_sample(connection, device, status)
			system = status.get("system", {}) or {}
			state = system.get("system_state") or "IDLE"
			app_name = system.get("active_app_name") or system.get("active_app_id") or "unknown"
			if args.json:
				print(json.dumps(status, indent=2, sort_keys=True))
			else:
				print(f"{status['observed_at']} {device.host} {state} {app_name}")

		if args.once:
			return 0

		time.sleep(max(1.0, args.interval))


if __name__ == "__main__":
	raise SystemExit(main())
