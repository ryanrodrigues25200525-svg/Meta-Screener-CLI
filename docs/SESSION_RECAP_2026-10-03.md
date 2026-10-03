# Meta Screener CLI — Session Recap and OpenCode Handoff

- **Date:** 2026-10-03
- **Version:** 0.3.0
- **Branch:** `codex/meta-screener-polish`
- **Pull request:** [#1](https://github.com/ryanrodrigues25200525-svg/Meta-Screener-CLI/pull/1) — open against `main`, not merged
- **Implementation baseline before this recap was added:** `cbfd360`

## Status

The v0.3.0 implementation, tests, live validation, and final code review are complete. The PR is ready for human review. No release tag has been created; wait until the PR is approved and the user confirms it is ready for release.

The implementation design and completed-task plan are in:

- [`docs/superpowers/specs/2026-10-03-meta-screener-tui-mcp-design.md`](superpowers/specs/2026-10-03-meta-screener-tui-mcp-design.md)
- [`docs/superpowers/plans/2026-10-03-meta-screener-tui-mcp.md`](superpowers/plans/2026-10-03-meta-screener-tui-mcp.md)
- [`tui/README.md`](../tui/README.md)

## What shipped

### Repository audit

- [`PYTHON_TOOLS.md`](../PYTHON_TOOLS.md) describes all 89 tracked Python files with one unique link per file.
- Ten one-off KG repair/backfill scripts were moved, byte-for-byte, into `archive/one-off-migrations/2026/`. They remain available as historical source and are not registered screeners.
- `CHANGELOG.md`, `VERSION`, `pyproject.toml`, `screeners.json`, and TUI package metadata are aligned at 0.3.0.

### CLI and runner

- Running `metascreener` with no subcommand launches the TUI. `meta-screener` remains as an alias; explicit `list`, `plan`, and `run` still work without Bun.
- `list --checks` reports the 47 built-in `meta_screen.py` checks. The registry contains 17 workflows in five stages; 16 are enabled by default and `screen-history` is optional.
- `run --json-events` emits structured JSON Lines, streams child output without blocking, runs selected workflows in registry order, and saves compact summaries under ignored `.meta-screener/runs/` with a 30-record retention limit.
- Top-ten result adapters are available for `meta-overlap`, `fundamental-rotation`, `short-interest`, and `dividend-analysis`. Other workflows show their available status/summary without invented ticker rankings.
- Yahoo-backed workflows run sequentially with one worker, batches of eight, and a 15-second cooldown by default. A detected rate limit stops the run without automatic retry.

### TUI design and behavior

The TUI uses OpenTUI Core with a restrained dark palette, stage-grouped workflow navigation, a selected-workflow/results pane, status indicators, and a keyboard-help footer. At narrow widths it changes to a single-column focused view.

- `↑/↓` or `j/k`: move focus; `space`: toggle selection.
- `a`: select all; `c`: clear; `r`/`Enter`: run the selection; `R`: run all default-enabled workflows.
- `d`: details/output; `f`: opt in/out of foreground daily refresh; `q`/`Esc`/`Ctrl+C`: quit cleanly.
- Startup preselects only `meta-overlap`, restores the latest valid saved result for display, and does not launch a screener.
- Rankings render only from validated result rows. Non-ranking workflows show status, summary, or report location.
- Daily refresh is opt-in, runs only the current selection, waits 24 hours from opt-in or the last in-session run, and never performs catch-up runs or overlaps an active run.

### MCP server

The optional `mcp` extra installs a local stdio MCP server with seven tools: `list_screeners`, `list_checks`, `plan_screeners`, `run_screeners`, `create_screener`, `register_screener`, and `remove_screener`. It delegates execution to the same CLI runner. Agents can compose named screens from existing checks or register existing repository-contained Python files; tools do not write arbitrary Python or delete registered source files. Setup is documented in [`docs/MCP.md`](MCP.md), which links to the [OpenCode local MCP configuration reference](https://opencode.ai/v2/docs/mcp-servers).

## Verification completed

- Python suite: **50 tests passed** with the optional MCP SDK v2 installed.
- TUI suite: **34 tests passed**; `bunx tsc --noEmit` passed.
- Python bytecode compilation, `metascreener list --checks`, `metascreener plan --all`, and `git diff --check` passed.
- Catalog reconciliation: 89 tracked `.py` files, 89 unique descriptions, no missing or duplicate links.
- TUI snapshots at 110 and 60 columns restored the saved run and displayed its rankings without requesting new market data.
- OpenCode Go final reviews found no Critical or Important findings. The follow-up review left two minor coverage suggestions: explicitly test empty/missing `screener_id` events and add runner-level absolute/traversal path tests. Existing runtime guards remain in place.

## Live-data validation record

The successful real run was `meta-overlap`, using one worker, batch size 8, and 15-second pauses. It completed successfully in 5m38s without a Yahoo rate-limit response. Run ID: `076c12d89dbc4a9da3cd24cec9efdc56`.

| Rank | Ticker | Signal families | Raw checks |
|---:|:---|---:|---:|
| 1 | MU | 4/5 | 15 |
| 2 | NVDA | 4/5 | 14 |
| 3 | COP | 4/5 | 12 |
| 4 | CRM | 4/5 | 12 |
| 5 | GILD | 4/5 | 12 |
| 6 | AMGN | 4/5 | 11 |
| 7 | DIS | 4/5 | 11 |
| 8 | PFE | 4/5 | 10 |
| 9 | TGT | 3/5 | 13 |
| 10 | ELV | 3/5 | 12 |

The saved result JSON, run record, dated note, and TUI snapshot agreed on all ten rows. An earlier keyboard-selection attempt picked optional `screen-history` and exited quickly; workflow selection/order was corrected before the successful run. The live screen was not repeated after the fix to avoid another Yahoo request cycle.

**Data-boundary note:** during that successful run, a helper fell back to the default local company-title index when given an explicitly empty map from the temporary graph root. This caused a read of company-title metadata from the default Finance Knowledge Graph, but no files were written there. Both link helpers now honor an explicit empty map, and regression tests cover that behavior.

## Recommended next phases

### Phase 0 — Human review of PR #1

1. Review the open PR and this recap; decide whether to approve it for merge.
2. If changes are requested, continue on the feature branch, add focused tests, and rerun the recorded checks.
3. Do not merge or create a release tag until the user approves.

**Done when:** the user has accepted the PR or provided specific review changes.

### Phase 1 — Add a safe CI gate

No GitHub Actions workflow exists yet. Add `.github/workflows/ci.yml` that runs on pull requests and pushes to `main`.

1. Set up Python 3.10 (the declared minimum) and install `requirements-screening.txt` plus `.[mcp]`.
2. Run `python -m unittest discover -s tests`.
3. Set up Bun 1.4.0, run `bun install --frozen-lockfile` in `tui/`, then run `bun test` and `bunx tsc --noEmit`.
4. Keep CI offline from Yahoo and independent of the user's Finance Knowledge Graph, portfolio files, and credentials. Do not run root-level `test_driver_map.py` until it has isolated fixtures.

**Done when:** a clean GitHub Actions run passes on the PR without external finance-data requests.

### Phase 2 — Close review follow-ups and improve failure visibility

1. Extend `tui/tests/events.test.ts` to verify empty and missing `screener_id` values do not create TUI entries; keep the guard in `tui/src/events.ts`.
2. Extend `tests/test_cli.py` to verify `command_for` rejects absolute and escaping paths and `result_artifact_for` declines them. Preserve the existing root-containment checks.
3. Wire the existing `onStderr` callback from `tui/src/runner.ts` into the selected-workflow detail/error view in `tui/src/app.ts`, so a failed Python workflow shows useful diagnostics. Keep stdout as JSONL and stderr separate. Add a focused Bun test for a failing workflow's visible diagnostic.
4. Run the full Python suite, Bun suite, TypeScript check, Python compile check, and `git diff --check`.

**Done when:** each review gap has a regression test, a failed workflow exposes its diagnostic, and all checks pass.

### Phase 3 — Validate OpenCode MCP setup in an isolated copy

1. Install the optional extra in a clean project virtual environment.
2. Configure the local `meta-screener-mcp` stdio process with `FINANCE_AI_HOME` pointed at a temporary copy of the registry. Do not write into global OpenCode configuration for this smoke test.
3. From OpenCode, call `list_screeners`, `list_checks`, and `plan_screeners`; create and remove one test profile; verify only the temporary registry changed.
4. Do not invoke Yahoo-backed `run_screeners` in this phase.

**Done when:** OpenCode connects to the server and all registry changes stay within the temporary copy.

### Phase 4 — Build a workflow-by-workflow validation matrix

1. For each of the 17 registry entries, record its provider, required inputs, local files read/written, and whether it produces a ranking or a report.
2. Validate local-data workflows using copied or synthetic fixtures. If required files are absent, record “not run” and the missing prerequisite rather than reading a different user data source.
3. Validate Yahoo-backed workflows one at a time with an explicitly approved universe, one worker, batch size 8, and 15-second pauses. Stop after a rate limit; do not retry automatically.
4. Reopen the TUI after a successful run and confirm it restores the saved result without starting another request.

**Done when:** every workflow has an evidence-backed status (offline tested, live tested with approved inputs, or not run with a precise reason), and no unexpected user-data writes occurred.

### Phase 5 — Release after approval

1. After the PR is approved and merged, confirm `main` contains the intended 0.3.0 commit and the CI checks pass.
2. Only after the user confirms release readiness, create the `v0.3.0` tag on that merged commit and publish release notes from `CHANGELOG.md`.
3. Verify the tag target, GitHub release page, and documented install/launch commands. Do not tag the unmerged feature branch.

## OpenCode continuation prompt

> Continue the Meta Screener CLI work from PR #1 and branch `codex/meta-screener-polish`. Read `docs/SESSION_RECAP_2026-10-03.md`, the linked design spec, and `docs/superpowers/plans/2026-10-03-meta-screener-tui-mcp.md` first. The v0.3.0 implementation is complete and the PR is open but not merged. Work through the recommended next phases, starting with Phase 1 CI and Phase 2 review follow-ups. Use only OpenCode Go Muse Spark 1.3 Contributor or DeepSeek 4.1 Flash for delegated work. Do not merge, tag, or run live Yahoo-backed workflows without the user's approval. Keep all tests and smoke checks isolated from the user's Finance Knowledge Graph and portfolio data.

---

## Addendum — 2026-10-03: v0.4.0 follow-up issues closed (tracker #5)

The history above is preserved as written. This addendum records the
follow-up work that closed issues #2, #3, #4 and tracker #5 on top of the
v0.3.0 base. Version metadata is now aligned at **0.4.0** (`VERSION`,
`pyproject.toml`, `screeners.json`, TUI `package.json`).

- **Issue #4 (CI + edge cases):** `.github/workflows/ci.yml` runs the Python
  suite on 3.10 and `bun test` + `bunx tsc --noEmit` in `tui/` on Bun 1.4.0,
  offline from Yahoo/KG. Regression tests pin absolute/root-escaping path
  rejection in `command_for`/`result_artifact_for` and empty/missing
  `screener_id` TUI event guards.
- **Issue #3 (stderr diagnostics):** failed workflows show a bounded
  `Diagnostics (stderr):` tail in the TUI detail view, wired from the existing
  `onStderr` plumbing; stdout stays JSONL-only.
- **Issue #2 (Yahoo-only screeners):** new shared `yahoo_client.py` serial
  scheduler/cache with fail-fast rate-limit stop is the only Yahoo request
  path. All 16 registry entries carry `"yahoo": true` with matching provider
  metadata. Fundamentals leave blanks on missing/mismatched periods;
  catalyst-calendar lists only Yahoo earnings dates; research-frontier lists
  Yahoo news in recency order without invented rankings; company screens take
  `--tickers` or the built-in universe (`demo_universe.py`) as selection
  input only. `macro-calendar` retired to `archive/econ_calendar.py`.
- **Verification:** `python3 -m unittest discover -s tests` 93 tests OK;
  `bun test` 37 tests pass; `bunx tsc --noEmit` exit 0; `py_compile` on the
  touched modules exit 0; registry grep confirms no screen reads the Finance
  Knowledge Graph, portfolio files, or local calendar notes.
