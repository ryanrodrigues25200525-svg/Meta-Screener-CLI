# Meta Screener CLI

**Find stocks worth a closer look without running scripts one by one.** This repository contains the 47-check cross-signal meta-screen plus the broader Python screeners, research workflows, and Finance Knowledge Graph utilities built for this workflow.

## Install

Requires Python 3.10 or newer. The OpenTUI dashboard also requires Bun 1.3 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-screening.txt
python -m pip install -e .
(cd tui && bun install)
```

To enable the MCP server, install its optional dependency:

```bash
python -m pip install -e '.[mcp]'
```

The full Python-file catalog is in [`PYTHON_TOOLS.md`](PYTHON_TOOLS.md); OpenTUI setup details are in [`tui/README.md`](tui/README.md).

## Run the dashboard

```bash
metascreener
```

`metascreener` is the no-hyphen console command. The existing `meta-screener` name remains available as an alias. Both commands open the dashboard with no subcommand and use the same direct CLI commands below.

The dashboard groups the registered Yahoo-only workflows by stage, lets you select one or more, and runs them sequentially. It shows ticker rankings only for stock screens that produce a validated ranked list; context and event screens show their status and available summary instead. A failed workflow shows a bounded stderr diagnostics tail in its detail view.

Keyboard controls: arrows or `j/k` move, `space` selects, `a` selects all defaults, `c` clears, `r` runs selected, `R` runs all default-enabled workflows, `d` shows details, `f` toggles the opt-in daily refresh, and `q` quits.

## Run directly from the CLI

```bash
metascreener list
metascreener list --checks
metascreener plan --all
metascreener plan --screener meta-momentum --screener fundamental-rotation
metascreener run --screener meta-momentum
metascreener run --all
```

`screeners.json` registers 28 Yahoo-only workflows: 8 meta family screens, 5 company screens (smart-money, insider-activity, altman-z, cash-return, dividend-growth), and the rest. Twenty-seven run with `--all`; `screen-history` is an optional outcome tracker. `metascreener leaderboard` lists the top 10 tickers most consistent across saved screener results. The CLI runs multiple selections in registry stage order. The other Python files are supporting workflows and are not launched automatically.

## Yahoo Finance pacing

All 28 registered workflows are Yahoo-only (`"yahoo": true` in `screeners.json`) and share one serial scheduler with an on-disk cache (`yahoo_client.py`). Yahoo-backed workflows run sequentially with one worker, batches of 8 tickers, and a 15-second pause by default. The CLI lets you set the batch size and a 10–30 second cooldown between workflows and ticker batches. If Yahoo reports a rate limit, the run stops and does not retry automatically. Use `metascreener plan ...` to review a selection before running it.

Company and event screens accept an explicit ticker list when invoked directly, or fall back to the shared built-in universe:

```bash
metascreener run --screener analyst-consensus
python3 short_interest.py --tickers AAPL,MSFT
python3 catalyst_scan.py --tickers NVDA,AVGO
```

The static `macro-calendar` workflow is retired: Yahoo supplies no macro calendar, so the approximate recurring schedule was removed from the registry rather than kept as fake FOMC/CPI dates. The script is preserved for reference at `archive/econ_calendar.py`; confirm macro dates with official sources (FRED API, central-bank calendars).

## MCP for local AI agents

After installing the optional MCP extra, configure your MCP client to launch `meta-screener-mcp` over stdio. The server can list workflows and checks, preview plans, run one or more workflows, create a named screen from existing checks, register an existing Python workflow inside this repository, and unregister a workflow. Unregistering keeps the source file; MCP tools do not write arbitrary Python source. Full setup, tool table, and examples: [`docs/MCP.md`](docs/MCP.md).

Example MCP client entry:

```json
{
  "mcpServers": {
    "meta-screener": {
      "command": "/path/to/venv/bin/meta-screener-mcp"
    }
  }
}
```

## Local data and limits

The public repository does not include portfolio positions, private watchlists, credentials, or generated research history. Personal files such as `pm_portfolio.json`, `positions.json`, and `universe.csv` stay local and are ignored by Git. MCP and TUI run the same Python CLI so they follow its registry, run order, and rate-limit handling.

A screen pass is a research lead, not an investment decision. The CLI does not place orders. This project is separate from [Trading CLI](https://github.com/ryanrodrigues25200525-svg/Trading-CLI), which is for paper-trading workflows.
