#!/usr/bin/env python3
"""Launch the Meta Screener dashboard and list, plan, or run registered workflows."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def find_project_root() -> Path:
    candidates = []
    configured_root = os.environ.get("FINANCE_AI_HOME")
    if configured_root:
        candidates.append(Path(configured_root).expanduser())
    candidates.extend((Path.cwd(), Path(__file__).resolve().parent))
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if (resolved / "screeners.json").is_file() and (
            (resolved / "screeners").is_dir()
            or (resolved / "meta_screen.py").is_file()
        ):
            return resolved
    raise RuntimeError("Finance AI folder not found; run from the repository root or set FINANCE_AI_HOME.")


ROOT = find_project_root()
REGISTRY_PATH = ROOT / "screeners.json"
VERSION_PATH = ROOT / "VERSION"
META_SCREEN_PATH = ROOT / "screeners" / "meta_signals" / "meta_screen.py"
RUNS_DIR = ROOT / ".meta-screener" / "runs"
RUN_HISTORY_LIMIT = 30
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
        if not isinstance(screener["id"], str) or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", screener["id"]):
            raise ValueError("Every screener id must use lowercase letters, digits, and single hyphens (start with a letter)")
        if screener["id"] in ids:
            raise ValueError(f"Duplicate screener id: {screener['id']}")
        ids.add(screener["id"])
        if screener["stage"] not in stage_ids:
            raise ValueError(f"Unknown stage {screener['stage']} for {screener['id']}")
        arguments = screener.get("args", [])
        if not isinstance(arguments, list) or any(not isinstance(arg, str) or "\0" in arg for arg in arguments):
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


def command_for(
    screener: dict[str, Any],
    python: str,
    workers: int,
    batch_size: int,
    gap: int,
    result_dir: Path | None = None,
) -> list[str]:
    file_value = screener["file"]
    if not isinstance(file_value, str) or Path(file_value).is_absolute():
        raise ValueError(f"Screener path must be relative to this folder: {file_value}")
    script = (ROOT / file_value).resolve()
    if not script.is_relative_to(ROOT):
        raise ValueError(f"Screener path escapes this folder: {screener['file']}")
    if not script.is_file() or script.suffix != ".py":
        raise ValueError(f"Screener script is missing or not Python: {screener['file']}")
    module = script.relative_to(ROOT).with_suffix("").as_posix().replace("/", ".")
    command = [python, "-m", module, *screener.get("args", [])]
    script_name = script.name
    if script_name == "meta_screen.py":
        command.extend([
            "--workers", str(workers),
            "--batch-size", str(batch_size),
            "--batch-pause-seconds", str(gap),
        ])
        if result_dir is not None:
            command.extend(["--top", "10", "--result-json", str(result_dir / f"{screener['id']}.json")])
    elif script_name == "rotation_screen.py" and result_dir is not None:
        command.extend([
            "--csv-out", str(result_dir / f"{screener['id']}.csv"),
            "--result-json", str(result_dir / f"{screener['id']}.json"),
        ])
    elif script_name == "growth_momentum.py" and result_dir is not None:
        command.extend([
            "--csv-out", str(result_dir / f"{screener['id']}.csv"),
            "--result-json", str(result_dir / f"{screener['id']}.json"),
        ])
    elif script_name in {"short_interest.py", "dividend_analysis.py",
                             "smart_money.py", "insider_activity.py",
                             "altman_z.py", "cash_return.py",
                             "dividend_growth.py"} and result_dir is not None:
        command.extend(["--result-json", str(result_dir / f"{screener['id']}.json")])
    elif script_name == "breadth_rotation.py" and result_dir is not None:
        command.extend(["--result-json", str(result_dir / f"{screener['id']}.json")])
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
        requested_ids = args.screener
        if isinstance(requested_ids, str):
            requested_ids = [requested_ids]
        if not requested_ids:
            raise ValueError("Select screeners with --all, --stage, or --screener")
        if len(set(requested_ids)) != len(requested_ids):
            raise ValueError("Do not select the same screener more than once")
        unknown_ids = [screener_id for screener_id in requested_ids if screener_id not in by_id]
        if unknown_ids:
            raise ValueError(f"Unknown screener(s): {', '.join(unknown_ids)}. Use 'list' to see IDs.")
        selected = [by_id[screener_id] for screener_id in requested_ids]

    selected_in_order = []
    selected_ids = {item["id"] for item in selected}
    for stage in registry["stages"]:
        in_stage = [item for item in selected if item["stage"] == stage["id"]]
        selected_in_order.extend(in_stage)
    if not selected_ids:
        raise ValueError("Selection contains no screeners")
    return selected_in_order


def list_command(registry: dict[str, Any], show_checks: bool) -> int:
    print(f"Meta Screener CLI {version()}")
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
        print("  Run `metascreener list --checks` to see every name and criterion.")
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
    print("Note: json-events runs add --result-json/--top/--csv-out for ranked workflows.")
    return 0


def run_process(
    command: list[str],
    *,
    event_sink: Callable[[dict[str, Any]], None] | None = None,
    run_id: str | None = None,
    screener_id: str | None = None,
) -> tuple[int, bool]:
    rate_limited = False
    try:
        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=environment,
        )
    except OSError as exc:
        message = f"Could not start screener: {exc}"
        if event_sink is None:
            print(message, file=sys.stderr)
        else:
            event_sink({"type": "error", "run_id": run_id, "screener_id": screener_id, "message": message})
        return 127, False

    assert process.stdout is not None
    try:
        for line in process.stdout:
            if event_sink is None:
                print(line, end="", flush=True)
            else:
                event_sink({
                    "type": "output_line",
                    "run_id": run_id,
                    "screener_id": screener_id,
                    "line": line.rstrip("\r\n"),
                })
            if RATE_LIMIT_RE.search(line):
                rate_limited = True
                if process.poll() is None:
                    process.terminate()
        return_code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
        message = "Interrupted; no later screeners were started."
        if event_sink is None:
            print(message, file=sys.stderr)
        else:
            event_sink({"type": "error", "run_id": run_id, "screener_id": screener_id, "message": message})
        return 130, rate_limited
    finally:
        process.stdout.close()
    return return_code, rate_limited


def result_artifact_for(screener: dict[str, Any], result_dir: Path) -> Path | None:
    file_value = screener.get("file")
    if not isinstance(file_value, str) or Path(file_value).is_absolute():
        return None
    script = (ROOT / file_value).resolve()
    if not script.is_relative_to(ROOT):
        return None
    relative_file = script.relative_to(ROOT).as_posix()
    if script.name in {
        "meta_screen.py", "rotation_screen.py", "growth_momentum.py",
        "short_interest.py", "dividend_analysis.py", "breadth_rotation.py",
        "smart_money.py", "insider_activity.py", "altman_z.py",
        "cash_return.py", "dividend_growth.py",
    }:
        return result_dir / f"{screener['id']}.json"
    return None


def read_result_artifact(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"top": [], "summary": None, "report_path": None, "result_error": None}
    if not path.is_file():
        return {"top": [], "summary": None, "report_path": None,
                "result_error": f"Expected result file was not written: {path.name}"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"top": [], "summary": None, "report_path": None,
                "result_error": f"Could not read {path.name}: {exc}"}
    if not isinstance(payload, dict) or not isinstance(payload.get("top"), list):
        return {"top": [], "summary": None, "report_path": None,
                "result_error": f"Invalid result data in {path.name}: expected an object with a top list"}

    top: list[dict[str, Any]] = []
    for row in payload["top"][:10]:
        if not isinstance(row, dict) or not isinstance(row.get("ticker"), str):
            return {"top": [], "summary": None, "report_path": None,
                    "result_error": f"Invalid ranked row in {path.name}: ticker is required"}
        rank = row.get("rank", len(top) + 1)
        name = row.get("name", row["ticker"])
        detail = row.get("detail", "")
        if type(rank) is not int or rank < 1 or not isinstance(name, str) or not isinstance(detail, str):
            return {"top": [], "summary": None, "report_path": None,
                    "result_error": f"Invalid ranked row in {path.name}: rank, name, or detail has wrong type"}
        top.append({
            "rank": rank,
            "ticker": row["ticker"],
            "name": name,
            "detail": detail,
        })
    return {
        "top": top,
        "summary": payload.get("summary") if isinstance(payload.get("summary"), str) else None,
        "report_path": payload.get("report_path") if isinstance(payload.get("report_path"), str) else None,
        "result_error": None,
    }


def write_run_record(record: dict[str, Any], runs_dir: Path | None = None) -> Path:
    directory = RUNS_DIR if runs_dir is None else runs_dir
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{record['run_id']}.json"
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=directory, prefix=".run-", suffix=".tmp", delete=False
        ) as handle:
            temporary_path = handle.name
            json.dump(record, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_path, destination)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)

    history = sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True)
    for old_record in history[RUN_HISTORY_LIMIT:]:
        old_record.unlink()
        old_artifacts = directory / old_record.stem
        if old_artifacts.is_dir():
            shutil.rmtree(old_artifacts)
    return destination


def run_json_command(registry: dict[str, Any], args: argparse.Namespace) -> int:
    run_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def emit(event: dict[str, Any]) -> None:
        payload = {"run_id": run_id, **event}
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)

    try:
        selected = select_screeners(registry, args)
    except ValueError as exc:
        emit({"type": "error", "message": str(exc)})
        emit({"type": "run_finished", "status": "failed", "exit_code": 2,
              "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        return 2

    emit({
        "type": "run_started",
        "ids": [item["id"] for item in selected],
        "started_at": started_at,
    })
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in selected:
        grouped.setdefault(item["stage"], []).append(item)
    active_stages = [stage for stage in registry["stages"] if stage["id"] in grouped]
    results: list[dict[str, Any]] = []
    result_dir = RUNS_DIR / run_id
    result_dir.mkdir(parents=True, exist_ok=True)
    exit_code = 0
    overall_status = "ok"
    stop_after_current = False

    for stage_index, stage in enumerate(active_stages):
        stage_items = grouped[stage["id"]]
        for item_index, item in enumerate(stage_items):
            screener_started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            started_clock = time.monotonic()
            screener_id = item["id"]
            emit({
                "type": "screener_started",
                "screener_id": screener_id,
                "name": item["name"],
                "started_at": screener_started_at,
            })
            try:
                command = command_for(
                    item, args.python, args.workers, args.batch_size, args.gap_seconds, result_dir
                )
                return_code, rate_limited = run_process(
                    command, event_sink=emit, run_id=run_id, screener_id=screener_id
                )
            except ValueError as exc:
                emit({"type": "error", "screener_id": screener_id, "message": str(exc)})
                return_code, rate_limited = 2, False

            result = read_result_artifact(result_artifact_for(item, result_dir))
            elapsed_seconds = round(time.monotonic() - started_clock, 3)
            if rate_limited:
                status = "rate_limited"
                overall_status = "rate_limited"
                exit_code = 2
            elif return_code != 0:
                status = "failed"
                overall_status = "failed"
                exit_code = return_code
            elif result["result_error"]:
                status = "result_error"
                overall_status = "failed"
                exit_code = 1
            else:
                status = "ok"

            screener_result = {
                "screener_id": screener_id,
                "name": item["name"],
                "status": status,
                "exit_code": return_code,
                "elapsed_seconds": elapsed_seconds,
                "summary": result["summary"],
                "report_path": result["report_path"],
                "top": result["top"],
            }
            if result["result_error"]:
                screener_result["result_error"] = result["result_error"]
            results.append(screener_result)
            emit({"type": "screener_finished", **screener_result})

            if rate_limited or (return_code != 0 and not args.continue_on_error) or (result["result_error"] and not args.continue_on_error):
                stop_after_current = True
                break

            if item["yahoo"] and item_index < len(stage_items) - 1:
                emit({
                    "type": "output_line",
                    "screener_id": screener_id,
                    "line": f"Yahoo cooldown: waiting {args.gap_seconds}s before the next screener.",
                })
                time.sleep(args.gap_seconds)

        if stop_after_current:
            break
        if stage_index < len(active_stages) - 1:
            emit({
                "type": "output_line",
                "screener_id": None,
                "line": f"Stage cooldown: waiting {args.gap_seconds}s.",
            })
            time.sleep(args.gap_seconds)

    finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": overall_status,
        "exit_code": exit_code,
        "screeners": results,
    }
    try:
        write_run_record(record)
    except OSError as exc:
        emit({"type": "error", "message": f"Could not save run summary: {exc}"})
        overall_status = "failed"
        exit_code = 1
    emit({
        "type": "leaderboard",
        "top": [{"ticker": t, "appearances": a, "best_rank": b}
                for t, a, b in compute_leaderboard(result_dir, 10)],
    })
    emit({
        "type": "run_finished",
        "status": overall_status,
        "exit_code": exit_code,
        "finished_at": finished_at,
    })
    return exit_code


def run_command(registry: dict[str, Any], args: argparse.Namespace) -> int:
    if getattr(args, "json_events", False):
        return run_json_command(registry, args)

    selected = select_screeners(registry, args)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in selected:
        grouped.setdefault(item["stage"], []).append(item)
    active_stages = [stage for stage in registry["stages"] if stage["id"] in grouped]
    statuses: list[tuple[str, str]] = []
    result_dir = RUNS_DIR / uuid.uuid4().hex
    result_dir.mkdir(parents=True, exist_ok=True)

    for stage_index, stage in enumerate(active_stages):
        stage_items = grouped[stage["id"]]
        print(f"\n=== {stage['name']} ===", flush=True)
        for item_index, item in enumerate(stage_items):
            command = command_for(item, args.python, args.workers, args.batch_size,
                                  args.gap_seconds, result_dir)
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
    board = compute_leaderboard(result_dir, 10)
    if board:
        print("\n=== Leaderboard: most consistent across screeners ===")
        for rank, (ticker, apps, best) in enumerate(board, 1):
            print(f"#{rank:<3} {ticker:<6} {apps}x (best #{best})")
    else:
        print("\nRun `metascreener leaderboard` for the cross-screener top 10.")
    return 0 if all(status == "ok" for _, status in statuses) else 1


def compute_leaderboard(result_dir: Path, top_n: int = 10) -> list[tuple]:
    """Rank tickers by appearances across saved result tops.

    Only measured rows count: rows whose detail starts with "blank" are
    not signals. Ties break on best rank, then ticker. Returns
    ``[(ticker, appearances, best_rank), ...]``.
    """
    counts: dict[str, list] = {}
    try:
        files = sorted(Path(result_dir).glob("*.json"))
    except OSError:
        return []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        for row in payload.get("top") or []:
            if not isinstance(row, dict) or not isinstance(row.get("ticker"), str):
                continue
            if str(row.get("detail") or "").startswith("blank"):
                continue
            rank = row.get("rank")
            entry = counts.setdefault(row["ticker"], [0, 10 ** 9])
            entry[0] += 1
            if type(rank) is int and rank < entry[1]:
                entry[1] = rank
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1][0], kv[1][1], kv[0]))
    return [(ticker, apps, best) for ticker, (apps, best) in ranked[:top_n]]


def leaderboard_command(args: argparse.Namespace) -> int:
    if args.run_id:
        result_dir = RUNS_DIR / args.run_id
        board = compute_leaderboard(result_dir, args.top)
    else:
        try:
            runs = sorted(RUNS_DIR.glob("*.json"),
                          key=lambda item: item.stat().st_mtime_ns, reverse=True)
        except OSError:
            runs = []
        board = []
        for record_path in runs:
            board = compute_leaderboard(RUNS_DIR / record_path.stem, args.top)
            if board:
                break
    if not board:
        print("No ranked screener results found yet; run some screeners first.",
              file=sys.stderr)
        return 1
    print("=== Leaderboard: most consistent across screeners ===")
    for rank, (ticker, apps, best) in enumerate(board, 1):
        print(f"#{rank:<3} {ticker:<6} {apps}x (best #{best})")
    return 0


def add_selection_arguments(parser: argparse.ArgumentParser) -> None:
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="run all default-enabled screeners")
    selection.add_argument("--stage", help="run one stage by ID")
    selection.add_argument("--screener", action="append", help="run a screener by ID; repeat to select multiple")
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
        prog="metascreener",
        description="Open the dashboard or list, plan, and run Meta Screener workflows.",
    )
    parser.add_argument("--version", action="version", version=f"Meta Screener CLI {version()}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="list registered screeners and embedded meta checks")
    list_parser.add_argument("--checks", action="store_true", help="show all individual meta_screen checks")

    plan_parser = subparsers.add_parser("plan", help="print the run order without launching anything")
    add_selection_arguments(plan_parser)

    run_parser = subparsers.add_parser("run", help="run selected screeners sequentially")
    add_selection_arguments(run_parser)
    run_parser.add_argument("--json-events", action="store_true",
                            help="emit JSON Lines run events for the TUI and MCP clients")
    run_parser.add_argument("--continue-on-error", action="store_true",
                            help="continue after ordinary failures; Yahoo rate limits always stop the run")

    board_parser = subparsers.add_parser("leaderboard", help="show tickers most consistent across saved screener results")
    board_parser.add_argument("--run-id", default=None,
                              help="run record id; default: latest run with results")
    board_parser.add_argument("--top", type=int, default=10,
                              help="how many tickers to list (default: 10)")
    return parser


def launch_tui() -> int:
    bun = shutil.which("bun")
    tui_dir = ROOT / "tui"
    if bun is None:
        print("The OpenTUI dashboard requires Bun 1.3 or newer. Install Bun to use bare `metascreener`.",
              file=sys.stderr)
        return 2
    if not (tui_dir / "package.json").is_file():
        print(f"OpenTUI dashboard files are missing from {tui_dir}.", file=sys.stderr)
        return 2
    if not (tui_dir / "node_modules").is_dir():
        print(f"Install the dashboard dependencies with: cd {shlex.quote(str(tui_dir))} && bun install",
              file=sys.stderr)
        return 2

    environment = os.environ.copy()
    environment["META_SCREENER_ROOT"] = str(ROOT)
    environment["META_SCREENER_PYTHON"] = sys.executable
    try:
        return subprocess.call([bun, "run", "start"], cwd=tui_dir, env=environment)
    except OSError as exc:
        print(f"Could not start the OpenTUI dashboard: {exc}", file=sys.stderr)
        return 127


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        return launch_tui()
    args = parser.parse_args(arguments)
    try:
        registry = read_registry()
        if args.command == "list":
            return list_command(registry, args.checks)
        if args.command == "plan":
            return plan_command(registry, args)
        if args.command == "run":
            return run_command(registry, args)
        if args.command == "leaderboard":
            return leaderboard_command(args)
    except ValueError as exc:
        if getattr(args, "json_events", False):
            run_id = uuid.uuid4().hex
            finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            print(json.dumps({"type": "error", "run_id": run_id, "message": str(exc)}, ensure_ascii=False))
            print(json.dumps({"type": "run_finished", "run_id": run_id, "status": "failed",
                              "exit_code": 2, "finished_at": finished_at}, ensure_ascii=False))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
