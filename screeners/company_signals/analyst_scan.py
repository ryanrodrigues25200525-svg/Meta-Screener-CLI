#!/usr/bin/env python3
"""analyst_scan.py — sell-side analyst consensus from Yahoo Finance.

Yahoo-backed: recommendation, price-target range, and analyst count come
from Yahoo Finance ``info`` via ``yahoo_client`` (the only allowed Yahoo
path — never call ``yf.Ticker`` directly). The ticker list is an explicit
``--tickers`` selection or the shared built-in universe; nothing is read
from local portfolio files or company notes.

EVERY RATING IS A CLAIM from a conflicted crowd, not a fact.

Usage:
    python3 analyst_scan.py [--tickers AAPL,MSFT] [--top N]
        [--batch-size N] [--batch-pause-seconds 10..30]
        [--result-json out/analyst.json]
"""

import argparse
import json
import os
import tempfile
import time
from datetime import date

from demo_universe import HOLDINGS_TICKERS


def _default_notes_dir():
    override = os.environ.get("SCREEN_NOTES_DIR")
    if override:
        return override
    legacy = os.environ.get("FINANCE_KG_ROOT")
    if legacy:
        return os.path.join(legacy, "Notes")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")


NOTES_DIR = _default_notes_dir()


def default_tickers():
    """Shared built-in universe (selection input only)."""
    return list(HOLDINGS_TICKERS)


def collect_tickers(explicit=None):
    """Explicit --tickers selection, else the shared built-in universe."""
    if explicit:
        return [t.strip().upper() for t in explicit if t.strip()]
    return default_tickers()


def _client_for(provider):
    """Return a YahooClient-compatible object (injected stub or live client)."""
    if provider is None:
        import yahoo_client
        return yahoo_client
    if hasattr(provider, "get_info"):
        return provider
    if callable(provider):
        from yahoo_client import YahooClient
        return YahooClient(provider=provider)
    raise TypeError("provider must be a YahooClient, a stub with "
                    "get_info, or a provider callable")


def fetch_consensus(sym, client=None):
    """Yahoo analyst fields for one symbol, or None when unavailable.

    Rate-limit RuntimeErrors propagate (fail fast); per-ticker gaps are blank.
    """
    holder = _client_for(client)
    try:
        info = holder.get_info(sym)
    except RuntimeError:
        raise
    except Exception:
        return None
    if not info:
        return None
    try:
        return {
            "rec": info.get("recommendationKey"),
            "tgt": info.get("targetMeanPrice"),
            "hi": info.get("targetHighPrice"),
            "lo": info.get("targetLowPrice"),
            "n": info.get("numberOfAnalystOpinions"),
            "last": info.get("currentPrice") or info.get("regularMarketPrice"),
        }
    except AttributeError:
        return None


def screen_tickers(tickers, provider=None):
    """Yahoo analyst consensus rows for each ticker. One row per ticker."""
    client = _client_for(provider)
    rows = []
    for tk in tickers:
        ticker = tk.strip().upper()
        if not ticker:
            continue
        consensus = fetch_consensus(ticker, client=client)
        if consensus is None:
            rows.append({"sym": ticker, "blank": True})
        else:
            rows.append({"sym": ticker, **consensus})
    return rows


def _upside(row):
    try:
        if row.get("tgt") and row.get("last"):
            return (row["tgt"] / row["last"] - 1) * 100
    except (TypeError, ZeroDivisionError):
        pass
    return None


def payload_from_rows(rows, report_path=None):
    """Consensus rows ordered by implied upside; blanks last."""
    measured = [r for r in rows if not r.get("blank")]
    blanks = [r for r in rows if r.get("blank")]
    measured.sort(key=lambda r: (_upside(r) is None, -(_upside(r) or 0)))
    top = []
    for rank, row in enumerate(measured, 1):
        ups = _upside(row)
        ups_text = f"{ups:+.0f}%" if ups is not None else "n/a"
        text = lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) else "n/a"
        top.append({
            "rank": rank,
            "ticker": row["sym"],
            "name": row["sym"],
            "detail": (f"Rec {row.get('rec') or 'n/a'}; mean PT {text(row.get('tgt'))} "
                       f"(hi {text(row.get('hi'))}, lo {text(row.get('lo'))}); "
                       f"n={row.get('n') or 'n/a'}; upside {ups_text} "
                       "(sell-side claim, not a fact)"),
        })
    for row in blanks:
        top.append({
            "rank": len(top) + 1,
            "ticker": row["sym"],
            "name": row["sym"],
            "detail": f"blank — no Yahoo analyst info for {row['sym']}",
        })
    return {
        "summary": (f"Sell-side consensus for {len(measured)} of {len(rows)} "
                    f"tickers from Yahoo info; {len(blanks)} blank. "
                    "Every rating is a CLAIM, not a fact."),
        "report_path": str(report_path) if report_path else None,
        "top": top,
    }


def build_result_payload(rows, report_path=None):
    """Ranked payload for the CLI dashboard (same contract as payload_from_rows)."""
    return payload_from_rows(rows, report_path)


def write_result_json(path, payload):
    absolute_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute_path) or ".", exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=os.path.dirname(absolute_path) or ".",
            prefix=".analyst-", suffix=".tmp", delete=False,
        ) as handle:
            temporary_path = handle.name
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_path, absolute_path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def write_note(today, rows, notes_dir=None, result_json_path=None):
    notes_dir = notes_dir or NOTES_DIR
    os.makedirs(notes_dir, exist_ok=True)
    text = lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) else ""
    lines = [
        "---",
        'type: "research-note"',
        f'date: "{today}"',
        'topic: "Analyst consensus — sell-side PTs (claims, not facts)"',
        'tags: ["analyst", "consensus"]',
        "---",
        "",
        f"# Analyst Consensus (Yahoo) {today}",
        "",
        "Sell-side consensus from Yahoo info. **Every rating is a CLAIM** — "
        "sell-side targets skew optimistic; credibility-tagged, not facts.",
        "",
        "| Ticker | Rec | Mean PT | Hi | Lo | n | Last | Upside |",
        "|--------|-----|---------|----|----|---|------|--------|",
    ]
    for row in [r for r in rows if not r.get("blank")]:
        ups = _upside(row)
        ups_text = f"{ups:+.0f}%" if ups is not None else ""
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            row["sym"], row.get("rec") or "n/a", text(row.get("tgt")),
            text(row.get("hi")), text(row.get("lo")), row.get("n") or "",
            text(row.get("last")), ups_text))
    for row in [r for r in rows if r.get("blank")]:
        lines.append(f"| {row['sym']} | blank | | | | | | |")
    lines.append("")
    lines.append("- High analyst count (n high) = efficiently priced; low n = thinner coverage.")
    path = os.path.join(notes_dir, f"{today} Analyst Consensus.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote", path)
    if result_json_path:
        write_result_json(result_json_path, payload_from_rows(rows, path))
    return path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", help="comma-separated symbols; default: built-in universe")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--batch-pause-seconds", type=int, choices=range(10, 31), default=15)
    ap.add_argument("--result-json", help="write the ranked rows for the CLI dashboard")
    a = ap.parse_args(argv)
    if a.batch_size < 1:
        ap.error("--batch-size must be at least 1")

    syms = collect_tickers(a.tickers.split(",") if a.tickers else None)
    rows = []
    for index, sym in enumerate(syms, start=1):
        consensus = fetch_consensus(sym)
        rows.append({"sym": sym, **consensus} if consensus is not None
                    else {"sym": sym, "blank": True})
        if index < len(syms) and index % a.batch_size == 0:
            print(f"Yahoo cooldown: waiting {a.batch_pause_seconds}s after {index} analyst lookups")
            time.sleep(a.batch_pause_seconds)

    payload = payload_from_rows(rows)
    print(payload["summary"])
    for row in payload["top"][:a.top]:
        print("   %2d. %-6s %s" % (row["rank"], row["ticker"], row["detail"]))
    write_note(date.today().isoformat(), rows, result_json_path=a.result_json)


if __name__ == "__main__":
    main()
