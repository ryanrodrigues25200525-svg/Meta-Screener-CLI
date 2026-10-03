#!/usr/bin/env python3
"""Scan insider transactions from Yahoo Finance.

Yahoo-backed: transaction tables come from Yahoo Finance via
``yahoo_client`` (the only allowed Yahoo path — never call ``yf.Ticker``
directly). The ticker list is an explicit ``--tickers`` selection or the
shared built-in universe; nothing is read from local files.

Usage:
    python3 insider_activity.py [--tickers AAPL,MSFT] [--result-json out/insider.json]
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

_BUY_RE = ("buy", "purchase", "acqui", "award", "grant", "exercise")
_SELL_RE = ("sale", "sell", "dispos")


def default_tickers():
    """Shared built-in universe (selection input only)."""
    return list(HOLDINGS_TICKERS)


def _client_for(provider):
    """Return a YahooClient-compatible object (injected stub or live client)."""
    if provider is None:
        import yahoo_client
        return yahoo_client
    if hasattr(provider, "get_insider"):
        return provider
    if callable(provider):
        from yahoo_client import YahooClient
        return YahooClient(provider=provider)
    raise TypeError("provider must be a YahooClient, a stub with "
                    "get_insider, or a provider callable")


def _classify(text):
    lowered = str(text or "").lower()
    if any(marker in lowered for marker in _BUY_RE):
        return "buy"
    if any(marker in lowered for marker in _SELL_RE):
        return "sell"
    return None


def _summarize(frame):
    """(buyers, sellers, net_shares) from an insider-transactions frame."""
    if frame is None or getattr(frame, "empty", True):
        return None
    try:
        columns = [str(c) for c in frame.columns]
    except Exception:
        return None
    lowered = {c.lower(): c for c in columns}
    txn_key = next((lowered[c] for c in lowered
                    if "trans" in c or "type" in c), None)
    text_key = next((lowered[c] for c in lowered if c == "text"), None)
    shares_key = next((lowered[c] for c in lowered if "share" in c), None)
    insider_key = next((lowered[c] for c in lowered
                        if "insider" in c or "name" in c or "holder" in c), None)
    if txn_key is None:
        return None
    buyers: set[str] = set()
    sellers: set[str] = set()
    net = 0.0
    for _, row in frame.iterrows():
        side = _classify(row.get(txn_key))
        if side is None and text_key is not None:
            side = _classify(row.get(text_key))
        if side is None:
            continue
        try:
            value = float(row.get("Value") or 0)
        except (TypeError, ValueError):
            value = 0.0
        text = f"{row.get(txn_key) or ''} {row.get(text_key) or ''}".lower()
        if side == "buy" and value == 0 and any(
                w in text for w in ("award", "grant", "gift")):
            continue  # compensation, not open-market conviction
        try:
            shares = float(row.get(shares_key) or 0) if shares_key else 0.0
        except (TypeError, ValueError):
            shares = 0.0
        name = str(row.get(insider_key) or "?") if insider_key else "?"
        if side == "buy":
            buyers.add(name)
            net += shares
        else:
            sellers.add(name)
            net -= shares
    if not buyers and not sellers:
        return None
    return len(buyers), len(sellers), net


def screen_tickers(tickers, provider=None):
    """Insider-activity rows for the given tickers, fetched via Yahoo only."""
    client = _client_for(provider)
    rows = []
    for tk in tickers:
        ticker = tk.strip().upper()
        if not ticker:
            continue
        try:
            frame = client.get_insider(ticker)
        except RuntimeError:
            raise
        except Exception:
            frame = None
        summary = _summarize(frame)
        if summary is None:
            rows.append({"ticker": ticker, "blank": True})
            continue
        buyers, sellers, net = summary
        rows.append({"ticker": ticker, "buyers": buyers,
                     "sellers": sellers, "net": net})
    return rows


def build_result_payload(data, report_path):
    measured = [r for r in data if not r.get("blank")]
    blanks = [r for r in data if r.get("blank")]
    ranked = sorted(measured, key=lambda row: (row.get("buyers") or 0,
                                               row.get("net") or 0), reverse=True)
    top = []
    for rank, row in enumerate(ranked, 1):
        top.append({
            "rank": rank,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": (f"{row['buyers']} buyers / {row['sellers']} sellers "
                       f"(net {row['net']:+.0f} sh)"),
        })
    for row in blanks:
        top.append({
            "rank": len(top) + 1,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": f"blank — no Yahoo insider info for {row['ticker']}",
        })
    return {
        "summary": (f"{len(ranked)} names with Yahoo insider info "
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
            prefix=".insider-activity-", suffix=".tmp", delete=False,
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
        'topic: "Insider activity — Yahoo transactions"',
        'tags: ["insider", "transactions"]',
        "---",
        "",
        f"# Insider Activity (Yahoo) — {today}",
        "",
        "| Ticker | Buyers | Sellers | Net sh |",
        "|--------|--------|---------|--------|",
    ]
    ranked = sorted([d for d in data if not d.get("blank")],
                    key=lambda x: (x.get("buyers") or 0, x.get("net") or 0),
                    reverse=True)
    for d in ranked:
        lines.append(f"| {d['ticker']} | {d['buyers']} | {d['sellers']} | {d['net']:+.0f} |")
    for d in [d for d in data if d.get("blank")]:
        lines.append(f"| {d['ticker']} | blank | | |")
    path = os.path.join(notes_dir, f"{today} Insider-Activity.md")
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
    print(f"Insider activity for {len(ranked)} of {len(tickers)} tickers; {len(blanks)} blank")
    for row in sorted(ranked, key=lambda r: (r.get("buyers") or 0, r.get("net") or 0),
                      reverse=True)[:10]:
        print(f"  {row['ticker']:6} {row['buyers']} buyers / {row['sellers']} sellers")
    for row in blanks:
        print(f"  {row['ticker']:6} blank — no Yahoo insider info")
    write_note(today, data, args.result_json)


if __name__ == "__main__":
    main()
