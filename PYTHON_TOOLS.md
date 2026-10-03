# Python tools catalog

89 tracked Python files: 1 runner, 17 registered workflow scripts, 53
supporting tools, 1 MCP server, 7 tests, and 10 archived one-off migrations.
Descriptions below come from each module's own docstring. The 17 registered
workflows are the only scripts the CLI runs; everything else is a supporting
tool, test, or archived history.

## Runner and workflow registry

- [`meta_screener_cli.py`](meta_screener_cli.py) — opens the OpenTUI dashboard with no arguments; lists, plans, and runs registered workflows with paced JSON Lines events.

## Registered screeners (run via `meta-screener`)

17 workflows are registered in `screeners.json`; 16 are enabled by default and
`screen-history` is optional (excluded from the default all-run).

- [`meta_screen.py`](meta_screen.py) (`meta-overlap`) — deterministic 47-check cross-signal breadth screen over a curated universe; supports named check subsets and exports its top ranking.
- [`rotation_screen.py`](rotation_screen.py) (`fundamental-rotation`) — ranks the book and rotation themes on revenue growth, margin trend, and valuation from stored fundamentals; exports the passing shortlist.
- [`growth_momentum.py`](growth_momentum.py) (`revenue-growth-momentum`) — revenue growth and its direction per company from the stored fundamentals layer.
- [`sector_rotation.py`](sector_rotation.py) (`sector-rotation`) — sector ETF performance over short and medium horizons.
- [`breadth_rotation.py`](breadth_rotation.py) (`market-breadth`) — share of names above a 10-month moving average, positive 3-month returns, and median theme returns from stored monthly prices.
- [`volatility_regime.py`](volatility_regime.py) (`volatility-regime`) — VIX term structure and volatility-regime classification.
- [`market_sentiment.py`](market_sentiment.py) (`market-sentiment`) — VIX, put/call, and Fear & Greed proxy.
- [`commodities_fx.py`](commodities_fx.py) (`commodities-fx`) — commodity prices and FX rates.
- [`cot_report.py`](cot_report.py) (`cot-futures-proxy`) — futures positioning via a yfinance proxy (not official CFTC data).
- [`analyst_scan.py`](analyst_scan.py) (`analyst-consensus`) — sell-side consensus (recommendation, targets, analyst count) for graph-tracked tickers.
- [`short_interest.py`](short_interest.py) (`short-interest`) — ranks portfolio tickers by short percentage of float; also accepts an explicit ticker list.
- [`dividend_analysis.py`](dividend_analysis.py) (`dividend-analysis`) — ranks portfolio tickers by dividend yield and payout context.
- [`unusual_options.py`](unusual_options.py) (`options-activity`) — options-chain activity for holdings or an explicit ticker list.
- [`catalyst_scan.py`](catalyst_scan.py) (`catalyst-calendar`) — upcoming events already recorded in the graph's Important Dates folder.
- [`econ_calendar.py`](econ_calendar.py) (`macro-calendar`) — approximate recurring macro-event calendar (confirm dates with official sources).
- [`frontier_scan.py`](frontier_scan.py) (`research-frontier`) — open research questions and linked catalysts already recorded in the graph.
- [`screen_tracker.py`](screen_tracker.py) (`screen-history`, optional) — outcome tracker (not a candidate screener): returns since prior meta-screen flags vs SPY.

## Market and risk analysis (stored price/fundamentals layer, offline)

- [`attention_backtest.py`](attention_backtest.py) — tests whether indexed analyst attention predicts forward returns, market-relative to SPY.
- [`book_risk.py`](book_risk.py) — concentration and co-movement of the book (effective-bets estimate) from the stored daily layer.
- [`corr_regime.py`](corr_regime.py) — within-cluster vs cross-cluster return correlations for the semis and value halves across stress and uptrend windows.
- [`currency_check.py`](currency_check.py) — decides each new fundamentals file's currency by magnitude, or leaves it UNKNOWN.
- [`daily_gaps.py`](daily_gaps.py) — coverage-gap report for the stored daily price layer, per ticker and overall.
- [`driver_map.py`](driver_map.py) — groups holdings by their own kill-switch wording; group/proxy correlations and driver-level effective bets.
- [`fundamentals_consistency.py`](fundamentals_consistency.py) — review list for the stored fundamentals layer (magnitude plausibility checks).
- [`history_coverage.py`](history_coverage.py) — measures stored price/fundamentals coverage against fetch worklists.
- [`signal_validation.py`](signal_validation.py) — follow-ups: non-overlapping attention test and dated bear-pitch forward returns.
- [`source_corr.py`](source_corr.py) — maps screens to underlying data lineage; effective independent-source count per name.
- [`stop_calibration.py`](stop_calibration.py) — how often a 15% trailing stop would have fired on the book's daily data.
- [`stop_cost.py`](stop_cost.py) — what happened after each 15% trailing-stop trigger vs SPY over 3 and 6 months.
- [`stop_regime_rotation.py`](stop_regime_rotation.py) — the 15% trailing-stop test on rotation names vs semis.
- [`stop_regime_test.py`](stop_regime_test.py) — the 15% trailing-stop rule over the 2022 drawdown vs buy-and-hold.
- [`verify_3m.py`](verify_3m.py) — 3-month price changes for the semis complex and the value half, from the daily layer.
- [`verify_risk_rules.py`](verify_risk_rules.py) — gates the Portfolio.md risk-rules figures against the book-risk and stop-regime measurements.

## Knowledge-graph maintenance and indexing (kept active)

- [`context_pack.py`](context_pack.py) — assembles the vault context pack (company note, research, claims, calendar, themes) for a ticker.
- [`fix_wrapped_links.py`](fix_wrapped_links.py) — repairs wikilinks broken across a newline; reports unresolved links.
- [`fund_nodes_from_letters.py`](fund_nodes_from_letters.py) — creates Funds/ nodes from BuySide Digest letter coverage; never overwrites 13F-sourced nodes.
- [`graph_index.py`](graph_index.py) — regenerates Graph-Index.md by scanning the vault (idempotent).
- [`history_sync.py`](history_sync.py) — incremental refresh of the stored History layer (prices/fundamentals deltas).
- [`important_dates_index.py`](important_dates_index.py) — generates the Important Dates hub note from the catalyst notes.
- [`kg_links.py`](kg_links.py) — ticker-to-company-note resolver and graph-quality helpers shared by the scans.
- [`kg_validate.py`](kg_validate.py) — vault integrity and health validator (frontmatter, wikilinks, required fields, freshness).
- [`letter_coverage_sections.py`](letter_coverage_sections.py) — adds a Letter coverage section to company nodes.
- [`portfolio_node.py`](portfolio_node.py) — regenerates Portfolio.md from `pm_portfolio.json` (idempotent).
- [`price_stamp.py`](price_stamp.py) — stamps Companies frontmatter with live yfinance prices.
- [`theme_resolution.py`](theme_resolution.py) — resolves theme members to nodes/prices through one map.
- [`theme_tracker.py`](theme_tracker.py) — tracks theme baskets (equal-weight 1-month returns) and writes a snapshot note.
- [`ticker_nodes.py`](ticker_nodes.py) — creates company/ETF nodes for linked-but-missing tickers; skips tickers with no profile row.
- [`wire_note.py`](wire_note.py) — links a finished research note into theme nodes (idempotent; dry-run by default).

## Research grading and decision feedback loop

- [`catalyst_grade.py`](catalyst_grade.py) — grades discrete catalyst events into outcomes against the linked thesis.
- [`claim_grade.py`](claim_grade.py) — self-grading claim layer: links open claims to next earnings dates and grades what's resolvable.
- [`grade.py`](grade.py) — closes the "was I right?" loop: gradifies closed notes and computes realized returns vs SPY.
- [`reason.py`](reason.py) — deterministic typed-edge propagation: regime impact review, live kill-switches, catalyst triggers.
- [`validate.py`](validate.py) — data-quality gate: live reachability, freshness, price divergence, and fundamentals checks per ticker.
- [`verdict.py`](verdict.py) — evidence-weighted verdicts (INTACT / WEAKENED / BROKEN) per research note.

## Causal driver mapping

- [`build_roster.py`](build_roster.py) — step 1: roster of book plus rotation-theme names resolved to tickers.
- [`causal_map2.py`](causal_map2.py) — v2 sector-scoped, anchored, scored causal driver map with vault-sentence support.
- [`driver_evidence_allnotes.py`](driver_evidence_allnotes.py) — recomputes evidence strength against every kill-switch per name across all notes.
- [`driver_evidence_external.py`](driver_evidence_external.py) — third-party audit of the map against BuySideDigest and RhinoInvestory corpora.
- [`driver_evidence_vault.py`](driver_evidence_vault.py) — title-level claims plus theme research-notes evidence pass.
- [`driver_gap_worklist.py`](driver_gap_worklist.py) — evidence-gap worklist and final accounting update.
- [`driver_sector_primer.py`](driver_sector_primer.py) — sector-primer evidence pass, family-level only.

## Portfolio management and monitoring

- [`monitor.py`](monitor.py) — position and peer-news monitor via Google News RSS.
- [`pm_trader.py`](pm_trader.py) — $1M Portfolio Manager engine: positions, risk rules, trades, and weekly briefs.

## News and signal scans

- [`podcast_scan.py`](podcast_scan.py) — recent investing-podcast episodes flagged by signal category.
- [`twitter_scan.py`](twitter_scan.py) — curated finance-account posts flagged by signal category; feeds the Claims layer.

## TradingAgents research

- [`ta_batch_holdings.py`](ta_batch_holdings.py) — TradingAgents research on PM holdings (one ticker at a time by default).
- [`ta_lite.py`](ta_lite.py) — lightweight 2-call TradingAgents-style research that banks conformed research notes.
- [`ta_opinion.py`](ta_opinion.py) — runs TradingAgents on an already-researched ticker; banks its verdict as an independent signal.
- [`ta_research.py`](ta_research.py) — runs TradingAgents as a general research engine; banks the full multi-agent report set.

## Shared helpers

- [`yahoo_guard.py`](yahoo_guard.py) — shared fail-fast handling for Yahoo Finance rate-limit exceptions.

## MCP server

- [`screener_mcp.py`](screener_mcp.py) — local stdio MCP server for listing, planning, running, creating, registering, and unregistering workflows.

## Tests

- [`test_driver_map.py`](test_driver_map.py) — acceptance test re-deriving the driver map's headline numbers from the stored layer and CSV.
- [`tests/test_cli.py`](tests/test_cli.py) — CLI selection, JSON Lines output, TUI dispatch, and run-record behavior.
- [`tests/test_kg_links.py`](tests/test_kg_links.py) — ticker-map lookup honors an explicitly supplied graph root.
- [`tests/test_meta_screen_checks.py`](tests/test_meta_screen_checks.py) — custom meta-screen check selection and ranked-result export.
- [`tests/test_ranked_results.py`](tests/test_ranked_results.py) — JSON ranking adapters for rotation, short-interest, and dividend workflows.
- [`tests/test_screener_mcp.py`](tests/test_screener_mcp.py) — MCP tool validation and registry operations with isolated registries.
- [`tests/test_screener_mcp_stdio.py`](tests/test_screener_mcp_stdio.py) — end-to-end MCP stdio integration: launches the real server in a subprocess, drives it with the SDK client, and runs two non-Yahoo stub workflows under a temporary `FINANCE_AI_HOME`.

## Archive — one-off migrations (not runnable screens)

Preserved byte-for-byte under [`archive/one-off-migrations/2026/`](archive/one-off-migrations/2026/) with their own readme:

- [`kg_repair.py`](archive/one-off-migrations/2026/kg_repair.py) — first deterministic Finance Knowledge Graph cleanup and frontmatter repairs.
- [`kg_repair2.py`](archive/one-off-migrations/2026/kg_repair2.py) — canonicalizes theme-company tokens to company-node titles and applies residual fixes.
- [`kg_repair3.py`](archive/one-off-migrations/2026/kg_repair3.py) — collapses triple-bracket tokens and cleans remaining repair artifacts.
- [`kg_repair4.py`](archive/one-off-migrations/2026/kg_repair4.py) — fixes link titles and creates missing source nodes.
- [`kg_repair5.py`](archive/one-off-migrations/2026/kg_repair5.py) — wires remaining evidence gaps from existing Claims nodes.
- [`backfill_comp.py`](archive/one-off-migrations/2026/backfill_comp.py) — backfills competitor, partner, and position fields for PM-holding company nodes.
- [`backfill_comp2.py`](archive/one-off-migrations/2026/backfill_comp2.py) — backfills the same fields for remaining shortlist and watchlist nodes.
- [`backfill_verdicts_20260912.py`](archive/one-off-migrations/2026/backfill_verdicts_20260912.py) — 2026-09-12 layer-3 verdict write.
- [`repair_verdict_fields_20260912.py`](archive/one-off-migrations/2026/repair_verdict_fields_20260912.py) — 2026-09-12 verdict-date frontmatter repair.
- [`driver_taxonomy_fix.py`](archive/one-off-migrations/2026/driver_taxonomy_fix.py) — COPPER-to-BASE_METALS driver taxonomy fix.
