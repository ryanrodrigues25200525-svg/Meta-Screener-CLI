# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-10-03

### Added

- `PYTHON_TOOLS.md` catalog of the tracked Python files, grouped by purpose
  and built from each module's own docstring.
- `archive/one-off-migrations/2026/` preserving the ten one-off vault
  repair/backfill scripts as historical source, with a readme describing
  their one-off nature.
- `screeners.json` registry of 17 workflows across 5 stages; 16 are enabled
  by default and `screen-history` is an optional outcome tracker excluded
  from the default all-run.
- CLI workflow selection and inspection: `meta-screener list`
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
- OpenTUI terminal dashboard launched by a bare `meta-screener` invocation
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

- Version metadata aligned at 0.3.0: `VERSION`, `pyproject.toml`
  (`meta-screener-cli`, `requires-python >= 3.10`, `meta-screener` and
  `meta-screener-mcp` console scripts, `mcp` extra), `screeners.json`
  `version`, and the TUI `package.json` version.
- README documents the Python 3.10+/Bun 1.3+ install, the dashboard and its
  keyboard controls, direct CLI selection, Yahoo pacing and cooldowns, the
  optional MCP stdio setup, and local-data limits (portfolio, watchlists,
  credentials, and generated history stay out of the repository).

### Fixed

- `kg_links.company_link` now honors an explicitly supplied empty ticker map
  instead of falling back to the user's default Finance Knowledge Graph index,
  keeping isolated runs within their configured data root.
