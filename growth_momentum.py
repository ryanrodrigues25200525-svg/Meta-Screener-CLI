#!/usr/bin/env python3
"""growth_momentum.py — revenue growth and its direction, from the stored fundamentals layer.

Answers a live question for an AI-capex-heavy book: is the complex still accelerating? Reads only the
vault's own fundamentals files, so it is reproducible offline and needs no provider call.

Honesty constraints built in:
  * Fiscal year ends differ (MU Aug, NVDA Jan, TSM Dec, WDC Jun). YoY is computed WITHIN each company, so
    a comparison across names is directional, not calendar-aligned.
  * TSM reports in TWD and NVO in DKK. Growth rates are currency-neutral; absolute revenue is not.
  * Blank periods are skipped, never treated as zero (the provider leaves the oldest annual period and the
    newest quarter partly empty).
  * The newest period can be partially populated, so a missing revenue figure ends the series rather than
    producing a fake -100%.

Usage: python3 ~/Documents/finance-ai/growth_momentum.py
"""
import csv, glob, os

VAULT = next(c for c in (os.environ.get("KG_VAULT"), "/documents/Finance Knowledge Graph",
                         os.path.expanduser("~/Documents/Finance Knowledge Graph"))
             if c and os.path.isdir(c))
BASE = os.path.join(VAULT, "Datasets/History")

SEMIS = {"MU", "NVDA", "TSM", "WDC", "LITE", "MTSI", "SIMO", "ONTO", "RMBS", "TSEM", "AEIS", "AAOI",
         "AVGO", "AMD", "MRVL", "SNDK", "NBIS", "AXTI"}
VALUE = {"VTRS", "HPQ", "GM", "VALE", "SM", "PFE", "PRU", "NVO", "ADBE", "CAG", "GIS", "PBR"}


def series(path, metric="total_revenue"):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    if not rows:
        return [], []
    cols = [c for c in rows[0].keys() if c != "metric"]
    vals = {}
    for r in rows:
        if r.get("metric") == metric:
            for c in cols:
                v = (r.get(c) or "").strip()
                if v:
                    try:
                        vals[c] = float(v)
                    except ValueError:
                        pass
    cols = [c for c in cols if c in vals]
    return cols, [vals[c] for c in cols]


def analyse(kind):
    d = os.path.join(BASE, f"fundamentals_{kind}")
    out = []
    for p in sorted(glob.glob(os.path.join(d, "*.csv"))):
        tk = os.path.basename(p)[:-4]
        cols, vals = series(p)
        if len(vals) < 2:
            out.append((tk, kind, None, None, "insufficient periods (" + str(len(vals)) + ")"))
            continue
        if kind == "quarterly":
            # same-quarter YoY needs 5 quarterly points; with 4-5 stored, compare first vs last year
            growths = []
            for i in range(4, len(vals)):
                if vals[i - 4]:
                    growths.append(vals[i] / vals[i - 4] - 1)
        else:
            growths = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals)) if vals[i - 1]]
        if not growths:
            out.append((tk, kind, None, None, "no comparable pair"))
            continue
        last = growths[-1]
        prev = growths[-2] if len(growths) > 1 else None
        trend = "n/a" if prev is None else ("ACCELERATING" if last > prev else "decelerating")
        out.append((tk, kind, last, prev, trend + " (" + cols[-1] + ")"))
    return out


def qoq_table():
    """Sequential (quarter-on-quarter) growth — the view that separates 'broadening' from 'rollover'.

    Annual YoY can decelerate off a large base while sequential growth accelerates; MU showed exactly that
    (YoY +62%->+49% while quarters ran 13.6 -> 23.9 -> 41.5bn). A rollover shows up in the sequential series
    first, so this is the sharper of the two signals.
    """
    d = os.path.join(BASE, "fundamentals_quarterly")
    rows = []
    for p in sorted(glob.glob(os.path.join(d, "*.csv"))):
        tk = os.path.basename(p)[:-4]
        cols, vals = series(p)
        if len(vals) < 3:
            rows.append((tk, None, "only " + str(len(vals)) + " periods"))
            continue
        growths = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals)) if vals[i - 1]]
        if not growths:
            rows.append((tk, None, "no comparable pair"))
            continue
        trend = "n/a" if len(growths) < 2 else ("accelerating" if growths[-1] > growths[-2] else "decelerating")
        rows.append((tk, growths[-1], trend + " (" + ", ".join(pct(g) for g in growths) + ")"))
    return rows


def pct(x):
    return "n/a" if x is None else f"{x * 100:+.1f}%"


rows = analyse("annual") + analyse("quarterly")

for label, group in (("SEMIS / AI-CAPEX / OPTICS", SEMIS), ("VALUE / NON-SEMI PORTFOLIO", VALUE)):
    print("\n=== " + label + " ===")
    print(f"{'ticker':7} {'kind':10} {'latest YoY':>11} {'prior':>9}  {'direction':22} period")
    acc = dec = 0
    for tk, kind, last, prev, note in rows:
        if tk not in group:
            continue
        if isinstance(last, float):
            if "ACCELERATING" in note:
                acc += 1
            elif "decelerating" in note:
                dec += 1
        print(f"{tk:7} {kind:10} {pct(last):>11} {pct(prev):>9}  {note[:22]:22} {note[note.find('('):] if '(' in note else ''}")
    print(f"   accelerating: {acc}   decelerating: {dec}")

q = [r for r in rows if r[1] == "quarterly" and isinstance(r[2], float)]
print("\n=== QUARTERLY YoY (freshest signal, 12 portfolio names) ===")
for tk, kind, last, prev, note in sorted(q, key=lambda r: -r[2]):
    print(f"   {tk:6} {pct(last):>9}   (prior {pct(prev)}, {note.split('(')[0].strip()})")
print("\n=== SEQUENTIAL (QoQ) — the sharper signal for rollover ===")
q = qoq_table()
for tk, last, note in sorted(q, key=lambda r: (r[1] is None, -(r[1] or 0))):
    print(f"   {tk:6} latest QoQ {pct(last):>9}  {note}")

print(f"\n   annual files: {len(glob.glob(os.path.join(BASE, 'fundamentals_annual', '*.csv')))}"
      f"   quarterly files: {len(glob.glob(os.path.join(BASE, 'fundamentals_quarterly', '*.csv')))}")
