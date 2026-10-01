#!/usr/bin/env python3
"""fundamentals_consistency.py - review list for the stored fundamentals layer.

NOT a defect list. The provider's `ebitda` is computed BOTTOM-UP (net income + interest + tax + D&A), so
it can legitimately sit BELOW the stated operating income whenever large charges (impairments) land below
the operating line. Rows flagged for that relationship are expected, not broken.

What is actually a suspected defect is implausible MAGNITUDE, which is what the hard checks below catch:
  * ebitda negative while operating income positive AND the gap dwarfs revenue
  * |net income| greater than revenue
  * EBITDA larger than 4x revenue
Usage: python3 fundamentals_consistency.py
"""
import csv, glob, os

BASE = "/documents/Finance Knowledge Graph/Datasets/History"
rows_out, review_out = [], []

for d in ("fundamentals_annual", "fundamentals_quarterly"):
    for p in sorted(glob.glob(os.path.join(BASE, d, "*.csv"))):
        rows = list(csv.DictReader(open(p, encoding="utf-8")))
        if not rows:
            continue
        cols = [c for c in rows[0].keys() if c != "metric"]
        idx = {}
        for r in rows:
            idx.setdefault(r["metric"], []).append(r)

        def val(metric, col):
            for r in idx.get(metric, []):
                v = (r.get(col) or "").strip()
                if v:
                    try:
                        return float(v)
                    except ValueError:
                        return None
            return None

        for c in cols:
            oi, eb, ni, rev = (val("operating_income", c), val("ebitda", c),
                               val("net_income", c), val("total_revenue", c))
            if oi is not None and eb is not None and oi > 0 and eb < 0 and rev and abs(eb) > rev:
                rows_out.append((d, os.path.basename(p)[:-4], c, "SUSPECT magnitude",
                                 f"oi={oi:,.0f} ebitda={eb:,.0f} rev={rev:,.0f}"))
            elif oi is not None and eb is not None and oi > 0 and eb < oi:
                review_out.append((d, os.path.basename(p)[:-4], c,
                                   f"ebitda below operating income (expected if a large charge sits below the line): oi={oi:,.0f} ebitda={eb:,.0f}"))
            # BELOW-THE-LINE gain: net income materially above operating income means EPS is not a clean
            # earnings measure for that period (see DATA-QUALITY.md).
            if oi is not None and ni is not None and oi > 0 and ni > oi * 1.25:
                review_out.append((d, os.path.basename(p)[:-4], c,
                                   f"BELOW-THE-LINE gain: net income {ni:,.0f} vs operating income {oi:,.0f} "
                                   f"(+{(ni/oi-1)*100:.0f}%) - do not use EPS for this period"))
            if ni is not None and rev and rev > 0 and abs(ni) > rev:
                rows_out.append((d, os.path.basename(p)[:-4], c, "SUSPECT magnitude",
                                 f"net_income={ni:,.0f} exceeds revenue={rev:,.0f}"))
            if eb is not None and rev and rev > 0 and abs(eb) > 4 * rev:
                rows_out.append((d, os.path.basename(p)[:-4], c, "SUSPECT magnitude",
                                 f"ebitda={eb:,.0f} vs revenue={rev:,.0f}"))

print(f"SUSPECT magnitude (check against filings): {len(rows_out)}")
for r in rows_out:
    print(f"   {r[0][14:]:9} {r[1]:10} {r[2]}  {r[4]}")
print(f"\nReview list (definitional, expected): {len(review_out)}")
for r in review_out[:40]:
    print(f"   {r[0][14:]:9} {r[1]:10} {r[2]}  {r[3][:96]}")
