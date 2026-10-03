#!/usr/bin/env python3
"""Local stdio MCP server for managing and running Meta Screener workflows.

The server exposes a small, boundary-validated tool surface over the
``screeners.json`` registry.  Screen execution is delegated to the same
``meta_screener_cli.py`` runner used by the CLI and TUI, launched through an
argument vector with the current Python interpreter.  No shell string is ever
constructed.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from subprocess import PIPE, STDOUT, Popen
from typing import Any

try:  # Official MCP Python SDK v2 line.
    from mcp.server import MCPServer
except ImportError as exc:  # pragma: no cover - exercised only without the extra.
    raise ImportError(
        "screener_mcp requires the optional MCP Python SDK v2 extra. "
        "Install it with: pip install 'meta-screener-cli[mcp]' (mcp>=2,<3)."
    ) from exc


ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
RATE_LIMIT_RE = re.compile(
    r"too many requests|rate.?limit|YFRateLimitError|HTTP(?:Error)?\s*429|429\s*Client\s*Error",
    re.IGNORECASE,
)
REQUIRED_SCREENER_FIELDS = ("id", "name", "file", "stage", "description", "provider")
REGISTRY_NAME = "screeners.json"
META_SCREEN_FILE = "meta_screen.py"


# ---------------------------------------------------------------------------
# Repository and registry helpers
# ---------------------------------------------------------------------------
def repository_root() -> Path:
    """Return the repository root the MCP server should manage.

    ``FINANCE_AI_HOME`` is honoured first so an isolated registry can be used,
    matching ``meta_screener_cli.find_project_root``.  Otherwise the directory
    containing this module is used.
    """
    configured = os.environ.get("FINANCE_AI_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parent


def _registry_path(root: Path) -> Path:
    return Path(root) / REGISTRY_NAME


def _read_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def read_registry(root: Path) -> dict[str, Any]:
    """Read and structurally validate the registry at ``root``."""
    registry = _read_json(_registry_path(root))
    if not isinstance(registry, dict):
        raise ValueError(f"{REGISTRY_NAME} must contain a JSON object")
    _validate_registry_structure(registry)
    return registry


def _validate_registry_structure(registry: dict[str, Any]) -> None:
    stages = registry.get("stages")
    screeners = registry.get("screeners")
    if not isinstance(stages, list) or not isinstance(screeners, list):
        raise ValueError("screeners.json must contain 'stages' and 'screeners' lists")

    stage_ids: set[str] = set()
    for stage in stages:
        if not isinstance(stage, dict) or not stage.get("id"):
            raise ValueError("Every stage must have a unique, non-empty id")
        if not isinstance(stage["id"], str) or not ID_RE.match(stage["id"]):
            raise ValueError(f"Invalid stage id: {stage.get('id')!r}")
        if stage["id"] in stage_ids:
            raise ValueError(f"Duplicate stage id: {stage['id']}")
        stage_ids.add(stage["id"])

    screener_ids: set[str] = set()
    for screener in screeners:
        if not isinstance(screener, dict):
            raise ValueError("Every screener entry must be an object")
        if any(not screener.get(key) for key in REQUIRED_SCREENER_FIELDS):
            raise ValueError(f"Screener entry is missing one of {REQUIRED_SCREENER_FIELDS}")
        screener_id = screener["id"]
        if not isinstance(screener_id, str) or not ID_RE.match(screener_id):
            raise ValueError(f"Invalid screener id: {screener_id!r}")
        if screener_id in screener_ids:
            raise ValueError(f"Duplicate screener id: {screener_id}")
        screener_ids.add(screener_id)
        if screener["stage"] not in stage_ids:
            raise ValueError(f"Unknown stage {screener['stage']} for {screener_id}")
        for flag in ("yahoo", "default_enabled"):
            if not isinstance(screener.get(flag), bool):
                raise ValueError(f"{flag} must be a boolean for {screener_id}")
        args = screener.get("args", [])
        if not isinstance(args, list) or any(not isinstance(item, str) for item in args):
            raise ValueError(f"args must be a list of strings for {screener_id}")
        for key in ("requirements", "reads", "writes"):
            value = screener.get(key, [])
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ValueError(f"{key} must be a list of strings for {screener_id}")


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically using a sibling temp file."""
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(dir=directory, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def write_registry(root: Path, registry: dict[str, Any]) -> None:
    """Validate and atomically persist ``registry`` at ``root``."""
    _validate_registry_structure(registry)
    text = json.dumps(registry, indent=2, ensure_ascii=False) + "\n"
    _atomic_write(_registry_path(root), text)


def _known_stages(registry: dict[str, Any]) -> list[str]:
    return [stage["id"] for stage in registry["stages"]]


def _known_checks(root: Path) -> dict[str, tuple[str, str]]:
    """Return ``{name: (category, description)}`` parsed from meta_screen.py."""
    meta_screen = Path(root) / META_SCREEN_FILE
    try:
        source = meta_screen.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read {meta_screen}: {exc}") from exc
    try:
        tree = ast.parse(source, filename=str(meta_screen))
    except SyntaxError as exc:
        raise ValueError(f"Cannot parse {meta_screen}: {exc}") from exc

    checks: dict[str, tuple[str, str]] = {}
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
            name_arg, category_arg = decorator.args[0], decorator.args[1]
            if not (isinstance(name_arg, ast.Constant) and isinstance(name_arg.value, str)):
                continue
            category = (
                category_arg.value
                if isinstance(category_arg, ast.Constant) and isinstance(category_arg.value, str)
                else "other"
            )
            if category == "theme":
                description = (
                    "Theme member; passes when its theme basket beats SPY by >2 percentage points "
                    "over one month and has positive three-month return."
                )
            else:
                description = name_arg.value
            checks[name_arg.value] = (category, description)
    return checks


def _normalize_ids(registry: dict[str, Any], screener_ids: Any) -> list[str]:
    if isinstance(screener_ids, str):
        candidates = [screener_ids]
    elif isinstance(screener_ids, (list, tuple)):
        candidates = list(screener_ids)
    else:
        raise ValueError("screener_ids must be a screener id or a list of screener ids")

    ids: list[str] = []
    known = {item["id"] for item in registry["screeners"]}
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate:
            raise ValueError(f"Invalid screener id: {candidate!r}")
        if candidate not in known:
            raise ValueError(f"Unknown screener '{candidate}'. Use list_screeners to see IDs.")
        if candidate in ids:
            raise ValueError(f"Duplicate screener id in selection: {candidate}")
        ids.append(candidate)
    if not ids:
        raise ValueError("Select at least one screener")
    return ids


def _order_by_stage(registry: dict[str, Any], screener_ids: list[str]) -> list[dict[str, Any]]:
    selected = set(screener_ids)
    ordered: list[dict[str, Any]] = []
    for stage in registry["stages"]:
        ordered.extend(
            item for item in registry["screeners"] if item["id"] in selected and item["stage"] == stage["id"]
        )
    return ordered


def _build_run_command(root: Path, screener_ids: list[str], python: str | None = None) -> list[str]:
    """Build the argument vector for a sequential multi-screener run."""
    interpreter = python or sys.executable
    command = [interpreter, str(Path(root) / "meta_screener_cli.py"), "run", "--json-events"]
    for screener_id in screener_ids:
        command.extend(["--screener", screener_id])
    return command


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
def _list_screeners(root: Path) -> dict[str, Any]:
    registry = read_registry(root)
    stages = []
    for stage in registry["stages"]:
        entries = [item for item in registry["screeners"] if item["stage"] == stage["id"]]
        if not entries:
            continue
        stages.append(
            {
                "id": stage["id"],
                "name": stage.get("name", stage["id"]),
                "screeners": [
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "file": item["file"],
                        "yahoo": item["yahoo"],
                        "default_enabled": item["default_enabled"],
                        "provider": item.get("provider", ""),
                        "args": list(item.get("args", [])),
                    }
                    for item in entries
                ],
            }
        )
    return {"version": registry.get("version"), "stages": stages}


def _list_checks(root: Path) -> dict[str, Any]:
    checks = _known_checks(root)
    entries = [
        {"name": name, "category": category, "description": description}
        for name, (category, description) in sorted(checks.items(), key=lambda item: item[1][0])
    ]
    return {"count": len(entries), "checks": entries}


def _plan_screeners(root: Path, screener_ids: Any) -> dict[str, Any]:
    registry = read_registry(root)
    ids = _normalize_ids(registry, screener_ids)
    ordered = _order_by_stage(registry, ids)
    ordered_ids = [item["id"] for item in ordered]
    plan = []
    for item in ordered:
        plan.append(
            {
                "id": item["id"],
                "name": item["name"],
                "stage": item["stage"],
                "file": item["file"],
                "yahoo": item["yahoo"],
                "provider": item.get("provider", ""),
                "args": list(item.get("args", [])),
                "command": [sys.executable, str(Path(root) / "meta_screener_cli.py"), "run", "--json-events", "--screener", item["id"]],
            }
        )
    return {
        "screeners": ids,
        "ordered_ids": ordered_ids,
        "command": _build_run_command(root, ordered_ids),
        "plan": plan,
    }


def _run_screeners(root: Path, screener_ids: Any, python: str | None = None) -> dict[str, Any]:
    """Run one or more screeners sequentially through the shared CLI runner."""
    registry = read_registry(root)
    ids = _normalize_ids(registry, screener_ids)
    ids = [item["id"] for item in _order_by_stage(registry, ids)]
    command = _build_run_command(root, ids, python=python)

    try:
        process = Popen(
            command,
            cwd=str(root),
            stdout=PIPE,
            stderr=STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except OSError as exc:
        raise RuntimeError(f"Could not start meta_screener_cli.py: {exc}") from exc

    events: list[dict[str, Any]] = []
    raw_output: list[str] = []
    rate_limited = False
    assert process.stdout is not None
    try:
        for line in process.stdout:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                raw_output.append(stripped)
                parsed = None
            if isinstance(parsed, dict):
                events.append(parsed)
            elif parsed is not None:
                raw_output.append(stripped)
            if RATE_LIMIT_RE.search(stripped):
                rate_limited = True
                if process.poll() is None:
                    process.terminate()
        return_code = process.wait()
    except BaseException:
        if process.poll() is None:
            process.terminate()
            process.wait()
        raise

    return {
        "screeners": ids,
        "command": command,
        "returncode": return_code,
        "rate_limited": rate_limited,
        "ok": return_code == 0 and not rate_limited,
        "events": events,
        "raw_output": raw_output,
    }


def _create_screener(
    root: Path,
    screener_id: str,
    name: str,
    checks: Any,
    description: str | None = None,
) -> dict[str, Any]:
    registry = read_registry(root)
    stage_id = "discovery"
    if stage_id not in _known_stages(registry):
        raise ValueError(f"Registry has no '{stage_id}' stage for custom screens")

    _validate_new_id(registry, screener_id)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string")
    if not isinstance(checks, (list, tuple)) or not checks:
        raise ValueError("checks must be a non-empty list of check names")

    known_checks = _known_checks(root)
    selected: list[str] = []
    for check in checks:
        if not isinstance(check, str) or not check:
            raise ValueError(f"Invalid check name: {check!r}")
        if check not in known_checks:
            raise ValueError(f"Unknown meta_screen check: {check!r}")
        if check in selected:
            raise ValueError(f"Duplicate check name: {check!r}")
        selected.append(check)

    args: list[str] = []
    for check in selected:
        args.extend(["--check", check])

    entry = {
        "id": screener_id,
        "name": name.strip(),
        "file": META_SCREEN_FILE,
        "stage": stage_id,
        "description": (description or f"Custom meta-screen profile: {', '.join(selected)}.").strip(),
        "provider": "Yahoo Finance via yfinance",
        "yahoo": True,
        "requirements": ["yfinance", "pandas", "numpy"],
        "reads": ["Finance Knowledge Graph company/theme notes"],
        "writes": [],
        "default_enabled": False,
        "args": args,
    }
    registry["screeners"].append(entry)
    write_registry(root, registry)
    return {"created": entry}


def _register_screener(
    root: Path,
    screener_id: str,
    name: str,
    file: str,
    stage: str,
    description: str | None = None,
    provider: str | None = None,
    yahoo: bool = False,
    default_enabled: bool = False,
    args: Any = None,
    requirements: Any = None,
    reads: Any = None,
    writes: Any = None,
) -> dict[str, Any]:
    registry = read_registry(root)
    _validate_new_id(registry, screener_id)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string")
    if stage not in _known_stages(registry):
        raise ValueError(f"Unknown stage {stage!r}; valid stages: {', '.join(_known_stages(registry))}")
    for flag_name, flag_value in (("yahoo", yahoo), ("default_enabled", default_enabled)):
        if not isinstance(flag_value, bool):
            raise ValueError(f"{flag_name} must be a boolean")

    resolved = _resolve_repo_file(root, file)
    argument_list = _validate_string_list("args", args if args is not None else [])

    entry = {
        "id": screener_id,
        "name": name.strip(),
        "file": file,
        "stage": stage,
        "description": (description or f"Repository workflow {file}.").strip(),
        "provider": provider or "Repository Python workflow",
        "yahoo": yahoo,
        "requirements": _validate_string_list("requirements", requirements if requirements is not None else []),
        "reads": _validate_string_list("reads", reads if reads is not None else []),
        "writes": _validate_string_list("writes", writes if writes is not None else []),
        "default_enabled": default_enabled,
        "args": argument_list,
    }
    registry["screeners"].append(entry)
    write_registry(root, registry)
    return {"registered": entry, "resolved_file": str(resolved)}


def _remove_screener(root: Path, screener_id: str) -> dict[str, Any]:
    registry = read_registry(root)
    matches = [item for item in registry["screeners"] if item["id"] == screener_id]
    if not matches:
        raise ValueError(f"Unknown screener '{screener_id}'. Use list_screeners to see IDs.")
    registry["screeners"] = [item for item in registry["screeners"] if item["id"] != screener_id]
    write_registry(root, registry)
    return {"removed": matches[0], "source_deleted": False}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def _validate_new_id(registry: dict[str, Any], screener_id: Any) -> None:
    if not isinstance(screener_id, str) or not ID_RE.match(screener_id):
        raise ValueError(
            f"Invalid screener id {screener_id!r}; use lowercase letters, digits, and single hyphens."
        )
    if any(item["id"] == screener_id for item in registry["screeners"]):
        raise ValueError(f"Screener id already registered: {screener_id}")


def _validate_string_list(field: str, value: Any) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be a list of strings")
    return list(value)


def _resolve_repo_file(root: Path, file: Any) -> Path:
    if not isinstance(file, str) or not file.strip():
        raise ValueError("file must be a non-empty string")
    candidate = Path(file)
    if candidate.is_absolute():
        raise ValueError(f"Screener file must be repository-relative: {file!r}")

    root_resolved = Path(root).resolve()
    try:
        resolved = (root_resolved / candidate).resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"Screener file does not exist: {file!r}") from exc
    except OSError as exc:
        raise ValueError(f"Cannot resolve screener file {file!r}: {exc}") from exc

    if not resolved.is_relative_to(root_resolved):
        raise ValueError(f"Screener file escapes the repository: {file!r}")
    if not resolved.is_file():
        raise ValueError(f"Screener path is not a regular file: {file!r}")
    if resolved.suffix != ".py":
        raise ValueError(f"Screener file must be a Python file: {file!r}")
    return resolved


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
def build_server() -> MCPServer:
    """Build the stdio MCP server exposing the registry management tools."""
    server = MCPServer(
        name="meta-screener",
        instructions=(
            "Manage and run Meta Screener workflows registered in screeners.json. "
            "Listing and planning never launch screeners; run_screeners delegates to the "
            "shared rate-limited Python runner."
        ),
    )

    @server.tool(description="List registered screener workflows grouped by stage.")
    def list_screeners() -> dict[str, Any]:
        return _list_screeners(repository_root())

    @server.tool(description="List the built-in meta_screen check names, categories, and criteria.")
    def list_checks() -> dict[str, Any]:
        return _list_checks(repository_root())

    @server.tool(description="Preview the ordered run plan for one or more registered screeners without launching them.")
    def plan_screeners(screener_ids: list[str]) -> dict[str, Any]:
        return _plan_screeners(repository_root(), screener_ids)

    @server.tool(description="Run one or more registered screeners sequentially through the shared runner.")
    def run_screeners(screener_ids: list[str]) -> dict[str, Any]:
        return _run_screeners(repository_root(), screener_ids)

    @server.tool(description="Create a named custom meta_screen profile from existing check names.")
    def create_screener(
        screener_id: str,
        name: str,
        checks: list[str],
        description: str | None = None,
    ) -> dict[str, Any]:
        return _create_screener(repository_root(), screener_id, name, checks, description)

    @server.tool(description="Register an existing repository-contained Python workflow in the registry.")
    def register_screener(
        screener_id: str,
        name: str,
        file: str,
        stage: str,
        description: str | None = None,
        provider: str | None = None,
        yahoo: bool = False,
        default_enabled: bool = False,
        args: list[str] | None = None,
        requirements: list[str] | None = None,
        reads: list[str] | None = None,
        writes: list[str] | None = None,
    ) -> dict[str, Any]:
        return _register_screener(
            repository_root(),
            screener_id,
            name,
            file,
            stage,
            description=description,
            provider=provider,
            yahoo=yahoo,
            default_enabled=default_enabled,
            args=args,
            requirements=requirements,
            reads=reads,
            writes=writes,
        )

    @server.tool(description="Unregister a screener workflow without deleting its source file.")
    def remove_screener(screener_id: str) -> dict[str, Any]:
        return _remove_screener(repository_root(), screener_id)

    return server


def main() -> None:
    """Run the MCP server over local stdio transport."""
    build_server().run("stdio")


if __name__ == "__main__":
    main()
