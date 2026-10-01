#!/usr/bin/env python3
"""evidence3.py - tighten the harvest: title-level claims + theme research notes.

Fixes evidence2's looseness (it matched a driver word anywhere in a claim file, so "ADBE 200SMA holds"
counted as AI-driver support). Now a claim counts only if its TITLE matches the driver pattern, and a
third source is added: the theme node's `research:` notes (the industry maps), searched line-wise for the
name with the driver term in the same sentence.
Rewrites drivers.csv (evidence2_source/text/verdict columns) and reports the final coverage.
"""
import csv, os, re, glob, collections, shutil

KG = "/documents/Finance Knowledge Graph"
MC, CLAIMS, THEMES, NOTES = (os.path.join(KG, x) for x in ("Market Context", "Claims", "Themes", "Notes"))
ROSTER = "/tmp/driverwork/roster.csv"
OUT = os.path.join(KG, "Datasets", "Driver Map", "drivers.csv")
SRC = os.path.join(KG, "Datasets", "Driver Map", "drivers_prev.csv")   # pre-harvest state: 78 vault / 86 analyst

REGIME_DRIVER = {"Rates": "RATES", "Dollar": "REAL_RATES", "Inflation": "STAPLES_VOL",
                 "Growth recession risk": "INDUSTRIAL", "Risk appetite": "HCAPEX", "Volatility": "SOFTWARE"}
PARENT_OF = {"HCAPEX": "AI_CAPEX", "OPT_ATTACH": "AI_CAPEX", "SEMICAP": "AI_CAPEX", "MEM_PRICE": "MEM_CYCLE",
             "OIL": "ENERGY", "GAS": "ENERGY", "OILSERV": "ENERGY", "GOLD_RATES": "REAL_RATES",
             "ROYALTY": "REAL_RATES", "COPPER": "CHINA_INDUSTRIAL", "RATES_NIM": "RATES",
             "SMALLCAP_VAL": "RATES", "REIT_CAP": "RATES", "JAPAN_FX": "POLICY", "TARIFF": "POLICY",
             "DEFENSE_BUDGET": "POLICY", "POWER_LOAD": "POWER", "STAPLES_VOL": "CONSUMER",
             "PHARMA_PRICE": "HEALTH", "LSTOOLS": "HEALTH", "AI_SUB": "SOFTWARE", "SEAT_ARR": "SOFTWARE",
             "STEEL_IND": "INDUSTRIAL", "LITHIUM_AG": "INDUSTRIAL", "CONSUMER_HW": "CONSUMER"}
DRIVER_PAT = {
    "RATES_NIM": r"(rate|yield|NIM|spread|curve|Fed|deposit|credit|loan)", "SMALLCAP_VAL": r"(rate|yield|small-?cap|credit|Russell)",
    "GOLD_RATES": r"(gold|real rate|real yield|dollar|AISC)", "ROYALTY": r"(gold|royalt|stream)",
    "HCAPEX": r"(AI capex|capex|hyperscaler|GPU|accelerator|data ?cent)", "OPT_ATTACH": r"(optical|transceiver|laser|CPO|photonics)",
    "MEM_PRICE": r"(DRAM|NAND|HBM|memory|bit)", "SEMICAP": r"(fab|capex|wafer|equipment|tool|packaging)",
    "OIL": r"(crude|oil|Brent|WTI|crack|refin)", "GAS": r"(natural gas|Henry Hub|LNG|gas price)",
    "OILSERV": r"(rig|upstream|offshore|dayrate|service)", "COPPER": r"(copper|China|metal|concentrate)",
    "POWER_LOAD": r"(utility|power|rate base|load growth|electric|grid)", "TARIFF": r"(tariff|trade|duty|policy)",
    "DEFENSE_BUDGET": r"(defen[cs]e|backlog|appropriat|budget|award)", "JAPAN_FX": r"(yen|Japan|JPY|BOJ)",
    "STAPLES_VOL": r"(volume|input cost|staple|food|consumer|margin)", "PHARMA_PRICE": r"(patent|generic|GLP-1|pipeline|drug|pricing)",
    "LSTOOLS": r"(life science|instrument|diagnostic|R&D|biopharma)", "AI_SUB": r"(AI|ARR|subscription|seat)",
    "SEAT_ARR": r"(ARR|seat|subscription|cloud|security|retention)", "STEEL_IND": r"(steel|industrial|construction|spread|scrap)",
    "LITHIUM_AG": r"(lithium|potash|fertil|crop|chemical|caustic)", "CONSUMER_HW": r"(device|PC|handset|iPhone|refresh|ASP)",
}


def frontmatter(path):
    txt = open(path, encoding="utf-8", errors="ignore").read()
    m = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
    return (m.group(1) if m else ""), txt


def fm_list(fm, key):
    m = re.search(r"^%s:\s*(.*)$" % re.escape(key), fm, re.M)
    if not m or not m.group(1).strip().startswith("["):
        return []
    return [next((v for v in t if v), "").strip().strip("'\"")
            for t in re.findall(r"\[\[([^\]]+)\]\]|\"([^\"]+)\"|'([^']+)'", m.group(1))]


def tickers_in(text, known):
    return {t for t in re.findall(r"\b([A-Z]{1,5}(?:\.[A-Z]{1,3})?)\b", text) if t in known}


rows0 = list(csv.DictReader(open(SRC, encoding="utf-8")))
known = {r["ticker"] for r in rows0}

# regime edges
regime_edges = collections.defaultdict(list)
for p in glob.glob(os.path.join(MC, "*.md")):
    regime = os.path.basename(p)[:-3]
    fm, _ = frontmatter(p)
    for key in ("strengthens", "threatens"):
        for ent in fm_list(fm, key):
            for tk in tickers_in(ent, known):
                regime_edges[tk].append((regime, key))

# claims: title must match the pattern
claim_files = [(os.path.basename(p)[:-3], p) for p in glob.glob(os.path.join(CLAIMS, "*.md"))]

# theme research notes per theme
theme_research, theme_members = {}, {}
for p in glob.glob(os.path.join(THEMES, "*.md")):
    name = os.path.basename(p)[:-3]
    fm, _ = frontmatter(p)
    theme_research[name] = fm_list(fm, "research")
    theme_members[name] = fm_list(fm, "companies")

note_cache = {}
def note_text(n):
    if n not in note_cache:
        p = os.path.join(NOTES, n + ".md")
        note_cache[n] = open(p, encoding="utf-8", errors="ignore").read() if os.path.exists(p) else ""
    return note_cache[n]

up_strength = collections.Counter()
final = []
for r in rows0:
    tk, driver = r["ticker"], r["driver"]
    parent = PARENT_OF.get(driver, "?")
    pat = DRIVER_PAT.get(driver, r"(?!)")
    ev, src, verdict = "", "", "none"

    # (a) regime edge whose family matches the driver's parent
    for regime, sign in regime_edges.get(tk, []):
        if REGIME_DRIVER.get(regime) == parent:
            ev, src, verdict = "%s %s %s" % (regime, sign, tk), "Market Context/%s.md" % regime, "supports"
            break
    # (b) claim whose TITLE matches the driver pattern
    if verdict == "none":
        for title, _ in claim_files:
            if re.search(r"(?:^|\s)%s(?:\s|$)" % re.escape(tk), title) and re.search(pat, title, re.I):
                ev, src, verdict = "claim: %s" % title, "Claims/%s.md" % title, "supports"
                break
    # (c) theme research note line naming the ticker with the driver term in the same sentence
    if verdict == "none":
        for theme in [t.strip() for t in r["theme_membership"].split(";") if t.strip()]:
            for n in theme_research.get(theme, []):
                body = note_text(n)
                if not body:
                    continue
                for line in body.splitlines():
                    if re.search(r"\b%s\b" % re.escape(tk), line) and re.search(pat, line, re.I):
                        ev = re.sub(r"\s+", " ", line.strip())[:200]
                        src, verdict = "Notes/%s.md (theme: %s)" % (n, theme), "supports"
                        break
                if verdict == "supports":
                    break
            if verdict == "supports":
                break
    # (d) informational: regime edges of a different family that name this ticker.
    # These are NOT contradictions - a risk-appetite edge naming CVX does not contradict an oil driver -
    # so they are recorded in a separate column rather than overwriting the verdict.
    others = sorted({("%s/%s" % (regime, sign)) for regime, sign in regime_edges.get(tk, [])
                     if REGIME_DRIVER.get(regime) and REGIME_DRIVER[regime] != parent})

    r["evidence2_source"], r["evidence2_text"], r["evidence2_verdict"] = src, ev[:220], verdict
    r["other_family_regime_edges"] = "; ".join(others)[:160]
    if verdict == "supports" and r["basis"].startswith("analyst"):
        r["basis"] = "vault (harvested)"
        if r["evidence_strength"] == "sector/theme only":
            r["evidence_strength"] = "regime/claim/theme-note"
            up_strength["sector/theme only -> harvested"] += 1
    final.append(r)

fields = list(final[0].keys())
shutil.copy(OUT, "/tmp/driverwork/drivers_before_evidence3.csv")
with open(OUT, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    w.writerows(final)

print("rows %d" % len(final))
print("basis    :", dict(collections.Counter(r["basis"] for r in final)))
print("strength :", dict(collections.Counter(r["evidence_strength"] for r in final)))
print("upgraded this pass:", dict(up_strength) or "none")
print("contradictions:", [r["ticker"] for r in final if r["evidence2_verdict"] == "contradicts"])
print("\nstill sector/theme only: %d of %d (%.0f%%)"
      % (sum(1 for r in final if r["evidence_strength"] == "sector/theme only"), len(final),
         100 * sum(1 for r in final if r["evidence_strength"] == "sector/theme only") / len(final)))
bk = [r for r in final if r["in_book"] == "1"]
print("book rows still sector/theme only: %d of %d"
      % (sum(1 for r in bk if r["evidence_strength"] == "sector/theme only"), len(bk)))
print("\nharvested evidence, by source kind:")
kinds = collections.Counter(r["evidence2_source"].split("/")[0] for r in final if r["evidence2_verdict"] == "supports")
print("  ", dict(kinds))
print("\nsample harvested rows:")
n = 0
for r in final:
    if r["basis"] == "vault (harvested)":
        print("  %-6s %-14s %-46s %s" % (r["ticker"], r["driver"], r["evidence2_source"][:44], r["evidence2_text"][:90]))
        n += 1
        if n >= 30:
            break
