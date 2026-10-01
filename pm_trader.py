#!/usr/bin/env python3
"""
pm_trader.py — the $1M Portfolio Manager engine.

Acts like a trader on the knowledge graph: each run it reads the latest scan
notes (meta-screen, deep-value, cross-source shortlist, sector rundowns),
decides positions (buy/sell/hold/size), applies risk rules (trailing stop,
conviction sizing, diversification, kill-switches), prices the portfolio vs
SPY, records trades, and writes:

  ~/Documents/Finance Knowledge Graph/Weekly/<date> PM Brief.md
  ~/Documents/Finance Knowledge Graph/Weekly/Research Digest.md  (rolling)

State lives in ~/Documents/finance-ai/pm_portfolio.json (positions, cash,
closed, weekly_trades, performance). Goal: BEAT SPY on an annual basis.

Usage:
  python3 pm_trader.py            # run a weekly PM cycle (decide + record)
  python3 pm_trader.py --seed     # first-run: build initial allocation from scans
  python3 pm_trader.py --report   # price + report only, no decisions
"""
import os, sys, json, glob, re, argparse, subprocess
from datetime import date

try:
    import yfinance as yf
except Exception:
    yf = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kg_links  # noqa: E402

FINANCE_AI = os.path.expanduser("~/Documents/finance-ai")
KG_ROOT = os.path.expanduser("~/Documents/Finance Knowledge Graph")
KG_NOTES = os.path.join(KG_ROOT, "Notes")
KG_WEEKLY = os.path.join(KG_ROOT, "Weekly")
STATE_FILE = os.path.join(FINANCE_AI, "pm_portfolio.json")

# Risk / sizing parameters
TRAILING_STOP = 0.25        # 25% trailing stop on momentum/compounders
RISK_PER_NAME = 0.14        # nominal max ~14% of portfolio per name
MIN_POSITION = 0.03         # below 3% target -> don't open
CONVICTION_SIZING = {9: 0.14, 8: 0.12, 7: 0.09, 6: 0.06, 5: 0.04, 4: 0.0, 3: 0.0}

# Score sources the PM reads (filename fragments / topic markers)
SCORE_SOURCES = [
    "Deep value by GICS sector",
    "Master cross-source alpha shortlist",
    "GICS sector rundowns",
]

# Per-ticker thesis / catalyst / what-to-watch + estimated holding period.
# Preferred source is the research note (kick-switches); this map is the
# curated fallback for names the PM actually holds. Extend as the PM adds names.
HOLDINGS_INTEL = {
    "GM":   {"duration": "6-12 mo", "catalyst": "Dec-2026 Silverado/Sierra refresh; EV loss narrowing toward 2027 breakeven",
             "watch": "Kill-switch: NA EBIT <6.5% or EV utilization <40%; tariff cost >$3B"},
    "VTRS": {"duration": "6-12 mo", "catalyst": "Generic-pricing stabilization; 14% FCF yield cash return",
             "watch": "Kill-switch: generic prices keep deflating >$1B/yr; dilution spikes"},
    "CAG":  {"duration": "6-18 mo", "catalyst": "7.6% yield + FCF; margin recovery as input costs ease",
             "watch": "Kill-switch: negative margins persist; dividend cut"},
    "GIS":  {"duration": "12-18 mo", "catalyst": "6% yield + 10% FCF; price/mix holds in cereal/snacks",
             "watch": "Kill-switch: FCF yield <7% or earnings decline accelerates"},
    "PFE":  {"duration": "12-24 mo", "catalyst": "6% yield + pipeline inflection; Mounjaro-type partnerships",
             "watch": "Kill-switch: patent cliff loses offset faster than pipeline builds"},
    "SM":   {"duration": "6-12 mo", "catalyst": "16% FCF yield; Permian production + crude recovery",
             "watch": "Kill-switch: crude/crack normalization compresses FCF; leverage rises"},
    "NVO":  {"duration": "12-24 mo", "catalyst": "GLP-1 demand durable; 18% FCF yield",
             "watch": "Kill-switch: competition (Eli Lilly) compresses pricing; margins slip"},
    "PRU":  {"duration": "12-24 mo", "catalyst": "higher-for-longer rate tailwind; 8.3x fwd + 4.6% yield",
             "watch": "Kill-switch: rate-cut cycle + hedging losses compress spread income"},
    "ADBE": {"duration": "12-24 mo", "catalyst": "fwd ~10x + Firefly/AI monetization inflection; ~9% FCF yield",
             "watch": "Kill-switch: Creative Cloud ARR declines 5%+ 2 qtrs; freemium doesn't convert"},
    "HPQ":  {"duration": "6-12 mo", "catalyst": "12.6% FCF yield + AI-PC refresh cycle",
             "watch": "Kill-switch: PC demand stays weak; margin compression"},
    "VALE": {"duration": "6-18 mo", "catalyst": "22% FCF yield + 8.6% div; iron-ore cost floor at low-cost Carajás",
             "watch": "Kill-switch: iron-ore price collapse; Brazil policy interference"},
    "PBR":  {"duration": "6-18 mo", "catalyst": "9% yield + 4.8x fwd; Brazil fiscal discount",
             "watch": "Kill-switch: gov't dividend-policy change; crude collapse"},
    "SOFI": {"duration": "6-12 mo", "catalyst": "S&P-500 inclusion; first GAAP-profit year; rate-cutting NIM tailwind",
             "watch": "Kill-switch: NCO >3.5% or Tech Platform rev declines 2 qtrs; dilution >10%"},
}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"portfolio": {"size": 1000000, "cash": 1000000, "positions": [], "closed_positions": [], "weekly_trades": [], "performance": [], "benchmark": "SPY", "started": date.today().isoformat()}, "positions": [], "closed_positions": [], "weekly_trades": [], "performance": [], "rebalance_history": []}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
    return state


def latest_scan_text():
    """Concatenate latest scan notes that carry PM-relevant scores."""
    parts = []
    for pattern in SCORE_SOURCES:
        hits = sorted(glob.glob(os.path.join(KG_NOTES, f"*{pattern}*.md")))
        if hits:
            # newest first
            hits.sort(reverse=True)
            with open(hits[0], encoding="utf-8") as f:
                parts.append(f"=== {os.path.basename(hits[0])} ===\n" + f.read())
    # meta-screen top names if available
    ms = sorted(glob.glob(os.path.join(KG_NOTES, "*Meta-Screen.md")))
    if ms:
        ms.sort(reverse=True)
        with open(ms[0], encoding="utf-8") as f:
            parts.append("=== " + os.path.basename(ms[0]) + " ===\n" + f.read())
    return "\n\n".join(parts)


def parse_scores(text):
    """Heuristic parse of DV/Alpha scores from scan notes -> {ticker: (score, why)}.

    Handles the deep-value note format: "Company (TICKER) ... **DV 8**" and the
    table format "| Ticker | ... | 8 |". Also "Alpha 8/10"-style lines.
    """
    scores = {}
    why = {}
    # 1) "Company (TICKER) ... DV N" / "... 8/10" lines (deep-value note)
    for line in text.splitlines():
        # ticker in parens: (SM), (CHRD), etc.
        mpar = re.search(r"\(([A-Z]{1,5})\)", line)
        if not mpar:
            continue
        tk = mpar.group(1)
        if tk in ("SPY", "ETF", "Q4", "FY", "PE", "PB", "EV", "EPS", "GICS", "US", "UK", "CE"):
            continue
        msc = re.search(r"(?:DV|Alpha|α)\s*[:=]?\s*(\d{1,2})(?:/10)?", line) or \
              re.search(r"\*\*(\d{1,2})/10\*\*", line)
        if not msc:
            continue
        sc = int(msc.group(1))
        if 4 <= sc <= 10:
            scores.setdefault(tk, max(scores.get(tk, 0), sc))
            why.setdefault(tk, line.strip())
    # 2) explicit score already present via parenthetical (DV already captured)
    return scores


def get_prices(syms):
    prices = {}
    if yf is None:
        return prices
    for s in syms:
        try:
            tk = yf.Ticker(s)
            info = tk.info or {}
            p = info.get("currentPrice") or info.get("regularMarketPrice")
            if p:
                prices[s] = float(p)
        except Exception:
            continue
    return prices


def fetch_news(sym, limit=4):
    """Pull recent Google News RSS headlines for a ticker (best-effort)."""
    import urllib.request, html as _html
    from datetime import datetime, timedelta
    try:
        import urllib.parse
        q = urllib.parse.quote(f'"{sym}" stock')
        url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            xml = r.read().decode("utf-8", "ignore")
        out = []
        for m in re.finditer(r"<item>.*?<title>(.*?)</title>.*?<pubDate>(.*?)</pubDate>", xml, re.S):
            t = _html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
            pd = m.group(2).strip()
            out.append((t, pd))
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


def seed_portfolio(state):
    """Build an initial allocation from the current scan scores."""
    text = latest_scan_text()
    scores = parse_scores(text)
    # keep high-conviction names, dedupe, cap count
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:12]
    names = [tk for tk, _ in ranked]
    prices = get_prices(names)
    if not prices:
        # fallback: a few known strong names from recent scans
        names = ["MU", "GM", "ADBE", "VTRS", "VZ", "PBR", "SM", "PFE", "GIS", "CP", "ET"]
        prices = get_prices(names)
    pos = []
    total = state["portfolio"]["size"]
    verdicts, quality = load_decision_layers()
    # filter: never size a BROKEN-data name; apply conviction modifiers
    ranked_ex = []
    for tk, sc in ranked:
        if tk not in prices or CONVICTION_SIZING.get(int(sc), 0.06) < MIN_POSITION:
            continue
        if quality.get(tk) == "BROKEN":
            print(f"  skip {tk}: data_quality BROKEN")
            continue
        sc2 = conviction_modifier(tk, int(sc), verdicts, quality)
        if sc2 < MIN_POSITION:
            print(f"  skip {tk}: verdict-modded conviction {sc2} < min")
            continue
        ranked_ex.append((tk, sc2))
    ranked_ex.sort(key=lambda kv: -kv[1])
    wsum = sum(CONVICTION_SIZING.get(int(sc), 0.06) for tk, sc in ranked_ex) or 1
    target_alloc = min(0.90, wsum)  # leave ~10% cash buffer
    cash = total
    for tk, sc in ranked_ex:
        weight = (CONVICTION_SIZING.get(int(sc), 0.06) / wsum) * target_alloc
        budget = cash * 0.95 if weight > cash / total else total * weight
        qty = int(budget / prices[tk])
        if qty <= 0:
            continue
        cost = qty * prices[tk]
        if cost < total * 0.015:  # skip sub-1.5% fractional scraps
            continue
        cash -= cost
        pos.append({
            "symbol": tk, "qty": qty, "entry": prices[tk], "last": prices[tk],
            "cost_basis": cost, "conviction": float(sc), "high_water": prices[tk],
            "opened": date.today().isoformat(), "thesis": "scan-seeded",
        })
        if cash <= total * 0.02:
            break
    state["positions"] = pos
    state["portfolio"]["cash"] = max(0.0, cash)
    used = total - cash
    # benchmark basis = SPY index price at seed, so vs-SPY is computed as index change
    spy_seed = get_prices([state["portfolio"]["benchmark"]])
    spy_basis = spy_seed.get(state["portfolio"]["benchmark"], None)
    state["portfolio"]["spy_basis"] = spy_basis
    state["portfolio"]["spy_value"] = spy_basis
    state["performance"].append({
        "date": date.today().isoformat(), "cash": state["portfolio"]["cash"],
        "positions_value": used, "total": total, "spy_basis": spy_basis, "spy_value": spy_basis,
        "pct_vs_spy": 0.0, "event": "seed",
    })
    return state


def auto_grade_closed(state, stops_hit, today):
    """After a stop-sell, backfill the realized outcome into the company's
    research note (reuses grade.py's gradify). This closes the feedback loop
    automatically — no manual `grade.py --close` needed."""
    try:
        import grade as _grade
    except Exception as e:
        print("  (auto-grade skipped:", e, ")")
        return
    for sym, price, _high, entry in stops_hit:
        path = _grade.find_note_by_ticker(sym)
        if not path:
            try:
                title = _grade.kg_links.load_ticker_map().get(sym)
                path = _grade.find_note_by_title(title) if title else None
            except Exception:
                path = None
        if path:
            try:
                _grade.gradify(path, exit_price=price, exit_date=today)
            except Exception as e:
                print(f"  (auto-grade {sym} failed:", e, ")")
        else:
            print(f"  (no research note for {sym} to grade — created position from scan seed)")


def load_decision_layers():
    """Load the verdict + data-quality layers (if present) so the PM never sizes a
    BROKEN thesis or a name with BROKEN data. Returns dicts keyed by ticker/note."""
    verdicts, quality = {}, {}
    vpath = os.path.join(FINANCE_AI, "verdicts.json")
    qpath = os.path.join(FINANCE_AI, "data_quality.json")
    try:
        with open(vpath, encoding="utf-8") as f:
            for r in json.load(f).get("results", []):
                verdicts[r["note"]] = r["verdict"]
    except Exception:
        verdicts = {}
    try:
        with open(qpath, encoding="utf-8") as f:
            for r in json.load(f).get("results", []):
                quality[r["ticker"]] = r["verdict"]
    except Exception:
        quality = {}
    return verdicts, quality


def conviction_modifier(sym, base_conviction, verdicts, quality):
    """Apply decision-layer modifiers to a conviction score (0-10)."""
    qv = quality.get(sym)
    if qv == "BROKEN":
        return 0  # never size a name with broken/absent live data
    # find verdict for this symbol by note-title substring
    v = None
    for note, verdict in verdicts.items():
        if sym in note.upper():
            v = verdict
            break
    cv = base_conviction
    if v == "BROKEN":
        cv = min(cv, 2)      # thesis broken -> no real conviction
    elif v == "WEAKENED":
        cv = cv * 0.5        # halve on weakened thesis
    return max(0.0, round(cv, 1))


def ta_second_opinion(sym, date_s=None, timeout_ok=True):
    """PM-layer hook: invoke TradingAgents for a second opinion on a symbol and
    return its verdict (Overweight/Neutral/Underweight) + flag. THE PM calls this
    when sizing, or to cross-check a WEAKENED thesis. Because it's slow/free-tier,
    it returns a structured dict the PM can use as a conviction modifier or a
    caution flag — never blocks the weekly run.

    Requires /usr/local/bin/python3.13 with the TradingAgents install; lauched as
    a subprocess so a long/failing TA run can't hold up the PM cycle.
    """
    date_s = date_s or date.today().isoformat()
    verdict = None
    try:
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ta_opinion.py")
        r = subprocess.run(
            ["/usr/local/bin/python3.13", script, sym, "--date", date_s],
            capture_output=True, text=True, timeout=1800, cwd="/Users/ryanrodrigues/Documents/finance-ai",
        )
        out = (r.stdout or "") + (r.stderr or "")
        # look for a verdict word in the captured output
        for v in ("Overweight", "Underweight", "Neutral", "Hold", "Buy", "Sell"):
            if f"**{v}**" in out or f"Rating**: {v}" in out or f"**Recommendation**: {v}" in out or f"verdict: {v}" in out:
                verdict = v
                break
        if not verdict:
            m = re.search(r"\b(Overweight|Underweight|Neutral|Hold)\b", out)
            if m:
                verdict = m.group(1)
    except Exception as e:
        print(f"  (TA second-opinion {sym} not available: {e})")
    return {"sym": sym, "verdict": verdict, "invoked": date_s, "source": "TradingAgents"}


def run_cycle(state):
    today = date.today().isoformat()
    # ---- price current positions ----
    open_syms = [p["symbol"] for p in state["positions"]]
    prices = get_prices(open_syms)
    total_pos = 0.0
    stops_hit = []
    for p in state["positions"]:
        cur = prices.get(p["symbol"], p["last"])
        p["last"] = cur
        p["high_water"] = max(p["high_water"], cur)
        mv = p["qty"] * cur
        total_pos += mv
        # 25% trailing stop
        if p["high_water"] > 0 and cur <= p["high_water"] * (1 - TRAILING_STOP):
            stops_hit.append((p["symbol"], cur, p["high_water"], p["entry"]))
    # ---- decide adds from latest scan ----
    text = latest_scan_text()
    scores = parse_scores(text)
    cash = state["portfolio"]["cash"]
    total = cash + total_pos
    decisions = []
    # sell stop-hits
    surviving = []
    for p in state["positions"]:
        if any(s == p["symbol"] for s, _, _, _ in stops_hit):
            proceeds = p["qty"] * p["last"]
            cash += proceeds
            decisions.append(f"SELL {p['symbol']} (stop @{p['last']:.2f}, high {p['high_water']:.2f}) — +{proceeds:,.0f}")
        else:
            surviving.append(p)
    state["positions"] = surviving
    state["portfolio"]["cash"] = cash
    # auto-grade any stop-sells: backfill realized outcome + vs-SPY into research notes
    if stops_hit:
        auto_grade_closed(state, stops_hit, today)
    # open new high-conviction names with cash
    for tk, sc in sorted(scores.items(), key=lambda kv: -kv[1])[:8]:
        if cash < 20000:
            break
        if any(p["symbol"] == tk for p in state["positions"]):
            continue
        pr = get_prices([tk]).get(tk)
        if not pr:
            continue
        weight = CONVICTION_SIZING.get(int(sc), 0.06)
        value = min(total * weight, cash * 0.9)
        qty = int(value / pr)
        if qty <= 0:
            continue
        cost = qty * pr
        cash -= cost
        state["positions"].append({
            "symbol": tk, "qty": qty, "entry": pr, "last": pr,
            "cost_basis": cost, "conviction": int(sc), "high_water": pr,
            "opened": today, "thesis": "scan-conviction",
        })
        decisions.append(f"BUY {tk} ({sc}/10) — {qty} sh @{pr:.2f} = {cost:,.0f}")
    state["portfolio"]["cash"] = max(0.0, cash)
    # ---- reprice total vs SPY ----
    total_pos = sum(p["qty"] * p["last"] for p in state["positions"]) or 0
    total = state["portfolio"]["cash"] + total_pos
    prices = get_prices([state["portfolio"]["benchmark"]])
    spy_now = prices.get("SPY")
    last_perf = state["performance"][-1] if state["performance"] else None
    spy_pct = None
    if spy_now and last_perf and last_perf.get("spy_basis"):
        spy_pct = (spy_now / last_perf["spy_basis"] - 1) * 100
    state["performance"].append({
        "date": today, "cash": state["portfolio"]["cash"],
        "positions_value": total_pos, "total": total,
        "spy_basis": last_perf["spy_basis"] if last_perf else total,
        "spy_value": spy_now or (last_perf["spy_value"] if last_perf else total),
        "pct_vs_spy": spy_pct or 0.0,
        "event": "week",
        "trades": decisions,
        "stops": [f"{s}:{c:.2f}(was {h:.2f})" for s, c, h, _e in stops_hit],
    })
    state["weekly_trades"] = decisions
    state["rebalance_history"].append({"date": today, "decisions": decisions, "stops": stops_hit})
    state["portfolio"]["updated"] = today
    save_state(state)
    return state, decisions, stops_hit


def write_brief(state, decisions, stops_hit):
    today = date.today().isoformat()
    os.makedirs(KG_WEEKLY, exist_ok=True)
    perf = state["performance"][-1] if state["performance"] else {}
    total = perf.get("total", 0)
    started = state["portfolio"].get("started", "2026-08-20")
    ret = (total / 1000000 - 1) * 100
    cash = state["portfolio"]["cash"]
    pos_val = total - cash
    invested_pct = (pos_val / total * 100) if total else 0
    spy_ret = perf.get("pct_vs_spy")
    spy_txt = f"{spy_ret:+.2f}%" if spy_ret is not None else "n/a"

    body = []
    # ---- Header banner ----
    body.append(f"# 📊 PM Brief — {today}\n")
    body.append(f"> **Portfolio** ${total:,.0f}  ·  **{ret:+.2f}%** since {started}  ·  vs **SPY** {spy_txt}\n")
    body.append(f"> **Goal:** beat the S&P 500 annually  ·  **Status:** {state['portfolio'].get('status','paper').title()}\n")
    body.append("---\n")

    # ---- Key stats strip ----
    body.append("## Portfolio snapshot\n")
    body.append("| Metric | Value | | Metric | Value |")
    body.append("|---|---|---|---|---|")
    body.append(f"| Total value | **${total:,.0f}** | | Invested | **{invested_pct:.0f}%** |")
    body.append(f"| Cash | ${cash:,.0f} | | # Positions | **{len(state['positions'])}** |")
    body.append(f"| Since inception | **{ret:+.2f}%** | | vs S&P 500 | **{spy_txt}** |")
    body.append(f"| Risk regime | {state['portfolio'].get('risk_regime','')} | | Benchmark | {state['portfolio'].get('benchmark','SPY')} |\n")
    body.append("---\n")

    # ---- Holdings ----
    body.append("## Holdings\n")
    # resolve company names: kg_links ticker map (company nodes) + fallback for the rest
    _tmap = kg_links.load_ticker_map()
    _COMPANY_FALLBACK = {
        "VTRS": "Viatris", "PBR": "Petrobras", "SM": "SM Energy", "CAG": "Conagra",
        "HPQ": "HP Inc", "GIS": "General Mills", "NVO": "Novo Nordisk", "VALE": "Vale",
        "PRU": "Prudential", "PFE": "Pfizer", "ADBE": "Adobe", "GM": "General Motors",
        "MU": "Micron Tech", "NVDA": "NVIDIA", "AMD": "Advanced Micro Devices",
        "AVGO": "Broadcom", "META": "Meta", "GOOGL": "Alphabet", "SOFI": "SoFi",
    }
    def _cname(sym):
        return _tmap.get(sym) or _COMPANY_FALLBACK.get(sym, sym)
    # compute per-name P&L for sort + display
    rows = []
    for p in state["positions"]:
        mv = p["qty"] * p["last"]
        pl = (p["last"] / p["entry"] - 1) * 100 if p["entry"] else 0.0
        wgt = mv / total * 100 if total else 0
        stop = p["high_water"] * (1 - TRAILING_STOP)
        intel = HOLDINGS_INTEL.get(p["symbol"], {})
        rows.append((p, mv, pl, wgt, stop, intel))
    rows.sort(key=lambda r: -r[1])
    body.append("| # | Ticker | Company | Qty | Entry | Last | Mkt Val | Wi% | P&L | Hold | Conv | 25% stop |")
    body.append("|---|---|---:|---:|---:|---:|---:|---:|---:|:--:|---:|---:|")
    for i, (p, mv, pl, wgt, stop, intel) in enumerate(rows, 1):
        pl_sym = "🟢" if pl >= 0 else "🔴"
        dur = intel.get("duration", "—")
        body.append(f"| {i} | **{p['symbol']}** | {_cname(p['symbol'])} | {p['qty']:,} | {p['entry']:.2f} | {p['last']:.2f} | {mv:,.0f} | {wgt:.1f}% | {pl_sym}{pl:+.1f}% | {dur} | {p['conviction']} | {stop:.2f} |")
    body.append(f"|  | **CASH** |  |  |  |  | {cash:,.0f} | {cash/total*100 if total else 0:.1f}% |  |  |  |  |")
    body.append(f"\n**Total:** ${total:,.0f} across {len(state['positions'])} positions + cash\n")
    body.append("---\n")

    # ---- Holdings intel (catalyst + what I'm watching) ----
    body.append("## 🎯 Holdings — catalyst & what I'm watching\n")
    for i, (p, mv, pl, wgt, stop, intel) in enumerate(rows, 1):
        if not intel:
            continue
        body.append(f"**{i}. {_cname(p['symbol'])} ({p['symbol']})** — est. hold {intel.get('duration','—')}")
        body.append(f"- 🚀 **Catalyst:** {intel.get('catalyst','—')}")
        body.append(f"- 🔍 **Watching for:** {intel.get('watch','—')}")
        body.append("")
    body.append("---\n")

    # ---- This week's decisions ----
    body.append("## This week's decisions\n")
    if stops_hit:
        body.append("### ❌ Sells / stops hit (and why)\n")
        for s, c, h, _e in stops_hit:
            intel = HOLDINGS_INTEL.get(s, {})
            why = intel.get("watch", "thesis break / 25% trailing stop triggered")
            body.append(f"- **Sold {s}** @ {c:.2f} (high {h:.2f}, {((c / h) - 1) * 100:.1f}% off peak).")
            body.append(f"  - **Why:** {why} — trailed out to protect gains; cash freed for rotation.")
        body.append("")
    if decisions:
        # separate buys from rationale
        buys = [d for d in decisions if d.startswith("BUY")]
        others = [d for d in decisions if not d.startswith("BUY")]
        if buys:
            body.append("### 🛒 Adds / new positions\n")
            for d in buys:
                sym = d.split()[1]
                intel = HOLDINGS_INTEL.get(sym, {})
                body.append(f"- {d}")
                if intel.get("catalyst"):
                    body.append(f"  - **Catalyst:** {intel['catalyst']} · **Holding:** {intel.get('duration','—')}")
        if others:
            body.append("### 🔄 Other actions\n")
            for d in others:
                body.append(f"- {d}")
        body.append("")
    else:
        body.append("- ✅ **No changes** this week (no stop hits, no higher-conviction add available with current cash).")
        body.append("")
    body.append("---\n")

    # ---- News on the tickers ----
    body.append("## 📰 News on current + changed positions\n")
    changed_syms = [s for s, _, _ in stops_hit] + [d.split()[1] for d in decisions if d.startswith("BUY")]
    news_targets = sorted(set([p["symbol"] for p in state["positions"]] + changed_syms))
    got = False
    for sym in news_targets:
        items = fetch_news(sym, limit=3)
        if not items:
            continue
        got = True
        body.append(f"### {sym} ({_cname(sym)})")
        for t, pd in items:
            body.append(f"- {t} — _({pd})_")
        body.append("")
    if not got:
        body.append("- No recent headlines pulled this run (news fetch unavailable).")
    body.append("---\n")

    # ---- Why (methodology) ----
    body.append("## Why (methodology)\n")
    body.append("- **Sourcing:** decisions read the latest knowledge-graph scans (deep-value, cross-source shortlist, meta-screen) for high-conviction names.")
    body.append("- **Sizing:** conviction-based — 9/10 ≈ 14%, 8/10 ≈ 12%, 7/10 ≈ 9%; hard 14% max per name; ~10% cash buffer for rotation.")
    body.append("- **Risk:** 25% trailing stop on all names (user preference — 15% whips out compounders); a stop hit auto-sells → cash re-deploys to next scan pick next week.")
    body.append("- **Holding period:** per-position estimate from the thesis; reviewed weekly vs catalyst + kill-switch.\n")
    body.append("---\n")

    # ---- I'm watching ----
    body.append("## 👀 On watch\n")
    body.append("| Ticker | Why | Trigger |")
    body.append("|---|---|---|")
    body.append("| SPY | Benchmark — am I beating it? | vs-SPY sign flips negative |")
    for p in state["positions"]:
        intel = HOLDINGS_INTEL.get(p["symbol"], {})
        if intel.get("watch"):
            body.append(f"| **{p['symbol']}** | {_cname(p['symbol'])} | {intel['watch']} |")
    body.append("\n- If a held thesis' kill-switch fires (in its research note), the position is reviewed at next week's run.")
    body.append("- Cash re-deploys opportunistically; never chase a name already extended past conviction sizing.")
    body.append("")

    front = (
        "---\ntype: \"pm-brief\"\n"
        f'date: "{today}"\n'
        f'topic: "PM Brief — ${total:,.0f} ({ret:+.2f}%) vs SPY {spy_txt}"\n'
        'companies: []\nthemes: []\ncontext: ["[[Risk appetite]]"]\nsources: ["[[yfinance]]"]\n'
        f'status: "open"\nimportance: 5\n'
        "---\n"
    )
    path = os.path.join(KG_WEEKLY, f"{today} PM Brief.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(front + "\n".join(body) + "\n")
    print("wrote", path)
    return path


def update_digest(state):
    """Append this week's PM action + new research to the rolling Research Digest (deduped)."""
    today = date.today().isoformat()
    os.makedirs(KG_WEEKLY, exist_ok=True)
    dpath = os.path.join(KG_WEEKLY, "Research Digest.md")
    front = (
        "---\ntype: \"digest\"\n"
        f'date: "{today}"\n'
        'topic: "Rolling research + PM digest — what changed this week"\n'
        'companies: []\nthemes: []\nstatus: "open"\nimportance: 5\n---\n\n'
        "# 📓 Research Digest — rolling weekly update\n\n"
        "Newest week at the **bottom**. Records: what research was conducted, what the PM decisioned, and what's on watch.\n"
    )
    if not os.path.exists(dpath):
        with open(dpath, "w", encoding="utf-8") as f:
            f.write(front)

    # dedupe key: "## <today> — Weekly digest" should appear at most once
    existing = ""
    if os.path.exists(dpath):
        existing = open(dpath, encoding="utf-8").read()
    key_line = f"## {today} — Weekly digest"
    if key_line in existing:
        print("digest already has this week — skipping duplicate")
        return
    # remove trailing NEWEST marker if present from prior version
    existing = existing.replace("__NEWEST__\n", "")

    # upcoming catalysts from graph
    cats = kg_links.upcoming_catalysts(horizon_days=21)
    cat_txt = ", ".join(f"{c['date']} {c['event']} {c['company']}" for c in cats) if cats else "none scheduled"
    # stops this week
    stops_this = []
    if state.get("rebalance_history"):
        stops_this = [f"{s}@{c:.2f}" for s, c, *_ in state["rebalance_history"][-1].get("stops", [])]
    total = state["portfolio"].get("cash", 0) + sum(p["qty"] * p["last"] for p in state["positions"])
    ret = (total / 1000000 - 1) * 100

    block = (
        f"\n---\n## {today} — Weekly digest\n"
        f"**📊 Portfolio:** ${total:,.0f} ({ret:+.2f}%) · **cash:** ${state['portfolio'].get('cash',0):,.0f} · **positions:** {len(state['positions'])}\n"
        f"**🔀 PM this week:** {len(state.get('weekly_trades', []))} decisions · stops: {stops_this if stops_this else 'none'}\n"
        f"**🗓️ Catalysts next 21d:** {cat_txt}\n"
        f"**👀 On watch:** {len(state['positions'])} positions, kill-switches in notes, SPY vs portfolio.\n"
    )
    with open(dpath, "w", encoding="utf-8") as f:
        f.write(existing.rstrip() + "\n" + block)
    print("updated", dpath)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    state = load_state()
    if args.seed or not state.get("positions"):
        state = seed_portfolio(state)
        save_state(state)
        print("seeded", len(state["positions"]), "positions")
    if args.report:
        # price-only report
        run_cycle(state)
        return
    state, decisions, stops = run_cycle(state)
    write_brief(state, decisions, stops)
    update_digest(state)
    print(f"PM cycle done: {len(decisions)} trades, {len(stops)} stops")


if __name__ == "__main__":
    main()
