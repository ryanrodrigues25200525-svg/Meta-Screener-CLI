# Meta Screener CLI 0.3.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an understandable, versioned Python screener repository with a polished OpenTUI dashboard and a local MCP server for managing and running screens.

**Architecture:** Python remains responsible for registry validation, screen execution, pacing, and result extraction. The Bun/OpenTUI process and the Python MCP server both call that shared runner; the TUI consumes its JSON Lines events. A bounded MCP registry API can compose existing checks or register a repository-contained Python workflow without accepting executable source.

**Tech Stack:** Python 3.10+, stdlib `unittest`, optional MCP Python SDK v2, Bun 1.3+, TypeScript, `@opentui/core`, Bun test runner.

**Spec:** `docs/superpowers/specs/2026-10-03-meta-screener-tui-mcp-design.md`

## Global Constraints

- Use only OpenCode Go models `opencode-go/muse-spark-1.3-contributor` and `opencode-go/deepseek-v4.1-flash` for delegated implementation/review.
- Keep work on `codex/meta-screener-polish`; prepare a PR for review and do not merge to `main`.
- Preserve the original checkout and its untracked `.DS_Store`.
- Keep Yahoo-backed work sequential, use one worker, the runner defaults of 8-symbol batches and a 15-second pause for the live validation run, and stop on rate-limit detection without retrying.
- Set `FINANCE_KG_ROOT` to a temporary directory for the live run. Do not write validation output into the user's Finance Knowledge Graph.
- Save runtime summaries and result artifacts under `.meta-screener/`, and keep that directory ignored by Git.
- MCP may update `screeners.json`, but may not write arbitrary Python source or delete source files.
- Run requested tests and static checks; do not claim runtime success without recorded command output.

## File Responsibilities

- `meta_screener_cli.py`: validate and select registered workflows, launch the dashboard with no arguments, preserve direct subcommands, emit structured run events, sequence child processes, and persist run summaries.
- `meta_screen.py`: accept a validated subset of built-in check names for named custom screen profiles and expose a stable top-ranking result for the runner.
- `rotation_screen.py`, `short_interest.py`, and `dividend_analysis.py`: expose their existing ranked output as optional JSON result rows without changing their legacy reports.
- `kg_links.py`: make `load_ticker_map(root=...)` resolve Company notes from the supplied root so `FINANCE_KG_ROOT` works for isolated runs.
- `screeners.json`: remain the versioned source of registered workflow metadata at schema/project version `0.3.0`; validate built-in and custom entries.
- `screener_mcp.py`: expose the shared runner and safe registry operations over local stdio MCP.
- `tui/`: contain the Bun/OpenTUI terminal application; it renders events and never starts screen scripts directly.
- `tests/`: contain focused stdlib Python tests and Bun tests using the project's supported OpenTUI test surface.
- `PYTHON_TOOLS.md`, `archive/`, `README.md`, `CHANGELOG.md`, `VERSION`, `pyproject.toml`, `.gitignore`: document, curate, version, and package the repository.

## Tasks

### Task 1 — Curate and document the Python repository

**Owner:** OpenCode Go Muse Spark 1.3 Contributor. Limit changes to `PYTHON_TOOLS.md`, the listed archive moves and archive README, missing module docstrings, `README.md`, `CHANGELOG.md`, and `VERSION`. Do not modify runner, MCP, TUI, `.gitignore`, or `pyproject.toml` implementation files.

- [ ] Build a concise catalog from actual module docstrings and classify every tracked Python file by purpose.
- [ ] Move only the ten one-off migration/backfill scripts named in the spec into the dated archive; preserve their source and document that they are not normal runnable screens.
- [ ] Add docstrings to `corr_regime.py`, `daily_gaps.py`, and `verify_3m.py` without changing their behavior.
- [ ] Create a `CHANGELOG.md` with a provisional `[Unreleased]` section for the planned work and set `VERSION` to `0.3.0`; leave release-date/finalized entries and `pyproject.toml` to the integration task.
- [ ] Link the catalog and clarify the 17 registered workflows and default-enabled subset in the README.
- [ ] Review only this task's diff for accurate descriptions, unintended content changes, and stray data files.

**Review gate:** Root reviews the catalog against all filenames/docstrings and checks every archive move is content-preserving before accepting the task.

### Task 2 — Add a tested Python runner/event contract

**Owner:** Root agent. Depends on the interface below; do not touch catalog/archive files assigned to Task 1.

- [ ] Write failing `unittest` cases for selection, event shape, result persistence, no-argument TUI launch dispatch, ticker-map root isolation, and ranked-result validation.
- [ ] Define JSON Lines stdout events: `run_started`, `screener_started`, `output_line`, `screener_finished`, `run_finished`, and `error`. Every event includes `run_id`; screener events include `screener_id`. Finish events include status and exit code; successful result events may include `summary`, `report_path`, and `top` rows shaped as `{rank,ticker,name,detail}`.
- [ ] Implement `run --json-events` so stdout contains only JSON Lines, child output is forwarded as `output_line`, and ordinary CLI text behavior remains unchanged without the flag. Allow repeated `--screener ID` arguments to run an explicit list sequentially while preserving existing single-ID usage.
- [ ] Set `PYTHONUNBUFFERED=1` in captured Python child environments so TUI/MCP clients receive progress lines while a screen is running, not only at process exit.
- [ ] Store the final run record under `.meta-screener/runs/<run_id>.json`; use atomic writes and retain at most the 30 most recent records.
- [ ] Extract ranked rows from meta-overlap, fundamental rotation, short interest, and dividend analysis. Add opt-in `--result-json` output to the latter three without changing their existing text/Markdown reports. Pass the rotation CSV path under the per-run `.meta-screener/` directory. Other workflows report summaries/paths without fabricated stock ranks.
- [ ] Support validated custom check subsets in `meta_screen.py` and the registry while preserving the existing full 47-check default. Store selected names as repeated `--check <name>` values in a custom entry's `args`; `meta_screen.py` accepts repeated `--check` values.
- [ ] Pass `FINANCE_KG_ROOT` through the meta-screen ticker-map lookup so temporary validation does not read the user's real vault.
- [ ] Make no-argument `meta-screener` launch `bun run` in `tui/`, pass the active Python executable, and provide a clear missing-Bun/dependency message. Keep `list`, `plan`, and `run` usable without Bun.
- [ ] Run the focused Python tests and inspect normal and JSON event output.

### Task 3 — Build the OpenTUI dashboard

**Owner:** OpenCode Go Muse Spark 1.3 Contributor in `tui/` only. Start after Task 2's JSON Lines contract is fixed; do not edit Python runner files or project-level docs.

- [ ] Write Bun tests for workflow selection, JSON event handling, and narrow-terminal state/layout.
- [ ] Implement an OpenTUI Core dashboard with grouped workflow navigation, a compact status summary, a focused workflow/results pane, and keyboard-help footer.
- [ ] Add keyboard navigation, selection toggles, run selected, run all, details, and clean quit/terminal cleanup.
- [ ] Launch the Python CLI as a child process using the passed interpreter; consume JSON Lines incrementally, show progress, and prevent overlapping runs.
- [ ] Render rankings only from `top` result rows; show an honest summary or report path for non-ranking workflows.
- [ ] Load the latest valid compact run record from `.meta-screener/runs/` at startup so results remain visible after closing and reopening the TUI; never auto-run during startup.
- [ ] Add optional foreground daily refresh, disabled by default, with no background process and no catch-up burst.
- [ ] Lock dependencies and document the Bun install command in `tui/README.md` or the root README assigned to Task 1 only if the root agent explicitly accepts a separate handoff.
- [ ] Run focused Bun tests and inspect a real terminal session at normal and narrow widths.

### Task 4 — Add MCP management tools

**Owner:** OpenCode Go DeepSeek 4.1 Flash. Limit changes to `screener_mcp.py` and `tests/test_screener_mcp.py`; do not edit the runner, TUI, README, `pyproject.toml`, or registry defaults.

- [ ] Write failing tests for tool input validation, custom profile create/remove, path containment, and sequential run delegation.
- [ ] Implement stdio tools to list workflows/checks, plan a run, run one or multiple workflows, create a named profile from existing checks, register an existing in-repo Python workflow, and unregister a workflow without deleting source.
- [ ] Name the tools `list_screeners`, `list_checks`, `plan_screeners`, `run_screeners`, `create_screener`, `register_screener`, and `remove_screener`. Delegate multi-screen runs to `meta_screener_cli.py run --json-events --screener ID ...` through an argument vector using the same Python interpreter; never build a shell command string.
- [ ] Validate IDs, check names, stage IDs, argument shapes, and resolved file paths; reject symlinks and paths outside the repository; update registry atomically.
- [ ] Reuse the same Python runner used by the CLI/TUI and preserve rate-limit behavior.
- [ ] Run focused Python tests and an SDK client/list-tools smoke check without launching Yahoo screeners.

### Task 5 — Integrate and verify end to end

**Owner:** Root agent; delegated contributors must finish and pass review before this task.

- [ ] Review every subagent diff for spec compliance, unrelated changes, registry safety, terminal cleanup, and dependency lock integrity; request focused fixes if needed.
- [ ] Run the complete Python and Bun test suites, static checks, package metadata checks, and `git diff --check`.
- [ ] Add the optional `mcp>=2,<3` extra and `meta-screener-mcp` entry point in `pyproject.toml`; align project metadata at `0.3.0`. Add `.meta-screener/` and `.DS_Store` ignore rules in `.gitignore`.
- [ ] Update `screeners.json` to version `0.3.0` and update the README so bare `meta-screener` launches the TUI, direct commands remain documented, and Bun setup is clear.
- [ ] Finalize the changelog entry, include `.superpowers/` and `tui/node_modules/` ignore rules plus exceptions for tracked TUI JSON manifests, and catalog any new tracked Python files added by the runner, MCP server, and tests.
- [ ] Run the real default-universe `meta-overlap` workflow from the TUI through JSON Lines with one worker, the CLI defaults of batch size 8 and a 15-second pause. Set `FINANCE_KG_ROOT` to a temporary directory; capture the actual ticker ranking, check it matches the saved JSON result, and stop immediately if Yahoo returns a rate limit.
- [ ] Launch MCP over stdio and confirm the tool list and registry operations work against an isolated copy of `screeners.json`.
- [ ] Inspect final TUI behavior at normal and narrow widths, status/error handling, terminal cleanup, docs, changelog, version files, and final Git diff.
- [ ] Reopen the TUI after the live run and confirm it displays the same saved ranking without launching a new Yahoo run.
- [ ] Commit coherent changes to `codex/meta-screener-polish`, push the feature branch, and open a PR for user review. Do not merge to `main`; only create/push a `v0.3.0` tag if the user confirms the PR is ready to release.

## Execution

The user explicitly selected OpenCode Go subagents and restricted model choices to Muse Spark 1.3 Contributor and DeepSeek 4.1 Flash. Execute Tasks 1, 2, and 4 concurrently where file ownership allows. Start Task 3 after the event contract in Task 2 is stable. Finish with the integration/review task before creating the PR.
