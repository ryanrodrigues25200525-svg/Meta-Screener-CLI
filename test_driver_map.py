#!/usr/bin/env python3
"""test_driver_map.py - acceptance test for the causal driver map deliverable.

The point is that the note's headline numbers are re-derived here from the stored price layer and the CSV,
instead of being trusted as prose. Run:  python3 test_driver_map.py   (or pytest -q this file)

Checks
  1. coverage: one row per roster name, no duplicates, every row fully populated
  2. taxonomy: every driver maps to a parent, both dictionaries closed (no stray labels)
  3. the answer: book covers 9 parents, universe 12, rotation-only 3 (REAL_RATES, POWER, INDUSTRIAL)
  4. the eight candidate drivers resolve to the right parents and the book/rotation split matches the note
  5. independence: N_eff recomputed from Datasets/History/prices_daily reproduces 5.2 (calm) / 2.2 (2022)
  6. evidence accounting: gaps file == judgement-only rows, and every gap name is in drivers.csv
  7. the note itself: parses, links resolve, and carries the answer + the mismatch flags
"""
import csv, os, re, glob, statistics, itertools, sys

KG = "/documents/Finance Knowledge Graph"
DM = os.path.join(KG, "Datasets", "Driver Map")
PRICES = os.path.join(KG, "Datasets", "History", "prices_daily")
NOTE = os.path.join(KG, "Notes", "2026-09-16 Book drivers research.md")

PARENT_OF = {"HCAPEX": "AI_CAPEX", "OPT_ATTACH": "AI_CAPEX", "SEMICAP": "AI_CAPEX", "MEM_PRICE": "MEM_CYCLE",
             "OIL": "ENERGY", "GAS": "ENERGY", "OILSERV": "ENERGY", "GOLD_RATES": "REAL_RATES",
             "ROYALTY": "REAL_RATES", "BASE_METALS": "CHINA_INDUSTRIAL", "RATES_NIM": "RATES",
             "SMALLCAP_VAL": "RATES", "REIT_CAP": "RATES", "JAPAN_FX": "POLICY", "TARIFF": "POLICY",
             "DEFENSE_BUDGET": "POLICY", "POWER_LOAD": "POWER", "STAPLES_VOL": "CONSUMER",
             "PHARMA_PRICE": "HEALTH", "LSTOOLS": "HEALTH", "AI_SUB": "SOFTWARE", "SEAT_ARR": "SOFTWARE",
             "STEEL_IND": "INDUSTRIAL", "LITHIUM_AG": "INDUSTRIAL", "CONSUMER_HW": "CONSUMER"}
PARENTS = set(PARENT_OF.values())
# the published correlation grouping (book names), used to re-derive N_eff
GROUP_OF = {"HCAPEX": "hyperscaler_capex", "OPT_ATTACH": "optical_attach", "SEMICAP": "semicap_equipment",
            "MEM_PRICE": "memory_price", "OIL": "oil_price", "RATES_NIM": "rates_spread_income",
            "TARIFF": "tariff_auto", "STAPLES_VOL": "staples_margin", "PHARMA_PRICE": "pharma_patent",
            "AI_SUB": "ai_disrupted_software", "BASE_METALS": "base_metals", "CONSUMER_HW": "pc_memory_cost"}
TICKER_GROUP_OVERRIDE = {"TSEM": "specialty_foundry"}   # published as its own group (specialty foundry)

FAILS = []


CHECKS = []


def check(name, cond, detail=""):
    print("%-4s %s%s" % ("PASS" if cond else "FAIL", name, ("   [%s]" % detail) if detail else ""))
    CHECKS.append(name)
    if not cond:
        FAILS.append(name)


def load(path):
    return list(csv.DictReader(open(path, encoding="utf-8")))


# ---------------------------------------------------------------- 1. coverage
roster = load(os.path.join(DM, "roster.csv"))
rows = load(os.path.join(DM, "drivers.csv"))
rt, dt = {r["ticker"] for r in roster}, [r["ticker"] for r in rows]
check("coverage: one row per roster name", set(dt) == rt, "%d rows vs %d roster names" % (len(rows), len(roster)))
check("coverage: no duplicate tickers", len(dt) == len(set(dt)))
missing = [r["ticker"] for r in rows
           if not (r["driver"] and r["parent_driver"] and r["mechanism"] and r["sign"] and r["lag"] and r["evidence"])]
check("coverage: every row has driver/parent/mechanism/sign/lag/evidence", not missing, ",".join(missing[:6]))

# ---------------------------------------------------------------- 2. taxonomy
bad_parent = [r["ticker"] for r in rows if PARENT_OF.get(r["driver"]) != r["parent_driver"]]
check("taxonomy: driver->parent consistent", not bad_parent, ",".join(bad_parent[:6]))
stray = sorted({r["driver"] for r in rows} - set(PARENT_OF))
check("taxonomy: no unregistered driver labels", not stray, ",".join(stray))
check("taxonomy: 24 drivers under 12 parents",
      len({r["driver"] for r in rows}) == 24 and len({r["parent_driver"] for r in rows}) == 12,
      "%d/%d" % (len({r["driver"] for r in rows}), len({r["parent_driver"] for r in rows})))

# ---------------------------------------------------------------- 3. the answer
book = [r for r in rows if r["in_book"] == "1"]
book_par = {r["parent_driver"] for r in book}
all_par = {r["parent_driver"] for r in rows}
check("answer: book is 34 names", len(book) == 34, str(len(book)))
check("answer: book covers 9 of 12 parents", len(book_par) == 9, ",".join(sorted(book_par)))
check("answer: universe is 12 parents", len(all_par) == 12, str(len(all_par)))
check("answer: rotation-only parents are REAL_RATES/POWER/INDUSTRIAL",
      all_par - book_par == {"REAL_RATES", "POWER", "INDUSTRIAL"}, ",".join(sorted(all_par - book_par)))

# ---------------------------------------------------------------- 4. the eight candidates
want = {"MEM_CYCLE": 5, "AI_CAPEX": 17, "OPT_ATTACH": 7, "ENERGY": 2, "REAL_RATES": 0, "RATES": 1,
        "JAPAN_FX": 0, "TARIFF": 1}
got = {p: sum(1 for r in book if r["parent_driver"] == p or r["driver"] == p) for p in want}
check("candidates: book counts match the note", got == want, "%s" % got)
rot_only = {"REAL_RATES": 10, "JAPAN_FX": 5, "RATES": 14, "ENERGY": 26, "TARIFF": 0}
got2 = {p: sum(1 for r in rows if r["in_book"] == "0" and (r["parent_driver"] == p or r["driver"] == p))
        for p in rot_only}
check("candidates: rotation counts match the note", got2 == rot_only, "%s" % got2)


# ---------------------------------------------------------------- 5. independence, recomputed
def load_prices(tk):
    p = os.path.join(PRICES, tk + ".csv")
    if not os.path.exists(p):
        return {}
    out = {}
    for r in csv.DictReader(open(p, encoding="utf-8", errors="ignore")):
        try:
            c = float(r["close"])
            if c > 0:
                out[r["date"][:10]] = c
        except (ValueError, KeyError):
            pass
    return out


def corr(x, y):
    mx, my = statistics.mean(x), statistics.mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    dx = (sum((a - mx) ** 2 for a in x)) ** .5
    dy = (sum((b - my) ** 2 for b in y)) ** .5
    return num / (dx * dy) if dx and dy else None


def neff_for(start, end):
    groups = {}
    for r in book:
        g = TICKER_GROUP_OVERRIDE.get(r["ticker"]) or GROUP_OF.get(r["driver"])
        if g:
            groups.setdefault(g, []).append(r["ticker"])
    series = {}
    for tks in groups.values():
        for t in tks:
            s = load_prices(t)
            if s:
                series[t] = s
    dates = sorted({d for s in series.values() for d in s if start <= d <= end})
    rets = {}
    for t, s in series.items():
        r = {}
        for i in range(1, len(dates)):
            a, b = dates[i - 1], dates[i]
            if a in s and b in s:
                r[b] = s[b] / s[a] - 1
        rets[t] = r
    gser = {}
    for g, tks in groups.items():
        tks = [t for t in tks if t in rets and len(rets[t]) >= 20]
        if not tks:
            continue
        ds = set.intersection(*[set(rets[t]) for t in tks])
        gser[g] = {d: statistics.mean(rets[t][d] for t in tks) for d in ds}
    keys = sorted(gser)
    rhos = []
    for a, b in itertools.combinations(keys, 2):
        d = sorted(set(gser[a]) & set(gser[b]))
        if len(d) >= 20:
            c = corr([gser[a][x] for x in d], [gser[b][x] for x in d])
            if c is not None:
                rhos.append(c)
    mean_rho = statistics.mean(rhos)
    n = len(keys)
    return n / (1 + (n - 1) * mean_rho), mean_rho, n


ne_calm, rho_calm, g_calm = neff_for("2025-09-01", "2026-12-31")
ne_stress, rho_stress, g_stress = neff_for("2022-01-01", "2022-12-31")
check("independence: calm N_eff reproduces ~5.2 (13 groups)", abs(ne_calm - 5.2) < 0.25,
      "%.2f from %d groups, mean rho %+.2f" % (ne_calm, g_calm, rho_calm))
check("independence: 2022 stress N_eff reproduces ~2.2", abs(ne_stress - 2.2) < 0.25,
      "%.2f from %d groups, mean rho %+.2f" % (ne_stress, g_stress, rho_stress))

# ---------------------------------------------------------------- 6. evidence accounting
gaps = load(os.path.join(DM, "evidence-gaps.csv"))
judgement = [r for r in rows if not (r["basis"].startswith("vault") or r["external_verdict"] == "supports")]
check("evidence: gaps file == judgement-only rows", {g["ticker"] for g in gaps} == {r["ticker"] for r in judgement},
      "%d gaps vs %d judgement rows" % (len(gaps), len(judgement)))
check("evidence: no book name is in the gap list", not [g for g in gaps if any(
    r["in_book"] == "1" and r["ticker"] == g["ticker"] for r in rows)])
check("evidence: book is 34/34 per-name",
      all(r["basis"].startswith("vault") or r["external_verdict"] == "supports" for r in book))
check("evidence: third-party audit has no contradiction",
      not [r for r in rows if r["external_verdict"] == "disagrees"])

# ---------------------------------------------------------------- 7. the note
txt = open(NOTE, encoding="utf-8").read()
try:
    import yaml
    fm = yaml.safe_load(re.match(r"^---\n(.*?)\n---\n", txt, re.S).group(1))
    check("note: frontmatter parses with kill-switches", isinstance(fm, dict) and len(fm.get("invalidations", [])) >= 4)
except ImportError:
    check("note: frontmatter parses with kill-switches", txt.startswith("---"), "pyyaml missing, structural check only")
names = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(KG, "**", "*.md"), recursive=True)}
links = set(re.findall(r"\[\[([^\]|#]+)", txt))
check("note: every wikilink resolves", not [l for l in links if l.strip() not in names],
      "%d links" % len(links))
for phrase in ("9 of the 12 causal drivers", "~5.2", "~2.2", "stated theme ≠ actual driver",
               "Datasets/Driver Map/drivers.csv", "evidence-gaps.csv"):
    check("note: contains %r" % phrase[:38], phrase in txt)
for tkr in ("ADBE", "VALE", "WDC", "AXTI", "MRVL", "HPQ", "PRU", "GM", "POET", "MXL", "HBM"):
    check("note: mismatch flag mentions %s" % tkr, re.search(r"\b%s\b" % tkr, txt) is not None)

print("\n%d checks, %d failed" % (len(CHECKS), len(FAILS)))
print("RESULT:", "ALL CHECKS PASS" if not FAILS else "FAILURES: " + ", ".join(FAILS))
sys.exit(1 if FAILS else 0)
