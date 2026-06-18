#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from roku_ecp import RokuDevice, ensure_database, poll_roku_device, store_usage_sample


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Poll a Roku device once and optionally store the sample.")
	parser.add_argument("host", help="Roku host name or IP address.")
	parser.add_argument("--database", help="SQLite database path for logging.")
	parser.add_argument("--json", action="store_true", help="Print JSON output.")
	return parser


def main(argv: Sequence[str] | None = None) -> int:
	args = build_parser().parse_args(argv)
	device = RokuDevice(host=args.host)
	status = poll_roku_device(device)

	if not status:
		raise SystemExit(f"Unable to contact Roku at {args.host}")

	if args.database:
		connection = ensure_database(Path(args.database))
		store_usage_sample(connection, device, status)

	system = status.get("system", {}) or {}
	state = system.get("system_state") or "IDLE"
	app_name = system.get("active_app_name") or system.get("active_app_id") or "unknown"

	if args.json:
		print(json.dumps(status, indent=2, sort_keys=True))
		return 0

	print(f"{status['observed_at']} {device.host} {state} {app_name}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
