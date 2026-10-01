#!/usr/bin/env python3
"""breadth_rotation.py — test the Market Context regime read against the stored price layer.

The Market Context node says 'narrow risk-on / rotation' with leadership in Energy and Gold miners. That is
a claim about breadth and rotation, and the layer can measure both from our own data rather than accepting
it. Reads Datasets/History/prices_monthly/ only.

Breadth: share of names above their 10-month moving average (a monthly proxy for the 200-day), and share
with a positive 3m return. Rotation: 1m/3m/6m returns aggregated by theme membership.
"""
import csv, glob, os, re, statistics

V = "/documents/Finance Knowledge Graph"
H = V + "/Datasets/History/prices_monthly"
BOOK = {"GM", "VTRS", "VALE", "CAG", "GIS", "HPQ", "SM", "PRU", "NVO", "PBR", "PFE", "ADBE", "AAOI",
        "AXTI", "MU", "SNDK", "NBIS", "POET", "LITE", "MTSI", "SMTC", "AEHR", "MXL", "NVDA", "TSM",
        "AVGO", "AMD", "MRVL", "WDC", "ONTO", "RMBS", "TSEM", "AEIS", "SIMO"}
SEMIS = {"AAOI", "AXTI", "MU", "SNDK", "NBIS", "POET", "LITE", "MTSI", "SMTC", "AEHR", "MXL", "NVDA",
         "TSM", "AVGO", "AMD", "MRVL", "WDC", "ONTO", "RMBS", "TSEM", "AEIS", "SIMO", "ALAB", "CRDO",
         "COHR", "ACLS", "CAMT", "FORM", "SWKS", "TER", "NVMI", "DIOD", "AMAT", "INTC", "KLAC", "LRCX"}


def closes(tk):
    p = os.path.join(H, tk + ".csv")
    if not os.path.exists(p):
        return []
    out = []
    for r in csv.DictReader(open(p, encoding="utf-8", errors="ignore")):
        try:
            out.append(float(r["close"]))
        except (ValueError, KeyError):
            pass
    return out


def ret(c, n):
    return (c[-1] / c[-1 - n] - 1) * 100 if len(c) > n and c[-1 - n] > 0 else None


rows = []
for p in glob.glob(os.path.join(H, "*.csv")):
    tk = os.path.basename(p)[:-4]
    c = closes(tk)
    if len(c) < 13:
        continue
    ma10 = statistics.mean(c[-10:])
    rows.append({"tk": tk, "c": c, "r1": ret(c, 1), "r3": ret(c, 3), "r6": ret(c, 6),
                 "above": c[-1] > ma10, "ma_dist": (c[-1] / ma10 - 1) * 100})

def stats(subset, label):
    if not subset:
        print("   %s: no data" % label)
        return
    above = sum(1 for r in subset if r["above"])
    pos3 = sum(1 for r in subset if (r["r3"] or 0) > 0)
    med3 = statistics.median([r["r3"] for r in subset if r["r3"] is not None])
    med1 = statistics.median([r["r1"] for r in subset if r["r1"] is not None])
    print("   %-22s n=%4d  above 10m MA %3.0f%%   positive 3m %3.0f%%   median 1m %+5.1f%%   median 3m %+6.1f%%"
          % (label, len(subset), 100.0 * above / len(subset), 100.0 * pos3 / len(subset), med1, med3))

print("=== breadth (monthly layer, latest bar 2026-09) ===")
stats(rows, "whole universe")
stats([r for r in rows if r["tk"] in BOOK], "the book")
stats([r for r in rows if r["tk"] in SEMIS], "semis / AI complex")
stats([r for r in rows if r["tk"] in BOOK and r["tk"] not in SEMIS], "book ex-semis")

# rotation by theme membership
themes = {}
tick2theme = {}
for p in glob.glob(os.path.join(V, "Themes", "*.md")):
    name = os.path.basename(p)[:-3]
    members = set(re.findall(r"\[\[([^\]|#\n]+)", open(p, encoding="utf-8", errors="ignore").read()))
    if len(members) < 3:
        continue
    themes[name] = members
    for m in members:
        tick2theme.setdefault(m, set()).add(name)

print("\n=== rotation: themes by median 3m return (>=5 members with data) ===")
out = []
for name, members in themes.items():
    sub = [r for r in rows if r["tk"] in members and r["r3"] is not None]
    if len(sub) >= 5:
        out.append((name, len(sub), statistics.median([r["r3"] for r in sub]),
                    statistics.mean([r["r3"] for r in sub])))
out.sort(key=lambda x: -x[2])
for name, n, med, mean in out[:8]:
    print("   LEAD  %-46s n=%2d  median 3m %+7.1f%%" % (name[:46], n, med))
print("   ...")
for name, n, med, mean in out[-8:]:
    print("   LAG   %-46s n=%2d  median 3m %+7.1f%%" % (name[:46], n, med))
print("\nthemes measured: %d" % len(out))
