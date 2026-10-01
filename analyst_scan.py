#!/usr/bin/env python3
"""
analyst_scan.py — pulls sell-side analyst consensus (recommendation, mean/high/
low price targets, analyst count) for every ticker in the Finance Knowledge
Graph and writes ~/Documents/Finance Knowledge Graph/Notes/<today> Analyst
Consensus.md.

EVERY RATING IS A CLAIM from a conflicted crowd, not a fact.

Usage: python3 analyst_scan.py [--batch-size N] [--batch-pause-seconds 10..30]

The graph ticker list is processed in batches to reduce Yahoo request bursts.
"""
import os, sys, glob, json, argparse, time
from datetime import date

try:
    import yfinance as yf
except Exception as e:
    print(f"FATAL: yfinance required: {e}")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kg_links  # noqa: E402
from yahoo_guard import raise_if_yahoo_rate_limit  # noqa: E402

KG_NOTES = os.path.expanduser("~/Documents/Finance Knowledge Graph/Notes")

REC_LABEL = {1: "strong_buy", 2: "buy", 3: "hold", 4: "sell", 5: "strong_sell"}


def collect_tickers():
    tmap = kg_links.load_ticker_map()
    return sorted(tmap.keys())


def fetch_consensus(sym):
    """Return dict with recommendation, target stats, price, or None on fail."""
    try:
        tk = yf.Ticker(sym)
        info = tk.info or {}
        rec = info.get("recommendationKey")
        tgt = info.get("targetMeanPrice")
        hi = info.get("targetHighPrice")
        lo = info.get("targetLowPrice")
        n = info.get("numberOfAnalystOpinions")
        last = info.get("currentPrice") or info.get("regularMarketPrice")
        return {"rec": rec, "tgt": tgt, "hi": hi, "lo": lo, "n": n, "last": last}
    except Exception as exc:
        raise_if_yahoo_rate_limit(exc, f"analyst consensus for {sym}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-graph", action="store_true")
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--batch-pause-seconds", type=int, choices=range(10, 31), default=15)
    args = ap.parse_args()
    if args.batch_size < 1:
        ap.error("--batch-size must be at least 1")

    syms = collect_tickers()
    rows = []
    for index, sym in enumerate(syms, start=1):
        c = fetch_consensus(sym)
        if c is not None:
            rows.append({"sym": sym, **c})
        if index < len(syms) and index % args.batch_size == 0:
            print(f"Yahoo cooldown: waiting {args.batch_pause_seconds}s after {index} analyst lookups")
            time.sleep(args.batch_pause_seconds)
    rows.sort(key=lambda r: -((r["tgt"] or 0) / max(r["last"] or 1, 0.01)))

    _write_note(date.today().isoformat(), rows)


def _write_note(today, rows):
    os.makedirs(KG_NOTES, exist_ok=True)
    tmap = kg_links.load_ticker_map()
    front = (
        "---\n"
        f'type: "research-note"\n'
        f'date: "{today}"\n'
        f'topic: "Analyst consensus — sell-side PTs + credibility routing"\n'
        'companies: []\n'
        'themes: [""]\n'
        'context: [""]\n'
        'sources: ["[[SEC filings]]"]\n'
        'status: "open"\n'
        'importance: 3\n'
        "---\n\n"
    )
    body = [f"# Analyst Consensus {today}\n",
            "Sell-side consensus for graph-tracked names. **Every rating is a CLAIM** — sell-side targets are historically optimistic (buy-skew); credibility-tagged, not facts.\n",
            "| Ticker | Rec | Mean PT | Hi | Lo | n | Last | Upside |\n|--------|-----|------|----|----|---|------|--------|"]
    for r in rows:
        rec = r["rec"] or "None"
        ups = ""
        if r.get("tgt") and r.get("last") and r["last"]:
            try:
                ups = f"{((r['tgt']/r['last'])-1)*100:+.0f}%"
            except Exception:
                ups = ""
        f = lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) else ""
        body.append(f"| {r['sym']} | {rec} | {f(r['tgt'])} | {f(r['hi'])} | {f(r['lo'])} | {r['n'] or ''} | {f(r['last'])} | {ups} |")
    body.append("\n## Notes on the layer\n- High analyst count (n high) = efficiently priced; low n = thinner coverage / more idiosyncratic.")
    body.append("- Cross-reference any independent/activist Person node in the graph that contradicts a sell-side target (credibility layer tension).\n")
    title = os.path.join(KG_NOTES, f"{today} Analyst Consensus.md")
    with open(title, "w", encoding="utf-8") as f:
        f.write(front + "\n".join(body) + "\n")
    print("wrote", title)
    print(f"tickers: {len(rows)}")


if __name__ == "__main__":
    main()
