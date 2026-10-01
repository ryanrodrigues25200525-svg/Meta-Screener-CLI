# Meta Screener CLI 🔎

**One command. Your whole screening workflow. A cleaner way to find companies worth a closer look.**

The Meta Screener CLI brings your registered stock screens into a paced, staged run. Its default command applies 47 checks, ranks companies by cross-screener breadth, and prints the leading overlap candidates. This repository now also carries the broader 82-module Finance AI source toolkit.

> 🧭 Screens help you find research leads. They do not make investment decisions or place orders.

## ⚡ Get started

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

The default run uses one worker, groups up to 25 symbols, and pauses 10 seconds between full batches. With the 100-company demo universe, that is about 30 seconds of planned cooldown, plus Yahoo Finance response time. The demo universe is illustrative, not a recommended portfolio.

## 🎛️ Everyday commands

```bash
# Browse the registered screens and their requirements
meta-screener list

# See all 47 checks in the core screen
meta-screener list --checks

# Preview order and file effects without launching screeners
meta-screener plan --all --gap-seconds 15

# Run a stage or all registered screens
meta-screener run --stage discovery
meta-screener run --all --gap-seconds 15

# Check the installed version
meta-screener --version
```

`meta-screener run --all` launches the 16 default-enabled entries from `screeners.json`. Use `meta-screener run --screener <id>` for one. The CLI catalog is the source of truth for what this command launches; the other Python modules are supporting Finance AI workflows and are not automatically run.

## 📊 The 47-check Meta Screen

| Group | Checks | Examples |
| --- | ---: | --- |
| Momentum | 4 | Relative strength, re-acceleration, pullback in an uptrend |
| Technical | 4 | Moving-average structure, RSI, 52-week levels |
| Valuation | 5 | Forward P/E, price-to-book, price-to-sales, GARP, peer value |
| Fundamental | 3 | Revenue growth, return on equity, net margin |
| Theme rotation | 23 | Semiconductors/AI, defense, energy, healthcare, banks, robotics, and regions |
| Insider, earnings, and quality | 8 | Insider buying, earnings drift, Piotroski, cash conversion, buybacks |

The ranking measures breadth across five signal families: price action, valuation, business quality, earnings, and insider activity. Related checks do not count as independent confirmations. Theme hits add context rather than another score family. Missing inputs show as unavailable, not failed.

## 🧰 What is in this repo

This v0.2.0 snapshot includes **82 Python source modules** from the Finance AI workflow, including the screening catalog and supporting research, knowledge-graph, data-maintenance, portfolio, and risk utilities. The screen catalog remains focused: only entries in `screeners.json` are launched by the `meta-screener` command.

Some supporting scripts expect local Finance Knowledge Graph data, `officecli`, or other workflow-specific inputs. The core screener dependencies are in `requirements-screening.txt`; check each script's usage text for its own requirements.

## 🛡️ Yahoo pacing

- Registered screens run sequentially; the core screen uses one worker and ticker batches.
- Cooldowns can be set from 10 to 30 seconds between Yahoo-backed work.
- A detected 429/rate-limit response stops the run. The CLI does not retry automatically or start later Yahoo jobs.
- Yahoo does not publish a stable request quota. Pacing lowers burst risk but cannot guarantee uninterrupted access.
- Separate screeners do not share a result cache yet, so avoid rerunning Yahoo-backed stages unnecessarily.

Preview broad runs with `meta-screener plan --all --gap-seconds 15` before launching them.

## 🗂️ Private data stays local

The public repository includes source code and a generic demo universe. It does **not** include portfolio positions, private watchlists, generated screen history, personal research notes, or credentials. Local files such as `pm_portfolio.json`, `positions.json`, `universe.csv`, `rotation_history.csv`, and `Trackers.xlsx` are ignored by Git.

A local `universe.csv` overrides the demo universe. The core Meta Screen writes a dated note under `~/Documents/Finance Knowledge Graph/Notes/` and updates the local `rotation_history.csv`. Other modules may write their own notes, CSVs, or workbooks. `plan` is side-effect free; `run` may write the outputs shown in the catalog.

## 🌱 Up next

Good candidates for further evaluation with point-in-time data and out-of-sample checks:

- Earnings-estimate revision breadth and dispersion
- Share issuance and dilution
- Multi-year cash conversion and accruals
- A configurable liquidity floor
- Industry-aware balance-sheet resilience

The registry connects existing Python screens; it does not yet let non-coders author new rules. A later version could add safe rule files with a preview and backtest before activation.

No license file is included yet.
