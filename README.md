# Meta Screener CLI

**A local-first stock-screening CLI that runs checks in paced stages and ranks companies by cross-screener overlap.**

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Yahoo Finance](https://img.shields.io/badge/data-Yahoo%20Finance-6e89b5.svg)

Meta Screener CLI brings the project's Python screeners into one command. Its default run applies 47 checks to a company universe, prints the leading overlap candidates, and saves an auditable research note. The wider suite adds market context, company signals, catalysts, and local knowledge-graph scans.

It screens and reports. It does not place trades or generate a buy/sell recommendation.

## Quick start

Requires Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-screening.txt
python -m pip install -e .
```

Run the core Meta Screen:

```bash
meta-screener
```

The default run uses one worker and 25-symbol batches with a 10-second cooldown between full batches. With the 100-company demo universe, that adds about 30 seconds of deliberate waiting; Yahoo response time adds to the total. The demo list is for trying the workflow, not a recommended portfolio or a record of anyone's holdings.

## Common commands

```bash
# Show the screener catalog
meta-screener list

# List every check and criterion in the core Meta Screen
meta-screener list --checks

# Preview order and file effects without launching screeners
meta-screener plan --all --gap-seconds 15

# Run one stage or all default-enabled screeners
meta-screener run --stage discovery
meta-screener run --all --gap-seconds 15
```

The `run --all` option runs the default-enabled catalog in stage order. Use `meta-screener run --screener <id>` for one registered screener. `--gap-seconds` accepts 10–30 seconds and defaults to 15 for explicit `run` commands.

## Core Meta Screen

The 47 checks cover six groups:

| Group | Checks | Examples |
| --- | ---: | --- |
| Momentum | 4 | Six- and twelve-month relative strength, re-acceleration, pullback in an uptrend |
| Technical | 4 | Moving-average structure, RSI, 52-week high/low position |
| Valuation | 5 | Forward P/E, price-to-book, price-to-sales, GARP, peer-relative value |
| Fundamental | 3 | Revenue growth, return on equity, net margin |
| Theme rotation | 23 | Semiconductors/AI, defense, energy, healthcare, banks, robotics, and regional baskets |
| Insider, earnings, and quality | 8 | Insider buying, earnings drift, Piotroski, cash conversion, buybacks, capital discipline |

The ranking counts breadth across five signal families: price action, valuation, business quality, earnings, and insider activity. Related checks are not treated as independent confirmations. Theme matches add context, not another score family. Missing inputs are reported as unavailable rather than as failed checks.

## Registered screeners

| Stage | Screener | What it checks |
| --- | --- | --- |
| Candidate discovery | `meta-overlap` | The 47-check cross-signal Meta Screen |
| Candidate discovery | `fundamental-rotation` | Stored revenue growth, margin trend, and valuation history |
| Candidate discovery | `revenue-growth-momentum` | Direction of annual and quarterly revenue growth |
| Market context | `sector-rotation` | Relative performance across sector ETFs |
| Market context | `market-breadth` | Stored breadth and theme-return measures |
| Market context | `volatility-regime` | VIX and volatility conditions |
| Market context | `market-sentiment` | VIX and QQQ/SPY market proxies |
| Market context | `commodities-fx` | Commodity futures and major currency proxies |
| Market context | `cot-futures-proxy` | Futures-positioning proxy; not official CFTC COT data |
| Company signals | `analyst-consensus` | Ratings, analyst count, and price-target range |
| Company signals | `short-interest` | Short interest for selected holdings or tickers |
| Company signals | `dividend-analysis` | Yield and payout context for selected holdings |
| Company signals | `options-activity` | Available options activity for selected holdings |
| Events and research | `catalyst-calendar` | Catalysts already recorded in the local knowledge graph |
| Events and research | `macro-calendar` | Approximate recurring macro events; confirm dates with official sources |
| Events and research | `research-frontier` | Open research questions linked to upcoming catalysts |
| Optional tracking | `screen-history` | Post-screen returns; excluded from `run --all` and requires `officecli` |

Use `meta-screener list` for each screen's data source, requirements, and file effects.

## Pacing and Yahoo Finance

- Screeners run sequentially. The core screen uses one worker and pauses between ticker batches.
- The runner waits between Yahoo-backed scripts and stages. Cooldown length can be set from 10 to 30 seconds.
- A detected 429/rate-limit response stops the current run. The CLI does not retry automatically or start later Yahoo jobs.
- Yahoo does not publish a stable request quota for this workflow. Pacing lowers burst risk but cannot guarantee uninterrupted access.
- Separate screeners do not share a result cache yet. Avoid rerunning Yahoo-backed stages unnecessarily.

Use `meta-screener plan --all --gap-seconds 15` to see the exact order and listed outputs before a broad run.

## Local data and outputs

The public repository contains screening code and a generic demo universe, not portfolio positions or research-history files. Local files such as `pm_portfolio.json`, `positions.json`, `universe.csv`, `rotation_history.csv`, and generated notes are excluded from Git. `meta_screen.py` automatically uses a local `universe.csv` when present; otherwise it uses the built-in demo list. The CSV columns are `ticker`, `name`, and `theme`.

The default Meta Screen writes a dated note under `~/Documents/Finance Knowledge Graph/Notes/` and updates `rotation_history.csv` in this project folder. Some other screens write their own knowledge-graph notes or CSVs. `plan` is side-effect free; `run` can write the files shown in the plan and catalog.

Several screens use stored Finance Knowledge Graph data. Holdings-oriented screens use the local `~/finance-ai/pm_portfolio.json` file when no explicit tickers are supplied. These personal files are never included in this repository.

## Ideas for later

Potential additions to evaluate with point-in-time data and out-of-sample checks:

- Earnings-estimate revision breadth and dispersion
- Share issuance and dilution, separated from stock-based compensation and repurchases
- Multi-year cash conversion and accruals
- A configurable liquidity floor
- Industry-aware balance-sheet resilience

The registry connects existing Python screeners. It does not yet let non-coders author new rules. A later version could support safe rule files with a preview and backtest before activation.

## Scope

This project is separate from `tradingcli`. It only screens and reports. Yahoo Finance data may be delayed, incomplete, or unavailable, and a screen pass is a research lead rather than an investment conclusion.

No license file is included yet.
