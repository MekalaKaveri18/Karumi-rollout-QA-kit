"""
CLI for the Karumi Rollout QA Kit.

Usage:
    python -m qa_kit.cli run flows/northwind_demo_flow.json
    python -m qa_kit.cli run flows/northwind_demo_flow.json --headed
    python -m qa_kit.cli run flows/northwind_demo_flow.json --out reports/custom.html
"""
from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from .report import write_report
from .runner import load_flow, run_flow

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"


def _status_tag(status: str) -> str:
    if status == "pass":
        return f"{GREEN}{BOLD} PASS {RESET}"
    if status == "fail":
        return f"{RED}{BOLD} FAIL {RESET}"
    return f"{YELLOW}{BOLD} SKIP {RESET}"


def cmd_run(args: argparse.Namespace) -> int:
    flow = load_flow(args.flow_path)
    print(f"{BOLD}{flow.get('name', 'Unnamed flow')}{RESET}")
    print(f"{DIM}target: {flow['base_url']}{RESET}\n")

    screenshot_dir = Path(args.out).with_suffix("") if args.save_screenshots else None
    result = run_flow(flow, headless=not args.headed, screenshot_dir=screenshot_dir)

    for step in result.steps:
        tag = _status_tag(step.status)
        retry_note = f" {DIM}(retried {step.attempts - 1}x){RESET}" if step.attempts > 1 else ""
        print(f"  {tag}  {CYAN}{step.index:02d}{RESET}  {step.description}{retry_note}  {DIM}{step.duration_ms}ms{RESET}")
        if step.error:
            print(f"        {RED}{step.error}{RESET}")
        if step.suggestion:
            print(f"        {DIM}→ {step.suggestion}{RESET}")

    print()
    summary_color = GREEN if result.ok else RED
    print(
        f"{BOLD}{summary_color}{'PASS' if result.ok else 'FAIL'}{RESET}  "
        f"{result.passed}/{len(result.steps)} steps passed  "
        f"{DIM}({result.total_duration_ms}ms total){RESET}"
    )

    report_path = write_report(result, args.out)
    print(f"\nReport written to {BOLD}{report_path}{RESET}")

    if args.open_report:
        webbrowser.open(f"file://{report_path.resolve()}")

    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qa_kit", description="Karumi Rollout QA Kit")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run a flow config against its target")
    run_p.add_argument("flow_path", help="Path to a flow JSON file")
    run_p.add_argument("--headed", action="store_true", help="Show the browser window instead of running headless")
    run_p.add_argument("--out", default="reports/report.html", help="Output path for the HTML report")
    run_p.add_argument("--open-report", action="store_true", help="Open the report in a browser when done")
    run_p.add_argument("--save-screenshots", action="store_true", help="Also save each step's screenshot as a separate PNG")
    run_p.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
