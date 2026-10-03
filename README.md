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
meta-screener
```

The dashboard groups the registered workflows by stage, lets you select one or more, and runs them sequentially. It shows ticker rankings only for workflows that produce a ranked stock list; context, calendar, and research workflows show their status and available summary instead.

Keyboard controls: arrows or `j/k` move, `space` selects, `a` selects all defaults, `c` clears, `r` runs selected, `R` runs all default-enabled workflows, `d` shows details, `f` toggles the opt-in daily refresh, and `q` quits.

## Run directly from the CLI

```bash
meta-screener list
meta-screener list --checks
meta-screener plan --all
meta-screener plan --screener meta-overlap --screener fundamental-rotation
meta-screener run --screener meta-overlap
meta-screener run --all
```

`screeners.json` registers 17 workflows. Sixteen run with `--all`; `screen-history` is an optional outcome tracker. The CLI runs multiple selections in registry stage order. The other Python files are supporting workflows and are not launched automatically.

## Yahoo Finance pacing

Yahoo-backed workflows run sequentially with one worker, batches of 8 tickers, and a 15-second pause by default. The CLI lets you set the batch size and a 10–30 second cooldown between workflows and ticker batches. If Yahoo reports a rate limit, the run stops and does not retry automatically. Use `meta-screener plan ...` to review a selection before running it.

## MCP for local AI agents

After installing the optional MCP extra, configure your MCP client to launch `meta-screener-mcp` over stdio. The server can list workflows and checks, preview plans, run one or more workflows, create a named screen from existing checks, register an existing Python workflow inside this repository, and unregister a workflow. Unregistering keeps the source file; MCP tools do not write arbitrary Python source.

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
