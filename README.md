# Meta Screener CLI 🔎

**Find stocks worth a closer look—without running scripts one by one.**

Type `meta-screener` to run the core screen. It checks a demo universe, ranks companies by overlap across 47 signals, and prints the leading names. The repo also includes 82 Python tools from the wider Finance AI workflow; [`PYTHON_TOOLS.md`](PYTHON_TOOLS.md) catalogs every one of them by purpose.

## 🚀 Install

Requires Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-screening.txt
python -m pip install -e .
```

## ▶️ Run

```bash
meta-screener
```

To explore or run more screens:

```bash
meta-screener list
meta-screener list --checks
meta-screener plan --all
meta-screener run --stage discovery
meta-screener run --all
```

`run --all` runs the default-enabled subset of the 17 workflows registered in `screeners.json`: 16 run by default, while `screen-history` is an optional outcome tracker excluded from the default run. The other Python files are supporting tools; they do not run automatically. See [`PYTHON_TOOLS.md`](PYTHON_TOOLS.md) for the full catalog.

## 📊 What the core screen checks

The 47 checks look at price momentum, technical signals, valuation, business fundamentals, themes, insider activity, earnings, and company quality. The ranking favors breadth across signal families. Related checks are not treated as separate confirmations, and missing data is shown as unavailable.

## 🛡️ Yahoo Finance pacing

The core screen uses one worker and batches up to 25 symbols, with a 10-second pause between full batches. A 100-company run has about 30 seconds of planned cooldown, plus network time. If Yahoo returns a rate-limit error, the CLI stops and does not retry automatically.

## 🗂️ Local data

The public repo does not include portfolio positions, private watchlists, credentials, or generated research history. Personal files such as `pm_portfolio.json`, `positions.json`, and `universe.csv` stay local and are ignored by Git.

The core screen writes a dated note to your Finance Knowledge Graph and updates local screen history. Use `meta-screener plan --all` to preview the wider run before launching it. Some of the 82 supporting scripts need additional local data or tools.

A screen pass is a research lead, not an investment decision. The CLI does not place orders.

This is separate from [Trading CLI](https://github.com/ryanrodrigues25200525-svg/Trading-CLI), which is for paper-trading workflows.
