# Meta Screener CLI 0.3.0 Design

## Goal

Make the repository an understandable home for the existing Python screeners and workflows, give them a polished terminal dashboard, and let local AI agents manage and run registered screens through MCP.

## Current state

- The public GitHub repository has 82 tracked Python files and 17 registered workflows; 16 are enabled by default, while `screen-history` is optional.
- The current `meta-screener` entry runs the core 47-check meta-screen when invoked without arguments. `list`, `plan`, and `run` already use `screeners.json` and sequence Yahoo-backed workflows with cooldowns and stop on detected rate limits.
- Most scripts have useful module docstrings, but three (`corr_regime.py`, `daily_gaps.py`, and `verify_3m.py`) do not.
- Ten repair/backfill scripts are dated or hard-coded Finance Knowledge Graph migrations. They are not registered or imported by active workflows, and several mutate the vault at import time. Preserve them as historical source in an archive rather than deleting them.
- Registered workflows do not all produce ranked stock lists. The dashboard must show ticker rankings only when the workflow actually computes one; market context, calendars, and research workflows need status, metrics, or report summaries instead.

## Design

### Repository guide and history

- Add `PYTHON_TOOLS.md`, grouped by purpose, with a linked filename and concise description for every tracked `.py` file, including archived files.
- Add one-line module docstrings to the three undocumented scripts.
- Move the following files into a dated archive with a short readme describing their one-off nature: `kg_repair.py` through `kg_repair5.py`, `backfill_comp.py`, `backfill_comp2.py`, `backfill_verdicts_20260912.py`, `repair_verdict_fields_20260912.py`, and `driver_taxonomy_fix.py`.
- Keep reusable maintenance tools such as `fix_wrapped_links.py`, `kg_validate.py`, `graph_index.py`, and `kg_links.py` active.
- Update the README to link to the catalog and explain the runnable workflow registry. Add a Keep a Changelog style `CHANGELOG.md` and align `VERSION` and package metadata at `0.3.0`.

### Python runner and saved run data

- Keep Python as the source of truth for screen selection, registry validation, execution order, and Yahoo pacing.
- Preserve explicit `list`, `plan`, and `run` subcommands. A bare `meta-screener` starts the dashboard; `meta-screener run --screener meta-overlap` remains the direct core-screen command.
- Add an opt-in JSON Lines event mode for run start, workflow start/output/finish, and overall finish. The dashboard will consume this contract instead of scraping terminal formatting.
- Save compact run summaries and known structured rankings under an ignored `.meta-screener/` directory. Keep generated files out of Git and outside the user's Finance Knowledge Graph during validation.
- Add stable result adapters for the core meta-screen, fundamental rotation, short-interest, and dividend workflows; each already ranks names in its current output. For workflows with no stock ranking, show their status, useful summary, and report location.
- Run multiple selected workflows sequentially. Do not overlap runs. Reuse the runner's cooldown and rate-limit stop behavior.

### OpenTUI dashboard

- Add a Bun/TypeScript frontend under `tui/` using OpenTUI Core. The Python entry point launches Bun for the no-argument path and passes the active Python interpreter to the UI so child runs use the same environment.
- Use a restrained dark palette, clear hierarchy, compact status badges, and bordered panels: grouped workflow navigation on the left, selected workflow details and recent results on the right, and a keyboard-help/status footer.
- Preserve registry order between visible rows and keyboard focus. Preselect only the first default-enabled workflow (`meta-overlap`); allow selecting more, and keep a separate run-all action.
- Support keyboard navigation, one-screen and multi-screen runs, run status/progress, result inspection, and clean quit/terminal restoration. Provide a readable narrow-terminal layout.
- Load the latest valid compact run summary from `.meta-screener/runs/` at startup without executing any screener.
- Offer periodic refresh as an opt-in foreground setting for the current selection with a conservative 24-hour interval. It never starts a background service or catches up missed runs; an active run must finish before another starts.
- If Bun or the UI dependencies are unavailable, print a direct setup instruction. Explicit Python CLI subcommands remain usable without Bun.

### MCP server

- Add an optional local stdio MCP server using the official Python SDK. Keep the SDK an optional install extra so the existing Python CLI does not require MCP dependencies.
- Expose tools to list workflows and built-in checks, preview a run plan, run one or more registered workflows sequentially, create a named custom screen from existing meta-screen check names, register an existing repository-contained `.py` workflow, and remove a workflow from the registry.
- Validate IDs, check names, stages, argument types, and resolved paths at the boundary. Restrict registration to Python files inside the repository. Write registry changes atomically.
- Removal only unregisters a workflow; it does not delete source files. Screen creation composes existing checks and does not accept executable Python source.
- MCP and TUI call the same Python runner so ordering, output, and Yahoo rate-limit handling stay consistent.

## Dependencies and compatibility

- Preserve Python 3.10+ support.
- The TUI requires Bun 1.3+ and its locked OpenTUI dependencies. The current environment has Bun 1.4.0; current Node is below OpenTUI's documented Node minimum, so use Bun.
- The MCP extra uses the current stable Python SDK v2 line (`mcp>=2,<3`) and stdio transport.
- Keep repository changes on an isolated `codex/meta-screener-polish` branch. Prepare a pull request for review; do not merge it.

## Verification

- Add focused Python tests for registry validation, safe screen creation/removal, structured runner events, and result parsing; add Bun tests for selection, event handling, and narrow-terminal rendering where practical.
- Run the Python and Bun test suites and static checks.
- Run one real `meta-overlap` screener through the dashboard with one worker, 25-symbol batches, and the existing 10-second cooldown. Set `FINANCE_KG_ROOT` to a temporary directory so the test does not write into the user's Finance Knowledge Graph. Keep the generated `rotation_history.csv` and run summaries inside the isolated worktree or its ignored run-data directory.
- If Yahoo reports a rate limit, stop immediately and report the run as incomplete; do not retry automatically.
- Inspect the final Git diff and confirm the original checkout and its untracked `.DS_Store` remain untouched.

## Risks and limits

- OpenTUI adds a Bun runtime and native package dependency to the dashboard path; the Python CLI remains available independently.
- Several registered workflows are reports or market-context summaries, not stock-ranking screeners, so their cards will not invent ticker rankings.
- The MCP tools can change the versioned workflow registry but cannot delete source files or inject arbitrary Python through a tool call.
- The real Yahoo integration run may take several minutes or fail due to provider availability or rate limiting.
