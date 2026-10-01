#!/usr/bin/env python3
"""
portfolio_node.py — regenerate /documents/Finance Knowledge Graph/Portfolio.md
Graph-native PM portfolio node.

Reads /documents/finance-ai/pm_portfolio.json and the Companies ticker index,
pulls live price: lines, thesis links, invalidations, and Important Dates.

Idempotent: overwrites Portfolio.md each run. Never modifies other vault files.
"""
import os, re, json, glob
from datetime import date, datetime

# --- paths (sandbox uses /documents, fallback to ~/Documents) ---
FINANCE_AI = "/documents/finance-ai"
KG_ROOT = "/documents/Finance Knowledge Graph"
if not os.path.isdir(FINANCE_AI):
    FINANCE_AI = os.path.expanduser("~/Documents/finance-ai")
if not os.path.isdir(KG_ROOT):
    KG_ROOT = os.path.expanduser("~/Documents/Finance Knowledge Graph")

STATE_FILE = os.path.join(FINANCE_AI, "pm_portfolio.json")
COMPANIES_DIR = os.path.join(KG_ROOT, "Companies")
NOTES_DIR = os.path.join(KG_ROOT, "Notes")
IMPORTANT_DIR = os.path.join(KG_ROOT, "Important Dates")
OUTPUT = os.path.join(KG_ROOT, "Portfolio.md")

FM_RE = re.compile(r'^---\n(.*?)\n---', re.S)

def get_fm(path):
    try:
        txt = open(path, encoding="utf-8").read()
        m = FM_RE.search(txt)
        return m.group(1) if m else "", txt
    except Exception:
        return "", ""

def extract_list_field(fm_text, field):
    """Return raw '[...]' for a field, handling quoted strings + nested [[ ]]."""
    idx = fm_text.find(field + ":")
    if idx == -1:
        return None
    j = fm_text.find("[", idx)
    if j == -1:
        # maybe empty or not a list
        return None
    depth = 0
    in_str = False
    esc = False
    start = j
    for k in range(j, len(fm_text)):
        c = fm_text[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    return fm_text[start:k+1]
    return None

def parse_wikilinks(s):
    if not s:
        return []
    return re.findall(r"\[\[(.*?)\]\]", s)

def parse_quoted_strings(list_raw):
    """Extract quoted strings from a YAML list like [\"a\", \"b\"]."""
    if not list_raw:
        return []
    # capture "..." that are not escaped
    return re.findall(r'"((?:\\"|[^"])*)"', list_raw)

def load_ticker_map():
    tmap = {}  # ticker -> title
    cmap = {}  # ticker -> path
    price_map = {}  # ticker -> (price_float, raw_str)
    research_map = {} # ticker -> first thesis link name
    for path in glob.glob(os.path.join(COMPANIES_DIR, "*.md")):
        fm, txt = get_fm(path)
        m = re.search(r'ticker:\s*"([^"]*)"', fm)
        if not m:
            m2 = re.search(r"ticker:\s*'([^']*)'", fm)
            ticker = m2.group(1).strip().upper() if m2 else ""
        else:
            ticker = m.group(1).strip().upper()
        if not ticker:
            continue
        title = os.path.splitext(os.path.basename(path))[0]
        tmap[ticker] = title
        cmap[ticker] = path
        # price
        pm = re.search(r'price:\s*"([^"]*)"', fm)
        if pm:
            raw = pm.group(1)
            # first number is price
            nm = re.search(r"([0-9]+(?:\.[0-9]+)?)", raw)
            if nm:
                try:
                    price_map[ticker] = (float(nm.group(1)), raw)
                except: pass
        # research first link
        raw_list = extract_list_field(fm, "research")
        if raw_list:
            links = parse_wikilinks(raw_list)
            if links:
                research_map[ticker] = links[0]
    return tmap, cmap, price_map, research_map

def find_note_path(note_title):
    # exact in Notes
    cands = [
        os.path.join(NOTES_DIR, note_title + ".md"),
        os.path.join(KG_ROOT, note_title + ".md"),
    ]
    for p in cands:
        if os.path.exists(p):
            return p
    # glob fallback
    hits = glob.glob(os.path.join(NOTES_DIR, "*.md"))
    for h in hits:
        if os.path.splitext(os.path.basename(h))[0] == note_title:
            return h
    # case-insensitive search
    lo = note_title.lower()
    for h in hits:
        if os.path.splitext(os.path.basename(h))[0].lower() == lo:
            return h
    return None

def get_invalidations(note_path):
    if not note_path or not os.path.exists(note_path):
        return []
    fm, _ = get_fm(note_path)
    raw = extract_list_field(fm, "invalidations")
    if raw is None:
        return []
    if raw.strip() == "[]":
        return []
    return parse_quoted_strings(raw)

def get_catalysts_field(note_path):
    if not note_path or not os.path.exists(note_path):
        return []
    fm, _ = get_fm(note_path)
    raw = extract_list_field(fm, "catalysts")
    if raw is None or raw.strip() == "[]":
        return []
    links = parse_wikilinks(raw)
    if links:
        return links
    return parse_quoted_strings(raw)

def get_important_dates_for(ticker, title):
    """Scan Important Dates for matching company."""
    out = []
    if not os.path.isdir(IMPORTANT_DIR):
        return out
    for path in glob.glob(os.path.join(IMPORTANT_DIR, "*.md")):
        fm, _ = get_fm(path)
        # company field may be [[Title]] or plain
        cm = re.search(r'company:\s*"([^"]*)"', fm)
        if not cm:
            cm = re.search(r"company:\s*'([^']*)'", fm)
            cval = cm.group(1) if cm else ""
        else:
            cval = cm.group(1)
        # also check raw wikilinks in company field
        c_links = parse_wikilinks(cval) if cval else []
        # also check file if no fm company, try title match
        basename = os.path.splitext(os.path.basename(path))[0]
        # date
        dm = re.search(r'date:\s*"([^"]*)"', fm)
        dstr = dm.group(1) if dm else ""
        if not dstr:
            m = re.search(r"(\d{4}-\d{2}-\d{2})", basename)
            dstr = m.group(1) if m else ""
        # check match
        matched = False
        if title and (title in c_links or title.lower() in cval.lower()):
            matched = True
        if ticker and ticker.lower() in cval.lower():
            matched = True
        # also if basename contains ticker as a token (avoid substring hits like "sm" in "intismeran")
        if ticker and re.search(r"(?:^|[^a-z0-9])" + re.escape(ticker.lower()) + r"(?=[^a-z0-9]|$)", basename.lower()):
            matched = True
        if matched:
            # event
            em = re.search(r'event:\s*"([^"]*)"', fm)
            event = em.group(1) if em else basename
            out.append({"date": dstr, "event": event, "path": path, "company_raw": cval or basename})
    # sort by date
    def dkey(x):
        try: return datetime.strptime(x["date"], "%Y-%m-%d").date()
        except: return date.max
    out.sort(key=dkey)
    return out

# --- Risk policy: the decisions, with their measured basis -------------------------------
# Every figure is measured on the stored daily layer and reproducible from:
#   book_risk.py            per-name annualised vol + max DD, trend correlations, N_eff (uptrend)
#   corr_regime.py          N_eff by regime (2022 stress 2.4 / 2025-26 uptrend 3.3)
#   corr_regime_lib.py      within-bloc and cross-bloc rho by regime
#   stop_regime_rotation.py trailing-stop outcome by sector group and regime
# Windows: 2022-01-01..2022-12-31 (stress, 250 days), 2025-02-14..2026-09-15 (uptrend, 396 days).
NEFF_STRESS = 2.4              # 33 names, mean pairwise rho +0.39
NEFF_TREND = 3.3               # 35 names, mean pairwise rho +0.28
CLUSTER_CAP_PCT = 40.0         # 1/2.4 = 41.7% -> rounded down
NAME_CAP_PCT = 10.0
NAME_CAP_HIGHVOL_PCT = 5.0
HIGHVOL_ANN_PCT = 100.0
CASH_FLOOR_PCT = 10.0
RISK_POLICY_DATE = "2026-09-16"
RISK_POLICY_NOTE = "2026-09-16 Book risk and stop calibration research"

CLUSTER_OF = {
    "AI-capex / semis-photonics": [
        "AAOI", "AXTI", "MU", "SNDK", "NBIS", "POET", "LITE", "MTSI", "SMTC", "AEHR", "MXL",
        "NVDA", "TSM", "AVGO", "AMD", "MRVL", "WDC", "ONTO", "RMBS", "TSEM", "AEIS", "SIMO"],
    "value-defensive": ["GM", "VTRS", "VALE", "CAG", "GIS", "HPQ", "SM", "PRU", "NVO", "PBR", "PFE", "ADBE"],
}
CLUSTER_LOOKUP = {t: c for c, names in CLUSTER_OF.items() for t in names}

# Sector assignment used only to pick the stop policy. The tested baskets are the large-cap
# sector groups in stop_regime_rotation.py; names added here (the book's own energy/materials
# producers) are mapped by sector, which is a PM judgement, and are marked as such below.
SECTOR_STOP = {
    "software / cyber / cloud": {"policy": "keep 15% trailing",
        "why": "The only group where 15% is right in both tested regimes (+25.2%, helped 20 of 21 in 2022; -24.5% cost in the uptrend)"},
    "semis / photonics": {"policy": "keep 15% trailing",
        "why": "The payout side is the survival case (+26.3%, helped 12 of 16 in 2022; bloc maxDD -43.2%); the -219.6% uptrend premium is the expected cost of insurance"},
    "gold / life sciences": {"policy": "retire the 15% - thesis kill-switch exits only",
        "why": "15% barely paid in the break (+2.6%, helped 10 of 16) and cost -40.3% in the uptrend; the test cannot fit a level, so none is invented"},
    "energy / materials": {"policy": "retire the 15% - thesis kill-switch exits only",
        "why": "It hurt in BOTH regimes (-10.2%, helped 6 of 21 in 2022; -63.6%, helped 0 of 21 in the uptrend) because commodity-cyclicals were in an uptrend through the 2022 break"},
}
# ticker -> (sector, is the sector covered by a tested basket), for the live read-out only
TICKER_SECTOR = {
    "ADBE": ("software / cyber / cloud", "software / cyber / cloud"),
    "SM": ("energy — E&P", "energy / materials"),
    "VALE": ("materials — mining", "energy / materials"),
    "PBR": ("energy — integrated", "energy / materials"),
    "HPQ": ("tech hardware", None),
    "VTRS": ("pharma — generics", None),
    "PFE": ("pharma", None),
    "NVO": ("pharma", None),
    "GM": ("autos", None),
    "PRU": ("insurance", None),
    "CAG": ("staples", None),
    "GIS": ("staples", None),
}
LOWVOL_POLICY = {"policy": "keep 15%, labelled break-only circuit breaker",
    "why": "Untested sector: at 4-10 daily sigma the level cannot fire outside a break, so it is a circuit breaker rather than a trading stop"}

# Operative settings of the book's own trader, read from the engine rather than restated here, so the
# enforcement note below cannot go stale: change pm_trader.py and Portfolio.md follows on the next run.
PM_TRADER = os.path.join(FINANCE_AI, "pm_trader.py")


def _engine_settings(path=PM_TRADER):
    """(trailing stop, per-name cap, stated rationale) as pm_trader.py actually runs them."""
    try:
        src = open(path, encoding="utf-8").read()
    except OSError:
        return 0.0, 0.0, "engine not found — enforcement status unknown"

    def num(name):
        m = re.search(r"^%s\s*=\s*([\d.]+)" % name, src, re.M)
        return float(m.group(1)) if m else 0.0

    m = re.search(r"trailing stop on all names \((.*?)\)", src)
    return num("TRAILING_STOP"), num("RISK_PER_NAME"), (m.group(1) if m else "no rationale stated in the engine")


def _stop_for(sym):
    """(sector label, basis string, policy) for one position."""
    if sym in TICKER_SECTOR:
        sector, tested_group = TICKER_SECTOR[sym]
        if tested_group:
            return sector, "tested group: " + tested_group, SECTOR_STOP[tested_group]
        return sector, "untested sector — low-vol default", LOWVOL_POLICY
    if sym in CLUSTER_OF["AI-capex / semis-photonics"]:
        return "semis / photonics", "tested group: semis / photonics", SECTOR_STOP["semis / photonics"]
    return "unassigned", "untested sector — low-vol default", LOWVOL_POLICY


def risk_rules_block(pos_details, total_value):
    """Render the risk-rule decisions: cluster limits sized on the stress number, then the
    per-sector stop policy. Cluster/stop read-outs are computed off the live book."""
    L = []
    L.append("## Risk rules — cluster limits · stop policy")
    L.append("")
    L.append(f"> **Decided {RISK_POLICY_DATE}.** Basis note: [[{RISK_POLICY_NOTE}]]. Every number below is measured on the "
             "stored daily layer (`Datasets/History/prices_daily/`) and comes from two runs: `book_risk.py` (per-name vol and "
             "max DD, plus its regime block: effective bets, within/cross-bloc correlations, bloc vol / max DD, and the 15% "
             "stop in daily sigma) and `stop_regime_rotation.py` (trailing-stop outcome by sector). Windows: **2022 stress** "
             "2022-01-01→2022-12-31 (250 days), **2025-26 uptrend** 2025-02-14→2026-09-15 (396 days). `corr_regime.py` "
             "reproduces the bloc table on its own.")
    L.append("")
    L.append("### 1. Cluster position limits — sized on the STRESS number, not the trend number")
    L.append("")
    L.append("**The number.** Effective independent bets `N_eff = N / (1 + (N-1) * mean pairwise rho)` on daily returns "
             "(`book_risk.py`, regime block):")
    L.append("")
    L.append("| Window | Series | mean pairwise rho | N_eff |")
    L.append("|---|---:|---:|---:|")
    L.append("| 2022 stress | 33 (32 book names + SPY) | +0.39 | **2.4** |")
    L.append("| 2025-26 uptrend | 35 (34 book names + SPY) | +0.28 | 3.3 |")
    L.append("| 2022 stress, book names only | 32 | +0.38 | 2.5 |")
    L.append("| 2025-26 uptrend, book names only | 34 | +0.27 | 3.5 |")
    L.append("")
    L.append("Both bases are printed because they are the source of the two figures in circulation: **3.5** is the "
             "fair-weather *book-only* reading, **3.3** the same window with SPY in the series, and **2.4** (with SPY) is "
             "the stress number. The cap is **40% on either stress basis** (1/2.4 = 41.7%, 1/2.5 = 40.0%), so the rule does "
             "not turn on the choice; 2.4 is the anchor quoted here.")
    L.append("")
    L.append("**Companion measurement — the same book by driver, not by name.** [[2026-09-16 Book drivers research]] runs the "
             "same formula over **9 driver bets** instead of 34 names: **~5.2 independent drivers in the calm regime, ~2.2 in "
             "the 2022 stress window**, with 22 of the 34 names sitting inside one AI-capex bet (rho +0.69 internally). The two "
             "methods differ on the fair-weather number (3.3 by name, 5.2 by driver — different units, so the counts are not "
             "comparable) and agree on the stress number (2.4 by name, 2.2 by driver). Both conclude the stress figure is the "
             "one to size against, and **the cap is unchanged under either**: 1/2.4 = 41.7%, 1/2.2 = 45.5%, both rounding down "
             "to 40%. The driver view also states what the name view cannot: the 22 semis names are *one* bet, which is why the "
             "*cluster* cap and not the per-name cap is the one that binds.")
    L.append("")
    L.append("Where it changes (2022 → uptrend): within semis/photonics **+0.54 → +0.50** (already high, little headroom); "
             "within value **+0.26 → +0.21**; **semis vs value +0.29 → +0.08** — the offset the book relies on nearly "
             "quadruples in stress. Limits are set on **2.4**, the number that applies when a limit bites; 3.3 is the "
             "fair-weather reading.")
    L.append("")
    L.append("| Rule | Limit | Derivation |")
    L.append("|---|---|---|")
    L.append(f"| Cluster cap (each of the two blocs) | **{CLUSTER_CAP_PCT:.0f}% of book value** | one effective bet = 1/2.4 = 41.7% of book risk, rounded down |")
    L.append(f"| Single name | **{NAME_CAP_PCT:.0f}% of book** | ≥4 names to fill a cluster; at rho +0.54 a cluster is ~1 bet internally, so the cluster is the risk unit, not the ticker |")
    L.append(f"| Single name, annualised vol > {HIGHVOL_ANN_PCT:.0f}% | **{NAME_CAP_HIGHVOL_PCT:.0f}% of book** | book_risk.py vol column: AAOI 140%, AXTI 138%, POET 124%, AEHR 119%, NBIS 112%, MXL 108%, SNDK 106% |")
    L.append(f"| Cash floor | **{CASH_FLOOR_PCT:.0f}%** | unchanged |")
    L.append("")
    L.append("Clusters = **AI-capex / semis-photonics** and **value-defensive**, the two blocs the correlations are measured "
             "on. The cap sits on the cluster: 22 semis names at 3% each look like 22 positions and behave like ~1.8.")
    L.append("")
    # live cluster read-out
    cw = {}
    for x in pos_details:
        c = CLUSTER_LOOKUP.get(x["symbol"], "unclassified")
        cw[c] = cw.get(c, 0.0) + x["mv"]
    cash_now = 0.0
    try:
        import json as _json
        _st = _json.load(open(STATE_FILE, encoding="utf-8"))
        cash_now = float(_st.get("portfolio", {}).get("cash", 0) or 0)
    except Exception:
        cash_now = max(0.0, total_value - sum(x["mv"] for x in pos_details))
    L.append(f"**Read-out on this book** (marks from this file, total ${total_value:,.0f}):")
    L.append("")
    L.append("| Cluster | Current | Cap | Status |")
    L.append("|---|---:|---:|---|")
    for c in ["AI-capex / semis-photonics", "value-defensive"]:
        w = cw.get(c, 0.0) / total_value * 100 if total_value else 0.0
        if w > CLUSTER_CAP_PCT:
            status = f"**BREACH — {w / CLUSTER_CAP_PCT:.1f}x the cap (trim ~{w - CLUSTER_CAP_PCT:.0f}pp to reach it)**"
        elif w >= CLUSTER_CAP_PCT * 0.75:
            status = "at cap (inside 25% headroom)"
        else:
            status = "under"
        L.append(f"| {c} | {w:.1f}% | {CLUSTER_CAP_PCT:.0f}% | {status} |")
    if cw.get("unclassified"):
        w = cw["unclassified"] / total_value * 100 if total_value else 0.0
        L.append(f"| unclassified (no cluster assignment) | {w:.1f}% | — | add to a cluster map |")
    wcash = cash_now / total_value * 100 if total_value else 0.0
    L.append(f"| cash | {wcash:.1f}% | ≥{CASH_FLOOR_PCT:.0f}% floor | {'ok' if wcash >= CASH_FLOOR_PCT else 'below floor'} |")
    L.append("")
    value_w = cw.get("value-defensive", 0.0) / total_value * 100 if total_value else 0.0
    if value_w > CLUSTER_CAP_PCT:
        L.append("The book is a single-cluster book: the value-defensive bloc is over its cap while the AI-capex leg is "
                 "absent, so the stress offset the cap depends on (semis vs value +0.29) is not actually held. The rule binds "
                 "from this date — either trim toward the cap or record a written exception with its own stress argument.")
        L.append("")
    L.append("**Regime limits of this rule.**")
    L.append("- rho +0.39 / N_eff 2.4 is **one** stress realisation (2022, 250 days) and one trend (396 days). A different break "
             "(e.g. a rates-led drawdown with commodities falling, the opposite of 2022) is untested.")
    L.append("- **Notional is not risk.** Measured stress vols: semis bloc **41.1%** (maxDD -43.2%), value bloc **22.7%** "
             "(-19.4%), 34-name book at equal weight **32.2%** (-32.3%). At both caps the semis bloc carries ~**71%** of book "
             "stress risk. That is deliberate — it is the bloc whose stop payout the survival case rests on — but it means the "
             "cap controls *concentration*, not risk parity. For equal risk contribution the semis cap would be ~18% notional: "
             "a policy choice, not a measurement. The 40% cap is the one adopted.")
    L.append("- Bounds cluster concentration only: no leverage, liquidity, single-name event or currency bound.")
    L.append("")
    L.append("### 2. Stop policy — by sector, not one 15% rule for the whole book")
    L.append("")
    L.append("Same rule (15% trailing, measured from the running peak, one episode per breach), two regimes:")
    L.append("")
    L.append("| Sector group | n | 2022 stress: median vs buy-and-hold | helped | 2025-26 uptrend: median | helped | Decision |")
    L.append("|---|---:|---:|---:|---:|---:|---|")
    L.append("| Software / cyber / cloud | 21 | **+25.2%** | **20 of 21** | -24.5% | 5 of 21 | **keep 15%** — best-calibrated group in both regimes |")
    L.append("| Semis / photonics (the book) | 16 | **+26.3%** | 12 of 16 | **-219.6%** | 0 of 16 | **keep 15%** — insurance; the -219.6% premium is its price |")
    L.append("| Gold / life sciences | 16 | +2.6% | 10 of 16 | -40.3% | 1 of 16 | **retire 15%** — barely paid, cost 40% in the trend |")
    L.append("| Energy / materials | 21 | **-10.2%** | **6 of 21** | -63.6% | 0 of 21 | **retire 15%** — poor fit in BOTH regimes |")
    L.append("")
    L.append("**Why one level cannot be one rule.** The same 15% is a different rule on every name, because it sits at a "
             "different distance in daily sigma (`book_risk.py` regime block prints the full table; σ_daily = annualised vol "
             "÷ √252, uptrend window). The shortest distance in the book is AAOI/AXTI at **1.7σ** (140% / 138% annualised "
             "vol) and the longest is PFE at **9.7σ** (24%). Counted at the gap: **16 of the 34 names sit at ≤3.3σ** (the "
             "high-volatility semis/photonics: AAOI 1.7, AXTI 1.7, POET 1.9, AEHR 2.0, NBIS 2.1, MXL 2.2, SNDK 2.2, "
             "LITE 2.7, MRVL 3.1, SMTC 3.1, MU 3.2, RMBS 3.2, SIMO 3.2, ONTO 3.2, TSEM 3.3, WDC 3.3), AMD at 3.5σ, and the "
             "other **17 at ≥4.0σ** (AEIS 4.0, MTSI 4.1, SM 4.2, AVGO 4.8, NVO 4.8, HPQ 5.4, NVDA 5.6, TSM 5.9, ADBE 6.2, "
             "VTRS 6.7, GM 6.8, PBR 7.1, VALE 7.4, CAG 8.1, GIS 8.9, PRU 9.3, PFE 9.7). Every one of the 12 value-defensive "
             "names is in the ≥4.0σ group, and every name in the ≤3.3σ group is a semis/photonics name. So on the complex "
             "the stop fires in normal trading — the one place the sector test says it earns its keep — and on the value "
             "half it cannot fire outside a break, where it is a circuit breaker rather than a trading stop.")
    L.append("")
    L.append("**Applied to this book:**")
    L.append("")
    L.append("| Position | Wt% | Cluster | Sector (assigned) | Evidence | Stop policy |")
    L.append("|---|---:|---|---|---|---|")
    by_policy = {}
    for x in pos_details:
        sec, basis, pol = _stop_for(x["symbol"])
        w = x["mv"] / total_value * 100 if total_value else 0.0
        by_policy.setdefault(pol["policy"], {"w": 0.0, "sectors": {}, "why": pol["why"]})
        by_policy[pol["policy"]]["w"] += w
        by_policy[pol["policy"]]["sectors"][sec] = by_policy[pol["policy"]]["sectors"].get(sec, 0.0) + w
        L.append(f"| **{x['symbol']}** | {w:.1f}% | {CLUSTER_LOOKUP.get(x['symbol'], 'unclassified')} | {sec} | {basis} | {pol['policy']} |")
    L.append("")
    for pol, agg in sorted(by_policy.items(), key=lambda kv: -kv[1]["w"]):
        secs = ", ".join(f"{s} {sw:.1f}%" for s, sw in sorted(agg["sectors"].items(), key=lambda kv: -kv[1]))
        L.append(f"- **{pol}** — {agg['w']:.1f}% of book ({secs}). {agg['why']}.")
    L.append("")
    L.append("**Regime limits of the stop policy.**")
    L.append("- **Two periods only, both extreme** (a broad 2022 drawdown; a violent 2025-26 uptrend). No intermediate regime "
             "was tested, so this fits no level: the tested finding is *which sectors the 15% suits*, not a per-sector number. "
             "Where 15% fails there, the policy retires the rule rather than inventing an untested level.")
    L.append("- **Re-entry is not modelled** — each stopped position is assumed closed. The measured premium is therefore "
             "overstated where a strategy re-enters, and the payout understated.")
    L.append("- **Providers, not filings:** closes only; dividends/splits bases differ between the monthly and daily layers.")
    L.append("- **Sector baskets ≠ this book's names.** The tested energy/materials basket is large-cap oils, miners and "
             "chemicals; the tested gold/life-sciences basket is miners plus life-science tools — neither contains this book's "
             "E&P, mining or pharma names. Mapping them by sector is a PM judgement, marked in the Evidence column above, and "
             "the untested rows lean on the vol-normalised reading rather than on a stop test.")
    L.append("- **The 2022 commodity tape is the specific hazard:** commodity-cyclicals rose through the 2022 break, which is "
             "why the trailing stop hurt them in a window that helped everything else. A commodity-led drawdown is untested.")
    L.append("")
    L.append("**Re-test triggers.** Rerun `corr_regime.py`, `book_risk.py` and `stop_regime_rotation.py` when: the effective-bet "
             "count drifts below 2.0 on the trend window (concentration rising without a break), the book holds both blocs at "
             "≥25% each (the cross-rho becomes load-bearing and can then be measured live), a new drawdown supplies a third "
             "regime, or a rotation adds a sector whose placed stop was never tested.")
    L.append("")
    engine_stop, engine_risk, engine_why = _engine_settings()
    L.append("**Enforcement status — these are decisions of record, not rules the book runs yet.** The book's own trader "
             "(`~/Documents/finance-ai/pm_trader.py`) still carries its own settings and has no cluster or sector awareness:")
    L.append(f"- `TRAILING_STOP = {engine_stop}` applied to **every** position (the check is `cur <= high_water * "
             f"(1 - TRAILING_STOP)`), against the per-sector policy above. Its weekly brief prints a *"
             f"“{engine_stop:.0%} stop”* column per name and states the rationale as *“{engine_why}”*.")
    L.append(f"- `RISK_PER_NAME = {engine_risk}` nominal maximum per name, against the **{NAME_CAP_PCT:.0f}%** cap above "
             "(the cluster cap has no engine equivalent at all).")
    L.append("- Nothing reads this section: the policy binds the PM only once that file changes, which is one edit (per-sector "
             "stop, 10% name cap, cluster cap). Until then read the brief's stop column as the engine's rule, not this one.")
    L.append("")
    L.append(f"**The sharpest point.** The operative level is **{engine_stop:.0%}, and {engine_stop:.0%} has "
             f"never been tested on this book in either regime** — every measurement behind this section is at 15%. The engine's "
             "setting is also *looser* than the tested rule, so the '15% whips out compounders' preference is about the level, "
             "while the tested finding is about the sector: the same rule earned its keep on software/cyber and semis and lost "
             "it on commodity-cyclicals. The open choice is therefore a trading decision and it belongs to the PM: adopt the "
             f"per-sector policy in the engine, or record the uniform {engine_stop:.0%} as a deliberate exception and stop "
             "treating it as evidence-backed. This section is the standard; the engine is the divergence.")
    L.append("")
    return L


def main():
    today = date.today().isoformat()
    # load state
    if not os.path.exists(STATE_FILE):
        print(f"STATE missing: {STATE_FILE}")
        state = {}
        positions = []
        portfolio_meta = {}
    else:
        with open(STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
        # pm_portfolio.json schema: top-level has "portfolio" dict + "positions" list
        portfolio_meta = state.get("portfolio", {})
        positions = state.get("positions", [])
        if not isinstance(positions, list):
            # odd schema: positions under portfolio key
            positions = portfolio_meta.get("positions", []) if isinstance(portfolio_meta.get("positions"), list) else []

    # ticker index
    tmap, cmap, price_map, research_map = load_ticker_map()

    # compute book view
    cash = float(portfolio_meta.get("cash", 0) or 0)
    size = float(portfolio_meta.get("size", 1000000) or 1000000)
    benchmark = portfolio_meta.get("benchmark", "SPY")
    # performance for day P&L
    perf = state.get("performance", []) if isinstance(state.get("performance"),list) else []
    last_total = None
    prev_total = None
    if perf and len(perf) >= 1:
        last_total = perf[-1].get("total")
        if len(perf) >= 2:
            prev_total = perf[-2].get("total")
    # compute position market values using effective price
    pos_details = []
    total_mv_positions = 0.0
    total_cost = 0.0
    for p in positions:
        sym = str(p.get("symbol") or p.get("ticker") or p.get("name") or "").strip().upper()
        qty = p.get("qty", 0)
        entry = p.get("entry", 0)
        last_json = p.get("last", entry)
        cost_basis = p.get("cost_basis", qty*entry if entry else 0)
        # effective last: prefer company price: line
        eff_last = last_json
        price_raw = None
        company_price = None
        if sym in price_map:
            company_price, price_raw = price_map[sym]
            eff_last = company_price
        try:
            qty_f = float(qty)
            eff_last_f = float(eff_last) if eff_last is not None else 0
            entry_f = float(entry) if entry else 0
        except:
            qty_f = 0; eff_last_f = 0; entry_f = 0
        mv = qty_f * eff_last_f
        total_mv_positions += mv
        total_cost += float(cost_basis) if cost_basis else qty_f*entry_f
        # unrealized P&L
        unreal_pct = ((eff_last_f / entry_f - 1)*100) if entry_f else 0
        unreal_abs = mv - (float(cost_basis) if cost_basis else 0)
        # company link
        title = tmap.get(sym)
        company_link = f"[[{title}]]" if title else sym
        company_path = cmap.get(sym)
        # thesis note
        thesis_title = research_map.get(sym)
        # fallback: if company file missing, try research_map empty
        thesis_path = find_note_path(thesis_title) if thesis_title else None
        # if thesis not found via company research, try to find any note with ticker in name
        if not thesis_path and sym:
            cands = glob.glob(os.path.join(NOTES_DIR, f"*{sym}*.md"))
            if cands:
                # prefer TradingAgents or research
                cands.sort(key=lambda x: (0 if "TradingAgents" in x else 1, x))
                thesis_path = cands[0]
                thesis_title = os.path.splitext(os.path.basename(thesis_path))[0]
        kill_switches = get_invalidations(thesis_path) if thesis_path else []
        catalysts_note = get_catalysts_field(thesis_path) if thesis_path else []
        # Important Dates for this company
        imp_dates = get_important_dates_for(sym, title) if (sym or title) else []
        pos_details.append({
            "symbol": sym,
            "title": title,
            "company_link": company_link,
            "qty": qty_f,
            "entry": entry_f,
            "last_json": float(last_json) if last_json is not None else 0,
            "eff_last": eff_last_f,
            "price_raw": price_raw,
            "company_price": company_price,
            "cost_basis": float(cost_basis) if cost_basis else qty_f*entry_f,
            "mv": mv,
            "unreal_pct": unreal_pct,
            "unreal_abs": unreal_abs,
            "thesis_title": thesis_title,
            "thesis_path": thesis_path,
            "kill_switches": kill_switches,
            "catalysts_note": catalysts_note,
            "important_dates": imp_dates,
            "conviction": p.get("conviction"),
            "opened": p.get("opened"),
        })

    # sort details by mv desc for display + concentration
    pos_details.sort(key=lambda x: -x["mv"])

    total_value = cash + total_mv_positions
    cash_pct = (cash / total_value * 100) if total_value else 0
    invested_pct = 100 - cash_pct

    # day P&L
    day_pnl_abs = None
    day_pnl_pct = None
    if last_total is not None and prev_total is not None:
        try:
            day_pnl_abs = float(total_value) - float(prev_total)  # current vs previous perf total
            # alternative: last_total vs prev_total is recorded perf change
            day_pnl_abs_perf = float(last_total) - float(prev_total)
            day_pnl_pct = (float(last_total)/float(prev_total)-1)*100 if float(prev_total)!=0 else 0
        except:
            pass
    else:
        # fallback: vs size
        pass

    # concentration top-5
    top5 = pos_details[:5]
    top5_pct = sum(x["mv"] for x in top5) / total_value * 100 if total_value else 0

    # total unrealized
    total_unreal_abs = sum(x["unreal_abs"] for x in pos_details)
    total_unreal_pct = (total_unreal_abs / total_cost * 100) if total_cost else 0

    # build Portfolio.md
    lines = []
    # frontmatter
    lines.append("---")
    lines.append('type: "portfolio"')
    lines.append('generated: true')
    lines.append(f'last_updated: "{today}"')
    lines.append(f'cash_pct: {cash_pct:.2f}')
    lines.append(f'cash: {cash:.2f}')
    lines.append(f'positions: {len(pos_details)}')
    lines.append(f'total_value: {total_value:.2f}')
    lines.append(f'invested_pct: {invested_pct:.2f}')
    lines.append(f'benchmark: "{benchmark}"')
    lines.append(f'source: "pm_portfolio.json"')
    lines.append(f'portfolio_updated: "{portfolio_meta.get("updated","")}"')
    lines.append(f'risk_neff_stress: {NEFF_STRESS}')
    lines.append(f'risk_neff_trend: {NEFF_TREND}')
    lines.append(f'cluster_cap_pct: {CLUSTER_CAP_PCT:.0f}')
    lines.append(f'risk_policy_date: "{RISK_POLICY_DATE}"')
    lines.append("---")
    lines.append("")
    lines.append(f"# Portfolio — {portfolio_meta.get('name','Ryan PM Portfolio')} ({portfolio_meta.get('status','paper')})")
    lines.append("")
    lines.append(f"> **Last updated:** {today} · **Source:** `pm_portfolio.json` (updated {portfolio_meta.get('updated','—')}) · **Benchmark:** {benchmark} · **Horizon:** {portfolio_meta.get('horizon','annual')}")
    lines.append("")
    # caveat if no positions
    if not pos_details:
        lines.append("> ⚠️ No positions found in pm_portfolio.json — showing cash-only book. Schema dump below.")
        lines.append("")
        lines.append("## Raw state")
        lines.append("")
        lines.append("```json")
        try:
            lines.append(json.dumps(state, indent=2)[:4000])
        except:
            lines.append(str(state)[:4000])
        lines.append("```")
        lines.append("")
    # Book view
    lines.append("## Book view")
    lines.append("")
    lines.append(f"- **Total value:** ${total_value:,.2f}  (cash ${cash:,.2f} = {cash_pct:.1f}%, invested ${total_mv_positions:,.2f} = {invested_pct:.1f}%)")
    lines.append(f"- **Size (target):** ${size:,.0f}")
    # P&L vs perf
    if perf and last_total is not None:
        ret_since_inception = (total_value / size - 1)*100 if size else 0
        # use last perf pct_vs_spy if available
        spy_vs = perf[-1].get("pct_vs_spy")
        spy_txt = f"{spy_vs:+.2f}% vs SPY" if spy_vs is not None else "n/a vs SPY"
        lines.append(f"- **Return since inception ({portfolio_meta.get('started','')}):** {ret_since_inception:+.2f}% · {spy_txt} (perf entry {last_total:,.0f} on {perf[-1].get('date','')})")
        if day_pnl_abs is not None:
            lines.append(f"- **Day / week P&L (vs prev perf {prev_total:,.0f}):** ${day_pnl_abs:+,.2f} ({day_pnl_pct:+.2f}% perf) — current mark ${total_value:,.2f} vs last perf ${last_total:,.0f}")
        else:
            lines.append(f"- **Day P&L:** n/a (only one perf point)")
    else:
        lines.append(f"- **P&L:** no performance history — total ${total_value:,.2f}")
    lines.append(f"- **Total cost basis (positions):** ${total_cost:,.2f}")
    lines.append(f"- **Unrealized P&L (all positions, mark vs cost):** ${total_unreal_abs:+,.2f} ({total_unreal_pct:+.2f}%) — uses company `price:` line where available, else `pm_portfolio.json: last`")
    # concentration
    lines.append(f"- **Concentration top-5:** {top5_pct:.1f}% of book")
    if top5:
        lines.append("")
        lines.append("  | # | Ticker | Company | Mkt Val | Wt% |")
        lines.append("  |---|---|---|---:|---:|")
        for i, x in enumerate(top5, 1):
            wt = x["mv"]/total_value*100 if total_value else 0
            lines.append(f"  | {i} | {x['symbol']} | {x['company_link']} | ${x['mv']:,.0f} | {wt:.1f}% |")
    lines.append("")
    # if perf exists, show spark
    if perf:
        lines.append(f"- **Performance log:** {len(perf)} points; latest {perf[-1].get('date','')} total ${perf[-1].get('total',0):,.0f}, cash ${perf[-1].get('cash',0):,.0f}, positions ${perf[-1].get('positions_value',0):,.0f}")
        lines.append("")
    lines.append("---")
    lines.append("")
    # risk rules — the decisions, sized on the stress number, with a live read-out
    lines.extend(risk_rules_block(pos_details, total_value))
    lines.append("---")
    lines.append("")
    # Positions table summary
    lines.append(f"## Positions — {len(pos_details)} names")
    lines.append("")
    if pos_details:
        lines.append("| # | Ticker | Company | Qty | Entry | Last (json) | Price: (company) | Mkt Val (mark) | Cost | Unreal % | Thesis |")
        lines.append("|---|---|---|---:|---:|---:|---|---:|---:|---:|---|")
        for i, x in enumerate(pos_details, 1):
            price_disp = f"{x['company_price']:.2f}" if x['company_price'] is not None else "—"
            if x['price_raw']:
                # keep raw in tooltip? just price
                pass
            thesis_link = f"[[{x['thesis_title']}]]" if x['thesis_title'] else "—"
            # conviction
            lines.append(f"| {i} | **{x['symbol']}** | {x['company_link']} | {x['qty']:,.0f} | {x['entry']:.2f} | {x['last_json']:.2f} | {price_disp} | ${x['mv']:,.0f} | ${x['cost_basis']:,.0f} | {x['unreal_pct']:+.2f}% | {thesis_link} |")
        lines.append("")
    # Per-position detail
    lines.append("---")
    lines.append("")
    lines.append("## Position detail — thesis · kill-switches · catalysts")
    lines.append("")
    if not pos_details:
        lines.append("_No positions to detail._")
        lines.append("")
    for x in pos_details:
        lines.append(f"### {x['symbol']} — {x['company_link']}")
        lines.append("")
        lines.append(f"- **Qty:** {x['qty']:,.0f} · **Entry:** ${x['entry']:.2f} · **Cost basis:** ${x['cost_basis']:,.2f}")
        lines.append(f"- **Last (json):** ${x['last_json']:.2f} · **Price: (company node):** {x['price_raw'] or '— (no price: line)'} · **Mark used:** ${x['eff_last']:.2f}")
        lines.append(f"- **Market value (mark):** ${x['mv']:,.2f} ({x['mv']/total_value*100:.1f}% of book) · **Unrealized:** ${x['unreal_abs']:+,.2f} ({x['unreal_pct']:+.2f}%)")
        if x['conviction'] is not None:
            lines.append(f"- **Conviction:** {x['conviction']} · **Opened:** {x['opened'] or '—'}")
        # thesis
        if x['thesis_title']:
            # check if note exists
            note_exists = "✓" if x['thesis_path'] and os.path.exists(x['thesis_path']) else "✗ missing"
            lines.append(f"- **Thesis note:** [[{x['thesis_title']}]] {note_exists}")
        else:
            lines.append(f"- **Thesis note:** — (no research: link on company node)")
        # kill-switches
        if x['kill_switches']:
            lines.append(f"- **Kill-switches (invalidations):**")
            for ks in x['kill_switches']:
                # truncate very long
                ks_short = ks[:220]
                lines.append(f"  - {ks_short}")
        else:
            if x['thesis_path']:
                lines.append(f"- **Kill-switches:** — (none in linked note's `invalidations: []`)")
            else:
                lines.append(f"- **Kill-switches:** — (no thesis note to read)")
        # catalysts from note + Important Dates
        has_cats = False
        if x['catalysts_note']:
            lines.append(f"- **Catalysts (note frontmatter):** {', '.join(x['catalysts_note'])}")
            has_cats = True
        if x['important_dates']:
            lines.append(f"- **Next catalysts (Important Dates):**")
            for d in x['important_dates'][:5]:
                # link to file
                fname = os.path.splitext(os.path.basename(d['path']))[0]
                lines.append(f"  - {d['date']} — {d['event']} [[{fname}]]")
            has_cats = True
        if not has_cats:
            lines.append(f"- **Next catalysts:** — (no Important Dates for this company; no catalysts: in note)")
        # review cadence + layer-3 verdict (from thesis note frontmatter)
        rv = None
        if x['thesis_path'] and os.path.exists(x['thesis_path']):
            fm_txt, _ = get_fm(x['thesis_path'])
            rd = re.search(r'review_date:\s*"([^"]*)"', fm_txt)
            vd = re.search(r'verdict:\s*"([^"]*)"', fm_txt)
            vdd = re.search(r'verdict-date:\s*"([^"]*)"', fm_txt)
            rv = (rd.group(1) if rd else '', vd.group(1) if vd else '', vdd.group(1) if vdd else '')
        if rv and rv[0]:
            lines.append(f"- **Review:** next review {rv[0]} · **Verdict:** {rv[1] or '—'} (as of {rv[2] or today})")
        else:
            lines.append(f"- **Review:** — (no review_date in thesis note)")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Notes & caveats")
    lines.append("")
    asof = []
    for x in pos_details:
        m = re.search(r"as-of (\d{4}-\d{2}-\d{2})", x.get("price_raw") or "")
        if m:
            asof.append(m.group(1))
    if asof:
        if len(set(asof)) == 1:
            asof_txt = f" Company price as-of dates: all `as-of {asof[0]}`."
        else:
            asof_txt = f" Company price as-of dates: `{min(asof)}` to `{max(asof)}` ({len(set(asof))} distinct) from price_stamp.py."
    else:
        asof_txt = " Company price as-of dates: none stamped (no `as-of` in the `price:` lines)."
    lines.append(f"- Prices: `price:` frontmatter used where present ({len([x for x in pos_details if x['company_price'] is not None])}/{len(pos_details)} names had a price: line); otherwise `pm_portfolio.json: last`.{asof_txt}")
    lines.append(f"- Thesis resolution: via Companies ticker index ({len(tmap)} tickers indexed). Unresolved tickers show bare symbol (no company node).")
    thesis_ok = len([x for x in pos_details if x['thesis_path'] and os.path.exists(x['thesis_path'])])
    lines.append(f"- Thesis notes linked: {thesis_ok}/{len(pos_details)} resolved to a file in Notes/ (research: first link).")
    ks_count = len([x for x in pos_details if x['kill_switches']])
    lines.append(f"- Kill-switches: {ks_count}/{len(pos_details)} positions have non-empty `invalidations:` in their thesis note; empty means the note has no explicit kill-switch (common for TradingAgents notes which leave invalidations: []).")
    imp_count = len([x for x in pos_details if x['important_dates']])
    lines.append(f"- Important Dates: {imp_count}/{len(pos_details)} positions have a dated catalyst in Important Dates/ (only CAPR/NVDA/Moderna dated events exist in the vault).")
    # closed / cash notes
    closed = state.get("closed_positions", [])
    lines.append(f"- Closed positions: {len(closed) if isinstance(closed,list) else 0} (not shown).")
    lines.append(f"- Never fabricates P&L: all $ and % from pm_portfolio.json or company price: lines. No yfinance live fetch.")
    lines.append(f"- Regenerated by `portfolio_node.py` — rerun to refresh after pm_portfolio.json or company price: updates. Do not hand-edit Portfolio.md.")
    lines.append(f"- The **Risk rules** section is rendered from the policy constants at the top of `portfolio_node.py` (NEFF_STRESS {NEFF_STRESS}, CLUSTER_CAP_PCT {CLUSTER_CAP_PCT:.0f}, stop policy by sector). Change those, not this file; the measured basis is `book_risk.py` (regime block) + `stop_regime_rotation.py` in `~/Documents/finance-ai`.")
    lines.append("")

    # write
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"WROTE {OUTPUT} — {len(lines)} lines, {len(pos_details)} positions, total ${total_value:,.2f}, unreal ${total_unreal_abs:+,.2f} ({total_unreal_pct:+.2f}%)")
    # stats for caller
    for x in pos_details:
        print(f" {x['symbol']:4} {x['company_link']:30} qty {x['qty']:,.0f} entry {x['entry']:.2f} mark {x['eff_last']:.2f} mv {x['mv']:,.0f} pnl {x['unreal_pct']:+.2f}% thesis [[{x['thesis_title']}]] ks={len(x['kill_switches'])} imp={len(x['important_dates'])}")

if __name__ == "__main__":
    main()
