#!/usr/bin/env python3
"""Rank dividend-growth streaks from Yahoo Finance.

Yahoo-backed: payout history comes from Yahoo Finance via ``yahoo_client``
(the only allowed Yahoo path — never call ``yf.Ticker`` directly). Annual
payouts are summed per calendar year; the streak is the run of consecutive
year-over-year increases ending in the latest year. Missing history stays
blank.

Usage:
    python3 dividend_growth.py [--tickers VZ,JNJ] [--result-json out/divgrowth.json]
"""

import argparse
import json
import os
import tempfile
from datetime import date

from demo_universe import HOLDINGS_TICKERS


def _default_notes_dir():
    override = os.environ.get("SCREEN_NOTES_DIR")
    if override:
        return override
    legacy = os.environ.get("FINANCE_AI_ROOT") or os.environ.get("FINANCE_KG_ROOT")
    if legacy:
        return os.path.join(legacy, "Notes")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")


NOTES_DIR = _default_notes_dir()


def default_tickers():
    """Shared built-in universe (selection input only)."""
    return list(HOLDINGS_TICKERS)


def _client_for(provider):
    """Return a YahooClient-compatible object (injected stub or live client)."""
    if provider is None:
        import yahoo_client
        return yahoo_client
    if hasattr(provider, "get_dividends"):
        return provider
    if callable(provider):
        from yahoo_client import YahooClient
        return YahooClient(provider=provider)
    raise TypeError("provider must be a YahooClient, a stub with "
                    "get_dividends, or a provider callable")


def _annual_totals(divs):
    """Calendar-year payout sums oldest -> newest; empty when unusable."""
    try:
        import pandas as pd

        series = pd.to_numeric(pd.Series(divs).dropna(), errors="coerce").dropna()
    except Exception:
        return []
    if series.empty:
        return []
    try:
        grouped = series.groupby(series.index.year)
        totals = [(int(year), round(float(group.sum()), 4))
                  for year, group in grouped]
    except Exception:
        return []
    return sorted(totals)


def _streak(totals):
    """Consecutive YoY increases ending at the latest full year (0 when none).

    The current calendar year is still paying out, so it is excluded from
    the streak endpoint; otherwise every payer would read 0 in-year.
    """
    from datetime import date as _date

    full = [t for t in totals if t[0] < _date.today().year]
    if len(full) < 2:
        return 0, (full[-1][1] if full else 0.0), 0.0
    run = 0
    for i in range(len(full) - 1, 0, -1):
        if full[i][1] > full[i - 1][1]:
            run += 1
        else:
            break
    latest, previous = full[-1][1], full[-2][1]
    change = round((latest - previous) / previous * 100, 1) if previous else 0.0
    return run, latest, change


def screen_tickers(tickers, provider=None):
    """Dividend-growth rows for the given tickers, fetched via Yahoo only."""
    client = _client_for(provider)
    rows = []
    for tk in tickers:
        ticker = tk.strip().upper()
        if not ticker:
            continue
        try:
            divs = client.get_dividends(ticker)
        except RuntimeError:
            raise
        except Exception:
            divs = None
        totals = _annual_totals(divs)
        if not totals:
            rows.append({"ticker": ticker, "blank": True})
            continue
        run, latest, change = _streak(totals)
        rows.append({"ticker": ticker, "streak": run,
                     "latest": latest, "change": change})
    return rows


def build_result_payload(data, report_path):
    measured = [r for r in data if not r.get("blank")]
    blanks = [r for r in data if r.get("blank")]
    ranked = sorted(measured, key=lambda row: (row.get("streak") or 0,
                                               row.get("change") or 0), reverse=True)
    top = []
    for rank, row in enumerate(ranked, 1):
        top.append({
            "rank": rank,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": (f"{row['streak']}-year raiser; latest ${row['latest']} "
                       f"({row['change']:+.1f}%)"),
        })
    for row in blanks:
        top.append({
            "rank": len(top) + 1,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": f"blank — no Yahoo dividend history for {row['ticker']}",
        })
    return {
        "summary": (f"{len(ranked)} names with Yahoo dividend history "
                    f"({len(blanks)} blank)"),
        "report_path": str(report_path),
        "top": top,
    }


def write_result_json(path, payload):
    absolute_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=os.path.dirname(absolute_path),
            prefix=".dividend-growth-", suffix=".tmp", delete=False,
        ) as handle:
            temporary_path = handle.name
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_path, absolute_path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def write_note(today, data, result_json_path=None, notes_dir=None):
    notes_dir = notes_dir or NOTES_DIR
    os.makedirs(notes_dir, exist_ok=True)
    lines = [
        "---",
        'type: "research-note"',
        f'date: "{today}"',
        'topic: "Dividend growth — Yahoo payout streaks"',
        'tags: ["dividend", "growth"]',
        "---",
        "",
        f"# Dividend Growth (Yahoo) — {today}",
        "",
        "| Ticker | Streak | Latest $ | Change % |",
        "|--------|--------|----------|----------|",
    ]
    ranked = sorted([d for d in data if not d.get("blank")],
                    key=lambda x: (x.get("streak") or 0, x.get("change") or 0),
                    reverse=True)
    for d in ranked:
        lines.append(f"| {d['ticker']} | {d['streak']}y | ${d['latest']} | {d['change']:+.1f}% |")
    for d in [d for d in data if d.get("blank")]:
        lines.append(f"| {d['ticker']} | blank | | |")
    path = os.path.join(notes_dir, f"{today} Dividend-Growth.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {path}")
    if result_json_path:
        write_result_json(result_json_path, build_result_payload(data, path))
    return path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", type=str, default=None,
                    help="comma-separated symbols; default: built-in universe")
    ap.add_argument("--result-json", help="write the ranked rows for the CLI dashboard")
    args = ap.parse_args(argv)
    today = date.today().isoformat()
    tickers = ([t.strip().upper() for t in args.tickers.split(",") if t.strip()]
               if args.tickers else default_tickers())
    data = screen_tickers(tickers)
    ranked = [d for d in data if not d.get("blank")]
    blanks = [d for d in data if d.get("blank")]
    print(f"Dividend history for {len(ranked)} of {len(tickers)} tickers; {len(blanks)} blank")
    for row in sorted(ranked, key=lambda r: (r.get("streak") or 0, r.get("change") or 0),
                      reverse=True)[:10]:
        print(f"  {row['ticker']:6} {row['streak']}y raiser (${row['latest']})")
    for row in blanks:
        print(f"  {row['ticker']:6} blank — no Yahoo dividend history")
    write_note(today, data, args.result_json)


if __name__ == "__main__":
    main()
