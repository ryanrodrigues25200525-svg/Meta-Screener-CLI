#!/usr/bin/env python3
"""currency_check.py — decide each new fundamentals file's currency by magnitude, or leave it UNKNOWN.

The vault rule (History/FUNDAMENTALS-METHOD.md): a currency label has to be *established*, not assumed —
a wrong label is worse than an explicit UNKNOWN. Provider statements are shown in the filer's reporting
currency, which yfinance does not label, so it is inferred here from magnitude evidence:

  1. Domestic-filer rule — a US-domiciled issuer files in USD, so a USD label on it is confirmable by
     construction. The profile's hq_country is the evidence; it comes from the same fetch batch.
  2. Scale test — TTM revenue against the listing currency's market cap must give a plausible P/S
     (0.02x .. 60x). A ratio outside that band means the file is not in the currency the market cap is,
     which is the signature of a local-currency statement (TSM in TWD reads ~140x, NVO in DKK ~1.4x).
  3. Internal consistency — diluted EPS x diluted shares should reproduce net income within ~15%. This
     does not identify the currency, but it proves the row set is coherent, so a ratio test on top of it
     is testing units and not a parsing error.

Non-US-domiciled filers are printed for an explicit magnitude match against the company's own reported
figure (the PBR/VALE/TSM method), and stay UNKNOWN until that is recorded in a `currency_basis` row.

Usage: python3 currency_check.py            # every ticker with an annual file and a profile spill
       python3 currency_check.py TECK ERO   # subset
"""
import csv, glob, json, os, sys

VAULT = "/documents/Finance Knowledge Graph"
BASE = os.path.join(VAULT, "Datasets/History")
WORK = "/workspace/history/work"


def first_json(s):
    i, dec = s.find("{"), json.JSONDecoder()
    while i != -1:
        try:
            return dec.raw_decode(s[i:])[0]
        except Exception:
            i = s.find("{", i + 1)
    return None


def profile(tk):
    p = os.path.join(WORK, f"f2_{tk}_p.txt")
    if not os.path.exists(p):
        return None
    o = first_json(open(p, encoding="utf-8", errors="ignore").read())
    if isinstance(o, dict) and isinstance(o.get("result"), str):
        o = first_json(o["result"])
    if not isinstance(o, dict):
        return None
    rs = o.get("results")
    return (rs or [None])[0] if isinstance(rs, list) else o


def facts(tk):
    """(currency, latest annual revenue, latest net income, TTM quarterly revenue) from the stored files."""
    out = {"currency": None, "rev": None, "ni": None, "rev_ttm": None, "eps_x_shares": None}
    pa = os.path.join(BASE, "fundamentals_annual", f"{tk}.csv")
    pq = os.path.join(BASE, "fundamentals_quarterly", f"{tk}.csv")
    for p, kind in ((pa, "a"), (pq, "q")):
        if not os.path.exists(p):
            continue
        rows = list(csv.DictReader(open(p, encoding="utf-8")))
        if not rows:
            continue
        cols = [c for c in rows[0].keys() if c != "metric"]
        d = {}
        for r in rows:
            d[r["metric"]] = {c: float(r[c]) for c in cols if (r.get(c) or "").strip()
                              and _num(r[c])}
        if kind == "a":
            out["currency"] = (list(d.get("currency", {}).values()) or [None])[0]
            rev = [v for v in (d.get("total_revenue") or {}).values() if v]
            ni = [v for v in (d.get("net_income") or {}).values() if v is not None]
            out["rev"] = rev[-1] if rev else None
            out["ni"] = ni[-1] if ni else None
        else:
            ttm = [v for v in (d.get("total_revenue") or {}).values() if v]
            out["rev_ttm"] = sum(ttm[-4:]) if ttm else None
            eps = d.get("diluted_earnings_per_share") or {}
            sh = d.get("weighted_average_diluted_shares_outstanding") or {}
            common = [c for c in cols if c in eps and c in sh]
            if common:
                c = common[-1]
                if eps[c] is not None and sh[c]:
                    out["eps_x_shares"] = eps[c] * sh[c]
            if out["ni"] is None:
                niq = [v for v in (d.get("net_income") or {}).values() if v is not None]
                out["ni"] = sum(niq[-4:]) if niq else None
    return out


def _num(s):
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


def main():
    tks = [a.upper() for a in sys.argv[1:]]
    if not tks:
        tks = sorted(os.path.basename(p)[:-4] for p in
                     glob.glob(os.path.join(BASE, "fundamentals_annual", "*.csv")))
    print(f"{'ticker':7} {'label':7} {'domicile':14} {'rev/mcap(P/S)':>14} {'EPSxSH vs NI':>13}  verdict")
    for tk in tks:
        p, f = profile(tk), facts(tk)
        if not p or not f.get("currency"):
            print(f"{tk:7} {'?':7} {'no profile' if not p else 'no file':14} {'':14} {'':13}  SKIP")
            continue
        mcap = p.get("market_cap")
        ps = (mcap / f["rev_ttm"]) if (mcap and f.get("rev_ttm")) else None
        ratio = None
        if f.get("eps_x_shares") and f.get("ni"):
            ratio = f["eps_x_shares"] / f["ni"] if f["ni"] else None
        dom = str(p.get("hq_country") or "?")
        us = dom == "United States"
        note = []
        verdict = "OK" if (us and f["currency"] == "USD") else "CHECK"
        if ps is not None and not (0.02 <= ps <= 60):
            verdict, note = "SUSPECT", note + [f"P/S {ps:.1f}x out of band"]
        if ratio is not None and not (0.85 <= ratio <= 1.15):
            note.append(f"EPSxSH/NI {ratio:.2f}")
        if us and f["currency"] != "USD":
            note.append("US filer but labelled " + str(f["currency"]))
        if not us and f["currency"] == "USD" and ps and 0.05 < ps < 30:
            verdict = "OK*" if verdict == "CHECK" else verdict
            note.append("non-US filer labelled USD — confirm by magnitude")
        print(f"{tk:7} {str(f['currency']):7} {dom[:14]:14} "
              f"{('' if ps is None else format(ps, '.2f') + 'x'):>14} "
              f"{('' if ratio is None else format(ratio, '.2f')):>13}  {verdict} {'; '.join(note)}")


if __name__ == "__main__":
    main()
