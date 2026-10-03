#!/usr/bin/env python3
"""catalyst_scan.py — upcoming earnings catalysts from Yahoo Finance.

Yahoo-backed: per-ticker earnings dates come from Yahoo Finance via
``yahoo_client`` (the only allowed Yahoo path — never call ``yf.Ticker``
directly). Only events Yahoo supplies (earnings dates) are listed; there is
no fallback to local notes. Tickers with no Yahoo earnings dates are blank,
never fabricated.

Usage:
    python3 catalyst_scan.py [--tickers AAPL,MSFT] [--days 21]
        [--result-json out/catalyst.json]
"""

import argparse
import json
import os
import tempfile
from collections.abc import Mapping
from datetime import date, datetime, timedelta

from demo_universe import ROTATION_TICKERS as DEFAULT_TICKERS

def _default_notes_dir():
    override = os.environ.get("SCREEN_NOTES_DIR")
    if override:
        return override
    legacy = os.environ.get("FINANCE_KG_ROOT")
    if legacy:
        return os.path.join(legacy, "Notes")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")


NOTES_DIR = _default_notes_dir()


def _client_for(provider):
    """Return a YahooClient-compatible object (injected stub or live client)."""
    if provider is None:
        import yahoo_client
        return yahoo_client
    if hasattr(provider, "get_earnings_dates"):
        return provider
    if isinstance(provider, Mapping):
        from yahoo_client import YahooClient

        def _from_map(ticker, op="earnings_dates", **kwargs):
            return provider.get(ticker.upper(), [])

        return YahooClient(provider=_from_map)
    if callable(provider):
        from yahoo_client import YahooClient
        return YahooClient(provider=provider)
    raise TypeError("provider must be a YahooClient, a stub with "
                    "get_earnings_dates, a ticker->dates mapping, "
                    "or a provider callable")


def _as_date(value):
    """One date-like value -> datetime.date, or None when unparseable."""
    if value is None:
        return None
    try:
        import pandas as pd
        if isinstance(value, pd.Timestamp):
            return value.date()
    except Exception:
        pass
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (ValueError, TypeError):
        return None


def _earnings_dates(value):
    """Yahoo earnings-dates result (frame, list, or scalar) -> sorted dates."""
    if value is None:
        return []
    try:
        if getattr(value, "empty", False):
            return []
    except Exception:
        pass
    index = getattr(value, "index", None)
    if index is not None:
        try:
            items = list(index)
        except TypeError:
            items = []
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = [value]
    out = []
    for item in items:
        parsed = _as_date(item)
        if parsed is not None:
            out.append(parsed)
    return sorted(set(out))


def _safe_earnings(client, ticker, limit=12):
    """Yahoo earnings dates for one ticker; None when unavailable.

    Rate-limit RuntimeErrors propagate (fail fast); per-ticker gaps are blank.
    """
    try:
        return client.get_earnings_dates(ticker, limit)
    except RuntimeError:
        raise
    except Exception:
        return None


def screen_tickers(tickers, provider=None, days=21):
    """Upcoming Yahoo earnings dates per ticker. One row per ticker."""
    client = _client_for(provider)
    today = date.today()
    end = today + timedelta(days=days)
    rows = []
    for tk in tickers:
        ticker = tk.strip().upper()
        if not ticker:
            continue
        frame = _safe_earnings(client, ticker)
        upcoming = [d for d in _earnings_dates(frame) if today <= d <= end]
        row = {"ticker": ticker}
        if not upcoming:
            row["note"] = "blank — no Yahoo earnings dates in window"
        else:
            row["next"] = upcoming[0].isoformat()
            row["count"] = len(upcoming)
            row["dates"] = [d.isoformat() for d in upcoming]
        rows.append(row)
    return rows


def payload_from_rows(rows, report_path=None, days=21):
    """Earnings rows ordered by next date; blanks last with 'blank' detail."""
    dated = [r for r in rows if r.get("next")]
    blanks = [r for r in rows if not r.get("next")]
    dated.sort(key=lambda r: r["next"])
    top = []
    for rank, row in enumerate(dated, 1):
        extra = ""
        if (row.get("count") or 1) > 1:
            extra = f"; {row['count']} earnings dates in window"
        top.append({
            "rank": rank,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": (f"Earnings {row['next']} (Yahoo earnings dates{extra}; "
                       "confirm with company IR)"),
        })
    for row in blanks:
        top.append({
            "rank": len(top) + 1,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": (f"blank — no Yahoo earnings dates for {row['ticker']} "
                       f"in the next {days}d"),
        })
    return {
        "summary": (f"Upcoming Yahoo earnings dates for {len(dated)} of "
                    f"{len(rows)} tickers in the next {days}d; "
                    f"{len(blanks)} blank (no Yahoo earnings dates)"),
        "report_path": str(report_path) if report_path else None,
        "top": top,
    }


def build_catalyst_payload(tickers, provider=None, days=21, report_path=None):
    """Catalyst payload for the given tickers, fetched via Yahoo only."""
    return payload_from_rows(
        screen_tickers(tickers, provider=provider, days=days),
        report_path, days,
    )


def write_result_json(path, payload):
    absolute_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute_path) or ".", exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=os.path.dirname(absolute_path) or ".",
            prefix=".catalyst-", suffix=".tmp", delete=False,
        ) as handle:
            temporary_path = handle.name
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_path, absolute_path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def write_note(today, rows, days, notes_dir=None):
    notes_dir = notes_dir or NOTES_DIR
    os.makedirs(notes_dir, exist_ok=True)
    lines = [
        "---",
        'type: "research-note"',
        f'date: "{today}"',
        f'topic: "Upcoming earnings catalysts — Yahoo earnings dates, next {days}d"',
        'tags: ["earnings", "catalysts"]',
        "---",
        "",
        f"# Upcoming Catalysts (Yahoo earnings) — {today}",
        "",
        f"Only earnings dates Yahoo supplies, next {days} days. "
        "Confirm every date with company IR before acting.",
        "",
        "| Ticker | Next earnings (Yahoo) | Dates in window |",
        "|--------|-----------------------|-----------------|",
    ]
    for row in sorted(rows, key=lambda r: r.get("next") or "9999"):
        if row.get("next"):
            lines.append(f"| {row['ticker']} | {row['next']} | {row.get('count', 1)} |")
        else:
            lines.append(f"| {row['ticker']} | blank | 0 |")
    path = os.path.join(notes_dir, f"{today} Catalysts.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote", path)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers",
                    help="comma-separated symbols; default: built-in selection list")
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--result-json", help="write the ranked rows for the CLI dashboard")
    a = ap.parse_args(argv)
    tickers = ([t.strip().upper() for t in a.tickers.split(",") if t.strip()]
               if a.tickers else list(DEFAULT_TICKERS))
    rows = screen_tickers(tickers, days=a.days)
    payload = payload_from_rows(rows, days=a.days)
    print(payload["summary"])
    for row in payload["top"]:
        print("   %2d. %-6s %s" % (row["rank"], row["ticker"], row["detail"]))
    note_path = write_note(date.today().isoformat(), rows, a.days)
    if a.result_json:
        write_result_json(a.result_json,
                          payload_from_rows(rows, os.path.abspath(note_path), a.days))


if __name__ == "__main__":
    main()
