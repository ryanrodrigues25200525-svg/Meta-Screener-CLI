#!/usr/bin/env python3
"""book_risk.py — concentration and co-movement of the actual book, from the stored daily layer.

Answers the question the position sizing depends on: how many independent bets does this book really
hold? Uses only Datasets/History/prices_daily/ so it is reproducible offline.

Method: daily log returns over a recent window; average pairwise correlation within the semis/photonics
cluster, within the value cluster, and between them; then the standard effective-bets approximation
N_eff = N / (1 + (N-1) * mean_pairwise_rho). No eigen-decomposition needed, and the approximation is
conservative enough for a sizing decision.

The regime block at the end repeats the whole measurement over a STRESS window as well as the uptrend,
adds bloc-level vol / max DD, and prints the distance a 15% trailing stop sits at in daily sigma. Every
figure quoted in the Risk-rules section of Portfolio.md comes from one run of this file (the stop
payouts/penalties by sector come from stop_regime_rotation.py).
"""
import csv, glob, os, statistics, datetime

V = "/documents/Finance Knowledge Graph"
D = V + "/Datasets/History/prices_daily"

SEMIS = ["AAOI", "AXTI", "MU", "SNDK", "NBIS", "POET", "LITE", "MTSI", "SMTC", "AEHR", "MXL",
         "NVDA", "TSM", "AVGO", "AMD", "MRVL", "WDC", "ONTO", "RMBS", "TSEM", "AEIS", "SIMO"]
VALUE = ["GM", "VTRS", "VALE", "CAG", "GIS", "HPQ", "SM", "PRU", "NVO", "PBR", "PFE", "ADBE"]
BENCH = ["SPY"]

WINDOW_DAYS = 504   # ~2 trading years: recent regime, still enough observations for stable correlations


def load(tk):
    p = os.path.join(D, tk + ".csv")
    if not os.path.exists(p):
        return {}
    out = {}
    for r in csv.DictReader(open(p, encoding="utf-8", errors="ignore")):
        try:
            out[r["date"][:10]] = float(r["close"])
        except (ValueError, KeyError):
            pass
    return out


series = {t: load(t) for t in SEMIS + VALUE + BENCH}
series = {t: s for t, s in series.items() if len(s) > 100}
dates = sorted(set().union(*[set(s) for s in series.values()]))[-WINDOW_DAYS:]

rets = {}
for t, s in series.items():
    r = {}
    for i in range(1, len(dates)):
        a, b = dates[i - 1], dates[i]
        if a in s and b in s and s[a] > 0 and s[b] > 0:
            r[b] = s[b] / s[a] - 1
    rets[t] = r

common = sorted(set(rets.get("SPY", {})))
for t in rets:
    common = [d for d in common if d in rets[t]]
print("window: %s to %s (%d common trading days)" % (common[0], common[-1], len(common)))


def corr(a, b):
    x = [rets[a][d] for d in common]
    y = [rets[b][d] for d in common]
    mx, my = statistics.mean(x), statistics.mean(y)
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx = sum((xi - mx) ** 2 for xi in x) ** 0.5
    dy = sum((yi - my) ** 2 for yi in y) ** 0.5
    return num / (dx * dy) if dx and dy else 0.0


def avg_corr(names):
    names = [n for n in names if n in rets]
    pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
    if not pairs:
        return None, 0
    return statistics.mean(corr(a, b) for a, b in pairs), len(pairs)


def vol(tk):
    if tk not in rets:
        return None
    x = [rets[tk][d] for d in common]
    return statistics.stdev(x) * (252 ** 0.5) * 100


def maxdd(tk):
    s = series.get(tk, {})
    ds = [d for d in common if d in s]
    if len(ds) < 30:
        return None
    peak, dd = 0, 0
    base = s[ds[0]]
    for d in ds:
        peak = max(peak, s[d])
        if peak > 0:
            dd = min(dd, s[d] / peak - 1)
    return dd * 100, (s[ds[-1]] / base - 1) * 100


semis_in = [t for t in SEMIS if t in rets]
value_in = [t for t in VALUE if t in rets]
print("names loaded: %d semis/photonics, %d value, +SPY" % (len(semis_in), len(value_in)))

rho_s, n_s = avg_corr(semis_in)
rho_v, n_v = avg_corr(value_in)
rho_sv = statistics.mean([corr(a, b) for a in semis_in for b in value_in])
print("\n=== average pairwise correlation ===")
print("  within semis/photonics (%2d names, %4d pairs): %+.2f" % (len(semis_in), n_s, rho_s))
print("  within value          (%2d names, %4d pairs): %+.2f" % (len(value_in), n_v, rho_v))
print("  semis vs value        (%4d pairs):             %+.2f" % (len(semis_in) * len(value_in), rho_sv))

allb = semis_in + value_in
rho_all, n_all = avg_corr(allb)
n = len(allb)
neff = n / (1 + (n - 1) * rho_all)
print("\n=== effective number of bets ===")
print("  book size: %d names" % n)
print("  mean pairwise rho across the whole book: %+.2f" % rho_all)
print("  effective independent bets: %.1f  (i.e. the book behaves like ~%.0f positions, not %d)"
      % (neff, round(neff), n))

print("\n=== risk per name (annualised vol, max drawdown over the window) ===")
rows = []
for t in allb:
    v = vol(t)
    dd = maxdd(t)
    rows.append((t, v, dd[0] if dd else None, dd[1] if dd else None))
for t, v, dd, ret in sorted(rows, key=lambda r: -(r[1] or 0)):
    print("   %-6s vol %5.1f%%   maxDD %7s   window return %8s"
          % (t, v or 0, ("%.1f%%" % dd) if dd is not None else "n/a",
             ("%+.1f%%" % ret) if ret is not None else "n/a"))
sv = vol("SPY")
print("   %-6s vol %5.1f%%   (benchmark)" % ("SPY", sv or 0))


# --- regime comparison: stress vs uptrend, bloc risk, and the stop in daily sigma ----------
# The block above measures ONE window (the recent uptrend). The sizing and stop decisions in
# Portfolio.md are taken on the STRESS window, so the same measurement is repeated over a second
# regime here, with bloc-level vol / max DD and the distance a 15% trailing stop sits at in daily
# sigma. One run of this file reproduces every number quoted in that section's cluster-limit rule
# and stop-level argument; stop_regime_rotation.py supplies the per-sector payouts.
REGIMES = [("2022 stress", "2022-01-01", "2022-12-31"),
           ("2025-26 uptrend", "2025-02-14", "2026-09-15")]
STOP_PCT = 15.0


def _window(names, start, end):
    d = {t: {dt: c for dt, c in load(t).items() if start <= dt <= end} for t in names}
    return {t: s for t, s in d.items() if len(s) >= 100}


def _rets(data):
    alld = sorted(set().union(*[set(s) for s in data.values()]))
    r = {}
    for t, s in data.items():
        rr = {}
        for i in range(1, len(alld)):
            a, b = alld[i - 1], alld[i]
            if a in s and b in s and s[a] > 0:
                rr[b] = s[b] / s[a] - 1
        r[t] = rr
    return r, sorted(set.intersection(*[set(x) for x in r.values()]))


def _corr(r, a, b, common):
    x = [r[a][d] for d in common]
    y = [r[b][d] for d in common]
    mx, my = statistics.mean(x), statistics.mean(y)
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx = sum((xi - mx) ** 2 for xi in x) ** 0.5
    dy = sum((yi - my) ** 2 for yi in y) ** 0.5
    return num / (dx * dy) if dx and dy else 0.0


def _mean_corr(r, names, common):
    pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
    return statistics.mean(_corr(r, a, b, common) for a, b in pairs) if pairs else 0.0


def _basket(r, names, common):
    """Equal-weight daily-rebalanced basket: annualised vol, max DD, window return."""
    port = [statistics.mean(r[t][d] for t in names) for d in common]
    v = statistics.stdev(port) * (252 ** 0.5) * 100
    eq, peak, dd = 1.0, 1.0, 0.0
    for x in port:
        eq *= (1 + x)
        peak = max(peak, eq)
        dd = min(dd, eq / peak - 1)
    return v, dd * 100, (eq - 1) * 100


print("\n\n=== regime comparison: effective bets, bloc risk (SPY excluded from the book) ===")
for label, start, end in REGIMES:
    book = _window(SEMIS + VALUE, start, end)
    if len(book) < 8:
        print("\n--- %s (%s to %s) ---\n    NO DATA: %d of %d book names have 100+ bars - "
              "not a null result." % (label, start, end, len(book), len(SEMIS) + len(VALUE)))
        continue
    r, common = _rets(book)
    names = sorted(r)
    s_in, v_in = [t for t in names if t in SEMIS], [t for t in names if t in VALUE]
    rho_all = _mean_corr(r, names, common)
    n = len(names)
    print("\n--- %s (%s to %s) ---" % (label, start, end))
    print("    book names %d (%d semis/photonics, %d value)   common days %d" % (n, len(s_in), len(v_in), len(common)))
    print("    mean pairwise rho (book)  %+.2f   -> effective bets %.1f of %d" % (rho_all, n / (1 + (n - 1) * rho_all), n))
    r2 = dict(r)
    rs, _ = _rets(_window(BENCH, start, end))
    if rs:
        r2.update(rs)
        c2 = sorted(set.intersection(*[set(x) for x in r2.values()]))
        n2 = len(r2)
        print("    ...with SPY as one more series: rho %+.2f -> %.1f of %d" % (_mean_corr(r2, sorted(r2), c2), n2 / (1 + (n2 - 1) * _mean_corr(r2, sorted(r2), c2)), n2))
    print("    within semis/photonics    %+.2f" % _mean_corr(r, s_in, common))
    print("    within value              %+.2f" % _mean_corr(r, v_in, common))
    print("    semis vs value            %+.2f  <- the offset the book relies on" % statistics.mean(_corr(r, a, b, common) for a in s_in for b in v_in))
    bv, bdd, _ = _basket(r, s_in, common)
    vv_, vdd, _ = _basket(r, v_in, common)
    tv, tdd, _ = _basket(r, names, common)
    print("    equal-weight vol / maxDD:  semis %.1f%% / %.1f%%   value %.1f%% / %.1f%%   book %.1f%% / %.1f%%"
          % (bv, bdd, vv_, vdd, tv, tdd))

up = _window(SEMIS + VALUE, REGIMES[-1][1], REGIMES[-1][2])
ru, cu = _rets(up)
print("\n=== what a %.0f%% trailing stop is worth, in daily sigma (%s window) ===" % (STOP_PCT, REGIMES[-1][0]))
print("    below ~3 sigma it fires in normal trending; at 4+ sigma it cannot fire outside a break")
rows = []
for t in sorted(ru):
    sd = statistics.stdev([ru[t][d] for d in cu]) * 100
    rows.append((t, sd * (252 ** 0.5), sd, STOP_PCT / sd))
for t, ann, sd, k in sorted(rows, key=lambda z: z[3]):
    print("    %-5s ann vol %5.1f%%   daily sigma %5.2f%%   %.0f%% stop = %4.1f sigma" % (t, ann, sd, STOP_PCT, k))
