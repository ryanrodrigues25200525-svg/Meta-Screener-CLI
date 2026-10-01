#!/usr/bin/env python3
"""history_coverage.py — did the work actually land?

Three slices of the price widening sat unfetched for hours because nothing measured coverage per
worklist: two agents had returned degenerate output (raw tool syntax / a bare number) and reported
"completed", and a fourth slice was never dispatched at all. Counting what is on disk against each
worklist catches that in one command.

Reports:
  * series counts per layer (monthly / daily / fundamentals)
  * coverage of every worklist in /workspace/history/work against the stored tickers
  * slices that look unfetched (a slice with <15% coverage that has any coverage at all)
  * the no-data tallies, with the space-suffixed forms the tool rejects outright

Usage: python3 ~/Documents/finance-ai/history_coverage.py
"""
import csv, glob, os, re, statistics

VAULT = next(c for c in (os.environ.get("KG_VAULT"), "/documents/Finance Knowledge Graph",
                         os.path.expanduser("~/Documents/Finance Knowledge Graph"))
             if c and os.path.isdir(c))
HIST = os.path.join(VAULT, "Datasets/History")
WORK = "/workspace/history/work"

counts = {k: len(glob.glob(os.path.join(HIST, k, "*.csv")))
          for k in ("prices_monthly", "prices_daily", "fundamentals_annual", "fundamentals_quarterly")}
print("series on disk: " + ", ".join(f"{k}={v}" for k, v in counts.items()))

have = {os.path.basename(p)[:-4] for p in glob.glob(os.path.join(HIST, "prices_monthly", "*.csv"))}

print("\ncoverage per worklist (tickers on disk / tickers listed):")
WATCH = ["attn_prices_%d.txt" % i for i in range(1, 6)] + [
    "attn_2plus_mapped.txt", "tranche2_prices.txt", "new_node_prices.txt"]
# NOTE: profile worklists (profiles*.csv source) are deliberately NOT watched here — their tickers are
# fetched for name/sector, not prices, so a low price-coverage reading for them is expected, not a gap.
flagged = []
for name in WATCH:
    p = os.path.join(WORK, name)
    if not os.path.exists(p):
        continue
    tick = [x.strip() for x in open(p) if x.strip()]
    got = [t for t in tick if t in have]
    pct = 100.0 * len(got) / max(1, len(tick))
    tag = ""
    if got and pct < 15:
        tag = "   <-- LOOKS UNFETCHED (an agent may have reported success without doing the work)"
        flagged.append(name)
    print(f"   {name:26} {len(got):4}/{len(tick):4}  ({pct:5.1f}%){tag}")

nodata = []
for pat in ("attn_nodata_*.txt", "t2_nodata.txt", "newp_nodata.txt"):
    nodata += [l.strip() for f in glob.glob(os.path.join(WORK, pat))
               for l in open(f, encoding="utf-8", errors="ignore") if l.strip()]
print(f"\nno-data tickers recorded: {len(set(nodata))} distinct")

# Local exchange codes appear in three forms and all three are mechanically mappable to a provider symbol:
#   trailing market token   '1161 HK'    -> 1161.HK      (Tokyo/Osaka 'TYO'/'JP' -> .T)
#   prefix market token     'JP:3593'    -> 3593.T
#   dotted site suffix      'ENX.FP'     -> ENX.PA
# The agents that hit these recorded them as unresolvable; they are not. Printed here so the mapping is
# never re-derived by hand.
SUFFIX = {"HK": ".HK", "JP": ".T", "TYO": ".T", "UK": ".L", "LN": ".L", "LON": ".L", "FR": ".PA",
          "FP": ".PA", "IT": ".MI", "IM": ".MI", "DE": ".DE", "GR": ".DE", "SW": ".SW", "SS": ".SS",
          "SZ": ".SZ", "KS": ".KS", "KQ": ".KQ", "TW": ".TW", "TWO": ".TWO", "AX": ".AX", "AU": ".AX",
          "TO": ".TO", "V": ".V", "ST": ".ST", "OL": ".OL", "CO": ".CO", "HE": ".HE", "VI": ".VI",
          "NA": ".AS", "BB": ".BR", "SGX": ".SI", "SI": ".SI", "SH": ".SS"}
mappable = {}
for n in sorted(set(nodata)):
    m = re.match(r"^(?:([A-Z]{2,4})[:\s]+)([A-Z0-9.\-]{1,10})$", n)
    if m and m.group(1) in SUFFIX:
        mappable[n] = m.group(2) + SUFFIX[m.group(1)]
        continue
    m = re.match(r"^([A-Z0-9]{1,8})\.([A-Z]{2,3})$", n)
    if m and m.group(2) in SUFFIX:
        mappable[n] = m.group(1) + SUFFIX[m.group(2)]
        continue
    # US/Canadian class shares: the provider wants a dash where the site writes a dot (BRK.A -> BRK-A)
    m = re.match(r"^([A-Z]{1,5})\.([A-Z])$", n)
    if m:
        mappable[n] = m.group(1) + "-" + m.group(2)
if mappable:
    print(f"local codes that map to a provider symbol ({len(mappable)}) — fetch these, don't re-record them:")
    for a, b in list(mappable.items())[:30]:
        print(f"   {a:12} -> {b}")

if flagged:
    print("\nACTION: re-dispatch " + ", ".join(flagged) + " — verify output on disk, not the agent's report.")

# Daily coverage of the ACTUAL BOOK. Measured 2026-09-16: 39/39, i.e. the daily layer was built for the
# book and has no gap there. The 600+ book-less tickers with monthly-only series are foreign or screener
# names; fetching daily for them would be ~1.8M rows for no backtest use. Check this before proposing a
# daily widening pass.
BOOK = ["GM", "VTRS", "VALE", "CAG", "GIS", "HPQ", "SM", "PRU", "NVO", "PBR", "PFE", "ADBE",
        "AAOI", "AXTI", "MU", "SNDK", "NBIS", "POET", "LITE", "MTSI", "SMTC", "AEHR", "MXL",
        "NVDA", "TSM", "AVGO", "AMD", "MRVL", "WDC", "ONTO", "RMBS", "TSEM", "AEIS", "SIMO",
        "SPY", "QQQ", "SMH", "SOXX", "IWM"]
daily = {os.path.basename(p)[:-4] for p in glob.glob(os.path.join(HIST, "prices_daily", "*.csv"))}
book_missing = [t for t in BOOK if t not in daily]
# Calendar-year gaps. A series with a middle hole does not fail loudly: it makes a "daily" return span
# years and makes a period-filtered study return nothing. 70 of 74 daily series were missing 2018-2022 when
# this check was added, so it is reported for BOTH layers rather than assumed absent.
EXPECT_YEARS = [str(y) for y in range(2015, 2027)]
for layer, first in (("prices_daily", 2015), ("prices_monthly", 2000)):
    gaps = []
    expected_gaps = []
    for pth in glob.glob(os.path.join(HIST, layer, "*.csv")):
        yrs = set()
        for line in open(pth, encoding="utf-8", errors="ignore"):
            if len(line) > 4 and line[:4].isdigit():
                yrs.add(line[:4])
        # a series that simply starts later is not a gap; a HOLE between two present years is
        present = sorted(int(y) for y in yrs if y.isdigit())
        if not present:
            continue
        missing = [y for y in range(present[0] + 1, max(present)) if str(y) not in yrs]
        if missing:
            # A gap in an ILLIQUID series is the market's, not ours: the provider returns only months where
            # a trade printed, so a missing year can mean nobody traded. Verified 2026-09-16 on KWS/RX/DML,
            # where a refetch returned the same sparse bars (including months carried at one price with zero
            # volume). Those are reported separately so the real defects are not buried.
            try:
                rows = list(csv.DictReader(open(pth, encoding="utf-8", errors="ignore")))
                closes, vols = [], []
                for r in rows:
                    try:
                        closes.append(float(r["close"]))
                        vols.append(float(r.get("volume") or 0))
                    except (ValueError, TypeError):
                        pass
                # Illiquidity shows up as SPARSITY (bars per year), not only as low price or low volume:
                # RX prints >1,000 shares when it trades but only ~1.5 months a year, so its missing years
                # are months nobody traded. Sub-$1 prices and near-zero volume are the other two tells.
                # Span must come from the DATES, not the row count.
                ds = sorted(r["date"][:10] for r in rows if r.get("date"))
                span_years = 1.0
                if len(ds) >= 2:
                    y0, y1 = int(ds[0][:4]), int(ds[-1][:4])
                    span_years = max(1.0, (y1 - y0) + 1)
                bars_per_year = len(rows) / span_years
                illiquid = bool(closes) and (min(closes) < 1.0
                                             or (vols and statistics.median(vols) < 1000)
                                             or bars_per_year < 6)
            except OSError:
                illiquid = False   # only a read failure; a NameError/typo here must surface, not hide
            (expected_gaps if illiquid else gaps).append((os.path.basename(pth)[:-4], missing))
    if gaps:
        print(f"\n{layer}: {len(gaps)} series have an INTERNAL year gap (backtests across it are invalid)")
        for tk, miss in gaps[:8]:
            print(f"   {tk:10} missing {','.join(str(m) for m in miss)}")
        if len(gaps) > 8:
            print(f"   ... and {len(gaps) - 8} more")
    else:
        print(f"\n{layer}: no internal year gaps")
    if expected_gaps:
        print(f"   ({len(expected_gaps)} illiquid/OTC series also have gaps - no trade printed in those "
              f"months, so not a defect: " + ", ".join(t for t, _ in expected_gaps[:8]) + ")")

print(f"\ndaily coverage of the book: {len(BOOK) - len(book_missing)}/{len(BOOK)}"
      + ("" if not book_missing else "   MISSING: " + " ".join(book_missing)))

# Fundamentals coverage of the ROTATION SET — the members of the leading themes that had no fundamentals.
# The rotation screen is only as good as this number, so it is measured from disk rather than assumed, and
# the target for the screen to be trustworthy is >=90%.
p = os.path.join(WORK, "fund2_todo.txt")
rot = [l.strip() for l in open(p, encoding="utf-8", errors="ignore") if l.strip()] if os.path.exists(p) else []
if rot:
    fa = {os.path.basename(x)[:-4] for x in glob.glob(os.path.join(HIST, "fundamentals_annual", "*.csv"))}
    fq = {os.path.basename(x)[:-4] for x in glob.glob(os.path.join(HIST, "fundamentals_quarterly", "*.csv"))}
    both = [t for t in rot if t in fa and t in fq]
    a_only = [t for t in rot if t in fa and t not in fq]
    q_only = [t for t in rot if t in fq and t not in fa]
    neither = [t for t in rot if t not in fa and t not in fq]
    pct = 100.0 * len(both) / len(rot)
    print(f"\nfundamentals coverage of the rotation set: {len(both)}/{len(rot)} ({pct:.0f}%)")
    if a_only:
        print("   annual only (quarterly still missing): " + " ".join(a_only))
    if q_only:
        print("   quarterly only (annual still missing): " + " ".join(q_only))
    if neither:
        print(f"   neither ({len(neither)}): " + " ".join(neither))
