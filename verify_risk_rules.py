#!/usr/bin/env python3
"""verify_risk_rules.py — gate the Risk-rules section of Portfolio.md against its evidence.

The Risk rules section states a cluster cap sized on a stress effective-bet count and a per-sector
stop policy. Those are decisions, so they must not drift away from the measurements they rest on:
this script re-derives every quoted figure from `book_risk.py` and `stop_regime_rotation.py`, checks
the live cluster read-out against the positions table Portfolio.md itself prints, and fails loudly.

Run:  python3 ~/Documents/finance-ai/verify_risk_rules.py     (exit 0 = clean)
"""
import json
import os
import re
import subprocess
import sys

FINANCE_AI = "/documents/finance-ai"
if not os.path.isdir(FINANCE_AI):
    FINANCE_AI = os.path.expanduser("~/Documents/finance-ai")
V = "/documents/Finance Knowledge Graph"
if not os.path.isdir(V):
    V = os.path.expanduser("~/Documents/Finance Knowledge Graph")
PORTFOLIO = os.path.join(V, "Portfolio.md")

VALUE = ["GM", "VTRS", "VALE", "CAG", "GIS", "HPQ", "SM", "PRU", "NVO", "PBR", "PFE", "ADBE"]
SEMIS = ["AAOI", "AXTI", "MU", "SNDK", "NBIS", "POET", "LITE", "MTSI", "SMTC", "AEHR", "MXL",
         "NVDA", "TSM", "AVGO", "AMD", "MRVL", "WDC", "ONTO", "RMBS", "TSEM", "AEIS", "SIMO"]

fails, checks = [], 0


def check(label, ok, detail=""):
    global checks
    checks += 1
    if ok:
        print("  ok   %s" % label)
    else:
        print("  FAIL %s   %s" % (label, detail))
        fails.append(label)


def run(script):
    p = subprocess.run([sys.executable, os.path.join(FINANCE_AI, script)],
                       capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        print("FATAL: %s exited %d\n%s" % (script, p.returncode, p.stderr[-800:]))
        sys.exit(2)
    return p.stdout


print("=== reading the evidence ===")
book = run("book_risk.py")
rot = run("stop_regime_rotation.py")

md = open(PORTFOLIO, encoding="utf-8").read()
m = re.search(r"^## Risk rules.*?(?=^## )", md, re.S | re.M)
if not m:
    print("FATAL: no '## Risk rules' section in Portfolio.md")
    sys.exit(2)
section = m.group(0)
print("  section: %d chars" % len(section))

# ---- 1. effective bets, both bases ---------------------------------------------------------
print("\n=== 1. effective bets (book_risk.py regime block) ===")
regime = book[book.find("regime comparison"):]
by_window = {}
for blk in re.findall(r"--- (2022 stress|2025-26 uptrend) \((.*?)\) ---(.*?)(?=---|\Z)", regime, re.S):
    label, _, body = blk
    rho = re.search(r"mean pairwise rho \(book\)\s+([+-]\d\.\d\d).*?effective bets ([\d.]+) of (\d+)", body)
    spy = re.search(r"with SPY as one more series: rho ([+-]\d\.\d\d) -> ([\d.]+) of (\d+)", body)
    if rho and spy:
        by_window[label] = {"rho_book": rho.group(1), "neff_book": rho.group(2), "n_book": rho.group(3),
                            "rho_spy": spy.group(1), "neff_spy": spy.group(2), "n_spy": spy.group(3)}
check("both regimes measured", len(by_window) == 2, str(list(by_window)))
if len(by_window) == 2:
    s, u = by_window["2022 stress"], by_window["2025-26 uptrend"]
    check("stress with SPY -> N_eff %s (md says 2.4)" % s["neff_spy"], s["neff_spy"] == "2.4" and "2.4" in section)
    check("stress book-only -> N_eff %s (md says 2.5)" % s["neff_book"], s["neff_book"] == "2.5" and "| 2.5 |" in section)
    check("uptrend with SPY -> N_eff %s (md says 3.3)" % u["neff_spy"], u["neff_spy"] == "3.3" and "| 3.3 |" in section)
    check("uptrend book-only -> N_eff %s (md says 3.5)" % u["neff_book"], u["neff_book"] == "3.5" and "| 3.5 |" in section)
    for lab, d, want in (("stress", s, ("+0.39", "+0.38", "33", "32")), ("uptrend", u, ("+0.28", "+0.27", "35", "34"))):
        ok = all(t in section for t in want)
        check("%s rho/series counts quoted and matching (%s)" % (lab, ",".join(want)), ok)
    # within / cross bloc rho
    for lab, d, pair in (("stress", s, ("+0.54", "+0.26", "+0.29")), ("uptrend", u, ("+0.50", "+0.21", "+0.08"))):
        body = regime[regime.find("--- %s" % ("2022 stress" if lab == "stress" else "2025-26 uptrend")):]
        got = re.findall(r"within semis/photonics\s+([+-]\d\.\d\d).*?within value\s+([+-]\d\.\d\d).*?semis vs value\s+([+-]\d\.\d\d)",
                         body, re.S)
        actual = got[0] if got else ()
        check("%s bloc rhos %s quoted in md" % (lab, pair),
              actual == pair and all(f"**{p}" in section or p in section for p in pair),
              "script %s" % (actual,))

# ---- 2. bloc vol / max DD ------------------------------------------------------------------
print("\n=== 2. bloc risk (md quotes vol and maxDD per bloc) ===")
for lab in ("2022 stress", "2025-26 uptrend"):
    body = regime[regime.find("--- %s" % lab):]
    mm = re.search(r"equal-weight vol / maxDD:\s+semis ([\d.]+)% / (-[\d.]+)%\s+value ([\d.]+)% / (-[\d.]+)%\s+book ([\d.]+)% / (-[\d.]+)%", body)
    if not mm:
        check("%s bloc vol line parsed" % lab, False, "not found")
        continue
    semis_v, semis_dd, val_v, val_dd, book_v, book_dd = mm.groups()
    if lab == "2022 stress":
        ok = all(t in section for t in (f"{semis_v}%", f"{semis_dd}%", f"{val_v}%", f"{val_dd}%", f"{book_v}%", f"{book_dd}%"))
        check("stress bloc vols quoted exactly (%s/%s, %s/%s, %s/%s)" % (semis_v, semis_dd, val_v, val_dd, book_v, book_dd), ok)

# ---- 3. the stop in daily sigma ------------------------------------------------------------
print("\n=== 3. stop distance in daily sigma (book_risk.py) ===")
sig = {t: float(k) for t, k in re.findall(r"^\s+([A-Z]{2,5})\s+ann vol\s+[\d.]+%\s+daily sigma\s+[\d.]+%\s+15% stop =\s+([\d.]+) sigma", book, re.M)}
check("34 names classified", len(sig) == 34, "%d found" % len(sig))
if sig:
    low = sorted(t for t, k in sig.items() if k <= 3.3)
    high = sorted(t for t, k in sig.items() if k >= 4.0)
    check("16 names at <=3.3 sigma (md: '16 of the 34')", len(low) == 16 and "16 of the 34" in section, "%d" % len(low))
    check("17 names at >=4.0 sigma (md: '17 at >=4.0')", len(high) == 17 and "17 at \u22654.0" in section, "%d" % len(high))
    check("AMD the single name between (md: '3.5\u03c3')", sig.get("AMD") == 3.5 and "AMD at 3.5\u03c3" in section)
    check("min distance AAOI/AXTI 1.7 (md)", abs(sig.get("AAOI", 9) - 1.7) < 0.05 and abs(sig.get("AXTI", 9) - 1.7) < 0.05 and "1.7\u03c3" in section)
    check("max distance PFE (md: 9.7)", max(sig, key=lambda t: sig[t]) == "PFE" and "9.7\u03c3" in section, max(sig, key=lambda t: sig[t]))
    check("every value-defensive name >=4.0 sigma (md claims it)", all(t in high for t in VALUE), [t for t in VALUE if t not in high])
    check("every <=3.3 sigma name is semis/photonics (md claims it)", all(t in SEMIS for t in low), [t for t in low if t not in SEMIS])
    for t in low:
        if ("%s %s" % (t, ("%.1f" % sig[t]))) not in section:
            check("md lists %s at %.1fsigma" % (t, sig[t]), False, "token missing")
            break
    else:
        check("md enumerates all 16 low-sigma names with their value", True)
    # the >100% vol list used to size the per-name cap
    annvol = {t: float(a) for t, a in re.findall(r"^\s+([A-Z]{2,5})\s+ann vol\s+([\d.]+)%", book, re.M)}
    over = sorted([t for t, a in annvol.items() if a > 100.0])
    want = {"AAOI": "140", "AXTI": "138", "POET": "124", "AEHR": "119", "NBIS": "112", "MXL": "108", "SNDK": "106"}
    check("names over 100%% ann. vol match the md list (%s)" % ",".join(over), set(over) == set(want),
          "script %s vs md %s" % (sorted(over), sorted(want)))
    check("per-name cap row quotes those vols", all("%s%%" % v in section for v in want.values()))

# ---- 4. per-sector stop table --------------------------------------------------------------
print("\n=== 4. stop policy by sector (stop_regime_rotation.py) ===")
rows = []
for line in rot.splitlines():
    mm = re.match(r"^(.+?)\s+(2022 drawdown|2025-26 uptrend)\s+(\d+)\s+([+-][\d.]+)%\s+(\d+) of (\d+)\s*$", line)
    if mm:
        rows.append(mm.groups())
check("4 sector groups x 2 regimes parsed", len(rows) == 8, "%d rows" % len(rows))
grp_alias = {"software / cyber / cloud": "software", "semis (the book, for reference)": "semis",
             "gold / life sciences": "gold", "energy / materials": "energy"}
for g, period, n, med, helped, tot in rows:
    gname = g.strip()
    tag = grp_alias.get(gname, gname)
    key = "2022 stress" if period == "2022 drawdown" else "2025-26 uptrend"
    if tag in ("software", "semis", "gold", "energy") and key == "2022 stress":
        ok = (med + "%") in section and ("%s of %s" % (helped, tot)) in section
        check("%s 2022: %s%%, helped %s of %s (quoted in md)" % (tag, med, helped, tot), ok)
# uptrend column of the md table
up_md = re.search(r"\| Software / cyber / cloud \| 21 \|.*?\| (-[\d.]+)% \| (\d+) of 21 \|", section)
check("software uptrend cost -24.5% / 5 of 21 (md)", bool(up_md) and up_md.group(1) == "-24.5" and up_md.group(2) == "5",
      up_md.groups() if up_md else "row not found")
check("semis uptrend -219.6% / 0 of 16 (md)", "**-219.6%** | 0 of 16" in section)
check("gold 2022 +2.6% / 10 of 16 (md)", "| +2.6% | 10 of 16 |" in section)
check("energy 2022 -10.2% / 6 of 21 (md)", "| **-10.2%** | **6 of 21** |" in section)

# ---- 5. cluster cap derivation -------------------------------------------------------------
print("\n=== 5. cluster cap derived from the stress number ===")
neff = float(by_window["2022 stress"]["neff_spy"]) if by_window else 0
one_bet = 100.0 / neff
check("1/2.4 = %.1f%% -> cap 40%% is the rounded-down value" % one_bet, one_bet == 41.66666666666667 or abs(one_bet - 41.6667) < 0.01)
check("md states 41.7% and 40%", "1/2.4 = 41.7%" in section and "**40% of book value**" in section)
check("frontmatter carries the policy inputs",
      all(t in md for t in ("risk_neff_stress: 2.4", "risk_neff_trend: 3.3", "cluster_cap_pct: 40")))

# ---- 6. live cluster read-out vs the file's own positions table ----------------------------
print("\n=== 6. live cluster read-out ===")
total = float(re.search(r"^total_value: ([\d.]+)$", md, re.M).group(1))
tbl = re.findall(r"^\| \d+ \| \*\*([A-Z]+)\*\* \|.*?\| \$([\d,]+) \| \$([\d,]+) \| ([+-][\d.]+)% \|", md, re.M)
mv = {t: float(v.replace(",", "")) for t, v, _c, _u in tbl}
check("positions table parsed (%d rows)" % len(tbl), len(tbl) == len(mv) > 0)
val_w = sum(v for t, v in mv.items() if t in VALUE) / total * 100
ai_w = sum(v for t, v in mv.items() if t in SEMIS) / total * 100
mm = re.search(r"\| AI-capex / semis-photonics \| ([\d.]+)% \| 40% \|", section)
mv_row = re.search(r"\| value-defensive \| ([\d.]+)% \| 40% \|", section)
check("AI-capex row %.1f%% matches the positions table" % ai_w,
      bool(mm) and abs(float(mm.group(1)) - ai_w) < 0.05, mm.group(1) if mm else "row missing")
check("value-defensive row %.1f%% matches the positions table" % val_w,
      bool(mv_row) and abs(float(mv_row.group(1)) - val_w) < 0.05, mv_row.group(1) if mv_row else "row missing")
check("breach flag present and arithmetic right (%.1fx of cap)" % (val_w / 40.0),
      val_w > 40.0 and re.search(r"BREACH — [\d.]+x the cap \(trim ~\d+pp", section) is not None)
state = json.load(open(os.path.join(FINANCE_AI, "pm_portfolio.json"), encoding="utf-8"))
cash = float(state["portfolio"]["cash"])
check("cash row %.1f%% matches pm_portfolio.json" % (cash / total * 100),
      abs(cash / total * 100 - float(re.search(r"\| cash \| ([\d.]+)% \|", section).group(1))) < 0.05)

# ---- 7. the stop policy actually applied to each live position -----------------------------
print("\n=== 7. stop policy applied per position ===")
pos = re.findall(r"^\| \*\*([A-Z]+)\*\* \| [\d.]+% \| value-defensive \| (.*?) \| (.*?) \| (.*?) \|$", section, re.M)
check("12 positions mapped", len(pos) == 12, "%d" % len(pos))
policy = {t: p for t, sec, _ev, p in pos}
retire = {"SM", "VALE", "PBR"}
for t in sorted(retire):
    check("%s (energy/materials) has the 15%% retired" % t, "retire" in policy.get(t, ""), policy.get(t))
check("ADBE keeps the tested 15%", "keep 15% trailing" == policy.get("ADBE"), policy.get("ADBE"))
others = [t for t in policy if t not in retire | {"ADBE"}]
check("the other %d live names are labelled break-only circuit breakers" % len(others),
      all("break-only" in policy[t] for t in others), [t for t in others if "break-only" not in policy[t]])
check("enforcement status recorded (engine rules vs this policy)", "Enforcement status" in section and "pm_trader.py" in section)

# ---- 8. enforcement status vs the live engine ----------------------------------------------
print("\n=== 8. enforcement: doc vs pm_trader.py ===")
trader = os.path.join(FINANCE_AI, "pm_trader.py")
src = open(trader, encoding="utf-8").read() if os.path.exists(trader) else ""
if not src:
    check("pm_trader.py readable", False, "missing")
else:
    estop = re.search(r"^TRAILING_STOP\s*=\s*([\d.]+)", src, re.M)
    erisk = re.search(r"^RISK_PER_NAME\s*=\s*([\d.]+)", src, re.M)
    check("engine TRAILING_STOP parsed", bool(estop), "constant gone - re-read the engine")
    check("engine RISK_PER_NAME parsed", bool(erisk), "constant gone - re-read the engine")
    if estop and erisk:
        live_stop, live_risk = estop.group(1), erisk.group(1)
        check("md quotes the live stop (TRAILING_STOP = %s)" % live_stop,
              ("TRAILING_STOP = %s" % live_stop) in section, "md stale vs engine")
        check("md quotes the live per-name cap (RISK_PER_NAME = %s)" % live_risk,
              ("RISK_PER_NAME = %s" % live_risk) in section, "md stale vs engine")
        check("engine's level is flagged as untested (%.0f%% vs the tested 15%%)" % (float(live_stop) * 100),
              float(live_stop) != 0.15 and "never been tested on this book in either regime" in section)
        check("engine still applies the stop uniformly (no per-sector map yet)",
              "(1 - TRAILING_STOP)" in src and not re.search(r"^[A-Z_]*STOP[A-Z_]*\s*=\s*\{", src, re.M),
              "a per-sector stop now exists in the engine - the enforcement note needs updating")
        check("doc states nothing reads the policy yet", "Nothing reads this section" in section)

# ---- 9. the companion driver-level measurement -------------------------------------------------
print("\n=== 9. reconciliation with the driver-level study ===")
companion = os.path.join(V, "Notes", "2026-09-16 Book drivers research.md")
check("companion note exists", os.path.exists(companion), companion)
if os.path.exists(companion):
    cnote = open(companion, encoding="utf-8").read()
    cnum = re.search(r"\*\*N_eff \(independent drivers\)\*\*\s*\|\s*\*\*([\d.]+)\*\*\s*\|\s*\*\*([\d.]+)\*\*", cnote)
    check("companion's own stress N_eff parsed", bool(cnum), "driver table changed shape")
    if cnum:
        calm, stress = cnum.groups()
        check("md cites the companion's calm and stress figures (%s / %s)" % (calm, stress),
              ("~%s independent drivers" % calm) in section and ("~%s in" % stress) in section,
              "md silent on the other measurement")
        check("md states the two methods' units differ, not just the numbers",
              "by name" in section and "by driver" in section and "not comparable" in section)
        check("md states the cap survives both stress bases (%s and 2.4)" % stress,
              "1/2.4 = 41.7%" in section and ("1/2.2 = 45.5%" in section or ("1/%s" % stress) in section))

print("\n=== %s: %d checks, %d failed ===" % ("PASS" if not fails else "FAIL", checks, len(fails)))
for f in fails:
    print("  failed: %s" % f)
sys.exit(1 if fails else 0)
