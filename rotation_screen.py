#!/usr/bin/env python3
"""rotation_screen.py — rank the book and the rotation themes on revenue growth, margin trend and valuation.

Reads only the vault's own fundamentals layer (Datasets/History/fundamentals_{annual,quarterly}) plus the
profile spills written during the leading-theme fundamentals fetch (market cap). Nothing is fetched here, so
the screen is reproducible offline and every number in it is traceable to a stored file.

Honesty constraints (same spirit as growth_momentum.py):
  * Sequential (QoQ) growth is computed WITHIN each company; fiscal quarter ends differ, so cross-name
    comparison is directional, not calendar-aligned.
  * Blank periods are skipped, never treated as zero, and a blank revenue ends the run rather than
    producing a fake -100%.
  * Valuation needs ONE currency. Where a filer's reporting currency differs from the listing currency the
    row is marked and P/S is left blank unless an FX rate is supplied on the command line
    (--fx DKK=0.1570 converts fundamentals into USD). A wrong-currency ratio is worse than a blank.
  * P/E is blank for loss-makers or when TTM net income <= 0. Never a negative multiple.

Usage:
  python3 rotation_screen.py                      # every ticker with a quarterly file
  python3 rotation_screen.py --tickers MU,NVDA    # subset
  python3 rotation_screen.py --fx DKK=0.1570
"""
import argparse, csv, glob, json, os, re, statistics, sys

VAULT = next(c for c in (os.environ.get("KG_VAULT"), "/documents/Finance Knowledge Graph",
                         os.path.expanduser("~/Documents/Finance Knowledge Graph"))
             if c and os.path.isdir(c))
BASE = os.path.join(VAULT, "Datasets/History")
WORK = "/workspace/history/work"

BOOK = ["VTRS", "HPQ", "GM", "VALE", "SM", "PFE", "PRU", "NVO", "ADBE", "CAG", "GIS", "PBR"]
ROTATION_THEMES = ["Software & SaaS", "Cybersecurity", "Hyperscalers", "Information Technology", "Energy",
                   "Oil & gas", "Gold Miners", "Copper Miners", "Materials", "Life Sciences Tools",
                   "Exploration & Production", "Oil Services"]


def load(tk, kind):
    """{metric: (cols, values)} for one stored file."""
    p = os.path.join(BASE, f"fundamentals_{kind}", f"{tk}.csv")
    if not os.path.exists(p):
        return None
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    if not rows:
        return None
    cols = [c for c in rows[0].keys() if c != "metric"]
    out = {}
    for r in rows:
        vals = {}
        for c in cols:
            v = (r.get(c) or "").strip()
            if v:
                try:
                    vals[c] = float(v)
                except ValueError:
                    # keep non-numeric cells as strings: the `currency`, `source` and `currency_basis` rows
                    # are the provenance of the file. Dropping them silently made every currency read as
                    # '?' and left the whole valuation leg blank.
                    vals[c] = v
        out[r.get("metric")] = vals
    return {"cols": cols, "m": out, "currency": (out.get("currency", {}) or {})}


def currency_of(f):
    c = (f.get("currency") or {})
    vals = {v for v in c.values() if v}
    return vals.pop() if len(vals) == 1 else (sorted(vals)[0] if vals else "?")


def series(f, metric):
    d = f["m"].get(metric) or {}
    return [(c, d[c]) for c in f["cols"] if c in d and isinstance(d[c], float)]


def profile(tk):
    p = os.path.join(WORK, f"f2_{tk}_p.txt")
    if not os.path.exists(p):
        return None
    raw = open(p, encoding="utf-8", errors="ignore").read()

    def first_json(s):
        i, dec = s.find("{"), json.JSONDecoder()
        while i != -1:
            try:
                return dec.raw_decode(s[i:])[0]
            except Exception:
                i = s.find("{", i + 1)
        return None
    o = first_json(raw)
    if isinstance(o, dict) and isinstance(o.get("result"), str):
        o = first_json(o["result"])
    if not isinstance(o, dict):
        return None
    rs = o.get("results")
    return (rs or [None])[0] if isinstance(rs, list) else o


def theme_members():
    """ticker -> the leading themes that list it (member links resolve through Companies/ frontmatter)."""
    t2t, a2t = {}, {}
    for p in glob.glob(os.path.join(VAULT, "Companies", "*.md")):
        stem = os.path.basename(p)[:-3]
        txt = open(p, encoding="utf-8", errors="ignore").read()
        fm = txt.split("---", 2)[1] if txt.count("---") >= 2 else ""
        m = re.search(r'^ticker:\s*"?([A-Z0-9.\-]+)"?', fm, re.M)
        if m:
            t2t[stem] = m.group(1)
        for g in re.findall(r'aliases:\s*\[(.*?)\]', fm):
            for a in g.split(","):
                a = a.strip().strip('"\'')
                if a:
                    a2t[a] = stem
    out = {}
    for th in ROTATION_THEMES:
        p = os.path.join(VAULT, "Themes", th + ".md")
        if not os.path.exists(p):
            continue
        txt = open(p, encoding="utf-8", errors="ignore").read()
        fm = txt.split("---", 2)[1] if txt.count("---") >= 2 else ""
        m = re.search(r"^companies:\s*\[(.*)\]\s*$", fm, re.M)
        if not m:
            continue
        for mem in re.findall(r"\[\[([^\]|#\n]+)", m.group(1)):
            tk = t2t.get(mem) or (mem if mem.isupper() and 1 <= len(mem) <= 6 else
                                  t2t.get(a2t.get(mem, ""), None))
            if tk:
                out.setdefault(tk, []).append(th)
    return out


def pct(x):
    return "n/a" if x is None else f"{x * 100:+.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers")
    ap.add_argument("--fx", action="append", default=[], help="CUR=rate_in_usd, e.g. DKK=0.1570")
    ap.add_argument("--csv-out", default=os.path.join(WORK, "rotation_screen.csv"))
    a = ap.parse_args()
    fx = {}
    for item in a.fx:
        k, v = item.split("=")
        fx[k.upper()] = float(v)

    if a.tickers:
        tickers = [t.strip().upper() for t in a.tickers.split(",") if t.strip()]
    else:
        tickers = sorted(os.path.basename(p)[:-4] for p in
                         glob.glob(os.path.join(BASE, "fundamentals_quarterly", "*.csv")))
    tmap = theme_members()
    rows = []
    for tk in tickers:
        fq, fa = load(tk, "quarterly"), load(tk, "annual")
        if not fq:
            continue
        cur = currency_of(fq) or (currency_of(fa) if fa else "?")
        rev = series(fq, "total_revenue")
        gp = dict(series(fq, "gross_profit"))
        oi = dict(series(fq, "operating_income"))
        ni = dict(series(fq, "net_income"))
        r = {"ticker": tk, "currency": cur, "periods": len(rev),
             "group": "book" if tk in BOOK else ("rotation" if tk in tmap else "other"),
             "themes": "; ".join(tmap.get(tk, []))}
        if len(rev) >= 2:
            vals = [v for _, v in rev]
            # A quarter that is <50% of BOTH neighbours is the signature of a partial period in the
            # provider's series (OXY stores 1.75bn between 6.62bn and 5.23bn). Left unflagged it reads as a
            # -74% then +199% move, i.e. as a real collapse and recovery. Flagged, never plucked out.
            stubs = [rev[i][0] for i in range(1, len(vals) - 1)
                     if vals[i] and vals[i - 1] and vals[i + 1]
                     and vals[i] < 0.5 * min(vals[i - 1], vals[i + 1])]
            if stubs:
                r["suspect_partial_q"] = ",".join(stubs)
            qoq = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals)) if vals[i - 1]]
            r["qoq_run"] = ", ".join(pct(x) for x in qoq)
            r["qoq_last"] = qoq[-1] if qoq else None
            r["qoq_prev"] = qoq[-2] if len(qoq) > 1 else None
            r["revenue_last"] = vals[-1]
            r["revenue_ttm"] = sum(vals[-4:]) if len(vals) >= 4 else None
            r["qoq_trend"] = ("accel" if (len(qoq) > 1 and qoq[-1] > qoq[-2]) else
                              ("decel" if len(qoq) > 1 else "n/a"))
            # margin trend: latest vs the same metric four quarters back (a year), plus the last step
            for name, src in (("gm", gp), ("om", oi)):
                s = [(c, src[c] / v) for (c, v) in rev if c in src and v]
                if len(s) >= 2:
                    r[name + "_last"] = s[-1][1]
                    r[name + "_prev"] = s[-2][1]
                    r[name + "_d4q"] = (s[-1][1] - s[-5][1]) if len(s) >= 5 else None
                    r[name + "_d1q"] = s[-1][1] - s[-2][1]
        nis = [v for _, v in series(fq, "net_income")]
        r["ni_ttm"] = sum(nis[-4:]) if len(nis) >= 4 else None
        p = profile(tk)
        if p:
            r["name"] = p.get("name")
            r["mcap"] = p.get("market_cap")
        if r.get("mcap") and r.get("revenue_ttm"):
            conv = 1.0
            if cur != "USD":
                conv = fx.get(cur.upper())
                r["fx_missing"] = conv is None
            if conv:
                r["ps_ttm"] = r["mcap"] / (r["revenue_ttm"] * conv)
        if r.get("mcap") and r.get("ni_ttm") and r["ni_ttm"] > 0:
            conv = 1.0 if cur == "USD" else fx.get(cur.upper())
            if conv:
                r["pe_ttm"] = r["mcap"] / (r["ni_ttm"] * conv)
        rows.append(r)

    keys = ["ticker", "name", "group", "currency", "periods", "qoq_last", "qoq_prev", "qoq_trend",
            "qoq_run", "revenue_last", "revenue_ttm", "ni_ttm", "mcap", "ps_ttm", "pe_ttm",
            "gm_last", "gm_d4q", "om_last", "om_d4q", "suspect_partial_q", "themes", "fx_missing"]
    with open(a.csv_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    def show(title, key, fmt, n=25):
        print("\n=== " + title + " ===")
        for r in sorted([x for x in rows if x.get(key) is not None], key=lambda x: -x[key])[:n]:
            print(f"   {r['ticker']:6} {fmt(r):>34}   {r['group']:8} {str(r.get('themes', ''))[:44]}")

    show("QoQ revenue growth — latest quarter (all names with a quarterly file)",
         "qoq_last", lambda r: f"{pct(r['qoq_last'])}  (run {r.get('qoq_run', 'n/a')})")
    show("Valuation — P/S on TTM revenue (lower = cheaper)", "ps_ttm", lambda r: f"{r['ps_ttm']:.2f}x")
    show("Valuation — P/E on TTM net income", "pe_ttm", lambda r: f"{r['pe_ttm']:.1f}x")

    print("\n=== gross-margin change over 4 quarters (bps) — expanding first ===")
    for r in sorted([x for x in rows if x.get("gm_d4q") is not None], key=lambda x: -x["gm_d4q"])[:25]:
        print(f"   {r['ticker']:6} {r['gm_d4q'] * 10000:+8.0f} bps   latest {r['gm_last'] * 100:5.1f}%   "
              f"{r['group']:8} latestQoQ {pct(r.get('qoq_last'))}")

    print("\n=== operating-margin change over 4 quarters (bps) — expanding first ===")
    for r in sorted([x for x in rows if x.get("om_d4q") is not None], key=lambda x: -x["om_d4q"])[:25]:
        print(f"   {r['ticker']:6} {r['om_d4q'] * 10000:+8.0f} bps   latest {r['om_last'] * 100:5.1f}%   "
              f"{r['group']:8} latestQoQ {pct(r.get('qoq_last'))}")

    print(f"\n=== series carrying a suspected PARTIAL quarter (a quarter < 50% of both neighbours — the QoQ "
          f"run through it is not a real move) ===")
    fl = [x for x in rows if x.get("suspect_partial_q")]
    for r in sorted(fl, key=lambda x: x["ticker"]):
        print(f"   {r['ticker']:6} partial: {r['suspect_partial_q']}   run {r.get('qoq_run')}")
    if not fl:
        print("   none")

    # shortlist: revenue accelerating sequentially, operating margin not deteriorating, valuation not rich.
    # The valuation leg must be PRESENT to pass: an unknown P/S is not evidence of cheapness, so those names
    # go to their own list instead of silently passing the filter.
    cand = []
    ps_all = [x["ps_ttm"] for x in rows if x.get("ps_ttm")]
    med = statistics.median(ps_all) if ps_all else None
    unvalued = []
    for r in rows:
        if r.get("qoq_trend") != "accel" or r.get("qoq_last") is None or r["qoq_last"] <= 0:
            continue
        if r.get("om_d4q") is not None and r["om_d4q"] < 0:
            continue
        if not r.get("ps_ttm"):
            unvalued.append(r)
            continue
        if med and r["ps_ttm"] > med:
            continue
        cand.append(r)
    print(f"\n=== SHORTLIST (accel QoQ revenue + operating margin not deteriorating + P/S <= cohort median "
          f"{'' if med is None else format(med, '.2f') + 'x'}) ===")
    for r in sorted(cand, key=lambda x: -x["qoq_last"])[:20]:
        print(f"   {r['ticker']:6} QoQ {pct(r['qoq_last'])} (prior {pct(r.get('qoq_prev'))})  "
              f"om {r.get('om_last', 0) * 100:.1f}% (4q {r.get('om_d4q', 0) * 10000:+.0f}bps)  "
              f"P/S {'' if not r.get('ps_ttm') else format(r['ps_ttm'], '.2f') + 'x'}  {r['group']}")
    if not cand:
        print("   none — no name passed all three filters (see the note for why)")
    print(f"\n=== passes growth + margin, VALUATION NOT ESTABLISHED (P/S unavailable — not counted as passing) "
          f"===")
    for r in sorted(unvalued, key=lambda x: -x["qoq_last"]):
        print(f"   {r['ticker']:6} QoQ {pct(r['qoq_last'])}  om {r.get('om_last', 0) * 100:.1f}%  "
              f"currency {r['currency']}  {r['group']}")
    if not unvalued:
        print("   none")
    print(f"\nrows: {len(rows)}   csv: {a.csv_out}")


if __name__ == "__main__":
    main()
