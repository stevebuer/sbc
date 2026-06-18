#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from typing import Sequence

from roku_ecp import discover_roku_devices


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Discover Roku devices on the local network.")
	parser.add_argument("--timeout", type=float, default=2.0, help="Seconds to wait for SSDP responses.")
	parser.add_argument("--retries", type=int, default=1, help="Number of discovery search retries.")
	parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
	return parser


def main(argv: Sequence[str] | None = None) -> int:
	args = build_parser().parse_args(argv)
	devices = discover_roku_devices(timeout=args.timeout, retries=args.retries)

	if args.json:
		print(json.dumps([device.to_dict() for device in devices], indent=2, sort_keys=True))
		return 0

	if not devices:
		print("No Roku devices discovered.")
		return 0

	for device in devices:
		details = [device.name or device.host]
		if device.model:
			details.append(device.model)
		if device.serial:
			details.append(device.serial)
		print(" | ".join(details))
		print(f"  host: {device.host}:{device.port}")
		if device.location:
			print(f"  location: {device.location}")

	return 0


if __name__ == "__main__":
	raise SystemExit(main())

