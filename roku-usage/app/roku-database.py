#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from roku_ecp import ensure_database, format_usage_report


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Inspect the Roku usage database.")
	parser.add_argument("database", help="SQLite database path.")
	subparsers = parser.add_subparsers(dest="command", required=True)

	subparsers.add_parser("init", help="Create the database schema if needed.")

	report = subparsers.add_parser("report", help="Print a usage report.")
	report.add_argument("--days", type=int, default=7, help="Only include sessions from the last N days.")

	return parser


def main(argv: Sequence[str] | None = None) -> int:
	args = build_parser().parse_args(argv)
	connection = ensure_database(Path(args.database))

	if args.command == "init":
		print(f"Initialized {args.database}")
		return 0

	if args.command == "report":
		print(format_usage_report(connection, days=args.days))
		return 0

	return 0


if __name__ == "__main__":
	raise SystemExit(main())
