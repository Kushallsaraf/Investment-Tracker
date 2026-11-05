"""Command-line daily check: `./scripts/check` or `investment-tracker-check`."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from app.services.container import build_services
from app.services.daily_check import macos_notify, run_check


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="investment-tracker-check",
        description="Refresh prices for open review triggers and notify any due alerts not yet sent.",
    )
    parser.add_argument("--no-notify", action="store_true", help="print results without a macOS notification")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="%(levelname)s %(message)s")

    result = run_check(build_services(), notify=None if args.no_notify else macos_notify)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0

    print(f"Checked {result['open_triggers']} open trigger(s) at {result['checked_at']}.")
    if result["refreshed"]:
        print(f"Refreshed: {', '.join(result['refreshed'])}")
    for name, reason in result["failed"].items():
        print(f"Not refreshed: {name} ({reason})")
    if not result["due_alerts"]:
        print("Nothing new is due.")
    for alert in result["due_alerts"]:
        print(f"DUE  {alert['message']}")
        if alert.get("exit_plan_reasoning"):
            print(f"     Reasoning: {alert['exit_plan_reasoning']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
