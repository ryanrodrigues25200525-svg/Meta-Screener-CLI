#!/usr/bin/env python3
"""attention_backtest.py — does indexed analyst attention predict forward returns?

Tests the RhinoInvestory monthly attention series (month, ticker, articles) against the stored
monthly price layer, market-relative to SPY. Pure stdlib so it runs anywhere.

    python3 attention_backtest.py [--min-articles 1] [--verbose]

Method: for each (ticker, month) with at least one indexed write-up, take the close of that month and
the closes 1/3/6/12 months later from Datasets/History/prices_monthly, subtract SPY's return over the
same window, and aggregate by attention bucket.

Honesty notes baked into the output: overlapping windows (monthly observations share forward returns, so
the effective sample is far smaller than n and any t-like statistic is inflated); survivorship (only
tickers that exist in today's graph and have a price file are testable); no costs, no slippage.
"""
import argparse, csv, os, statistics as st
from collections import defaultdict

def _vault():
    """Resolve the vault in both the host and the docker sandbox (where ~ is /)."""
    for c in (os.environ.get("KG_VAULT"),
              "/documents/Finance Knowledge Graph",
              os.path.expanduser("~/Documents/Finance Knowledge Graph")):
        if c and os.path.isdir(c):
            return c
    raise SystemExit("vault not found - set KG_VAULT")


KG = _vault()
HIST = f"{KG}/Datasets/History/prices_monthly"
ATT = f"{KG}/Datasets/RhinoInvestory/rhino_monthly_attention.csv"


def load_prices():
    px = {}
    for fn in os.listdir(HIST):
        if not fn.endswith(".csv"):
            continue
        tk = fn[:-4]
        series = {}
        for r in csv.DictReader(open(f"{HIST}/{fn}")):
            c = r.get("close")
            try:
                c = float(c)
            except (TypeError, ValueError):
                continue
            if c > 0:
                series[str(r["date"])[:7]] = c
        if series:
            px[tk] = series
    return px


def fwd(series, months_sorted, start_month, k):
    """Return the close k months after start_month (month-index arithmetic on available months)."""
    if start_month not in series:
        return None
    i = months_sorted.index(start_month)
    if i + k >= len(months_sorted):
        return None
    return series[months_sorted[i + k]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-articles", type=int, default=1)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    px = load_prices()
    spy = px.get("SPY")
    if not spy:
        print("no SPY series - cannot compute market-relative returns"); return
    spy_sorted = sorted(spy)

    att = defaultdict(dict)          # ticker -> {month: articles}
    for r in csv.DictReader(open(ATT)):
        try:
            n = int(r["articles"])
        except (TypeError, ValueError):
            continue
        att[r["ticker"].upper()][r["month"]] = n

    testable = {t: s for t, s in att.items() if t in px}
    print(f"attention tickers: {len(att)} | with a price series: {len(testable)} "
          f"| monthly price files: {len(px)}")

    HORIZONS = (1, 3, 6, 12)
    obs = []                          # (ticker, month, articles, trailing_avg, {k: excess})
    for tk, months in testable.items():
        series, ms = px[tk], sorted(px[tk])
        past = []
        for m in sorted(months):
            n = months[m]
            if n < a.min_articles:
                past.append(n); continue
            trail = (sum(past[-3:]) / len(past[-3:])) if past else 0.0
            ex = {}
            for k in HORIZONS:
                f = fwd(series, ms, m, k)
                g = fwd(spy, spy_sorted, m, k)
                if f is None or g is None or series[m] <= 0 or spy[m] <= 0:
                    continue
                ex[k] = (f / series[m] - 1) - (g / spy[m] - 1)
            if ex:
                obs.append((tk, m, n, trail, ex))
            past.append(n)

    print(f"observations (ticker-months with indexed attention and a forward window): {len(obs)}")
    if not obs:
        return

    def agg(rows, k):
        v = [r[4][k] for r in rows if k in r[4]]
        if not v:
            return None
        return {"n": len(v), "mean": st.mean(v), "median": st.median(v),
                "hit": sum(1 for x in v if x > 0) / len(v)}

    def show(title, rows):
        print(f"\n{title}  (n={len(rows)})")
        print(f"  {'horizon':>8} {'n':>5} {'mean':>9} {'median':>9} {'beat SPY':>9}")
        for k in HORIZONS:
            r = agg(rows, k)
            if r:
                print(f"  {str(k)+'m':>8} {r['n']:>5} {r['mean']*100:>8.2f}% {r['median']*100:>8.2f}% {r['hit']*100:>8.1f}%")

    show("ALL attention months", obs)
    show("single write-up that month", [o for o in obs if o[2] == 1])
    show("multiple write-ups that month (2+)", [o for o in obs if o[2] >= 2])
    show("attention SPIKE (>=2x trailing 3m avg)", [o for o in obs if o[3] > 0 and o[2] >= 2 * o[3]])
    show("attention COOLING (below trailing 3m avg)", [o for o in obs if o[3] > 0 and o[2] < o[3]])

    # unconditional baseline: every month of every ticker that appears in the attention set
    base = []
    for tk in testable:
        series, ms = px[tk], sorted(px[tk])
        for m in ms:
            ex = {}
            for k in HORIZONS:
                f = fwd(series, ms, m, k); g = fwd(spy, spy_sorted, m, k)
                if f is None or g is None:
                    continue
                ex[k] = (f / series[m] - 1) - (g / spy[m] - 1)
            if ex:
                base.append((tk, m, 0, 0.0, ex))
    show("BASELINE: every month of the same tickers (no attention filter)", base)

    if a.verbose:
        print("\nlargest 12m excess returns in the attention set:")
        for tk, m, n, t, ex in sorted([o for o in obs if 12 in o[4]], key=lambda o: -o[4][12])[:12]:
            print(f"  {tk:8s} {m}  arts={n}  12m excess {ex[12]*100:+.1f}%")


if __name__ == "__main__":
    main()
