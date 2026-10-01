#!/usr/bin/env python3
"""List, plan, and run registered stock screeners in rate-limited stages."""

from __future__ import annotations

import argparse
import ast
import json
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "screeners.json"
VERSION_PATH = ROOT / "VERSION"
META_SCREEN_PATH = ROOT / "meta_screen.py"
RATE_LIMIT_RE = re.compile(
    r"too many requests|rate.?limit|YFRateLimitError|HTTP(?:Error)?\s*429|429\s*Client\s*Error",
    re.IGNORECASE,
)


def read_registry() -> dict[str, Any]:
    try:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Cannot read {REGISTRY_PATH}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {REGISTRY_PATH}: {exc}") from exc

    stages = registry.get("stages")
    screeners = registry.get("screeners")
    if not isinstance(stages, list) or not isinstance(screeners, list):
        raise ValueError("screeners.json must contain 'stages' and 'screeners' lists")
    stage_ids = {stage.get("id") for stage in stages if isinstance(stage, dict)}
    if None in stage_ids or len(stage_ids) != len(stages):
        raise ValueError("Every stage must have a unique, non-empty id")

    ids: set[str] = set()
    for screener in screeners:
        if not isinstance(screener, dict):
            raise ValueError("Every screener entry must be an object")
        required = ("id", "name", "file", "stage", "description", "provider")
        if any(not screener.get(key) for key in required):
            raise ValueError(f"Screener entry is missing one of {required}")
        for flag in ("yahoo", "default_enabled"):
            if flag not in screener or not isinstance(screener[flag], bool):
                raise ValueError(f"{flag} must be a boolean for {screener['id']}")
        if screener["id"] in ids:
            raise ValueError(f"Duplicate screener id: {screener['id']}")
        ids.add(screener["id"])
        if screener["stage"] not in stage_ids:
            raise ValueError(f"Unknown stage {screener['stage']} for {screener['id']}")
        if not isinstance(screener.get("args", []), list):
            raise ValueError(f"args must be a list for {screener['id']}")
    return registry


def version() -> str:
    try:
        return VERSION_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return "0+unknown"


def meta_screen_checks() -> list[tuple[str, str, str]]:
    """Read registered check names without importing yfinance or its dependencies."""
    try:
        tree = ast.parse(META_SCREEN_PATH.read_text(encoding="utf-8"), filename=str(META_SCREEN_PATH))
    except OSError as exc:
        raise ValueError(f"Cannot read {META_SCREEN_PATH}: {exc}") from exc
    except SyntaxError as exc:
        raise ValueError(f"Cannot parse {META_SCREEN_PATH}: {exc}") from exc

    checks: list[tuple[str, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            function = decorator.func
            if not isinstance(function, ast.Name) or function.id != "screen":
                continue
            if len(decorator.args) < 2:
                continue
            name_arg, category_arg = decorator.args[:2]
            if isinstance(name_arg, ast.Constant) and isinstance(name_arg.value, str):
                name = name_arg.value
            else:
                continue
            if isinstance(category_arg, ast.Constant) and isinstance(category_arg.value, str):
                category = category_arg.value
            else:
                category = "other"
            if category == "theme":
                description = (
                    "Theme member; passes when its theme basket beats SPY by >2 percentage points over one month "
                    "and has positive three-month return."
                )
            else:
                description = name
            checks.append((category, name, description))
    return checks


def command_for(screener: dict[str, Any], python: str, workers: int, batch_size: int, gap: int) -> list[str]:
    script = (ROOT / screener["file"]).resolve()
    if ROOT not in script.parents:
        raise ValueError(f"Screener path escapes this folder: {screener['file']}")
    if not script.is_file() or script.suffix != ".py":
        raise ValueError(f"Screener script is missing or not Python: {screener['file']}")
    command = [python, str(script), *screener.get("args", [])]
    if screener["file"] == "meta_screen.py":
        command.extend([
            "--workers", str(workers),
            "--batch-size", str(batch_size),
            "--batch-pause-seconds", str(gap),
        ])
    elif screener.get("batchable"):
        command.extend([
            "--batch-size", str(batch_size),
            "--batch-pause-seconds", str(gap),
        ])
    return command


def select_screeners(registry: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    by_id = {item["id"]: item for item in registry["screeners"]}
    stage_names = {item["id"]: item["name"] for item in registry["stages"]}
    if args.all:
        selected = [item for item in registry["screeners"] if item["default_enabled"]]
    elif args.stage:
        if args.stage not in stage_names:
            raise ValueError(f"Unknown stage '{args.stage}'. Valid stages: {', '.join(stage_names)}")
        selected = [item for item in registry["screeners"] if item["stage"] == args.stage]
    else:
        if args.screener not in by_id:
            raise ValueError(f"Unknown screener '{args.screener}'. Use 'list' to see IDs.")
        selected = [by_id[args.screener]]

    selected_in_order = []
    selected_ids = {item["id"] for item in selected}
    for stage in registry["stages"]:
        in_stage = [item for item in selected if item["stage"] == stage["id"]]
        selected_in_order.extend(in_stage)
    if not selected_ids:
        raise ValueError("Selection contains no screeners")
    return selected_in_order


def list_command(registry: dict[str, Any], show_checks: bool) -> int:
    print(f"Finance AI Meta Screener CLI {version()}")
    print("Screeners run only when requested; list and plan do not call Yahoo or write notes.\n")
    for stage in registry["stages"]:
        entries = [item for item in registry["screeners"] if item["stage"] == stage["id"]]
        if not entries:
            continue
        print(f"{stage['name']} ({stage['id']})")
        for item in entries:
            state = "default" if item["default_enabled"] else "optional"
            print(f"  {item['id']:<23} {item['name']} [{state}]")
            print(f"    {item['file']} · {item['provider']} · {item['description']}")
            print(f"    needs: {', '.join(item.get('requirements', [])) or 'Python only'}")
            if item.get("writes"):
                print(f"    writes: {', '.join(item['writes'])}")
        print()

    checks = meta_screen_checks()
    print(f"Meta-screen checks embedded in meta_screen.py: {len(checks)}")
    if show_checks:
        categories: dict[str, list[tuple[str, str]]] = {}
        for category, name, description in checks:
            categories.setdefault(category, []).append((name, description))
        for category, items in categories.items():
            print(f"\n  {category}")
            for name, description in items:
                print(f"    • {name} — {description}")
    else:
        print("  Run `meta-screener list --checks` to see every name and criterion.")
    return 0


def plan_command(registry: dict[str, Any], args: argparse.Namespace) -> int:
    selected = select_screeners(registry, args)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in selected:
        grouped.setdefault(item["stage"], []).append(item)

    print(f"Plan for {len(selected)} screener(s); Yahoo cooldown: {args.gap_seconds}s.")
    print("No screeners are launched and no files are written by this plan.\n")
    stage_list = [stage for stage in registry["stages"] if stage["id"] in grouped]
    for stage_index, stage in enumerate(stage_list):
        print(f"STAGE: {stage['name']}")
        stage_items = grouped[stage["id"]]
        for index, item in enumerate(stage_items):
            command = command_for(item, args.python, args.workers, args.batch_size, args.gap_seconds)
            print(f"  {index + 1}. {item['name']} [{item['id']}]")
            print(f"     {shlex.join(command)}")
            print(f"     source: {item['provider']}; requirements: {', '.join(item.get('requirements', [])) or 'Python only'}")
            if item.get("reads"):
                print(f"     reads: {', '.join(item['reads'])}")
            if item.get("writes"):
                print(f"     writes: {', '.join(item['writes'])}")
            if item["yahoo"] and index < len(stage_items) - 1:
                print(f"     cooldown before next screener: {args.gap_seconds}s")
        if stage_index < len(stage_list) - 1:
            print(f"  stage cooldown: {args.gap_seconds}s")
        print()
    print("The default run is sequential. It does not place trades.")
    return 0


def run_process(command: list[str]) -> tuple[int, bool]:
    rate_limited = False
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except OSError as exc:
        print(f"Could not start screener: {exc}", file=sys.stderr)
        return 127, False

    assert process.stdout is not None
    try:
        for line in process.stdout:
            print(line, end="")
            if RATE_LIMIT_RE.search(line):
                rate_limited = True
                if process.poll() is None:
                    process.terminate()
        return_code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
        print("Interrupted; no later screeners were started.", file=sys.stderr)
        return 130, rate_limited
    return return_code, rate_limited


def run_command(registry: dict[str, Any], args: argparse.Namespace) -> int:
    selected = select_screeners(registry, args)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in selected:
        grouped.setdefault(item["stage"], []).append(item)
    active_stages = [stage for stage in registry["stages"] if stage["id"] in grouped]
    statuses: list[tuple[str, str]] = []

    for stage_index, stage in enumerate(active_stages):
        stage_items = grouped[stage["id"]]
        print(f"\n=== {stage['name']} ===", flush=True)
        for item_index, item in enumerate(stage_items):
            command = command_for(item, args.python, args.workers, args.batch_size, args.gap_seconds)
            print(f"\n--- Running {item['name']} ({item['file']}) ---", flush=True)
            print(f"Data source: {item['provider']}", flush=True)
            return_code, rate_limited = run_process(command)
            status = "ok" if return_code == 0 else f"failed ({return_code})"
            if rate_limited:
                status = "stopped (Yahoo rate limit detected)"
            statuses.append((item["id"], status))

            if rate_limited:
                print(
                    f"\nYahoo rate limit detected while running {item['id']}. "
                    "The CLI will not start more screeners or retry automatically. "
                    "Wait for Yahoo to recover, then run the remaining stage explicitly.",
                    file=sys.stderr,
                )
                return 2

            if return_code != 0 and not args.continue_on_error:
                print("Stopping after the first failed screener. Use --continue-on-error to continue.", file=sys.stderr)
                return return_code

            if item["yahoo"] and item_index < len(stage_items) - 1:
                print(f"\nYahoo cooldown: waiting {args.gap_seconds}s before the next screener.", flush=True)
                time.sleep(args.gap_seconds)

        if stage["id"] != active_stages[-1]["id"]:
            print(f"\nStage cooldown: waiting {args.gap_seconds}s.", flush=True)
            time.sleep(args.gap_seconds)

    print("\n=== Run summary ===")
    for screener_id, status in statuses:
        print(f"{screener_id:<24} {status}")
    return 0 if all(status == "ok" for _, status in statuses) else 1


def add_selection_arguments(parser: argparse.ArgumentParser) -> None:
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="run all default-enabled screeners")
    selection.add_argument("--stage", help="run one stage by ID")
    selection.add_argument("--screener", help="run one screener by ID")
    parser.add_argument("--gap-seconds", type=int, choices=range(10, 31), default=15,
                        help="Yahoo cooldown between screeners/stages (10–30; default 15)")
    parser.add_argument("--workers", type=int, choices=(1, 2), default=1,
                        help="meta_screen ticker workers (1–2; default 1)")
    parser.add_argument("--batch-size", type=int, default=8,
                        help="meta_screen symbols per Yahoo batch (default 8)")
    parser.add_argument("--python", default=sys.executable,
                        help="Python interpreter for screener scripts (default: this interpreter)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meta-screener",
        description="List, plan, and run stock screeners in sequential, rate-limited stages.",
    )
    parser.add_argument("--version", action="version", version=f"Meta Screener CLI {version()}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="list registered screeners and embedded meta checks")
    list_parser.add_argument("--checks", action="store_true", help="show all individual meta_screen checks")

    plan_parser = subparsers.add_parser("plan", help="print the run order without launching anything")
    add_selection_arguments(plan_parser)

    run_parser = subparsers.add_parser("run", help="run selected screeners sequentially")
    add_selection_arguments(run_parser)
    run_parser.add_argument("--continue-on-error", action="store_true",
                            help="continue after ordinary failures; Yahoo rate limits always stop the run")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        arguments = [
            "run", "--screener", "meta-overlap",
            "--gap-seconds", "10", "--workers", "1", "--batch-size", "25",
        ]
    args = parser.parse_args(arguments)
    try:
        registry = read_registry()
        if args.command == "list":
            return list_command(registry, args.checks)
        if args.command == "plan":
            return plan_command(registry, args)
        if args.command == "run":
            return run_command(registry, args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
