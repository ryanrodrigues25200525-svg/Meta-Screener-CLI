#!/usr/bin/env python3
"""driver_map.py - what actually moves the book: driver groups + independence test.

Offline from the stored daily layer (same discipline as book_risk.py). Groups are defined by each
holding's OWN kill-switch wording, not by its stated theme. Outputs:
  1. group membership + days available
  2. each name vs driver proxies (SMH/XLE/TLT/GLD/SPY) and vs the market
  3. the group-vs-group correlation matrix, and N_eff = N/(1+(N-1)*mean_rho) at DRIVER level
  4. named cross-tests (HPQ vs MU, ADBE vs SMH, VALE vs GLD, ...)
Run:  python3 driver_map.py
"""
import csv, os, statistics, itertools

V = "/documents/Finance Knowledge Graph"
D = os.path.join(V, "Datasets", "History", "prices_daily")

GROUPS = {
    "hyperscaler_capex":     ["NVDA", "AVGO", "AMD", "TSM", "MRVL", "NBIS"],
    "memory_price":          ["MU", "SNDK", "RMBS", "SIMO", "WDC"],
    "optical_attach":        ["AAOI", "LITE", "MTSI", "SMTC", "POET", "AXTI", "MXL"],
    "semicap_equipment":     ["AEHR", "ONTO", "AEIS"],
    "specialty_foundry":     ["TSEM"],
    "oil_price":             ["SM", "PBR"],
    "rates_spread_income":   ["PRU"],
    "tariff_auto":           ["GM"],
    "staples_margin":        ["CAG", "GIS"],
    "pharma_patent":         ["VTRS", "PFE", "NVO"],
    "ai_disrupted_software": ["ADBE"],
    "iron_ore_china":        ["VALE"],
    "pc_memory_cost":        ["HPQ"],
}
AI_COMPLEX = ("hyperscaler_capex", "memory_price", "optical_attach", "semicap_equipment", "specialty_foundry")
PROXIES = ["SMH", "XLE", "TLT", "GLD", "SPY"]

n_all = sum(len(v) for v in GROUPS.values())
print("book covered: %d names in %d driver groups" % (n_all, len(GROUPS)))


def load(tk):
    p = os.path.join(D, tk + ".csv")
    if not os.path.exists(p):
        return {}
    out = {}
    with open(p, encoding="utf-8", errors="ignore") as fh:
        for r in csv.DictReader(fh):
            try:
                c = float(r["close"])
                if c > 0:
                    out[r["date"][:10]] = c
            except (ValueError, KeyError):
                pass
    return out


series = {}
for names in GROUPS.values():
    for t in names:
        series[t] = load(t)
for p in PROXIES:
    series[p] = load(p)
missing = [t for t, s in series.items() if not s]
print("series loaded: %d   missing: %s" % (len([t for t in series if series[t]]), missing or "none"))

all_dates = sorted(set().union(*[set(s) for s in series.values() if s]))


def returns_for(dates):
    rets = {}
    for t, s in series.items():
        if not s:
            continue
        r = {}
        for i in range(1, len(dates)):
            a, b = dates[i - 1], dates[i]
            if a in s and b in s:
                r[b] = s[b] / s[a] - 1
        rets[t] = r
    return rets


def corr(x, y):
    if len(x) < 20:
        return None
    mx, my = statistics.mean(x), statistics.mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    dx = sum((a - mx) ** 2 for a in x) ** 0.5
    dy = sum((b - my) ** 2 for b in y) ** 0.5
    return num / (dx * dy) if dx and dy else None


def run(label, start, end):
    dates = [d for d in all_dates if start <= d <= end]
    rets = returns_for(dates)
    print("\n" + "=" * 98)
    print("### %s   %s -> %s   (%d trading days)" % (label, dates[0], dates[-1], len(dates) - 1))
    gser = {}
    for g, names in GROUPS.items():
        mem = [n for n in names if n in rets and len(rets[n]) >= 20]
        dropped = [n for n in names if n not in mem]
        ds = set.intersection(*[set(rets[n]) for n in mem]) if mem else set()
        if len(ds) < 20:
            print("  [%-22s] members %-40s <20 days" % (g, ",".join(mem)))
            continue
        gser[g] = {d: statistics.mean(rets[n][d] for n in mem) for d in ds}
        print("  [%-22s] members %-42s days %d%s" % (g, ",".join(mem), len(ds),
              ("   (not listed yet: %s)" % ",".join(dropped)) if dropped else ""))

    print("\n  -- each name vs driver proxies (rho) --")
    print("  %-7s %-22s %s" % ("tkr", "group", " ".join("%-7s" % p for p in PROXIES)))
    for g, names in GROUPS.items():
        for n in names:
            if n not in rets:
                continue
            cells = []
            for p in PROXIES:
                r = None
                if p in rets:
                    d = sorted(set(rets[n]) & set(rets[p]))
                    r = corr([rets[n][x] for x in d], [rets[p][x] for x in d])
                cells.append("%+.2f" % r if r is not None else "n/a")
            print("  %-7s %-22s %s" % (n, g, " ".join("%-7s" % c for c in cells)))

    print("\n  -- group return vs benchmarks --")
    print("  %-22s %7s %7s %7s %7s %7s" % ("group", "SMH", "XLE", "TLT", "GLD", "SPY"))
    for g, s in gser.items():
        cells = []
        for p in PROXIES:
            if p in rets:
                d = sorted(set(s) & set(rets[p]))
                r = corr([s[x] for x in d], [rets[p][x] for x in d])
                cells.append("%+.2f" % r if r is not None else "n/a")
            else:
                cells.append("n/a")
        print("  %-22s %s" % (g, " ".join("%7s" % c for c in cells)))

    keys = sorted(gser)
    print("\n  -- mean pairwise rho BETWEEN driver groups --")
    pairs = []
    for a, b in itertools.combinations(keys, 2):
        d = sorted(set(gser[a]) & set(gser[b]))
        r = corr([gser[a][x] for x in d], [gser[b][x] for x in d])
        if r is not None:
            pairs.append((a, b, r))
    for a, b, r in sorted(pairs, key=lambda t: -abs(t[2]))[:14]:
        print("     %-22s vs %-22s %+0.2f" % (a, b, r))
    mean_rho = statistics.mean(p[2] for p in pairs)
    n = len(keys)
    neff = n / (1 + (n - 1) * mean_rho)
    print("\n  DRIVER-LEVEL: %d groups, mean pairwise rho %+.2f  ->  N_eff = %.1f independent drivers"
          % (n, mean_rho, neff))
    ai_pairs = [p[2] for p in pairs if p[0] in AI_COMPLEX and p[1] in AI_COMPLEX]
    other = [p[2] for p in pairs if not (p[0] in AI_COMPLEX and p[1] in AI_COMPLEX)]
    print("  within the AI complex (%d groups, %d pairs): %+.2f" % (len(AI_COMPLEX), len(ai_pairs),
                                                                     statistics.mean(ai_pairs)))
    print("  everything else     (%d pairs): %+.2f" % (len(other), statistics.mean(other)))
    # AI complex treated as ONE bet
    n2 = len(keys) - len(AI_COMPLEX) + 1
    keep = [p[2] for p in pairs if not (p[0] in AI_COMPLEX and p[1] in AI_COMPLEX)]
    mean2 = statistics.mean(keep) if keep else 0
    print("  (folding the AI complex into a single bet: %d bets, mean rho %+.2f -> N_eff %.1f)"
          % (n2, mean2, n2 / (1 + (n2 - 1) * mean2)))
    return rets, gser


run("recent", "2025-09-01", "2026-12-31")
run("2022 stress", "2022-01-01", "2022-12-31")

print("\n" + "=" * 98)
print("### NAMED CROSS-TESTS (recent)")
_cache = {}


def rho(a, b, start="2025-09-01", end="2026-12-31"):
    if (a, b) not in _cache:
        dates = [d for d in all_dates if start <= d <= end]
        rr = returns_for(dates)
        if a not in rr or b not in rr:
            _cache[(a, b)] = None
        else:
            d = sorted(set(rr[a]) & set(rr[b]))
            _cache[(a, b)] = (corr([rr[a][x] for x in d], [rr[b][x] for x in d]), len(d))
    return _cache[(a, b)]


tests = [
    ("HPQ", "MU", "PC maker vs memory price: NEGATIVE would confirm memory cost is HPQ's real driver"),
    ("HPQ", "SNDK", "PC maker vs NAND price"),
    ("HPQ", "SPY", "PC maker vs market"),
    ("ADBE", "SMH", "AI-disrupted software vs AI hardware: NEGATIVE would confirm AI-substitution driver"),
    ("ADBE", "SPY", "AI-disrupted software vs market"),
    ("PRU", "TLT", "insurer 'rate tailwind' vs long rates"),
    ("PRU", "GLD", "insurer vs gold (real-rate proxy)"),
    ("SM", "XLE", "E&P vs energy (oil driver)"),
    ("PBR", "XLE", "integrated oil vs energy (oil driver)"),
    ("VALE", "GLD", "iron ore vs gold (real-asset/real-rate driver)"),
    ("VALE", "SMH", "iron ore vs semis (stated 'critical minerals for semis' theme test)"),
    ("GM", "SPY", "tariff-exposed auto vs market"),
    ("CAG", "GIS", "staples pair (one driver?)"),
    ("VTRS", "PFE", "generics vs big pharma (one pharma driver?)"),
    ("MU", "SNDK", "memory pair (one driver?)"),
    ("LITE", "AAOI", "optical pair"),
    ("AXTI", "LITE", "InP substrate vs optical module (upstream/downstream same driver?)"),
    ("WDC", "MU", "HDD/nearline vs memory: stated NAND tag test"),
    ("TSEM", "SMH", "specialty foundry vs AI semis: stated leading-edge theme test"),
    ("MXL", "SMH", "broadband-exposed connectivity vs AI semis"),
    ("NBIS", "NVDA", "neocloud vs accelerator (same capex driver?)"),
]
for a, b, why in tests:
    out = rho(a, b)
    print("  %-5s vs %-5s  %-16s  %s" % (a, b, ("%+.2f (n=%d)" % out) if out else "n/a", why))
