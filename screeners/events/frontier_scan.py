#!/usr/bin/env python3
"""frontier_scan.py — latest Yahoo news per ticker (open research leads).

Yahoo-backed: every story comes from Yahoo Finance ``Ticker.news`` via
``yahoo_client`` (the only allowed Yahoo path — never call ``yf.Ticker``
directly). Stories are listed in recency order per ticker, capped at a few
per name; the list is NOT ranked by importance and no finding is invented.
Tickers with no Yahoo news are blank, never fabricated.

Usage:
    python3 frontier_scan.py [--tickers AAPL,MSFT] [--per-ticker 3]
        [--result-json out/frontier.json]
"""

import argparse
import json
import os
import tempfile
from collections.abc import Mapping
from datetime import date


def _default_notes_dir():
    override = os.environ.get("SCREEN_NOTES_DIR")
    if override:
        return override
    legacy = os.environ.get("FINANCE_KG_ROOT")
    if legacy:
        return os.path.join(legacy, "Notes")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")


NOTES_DIR = _default_notes_dir()

from demo_universe import ROTATION_TICKERS as DEFAULT_TICKERS


def _client_for(provider):
    """Return a YahooClient-compatible object (injected stub or live client)."""
    if provider is None:
        import yahoo_client
        return yahoo_client
    if hasattr(provider, "get_news"):
        return provider
    if isinstance(provider, Mapping):
        from yahoo_client import YahooClient

        def _from_map(ticker, op="news", **kwargs):
            return list(provider.get(ticker.upper(), []))

        return YahooClient(provider=_from_map)
    if callable(provider):
        from yahoo_client import YahooClient
        return YahooClient(provider=provider)
    raise TypeError("provider must be a YahooClient, a stub with "
                    "get_news, a ticker->stories mapping, "
                    "or a provider callable")


def _safe_news(client, ticker):
    """Yahoo news stories for one ticker; [] when unavailable.

    Rate-limit RuntimeErrors propagate (fail fast); per-ticker gaps are blank.
    """
    try:
        stories = client.get_news(ticker)
    except RuntimeError:
        raise
    except Exception:
        return []
    if not stories:
        return []
    try:
        return list(stories)
    except TypeError:
        return []


def _story_sort_key(story):
    try:
        published = story.get("providerPublishTime") or story.get("pubTime") or 0
        return -int(published)
    except (TypeError, ValueError, AttributeError):
        return 0


def screen_tickers(tickers, provider=None, per_ticker=3):
    """Latest Yahoo news stories per ticker. One row per (ticker, story)."""
    client = _client_for(provider)
    rows = []
    for tk in tickers:
        ticker = tk.strip().upper()
        if not ticker:
            continue
        stories = sorted(_safe_news(client, ticker), key=_story_sort_key)
        if not stories:
            rows.append({"ticker": ticker, "blank": True})
            continue
        for story in stories[:per_ticker]:
            if not isinstance(story, dict):
                continue
            rows.append({
                "ticker": ticker,
                "title": str(story.get("title") or "").strip(),
                "link": str(story.get("link") or story.get("url") or "").strip(),
                "publisher": str(story.get("publisher") or "").strip(),
            })
    return rows


def payload_from_rows(rows, report_path=None):
    """News rows in recency order with title/link detail; blanks last."""
    stories = [r for r in rows if not r.get("blank") and r.get("title")]
    blanks = [r for r in rows if r.get("blank")]
    tickers = sorted({r["ticker"] for r in rows})
    top = []
    for rank, row in enumerate(stories, 1):
        source = f" — {row['publisher']}" if row.get("publisher") else ""
        link = f" ({row['link']})" if row.get("link") else ""
        top.append({
            "rank": rank,
            "ticker": row["ticker"],
            "name": row["title"][:80],
            "detail": f"{row['title']}{source}{link}",
        })
    for row in blanks:
        top.append({
            "rank": len(top) + 1,
            "ticker": row["ticker"],
            "name": row["ticker"],
            "detail": (f"blank — no Yahoo news for {row['ticker']}; "
                       "no research lead"),
        })
    return {
        "summary": (f"Latest Yahoo news for {len(tickers)} tickers: "
                    f"{len(stories)} stories listed in recency order "
                    f"(not ranked by importance); {len(blanks)} blank "
                    "(no Yahoo news)"),
        "report_path": str(report_path) if report_path else None,
        "top": top,
    }


def build_frontier_payload(tickers, provider=None, report_path=None,
                           per_ticker=3):
    """Frontier payload for the given tickers, fetched via Yahoo only."""
    return payload_from_rows(
        screen_tickers(tickers, provider=provider, per_ticker=per_ticker),
        report_path,
    )


def write_result_json(path, payload):
    absolute_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute_path) or ".", exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=os.path.dirname(absolute_path) or ".",
            prefix=".frontier-", suffix=".tmp", delete=False,
        ) as handle:
            temporary_path = handle.name
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_path, absolute_path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def write_note(today, rows, notes_dir=None):
    notes_dir = notes_dir or NOTES_DIR
    os.makedirs(notes_dir, exist_ok=True)
    lines = [
        "---",
        'type: "research-note"',
        f'date: "{today}"',
        'topic: "Research frontier — latest Yahoo news per ticker"',
        'tags: ["news", "research-frontier"]',
        "---",
        "",
        f"# Research Frontier (Yahoo news) — {today}",
        "",
        "Latest Yahoo stories per ticker, recency order. "
        "Not ranked by importance — each story is a lead to check, not a finding.",
        "",
        "| Ticker | Story | Publisher | Link |",
        "|--------|-------|-----------|------|",
    ]
    for row in rows:
        if row.get("blank"):
            lines.append(f"| {row['ticker']} | blank — no Yahoo news | | |")
        else:
            lines.append("| %s | %s | %s | %s |" % (
                row["ticker"],
                (row.get("title") or "").replace("|", "/"),
                row.get("publisher") or "",
                row.get("link") or "",
            ))
    path = os.path.join(notes_dir, f"{today} Frontier.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote", path)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers",
                    help="comma-separated symbols; default: built-in selection list")
    ap.add_argument("--per-ticker", type=int, default=3)
    ap.add_argument("--result-json", help="write the stories for the CLI dashboard")
    a = ap.parse_args(argv)
    tickers = ([t.strip().upper() for t in a.tickers.split(",") if t.strip()]
               if a.tickers else list(DEFAULT_TICKERS))
    rows = screen_tickers(tickers, per_ticker=a.per_ticker)
    payload = payload_from_rows(rows)
    print(payload["summary"])
    for row in payload["top"][:20]:
        print("   %2d. %-6s %s" % (row["rank"], row["ticker"], row["detail"][:160]))
    note_path = write_note(date.today().isoformat(), rows)
    if a.result_json:
        write_result_json(a.result_json,
                          payload_from_rows(rows, os.path.abspath(note_path)))


if __name__ == "__main__":
    main()
