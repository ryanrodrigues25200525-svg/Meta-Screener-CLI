#!/usr/bin/env python3
"""signal_validation.py — follow-ups from the attention backtest:

 A. attention, NON-OVERLAPPING (one observation per ticker per quarter) — does the convergence
    bucket keep its sign when overlapping windows are removed?
 B. BuySide Digest dated BEAR pitches -> forward excess returns, split by source type
    (Fund Letters = an owner/fund arguing a case, Seeking Alpha = contributor article), which also
    tests the claim that most of the bearish "signal" is not smart money.

Pure stdlib.  python3 signal_validation.py
"""
import csv, os, statistics as st
from collections import defaultdict


def _vault():
    for c in (os.environ.get("KG_VAULT"), "/documents/Finance Knowledge Graph",
              os.path.expanduser("~/Documents/Finance Knowledge Graph")):
        if c and os.path.isdir(c):
            return c
    raise SystemExit("vault not found")


KG = _vault()
HIST = f"{KG}/Datasets/History/prices_monthly"


def load():
    px = {}
    for fn in os.listdir(HIST):
        if not fn.endswith(".csv"):
            continue
        s = {}
        for r in csv.DictReader(open(f"{HIST}/{fn}")):
            try:
                c = float(r["close"])
            except (TypeError, ValueError):
                continue
            if c > 0:
                s[str(r["date"])[:7]] = c
        if s:
            px[fn[:-4]] = s
    return px


def fwd(s, ms, start, k):
    if start not in s:
        return None
    i = ms.index(start)
    return s[ms[i + k]] if i + k < len(ms) else None


MONTHS = {m: f"{i:02d}" for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def to_month(d):
    """Accept ISO (2026-09-15) or the site's display form (Sep 15, 2026)."""
    d = (d or "").strip()
    if len(d) >= 7 and d[4] == "-":
        return d[:7]
    parts = d.replace(",", "").split()
    if len(parts) == 3 and parts[0][:3] in MONTHS:
        return f"{parts[2]}-{MONTHS[parts[0][:3]]}"
    if len(parts) == 3 and parts[1][:3] in MONTHS:
        return f"{parts[2]}-{MONTHS[parts[1][:3]]}"
    return ""


def excess(px, spy, spy_ms, tk, m, k):
    s, ms = px[tk], sorted(px[tk])
    f, g = fwd(s, ms, m, k), fwd(spy, spy_ms, m, k)
    if f is None or g is None:
        return None
    return (f / s[m] - 1) - (g / spy[m] - 1)


def line(label, vals):
    if not vals:
        print(f"  {label:<46} n=0")
        return
    hit = sum(1 for v in vals if v > 0) / len(vals)
    print(f"  {label:<46} n={len(vals):>4}  mean {st.mean(vals)*100:>+7.2f}%  "
          f"median {st.median(vals)*100:>+7.2f}%  beat SPY {hit*100:>5.1f}%")


def main():
    px = load()
    spy = px.get("SPY")
    spy_ms = sorted(spy)
    print(f"price files: {len(px)}\n")

    # ---------- A. non-overlapping attention (quarter-start months only) ----------
    att = defaultdict(dict)
    for r in csv.DictReader(open(f"{KG}/Datasets/RhinoInvestory/rhino_monthly_attention.csv")):
        try:
            att[r["ticker"].upper()][r["month"]] = int(r["articles"])
        except (ValueError, KeyError):
            continue
    QSTART = ("-01", "-04", "-07", "-10")
    print("A. NON-OVERLAPPING (attention sampled at quarter starts; 3m forward return)\n")
    buckets = {"any attention": [], "single write-up": [], "2+ write-ups": []}
    base = []
    for tk, months in att.items():
        if tk not in px:
            continue
        for m, n in months.items():
            if not m.endswith(QSTART):
                continue
            k = 3
            e = excess(px, spy, spy_ms, tk, m, k)
            if e is None:
                continue
            buckets["any attention"].append(e)
            if n == 1:
                buckets["single write-up"].append(e)
            if n >= 2:
                buckets["2+ write-ups"].append(e)
    for tk in {t for t in att if t in px}:
        for m in sorted(px[tk]):
            if m.endswith(QSTART):
                e = excess(px, spy, spy_ms, tk, m, 3)
                if e is not None:
                    base.append(e)
    for k, v in buckets.items():
        line(k, v)
    line("BASELINE (all quarter-start months)", base)

    # ---------- B. dated bear pitches ----------
    print("\nB. DATED BEAR PITCHES (BuySide Digest) -> forward excess return\n")
    rows = [r for r in csv.DictReader(open(f"{KG}/Datasets/BuySideDigest/bsd_pitches.csv"))
            if r["stance"] == "Bear"]
    by_type = defaultdict(lambda: defaultdict(list))
    detail = []
    for r in rows:
        tk = r["ticker"].upper()
        if tk not in px:
            continue
        m = to_month(r["date"])
        if not m or m not in px[tk]:
            continue
        rec = {"ticker": tk, "date": r["date"], "type": r["type"], "author": r["author"]}
        for k in (1, 3, 6):
            e = excess(px, spy, spy_ms, tk, m, k)
            if e is not None:
                rec[f"{k}m"] = e
                by_type[r["type"]][k].append(e)
        detail.append(rec)
    for k in (1, 3, 6):
        for typ in sorted(by_type):
            line(f"{typ} bears, {k}m", by_type[typ][k])
        allv = [v for typ in by_type for v in by_type[typ][k]]
        line(f"ALL bears, {k}m", allv)
        print()
    print("per-pitch detail (negative = the name lagged SPY after the bear pitch):")
    for d in sorted(detail, key=lambda d: d.get("3m", 9)):
        f = lambda k: f"{d[k]*100:+6.1f}%" if k in d else "   n/a"
        print(f"  {d['ticker']:<6} {d['date']:<12} {d['type']:<14} {str(d['author'])[:26]:<28} "
              f"1m {f('1m')}  3m {f('3m')}  6m {f('6m')}")


if __name__ == "__main__":
    main()
