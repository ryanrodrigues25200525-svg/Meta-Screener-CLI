# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-04

First stable release: 28 Yahoo-only screeners in 6 stages, family-split
meta screens, cross-screener leaderboard (CLI, TUI panel, MCP event),
one-word `meta-screener` command, and local MCP wiring for AI agents.
Weekly on-demand use; the CLI never places trades.

## [0.7.0] - 2026-10-03

### Added

- `metascreener leaderboard` lists the top 10 tickers most consistent
  across saved screener results (appearances in ranked tops, blanks
  excluded); JSON event runs also emit a `leaderboard` event for TUI/MCP.

### Removed

- Retired the `meta-overlap` full 47-check screen; the 8 `meta-*` family
  screens cover the same checks in runnable pieces. Registry is now
  28 entries (27 enabled by default).

## [0.6.0] - 2026-10-03

### Added

- Five company-signal screeners: `smart-money` (institutional ownership),
  `insider-activity` (buyer/seller counts from insider transactions),
  `altman-z` (balance-sheet safety zones), `cash-return` (FCF plus buyback
  yield), and `dividend-growth` (consecutive payout-increase streaks).
  Registry grows from 24 to 29 entries (28 enabled by default).
  `yahoo_client` gains `holders`, `insider`, and `dividends` ops on the
  shared serial scheduler with rate-limit stop.

## [0.5.0] - 2026-10-03

### Added

- Split `meta-overlap` into 8 family screeners (`meta-momentum`,
  `meta-technical`, `meta-valuation`, `meta-fundamental`, `meta-theme`,
  `meta-insider`, `meta-earnings`, `meta-quality`) covering all 47 checks via
  `--check` filters; `meta-overlap` still runs the full set. Registry grows
  from 16 to 24 entries (23 enabled by default; `screen-history` optional).

- Grouped the 9 meta screeners (`meta-overlap` plus 8 families) into a new
  `meta-signals` stage so the CLI, TUI, and MCP list them as one category;
  `discovery` keeps the fundamental screens. Six stages total.

## [0.4.0] - 2026-10-03

Closes follow-up issues #2 (Yahoo-only screeners), #3 (TUI stderr
diagnostics), and #4 (CI plus runner/TUI edge-case regression tests), and
closes tracker #5.

### Added

- `yahoo_client.py` shared Yahoo Finance client used by every screener: one
  serial scheduler with an on-disk cache and fail-fast stop on Yahoo
  rate-limit responses, with no automatic retries. `yahoo_guard.py` keeps its
  existing helpers and re-exports the shared client for compatibility.
  Per-screener `--tickers` selection (comma-separated symbols) backed by the
  shared built-in universe in `demo_universe.py` as selection input only.
- `.github/workflows/ci.yml` gate running `python -m unittest discover -s tests`
  on Python 3.10 plus `bun install --frozen-lockfile`, `bun test`, and
  `bunx tsc --noEmit` in `tui/` on Bun 1.4.0. CI stays offline from Yahoo and
  independent of the Finance Knowledge Graph, portfolio files, and credentials.
- TUI failed-screener diagnostics: failed workflows show a bounded
  `Diagnostics (stderr):` tail in the detail view, wired from the existing
  `onStderr` runner plumbing into bounded per-screener `stderr` state. Stdout
  stays JSONL-only and stderr is never parsed as events.
- Regression tests: absolute/root-escaping path rejection for
  `command_for`/`result_artifact_for`, empty and missing `screener_id` TUI
  event guards, failing-child stderr capture and bounds, and fake-provider
  Yahoo tests for fundamentals, market breadth, and earnings/news events.

### Changed

- All 16 registry entries are now Yahoo-only (`"yahoo": true`,
  `"provider": "Yahoo Finance via yfinance"`): fundamentals screens read
  Yahoo statements with blank output for missing/mismatched periods instead of
  fabricated growth; breadth and meta-overlap read Yahoo price history/info;
  catalyst-calendar lists only Yahoo earnings dates per ticker; research-frontier
  lists latest Yahoo news per ticker in recency order without invented rankings;
  analyst/short-interest/dividend/options screens fetch Yahoo info and options
  chains for an explicit `--tickers` list or the built-in universe.
- Validated ticker rankings are exposed only for stock screens that produce
  them; context and event screens report status and summary instead.
- Dashboard and CLI labels updated for the Yahoo-only registry: 16 workflows
  across 5 stages, 15 enabled by default, `screen-history` remaining the
  optional outcome tracker excluded from the default all-run.

### Removed

- `macro-calendar` retired from `screeners.json`: Yahoo supplies no macro
  calendar and the static `KNOWN_EVENTS` schedule is not data. The script is
  preserved for reference at `archive/econ_calendar.py`; confirm macro dates
  with official sources (FRED API, central-bank calendars).

### Fixed

- Issue #4: CI gate plus regression coverage for empty/missing `screener_id`
  events and absolute/escaping screener paths.
- Issue #3: failed-screener stderr is now visible and bounded in the TUI
  detail view instead of being silently dropped.
- Issue #2: per-entry `provider` metadata now matches the actual Yahoo source
  in every screen; no screen reads the Finance Knowledge Graph, portfolio
  files, or local calendar notes.

## [0.3.0] - 2026-10-03

### Added

- `PYTHON_TOOLS.md` catalog of the tracked Python files, grouped by purpose
  and built from each module's own docstring.
- Dated session recap and OpenCode handoff in
  `docs/SESSION_RECAP_2026-10-03.md`, including TUI design, validation evidence,
  and phased follow-up work.
- `archive/one-off-migrations/2026/` preserving the ten one-off vault
  repair/backfill scripts as historical source, with a readme describing
  their one-off nature.
- `screeners.json` registry of 17 workflows across 5 stages; 16 are enabled
  by default and `screen-history` is an optional outcome tracker excluded
  from the default all-run.
- `metascreener` no-hyphen console command as the primary CLI name; the existing
  `meta-screener` command remains available as an alias.
- CLI workflow selection and inspection: `metascreener list`
  (with `--checks` for the 47 registered `meta_screen.py` checks), `plan`,
  and `run` with `--all`, `--stage`, or repeatable `--screener`; multiple
  selections run in registry stage order. `plan` prints commands without
  launching screeners or writing files; duplicate and unknown ids are
  rejected.
- Opt-in JSON Lines runner mode (`run --json-events`) emitting `run_started`,
  `screener_started`, `output_line`, `screener_finished`, `run_finished`,
  and `error` events keyed by `run_id`/`screener_id`. Each run saves a
  compact summary record to `.meta-screener/runs/<run_id>.json`; only the
  latest 30 records are kept and `.meta-screener/` is git-ignored.
- Structured top-stock results for the four ranked workflows
  (`meta-overlap`, `fundamental-rotation`, `short-interest`,
  `dividend-analysis`) via `--result-json`: up to 10 `top` rows shaped as
  `{rank, ticker, name, detail}`, plus `summary` and `report_path` where the
  workflow provides them. Other workflows report status with their available
  summary instead of fabricated ranks.
- Yahoo pacing and rate-limit handling: sequential runs with `--workers`,
  `--batch-size`, and a `--gap-seconds` cooldown (10-30s, default 15s)
  between screeners and stages. A detected Yahoo rate limit stops the run
  without automatic retries; `--continue-on-error` continues past ordinary
  failures only.
- OpenTUI terminal dashboard launched by a bare `metascreener` invocation
  (requires Bun 1.3+ with `tui` dependencies installed). It groups
  registered workflows by stage, runs the selection sequentially through
  the `--json-events` stream, shows ticker rankings only for workflows that
  produce a ranked list, restores the latest saved run record at startup for
  display, and offers a details view plus an opt-in daily refresh. It never
  starts screener scripts directly.
- Optional local stdio MCP server (`meta-screener-mcp`, installed via the
  `mcp` extra) exposing `list_screeners`, `list_checks`, `plan_screeners`,
  `run_screeners`, `create_screener`, `register_screener`, and
  `remove_screener`. Runs delegate to the same CLI runner via an argument
  vector with `--json-events`. Creating a screen builds a named
  `meta_screen.py` profile from existing check names; registering requires
  a repository-contained Python file; unregistering keeps the source file
  and no tool writes arbitrary Python source.

### Changed

- Breaking: bare `metascreener` now launches the OpenTUI dashboard (previously ran `meta-overlap`).
- Version metadata aligned at 0.3.0: `VERSION`, `pyproject.toml`
  (`meta-screener-cli`, `requires-python >= 3.10`, `metascreener`, `meta-screener`, and
  `meta-screener-mcp` console scripts, `mcp` extra), `screeners.json`
  `version`, and the TUI `package.json` version.
- README documents the Python 3.10+/Bun 1.3+ install, the dashboard and its
  keyboard controls, direct CLI selection, Yahoo pacing and cooldowns, the
  optional MCP stdio setup, and local-data limits (portfolio, watchlists,
  credentials, and generated history stay out of the repository).

### Fixed

- KG link helpers honor an explicitly supplied empty ticker map instead of
  falling back to the user's default Finance Knowledge Graph index, keeping
  isolated runs within their configured data root.
- Ranked-result adapters identify built-in screens from canonical repository
  paths, so a valid `./rotation_screen.py` registry entry still exports its
  ranking.
- The dashboard ignores run-level output lines that have no screener ID,
  rather than creating a phantom screener log entry for stage cooldowns.
