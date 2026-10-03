# 📊 Meta Screener CLI

> Run 28 Yahoo-backed **stock screeners** from one command and find the tickers that keep showing up. 🏆 Weekly, on-demand, research only — **never places trades**. 🚫💸

| 🧺 Screeners | 🛠️ Engine |
|---|---|
| 8 meta signal families · fundamentals · breadth · sector · volatility · sentiment · holdings · events | Sequential Yahoo runner, serial scheduler + disk cache, fail-fast rate-limit stop, JSONL events, TUI dashboard, MCP server |

## ⚙️ Setup

Requires Python 3.10+ and Bun >= 1.3 (for the dashboard).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-screening.txt
pip install -e .                 # gives you meta-screener + metascreener
pip install -e '.[mcp]'          # optional: MCP server for AI agents 🤖
(cd tui && bun install)
```

Full file catalog: [`PYTHON_TOOLS.md`](PYTHON_TOOLS.md) · dashboard details: [`tui/README.md`](tui/README.md)

## 🖥️ Dashboard

```bash
meta-screener          # or: metascreener
```

Pick workflows, run them, watch ranked tickers stream in — plus a 🏆 leaderboard panel showing the most consistent names across your run.

`↑/↓·j/k` move · `space` select · `a` all · `r` run · `R` run-all · `d` details · `q` quit

## 🚀 Run

```bash
meta-screener list                        # all 28 screeners
meta-screener list --checks               # the 47 meta checks
meta-screener plan --all                  # preview, runs nothing
meta-screener run --screener altman-z     # one screener
meta-screener run --stage company-signals # one group
meta-screener run --all --continue-on-error  # weekly sweep 🧹
meta-screener leaderboard                 # top 10 most consistent tickers 🏆
```

Single scripts work too:

```bash
python3 altman_z.py --tickers AAPL,MSFT
python3 catalyst_scan.py --tickers NVDA,AVGO
```

27 run with `--all`; `screen-history` is opt-in only.

## 📚 The lineup

- 🔍 **Meta signal families** — `meta-momentum · technical · valuation · fundamental · theme · insider · earnings · quality` (47 checks, split up so each runs fast)
- 💰 **Company signals** — `analyst-consensus · short-interest · dividend-analysis · options-activity · smart-money · insider-activity · altman-z · cash-return · dividend-growth`
- 🌍 **Market context** — `sector-rotation · market-breadth · volatility-regime · market-sentiment · commodities-fx · cot-futures-proxy`
- 📅 **Events & tracking** — `catalyst-calendar · research-frontier · screen-history`

`meta-screener leaderboard` tallies every ranked top after a run and lists the 10 tickers that show up most. That's the whole game: **run weekly, buy nothing on the screen alone — dive deeper into the repeat names.** 🔎

## 🐢 Yahoo pacing

One serial scheduler + on-disk cache for everything (`yahoo_client.py`). Sequential runs, one worker, batches of 8, 15s cooldowns (tunable 10–30s). Yahoo rate limit → run stops, no retry, no fake data — blanks stay blank. 📭

## 🤖 MCP for agents

```bash
opencode mcp add meta-screener -- /path/to/repo/.venv/bin/meta-screener-mcp
```

7 tools: `list_screeners · list_checks · plan_screeners · run_screeners · create_screener · register_screener · remove_screener`. Full table + examples: [`docs/MCP.md`](docs/MCP.md).

## 🔒 Notes & limits

No portfolio positions, credentials, or private notes in this repo — they stay local and gitignored. Screens are research leads, not investment decisions. Paper-trading lives next door at [Trading CLI](https://github.com/ryanrodrigues25200525-svg/Trading-CLI). 📈
