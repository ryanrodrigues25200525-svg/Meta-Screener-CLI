# Fix Remaining Open Issues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close GitHub issues #2, #3, #4 (and tracker #5) on top of v0.3.0 PR #1 branch with Yahoo-only screeners, TUI stderr diagnostics, and CI plus regression tests.

**Architecture:** Keep the sequential `metascreener run --json-events` runner and OpenTUI JSONL contract unchanged; add a shared `yahoo_client.py` serial scheduler/cache with fail-fast rate-limit stop used by every screener; rewrite six local workflows to Yahoo-only sources (or retire where Yahoo has no equivalent); wire existing `onStderr` plumbing into TUI state and detail view with bounds; add `.github/workflows/ci.yml` with network-free deterministic tests.

**Tech Stack:** Python >=3.10 (`yfinance>=1.4.1,<3`, `pandas>=2.2,<3`, `numpy>=1.26,<3`, optional `mcp>=2,<3`), Bun 1.4.0 with `@opentui/core@0.5.14`, `bun test`, `bunx tsc --noEmit`, `python -m unittest discover -s tests`.

**Spec:** GitHub issues #2 (Yahoo-backed, Yahoo-only per 2026-10-03 user decision), #3 (stderr bug), #4 (CI + edge cases), tracker #5, PR #1 v0.3.0 base (`origin/codex/meta-screener-polish` at `4e5faab`).

## Global Constraints

- All automated tests use fake/injected providers and temporary inputs; they do not call Yahoo or read the user's Finance Knowledge Graph, portfolio files, or credentials.
- Do not run Yahoo-backed screeners or depend on Finance Knowledge Graph, portfolio files, or credentials in CI.
- Yahoo requests from all workflows share the same serial scheduler/cache and rate-limit stop behavior; no screen uses an unthrottled direct request path; stop on Yahoo rate-limit response and do not retry automatically.
- Unavailable/mismatched Yahoo data remains blank instead of fabricated; financial statement screens preserve within-company period comparisons.
- Meaningful stock screens expose validated rankings; context/event screens do not invent stock rankings.
- Keep stderr out of stdout event parsing and preserve line-buffer separation in TUI.
- Bound displayed diagnostics lines/length to prevent TUI growth without limit.
- Python version floor >=3.10; Bun locked deps via `tui/bun.lock` with `--frozen-lockfile` in CI.

## Review Focus

- Yahoo financials with missing quarters/TTM mismatches rendering blank instead of fabricated growth — reasonable person expects blank, not invented numbers.
- Yahoo earnings calendar returning no events for a ticker showing empty catalyst list, not fake catalysts.
- Macro-calendar retired (Yahoo supplies no macro calendar) — person running `--all` expects no fake FOMC/CPI from static list.
- Screener failing with 500-line traceback showing only bounded tail in TUI detail, not full dump or nothing.
- `screeners.json` with `yahoo:true` but script still importing `kg_links` or reading `~/Documents/Finance Knowledge Graph` — metadata must match actual source.

---

### Task 1: CI workflow and runner/TUI edge-case regression tests (Issue #4)

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `tests/test_cli.py`
- Modify: `tui/tests/events.test.ts`

**Interfaces:**
- Consumes: existing `meta_screener_cli.command_for(screener, python, workers, batch_size, gap, result_dir) -> list[str]`, `meta_screener_cli.result_artifact_for(screener, result_dir) -> Path | None`, `tui/src/events.applyEvent(state, event)`.
- Produces: CI proves `python -m unittest discover -s tests`, `bun test`, `bunx tsc --noEmit` pass network-free; new tests pin path rejection and empty/missing `screener_id` guard.

- [ ] **Step 1: Write failing Python test for absolute and root-escaping paths**

```python
def test_command_for_rejects_absolute_and_escaping_paths(self):
    with self.assertRaises(ValueError):
        cli.command_for({"id": "x", "file": "/abs.py", "args": []}, sys.executable, 1, 8, 15)
    with self.assertRaises(ValueError):
        cli.command_for({"id": "x", "file": "../outside.py", "args": []}, sys.executable, 1, 8, 15)

def test_result_artifact_for_declines_absolute_and_escaping_paths(self):
    self.assertIsNone(cli.result_artifact_for({"id": "x", "file": "/abs.py"}, Path("/tmp")))
    self.assertIsNone(cli.result_artifact_for({"id": "x", "file": "../outside.py"}, Path("/tmp")))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_cli -v`
Expected: FAIL (no such tests yet; new tests fail or missing coverage confirmed)

- [ ] **Step 3: Implement tests in `tests/test_cli.py` (no production change needed — guards at `meta_screener_cli.py:148-152` and `335-341` already exist)**

Add the two tests above using temp `result_dir`; keep deterministic, no Yahoo/KG.

- [ ] **Step 4: Write failing TUI test for empty/missing screener_id**

```typescript
test("run-level output with empty/missing screener_id creates no entry", () => {
  const s1 = blankRunState();
  applyEvent(s1, { type: "output_line", run_id: "r", screener_id: "", line: "Stage cooldown" } as any);
  expect(Object.keys(s1.byScreener)).toEqual([]);
  const s2 = blankRunState();
  applyEvent(s2, { type: "output_line", run_id: "r", line: "Stage cooldown" } as any);
  expect(Object.keys(s2.byScreener)).toEqual([]);
});
```

- [ ] **Step 5: Run TUI test to verify it fails**

Run: `(cd tui && bun test tests/events.test.ts)`
Expected: FAIL (empty-string case creates `""` entry because guard only covers `null`; missing-key case may also create entry)

- [ ] **Step 6: Fix `tui/src/events.ts:77-82` guard to also reject missing/undefined (empty-string already rejected by `length===0`; ensure `undefined` key path returns early)**

One-line guard tightening; no new event types.

- [ ] **Step 7: Create `.github/workflows/ci.yml`**

```yaml
name: ci
on:
  pull_request:
  push:
    branches: [main]
jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.10"}
      - run: pip install -r requirements-screening.txt
      - run: pip install -e ".[mcp]"
      - run: python -m unittest discover -s tests
  tui:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: oven-sh/setup-bun@v2
        with: {bun-version: "1.4.0"}
      - run: bun install --frozen-lockfile
        working-directory: tui
      - run: bun test
        working-directory: tui
      - run: bunx tsc --noEmit
        working-directory: tui
```

Do not add Yahoo/KG/portfolio steps.

- [ ] **Step 8: Run full verification**

Run: `python3 -m unittest discover -s tests` Expected: 50+ tests PASS
Run: `(cd tui && bun test)` Expected: 34+ tests PASS
Run: `(cd tui && bunx tsc --noEmit)` Expected: exit 0

- [ ] **Step 9: Commit**

```bash
git add .github/workflows/ci.yml tests/test_cli.py tui/tests/events.test.ts tui/src/events.ts
git commit -m "test: add CI and regression tests for path and event edge cases"
```

### Task 2: TUI failed-screener stderr diagnostics (Issue #3)

**Files:**
- Modify: `tui/src/types.ts:90-97`
- Modify: `tui/src/events.ts`
- Modify: `tui/src/runner.ts:70-78,101-104`
- Modify: `tui/src/app.ts:59-78,192-220`
- Modify: `tui/src/layout.ts:99-106`
- Test: `tui/tests/runner.test.ts`

**Interfaces:**
- Consumes: `startRunner(opts:{python,root,ids,active,state,onEvent,onStderr?})`, `applyEvent(state, event)`, `ScreenerRunState{status,exitCode,summary,reportPath,top,log}`.
- Produces: `ScreenerRunState.stderr: string[]` (bounded), `applyStderr(state, screener_id, line)` or extended `applyEvent` path, `detailText()` shows `Diagnostics:` section for failed entries, `launch()` wires `onStderr` to focused/active screener.

- [ ] **Step 1: Write failing test for failing child with stderr**

```typescript
test("failing child stderr is captured and bounded", async () => {
  const state = blankRunState();
  const seen: string[] = [];
  await startRunner({
    python: "bun", root: ".", ids: ["demo"],
    active: null, state,
    onEvent: () => {},
    onStderr: (line) => seen.push(line),
  });
  // driven by stub child that exits 1 with stderr lines; assert seen contains diagnostic
  expect(seen.join("\n")).toMatch(/traceback|boom/i);
});
```

Use existing `runner.test.ts:68-108` stub pattern with a failing `Bun.spawn` child (`exit 1`, stderr `boom` + 300 lines to test bound).

- [ ] **Step 2: Run test to verify it fails**

Run: `(cd tui && bun test tests/runner.test.ts)`
Expected: FAIL (production `app.ts` never passes `onStderr`; state has no `stderr` field; detail shows no diagnostics)

- [ ] **Step 3: Implement `stderr` state in `tui/src/types.ts:90-97`**

Add `stderr?: string[]` to `ScreenerRunState` with `MAX_STDERR_LINES=50`, `MAX_STDERR_CHARS=200` per line truncation (mirror `MAX_LOG_LINES=200` pattern in `events.ts:9`).

- [ ] **Step 4: Implement `pushStderr` + wiring in `tui/src/events.ts` and `tui/src/app.ts:203-210`**

Add bounded `pushStderr(entry, line)` helper; wire `startRunner({..., onStderr: (line)=>{ push to active/focused entry; paint(); }})`; keep stderr out of `parseEventLine` (already separate in `runner.ts:101-104`); route stderr lines to currently-running screener entry (or last failed if run finished).

- [ ] **Step 5: Render diagnostics in `detailText()` (`tui/src/app.ts:59-78`) and `tui/src/layout.ts`**

After `Result:` + `Output:` sections, add `Diagnostics (stderr):` showing `entry.stderr.slice(-8)` truncated, only when `entry.status==="failed"` and stderr non-empty; successful runs continue to show normal output/status.

- [ ] **Step 6: Run tests to verify pass**

Run: `(cd tui && bun test)` Expected: PASS
Run: `(cd tui && bunx tsc --noEmit)` Expected: exit 0

- [ ] **Step 7: Commit**

```bash
git add tui/src/types.ts tui/src/events.ts tui/src/runner.ts tui/src/app.ts tui/src/layout.ts tui/tests/runner.test.ts
git commit -m "fix: show failed screener stderr diagnostics in TUI detail view"
```

### Task 3: Shared Yahoo serial scheduler/cache with rate-limit stop (Issue #2 foundation)

**Files:**
- Create: `yahoo_client.py`
- Modify: `yahoo_guard.py` (re-export for compatibility)
- Test: `tests/test_yahoo_client.py`

**Interfaces:**
- Consumes: `yfinance`, existing `yahoo_guard.is_yahoo_rate_limit(error)`, `raise_if_yahoo_rate_limit(error, context)`.
- Produces: `yahoo_client.get_history(ticker, period, interval) -> DataFrame`, `yahoo_client.get_info(ticker) -> dict`, `yahoo_client.get_financials(ticker, kind) -> DataFrame`, `yahoo_client.get_earnings_dates(ticker) -> DataFrame`, `yahoo_client.get_news(ticker) -> list[dict]` — all via single serial lock, on-disk cache under temp or `.meta-screener/cache`, fail-fast `RuntimeError` on rate-limit markers, no retry; injectable `provider` for tests.

- [ ] **Step 1: Write failing test with fake provider**

```python
def test_shared_client_serializes_and_stops_on_rate_limit(self):
    calls = []
    def fake_fetch(ticker, **kw):
        calls.append(ticker)
        if ticker == "LIMIT":
            raise Exception("HTTPError 429 Too Many Requests")
        return {"ticker": ticker}
    client = YahooClient(provider=fake_fetch, cache_dir=self.tmp)
    self.assertEqual(client.get_info("AAPL")["ticker"], "AAPL")
    with self.assertRaises(RuntimeError):
        client.get_info("LIMIT")
    # cached second call does not refetch
    client.get_info("AAPL")
    self.assertEqual(calls.count("AAPL"), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_yahoo_client -v`
Expected: FAIL with "No module named yahoo_client"

- [ ] **Step 3: Implement `yahoo_client.py`**

Serial `threading.Lock`, `functools`-style disk cache (JSON/pickle under cache dir, TTL 24h), `is_yahoo_rate_limit` check on every exception → raise `RuntimeError` with stop message; no `time.sleep` retry; no direct `yf.Ticker` outside this module (document as only allowed path).

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_yahoo_client -v` Expected: PASS
Run: `python3 -m unittest discover -s tests` Expected: all PASS (no Yahoo calls — fake provider only)

- [ ] **Step 5: Commit**

```bash
git add yahoo_client.py yahoo_guard.py tests/test_yahoo_client.py
git commit -m "feat: add shared Yahoo serial scheduler cache with rate-limit stop"
```

### Task 4: Fundamental screens Yahoo-only (Issue #2 — fundamental-rotation, revenue-growth-momentum)

**Files:**
- Modify: `rotation_screen.py:25-40,74-76,97-127,184-188`
- Modify: `growth_momentum.py:20-23,31,49-52,83-85`
- Modify: `screeners.json` (2 entries: provider, yahoo:true, requirements, reads/writes)
- Modify: `meta_screener_cli.py:165-169,343-347` (result adapters if needed)
- Test: `tests/test_yahoo_fundamentals.py`

**Interfaces:**
- Consumes: `yahoo_client.get_financials(ticker, "annual"|"quarterly")`, `yahoo_client` universe list.
- Produces: same CLI flags (`--csv-out`, `--result-json`) plus `--tickers`, `--universe` removed from KG; `build_result_payload(tickers) -> {top, summary}` with within-company YoY/QoQ comparisons, blank when unavailable/mismatched; `screeners.json` entries with `"yahoo": true`, `"provider": "Yahoo Finance via yfinance"`.

- [ ] **Step 1: Write failing test with injected financials**

```python
def test_rotation_yahoo_financials_with_blank_on_missing(self):
    fake = {"AAPL": annual_df_with_revenue_margin, "MSFT": empty_df}
    payload = build_rotation_payload(["AAPL", "MSFT"], provider=FakeYahoo(fake))
    self.assertEqual(payload["top"][0]["ticker"], "AAPL")
    self.assertIn("blank", payload["top"][1]["detail"].lower() + payload["summary"].lower())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_yahoo_fundamentals -v`
Expected: FAIL (still reads `Datasets/History/fundamentals_*`, `Companies/*.md`, `Themes/*.md`)

- [ ] **Step 3: Implement Yahoo financials in both scripts**

Replace `BASE=VAULT/Datasets/History` globs with `yahoo_client` calls; remove `profile()` file reads and `theme_members()` KG reads; use built-in curated universe (shared `demo_universe.py` or `--tickers` flag) as symbol-selection input only; keep within-company period comparisons; leave currency ratios blank when unavailable.

- [ ] **Step 4: Update `screeners.json` + result adapters**

Set both entries `yahoo:true`, provider Yahoo, requirements `["yfinance","pandas","numpy"]`, reads `["Yahoo Finance statements per ticker; built-in symbol list as selection input only"]`; ensure `result_artifact_for` covers both for validated `top` rankings.

- [ ] **Step 5: Run tests**

Run: `python3 -m unittest tests.test_yahoo_fundamentals tests.test_ranked_results tests.test_cli -v` Expected: PASS, no Yahoo/KG reads (assert via temp dirs + stub provider)

- [ ] **Step 6: Commit**

```bash
git add rotation_screen.py growth_momentum.py screeners.json meta_screener_cli.py tests/test_yahoo_fundamentals.py
git commit -m "feat: make fundamental rotation screens Yahoo-backed"
```

### Task 5: Market-breadth and meta-overlap Yahoo-only (Issue #2)

**Files:**
- Modify: `breadth_rotation.py:13-14,23-33,41,70`
- Modify: `meta_screen.py:45,49-60,65-89,1087,1089,1125,761-769`
- Modify: `screeners.json` (2 entries)
- Test: `tests/test_yahoo_market.py`

**Interfaces:**
- Consumes: `yahoo_client.get_history(ticker, "6mo"|"3mo")`, `yahoo_client.get_info(ticker)`.
- Produces: `breadth_rotation.py` computes breadth from Yahoo `history` closes (no `prices_monthly/*.csv`, no `Themes/*.md`); `meta_screen.py` uses built-in demo universe or `--universe CSV` as selection input only, no `kg_links.load_ticker_map` fallback, no `rotation_history.csv` KG writes beyond run record; both expose validated `top` only for ranked screens.

- [ ] **Step 1: Write failing test**

```python
def test_breadth_uses_yahoo_prices_not_local_files(self):
    with patch("yahoo_client.get_history", return_value=fake_prices):
        result = compute_breadth(["AAPL", "MSFT"])
    self.assertIn("breadth", result["summary"].lower())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_yahoo_market -v`
Expected: FAIL (reads hardcoded `/documents/Finance Knowledge Graph`, `H/*.csv`)

- [ ] **Step 3: Implement Yahoo prices**

Replace `H=.../prices_monthly` and `V/Themes/*.md` globs with `yahoo_client.get_history` per symbol; hardcoded sector/market symbols (`SPY`, `^VIX`, sector ETFs) remain as selection inputs, documented as such; remove `VAULT`/`KG_ROOT` fallbacks.

- [ ] **Step 4: Implement meta-overlap Yahoo-only universe**

Remove `kg_links` import fallback and `UNIVERSE_FILE` KG dependency; keep `--universe CSV` as optional selection input, default to built-in `_DEMO_TICKERS`; Yahoo supplies all `history/info/insider/earnings/financials` facts.

- [ ] **Step 5: Update `screeners.json` reads/provider**

Both `yahoo:true`, provider Yahoo, reads list Yahoo facts + selection input note.

- [ ] **Step 6: Run tests**

Run: `python3 -m unittest tests.test_yahoo_market tests.test_meta_screen_checks tests.test_kg_links -v` Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add breadth_rotation.py meta_screen.py screeners.json tests/test_yahoo_market.py
git commit -m "feat: make breadth and meta-overlap Yahoo-only"
```

### Task 6: Events/research Yahoo-only or retire (Issue #2 — catalyst-calendar, macro-calendar, research-frontier, plus holdings screens)

**Files:**
- Modify: `catalyst_scan.py`, `kg_links.py:198-228` (remove or gate)
- Modify: `econ_calendar.py:15-24`
- Modify: `frontier_scan.py:17,26,39-45`
- Modify: `analyst_scan.py:32-34`, `short_interest.py:22-28`, `dividend_analysis.py:22-28,134-136`, `unusual_options.py:22-28`, `screen_tracker.py:53-67,70-80`
- Modify: `screeners.json` (8 entries + retire macro-calendar if needed)
- Test: `tests/test_yahoo_events.py`

**Interfaces:**
- Consumes: `yahoo_client.get_earnings_dates(ticker)`, `yahoo_client.get_news(ticker)`, `yahoo_client.get_info(ticker)`.
- Produces: `catalyst-calendar` lists only Yahoo `earnings_dates/calendar` events per ticker (no `Important Dates/*.md`); `macro-calendar` retired from registry (script kept in `archive/` if Yahoo has no macro equivalent); `research-frontier` replaced by Yahoo news output or removed; holdings/analyst screens require `--tickers` or built-in universe (no `pm_portfolio.json`, no `Companies/*.md`); context screens emit summary/report without invented `top` rankings.

- [ ] **Step 1: Write failing test**

```python
def test_catalyst_uses_yahoo_earnings_only(self):
    payload = build_catalyst_payload(["AAPL"], provider=FakeYahooEarnings({"AAPL": [date]}))
    self.assertTrue(any("earnings" in r["detail"].lower() for r in payload["top"]) or "earnings" in payload["summary"].lower())

def test_macro_retired_or_yahoo_only(self):
    registry = json.load(open("screeners.json"))
    self.assertNotIn("macro-calendar", [s["id"] for s in registry["screeners"]] if YAHOO_HAS_NO_MACRO else [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_yahoo_events -v`
Expected: FAIL (reads `Important Dates/*.md`, static `KNOWN_EVENTS`, `Notes/*.md`, `pm_portfolio.json`)

- [ ] **Step 3: Implement catalyst Yahoo earnings**

Replace `kg_links.upcoming_catalysts()` with per-ticker `get_earnings_dates`; limit to events Yahoo supplies; no fallback to KG notes.

- [ ] **Step 4: Retire or replace macro-calendar and research-frontier**

If `yfinance` has no macro calendar: remove `macro-calendar` from `screeners.json`, move `econ_calendar.py` to `archive/` or mark deprecated; replace `frontier_scan.py` with Yahoo `Ticker.news` output (title/link per ticker) or remove if not useful; do not invent rankings for context screens.

- [ ] **Step 5: Implement holdings/analyst Yahoo-only tickers**

Replace `load_holdings()` (`pm_portfolio.json`) and `collect_tickers()` (`Companies/*.md`) with `--tickers` required or built-in universe; Yahoo `info`/`options`/`option_chain` supply all facts; remove hardcoded `VZ,JNJ,...` fallback unless documented as selection input.

- [ ] **Step 6: Update `screeners.json` metadata**

Every entry `yahoo:true`, provider matches actual source, requirements include yfinance where needed, reads list Yahoo facts only, `default_enabled:false` for `screen-history` preserved; retired entries removed.

- [ ] **Step 7: Run tests**

Run: `python3 -m unittest discover -s tests` Expected: PASS (fake providers, temp inputs only)
Run: `grep -r "Finance Knowledge Graph\|pm_portfolio\|Important Dates" --include="*.py" rotation_screen.py growth_momentum.py breadth_rotation.py catalyst_scan.py econ_calendar.py frontier_scan.py analyst_scan.py short_interest.py dividend_analysis.py unusual_options.py meta_screen.py | grep -v test | grep -v archive` Expected: no matches (prove Yahoo-only)

- [ ] **Step 8: Commit**

```bash
git add catalyst_scan.py econ_calendar.py frontier_scan.py analyst_scan.py short_interest.py dividend_analysis.py unusual_options.py screen_tracker.py screeners.json kg_links.py tests/test_yahoo_events.py
git commit -m "feat: make events and holdings screens Yahoo-only, retire macro static calendar"
```

### Task 7: Docs, changelog, and tracker close-out

**Files:**
- Modify: `CHANGELOG.md`, `README.md`, `PYTHON_TOOLS.md` (if present), `docs/MCP.md`, `docs/SESSION_RECAP_2026-10-03.md` (addendum, do not rewrite history)
- Modify: `VERSION` (0.3.1 or 0.4.0)
- Modify: `pyproject.toml` (version bump)

**Interfaces:**
- Consumes: Tasks 1-6 verification evidence.
- Produces: Changelog entries for #2/#3/#4, Yahoo-only usage docs, closed tracker #5 note.

- [ ] **Step 1: Update docs and version**

Bump `VERSION` to `0.4.0` (new Yahoo-only behavior), sync `pyproject.toml`, add `CHANGELOG.md` entries for each issue, update `README.md` dashboard/provider labels, note `macro-calendar` retirement and `--tickers` usage.

- [ ] **Step 2: Full verification**

Run: `python3 -m unittest discover -s tests` Expected: 50+ PASS
Run: `(cd tui && bun test)` Expected: 34+ PASS
Run: `(cd tui && bunx tsc --noEmit)` Expected: exit 0
Run: `python3 -m py_compile yahoo_client.py rotation_screen.py growth_momentum.py breadth_rotation.py catalyst_scan.py frontier_scan.py meta_screen.py meta_screener_cli.py` Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md README.md VERSION pyproject.toml docs/
git commit -m "docs: record Yahoo-only v0.4.0 and close follow-up tracker"
```

## Self-Review

**1. Spec coverage:** Issue #4 (CI + empty/missing screener_id + absolute/escaping paths) → Task 1. Issue #3 (stderr wiring + bounds + regression test + bun test/tsc) → Task 2. Issue #2 (per-entry provider match, Yahoo statements with blank, breadth Yahoo prices, catalyst limited to Yahoo events, frontier news-or-remove, shared scheduler/cache + stop, validated rankings only for stock screens, fake-provider temp-input tests) → Tasks 3-6. Tracker #5 → Task 7. Fixed-in-PR#1 items need no new tasks.

**2. Step scan:** Every test step names exact test and assertions with spec values; every code step names exact file:line and signature; every verification step names command and expected output. No TBD or vague validation lines.

**3. Type consistency:** `YahooClient(provider, cache_dir)` injected in Task 3 and reused as `FakeYahoo`/`provider` in Tasks 4-6; `ScreenerRunState.stderr: string[]` defined in Task 2 and rendered in same task; `command_for`/`result_artifact_for`/`applyEvent` signatures match existing code.

**4. Review Focus:** Five failure modes listed at top, each pinned to owning task tests (blank financials → Task 4, empty catalyst → Task 6, macro retirement → Task 6, bounded traceback → Task 2, metadata mismatch → Task 6 grep check).

**5. Proportion:** Plan is longer than any single issue body but shorter than the code it changes (17 screeners + TUI + CI); code blocks are only test sketches and CI YAML, not program transcripts; each step leaves implementation body to executor.
