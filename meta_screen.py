#!/usr/bin/env python3
"""
Deterministic multi-category meta-screen — Stoic Point style.

Runs overlapping market, valuation, fundamental, event, and theme checks over
a curated universe. Rankings use breadth across signal families; raw check
counts remain visible but are not treated as independent confirmations.
Inputs come from Yahoo Finance via yahoo_client (the only allowed Yahoo
path); no LLM-generated signals are used.

The built-in universe (or --universe CSV) is a symbol-selection input only;
every fact (history/info/insider/earnings/financials) is supplied by Yahoo.
No Knowledge Graph reads.

Usage:
    python3 meta_screen.py [--universe universe.csv] [--top N]
        [--workers 1..4] [--batch-size N] [--batch-pause-seconds 10..30]

Writes: ~/Documents/Finance Knowledge Graph/Notes/<today> Meta-Screen.md
Also updates this repo's rotation_history.csv (run record)
"""
import os, sys, csv, json, argparse, tempfile, time
from datetime import date, datetime

import pandas as pd
import numpy as np

import yahoo_client  # noqa: E402  (only allowed Yahoo path)

def _first_dir(*paths):
    for p in paths:
        if os.path.isdir(p):
            return p
    return paths[0]


KG_ROOT = os.environ.get("FINANCE_KG_ROOT") or _first_dir(
    "/documents/Finance Knowledge Graph",
    os.path.expanduser("~/Documents/Finance Knowledge Graph"),
)
KG_NOTES = os.path.join(KG_ROOT, "Notes")
FINANCE_AI = os.path.dirname(os.path.abspath(__file__))
ROTATION_CSV = os.path.join(FINANCE_AI, "rotation_history.csv")

# Default curated universe (ticker, name, theme): symbol-selection input
# only — an optional --universe CSV overrides it. Every screen fact comes
# from Yahoo; membership here implies nothing about a company.
_DEMO_TICKERS = """
AAPL MSFT NVDA AMZN GOOGL GOOG META AVGO ORCL CRM
AMD INTC CSCO IBM QCOM TXN AMAT MU LRCX KLAC
NOW ADBE NFLX DIS CMCSA TMUS T VZ JPM BAC
WFC C GS MS BLK SCHW AXP V MA PYPL
COF USB PNC WMT COST HD LOW TGT NKE MCD
SBUX BKNG MAR GM F PG KO PEP MDLZ KHC
PM MO XOM CVX COP SLB EOG CAT DE HON
GE RTX LMT NOC UPS FDX UNP CSX LLY JNJ
ABBV MRK PFE AMGN GILD UNH ELV CVS ABT MDT
ISRG TMO DHR BMY REGN CI MCK SPGI MSCI ADP
""".split()
DEFAULT_UNIVERSE = [(ticker, ticker, "demo") for ticker in _DEMO_TICKERS]



# Theme baskets: (benchmark ETF, member symbols) are symbol-selection inputs
# only. Basket hot/not-hot status is computed from Yahoo ETF histories;
# nothing is read from Theme notes.
THEME_ETFS = {
    "semis/AI": ("SMH", ["NVDA", "AMD", "AVGO", "MU", "AEHR", "SMCI", "TSM", "ASML", "ARM", "ANET"]),
    "small-cap value": ("IWM", ["AVUV"]),
    "Japan": ("EWJ", ["EWJ"]),
    "Defense": ("XAR", ["LMT", "RTX", "NOC", "GD"]),
    "Oil & gas": ("XLE", ["MPC", "VLO", "COP", "CVX", "XOM", "OXY", "EQT", "KMI", "SLB"]),
    "Dividend/income": ("VYM", ["VZ", "JNJ", "KO", "PEP"]),
    "Healthcare": ("XLV", ["LLY", "MRK", "PFE", "ABBV"]),
    "Gold & miners": ("GDX", ["AEM", "NEM", "HL"]),
    "Nuclear/power": ("URA", ["CEG", "VST", "CCJ", "NEE", "SO"]),
    "Cybersecurity": ("CIBR", ["CRWD", "PANW", "FTNT", "ZS"]),
    "Space & defense-tech": ("ARKX", ["RKLB", "KTOS", "LHX", "PLTR"]),
    "Copper/electrification": ("COPX", ["FCX", "SCCO", "TECK", "ETN", "NUE", "VMC"]),
    "Memory/AI hardware": ("DRAM", ["MU", "WDC", "STX", "SNDK"]),
    "AI grid & cooling": ("GRID", ["GEV", "VRT", "PWR", "CAT"]),
    "Biotech": ("XBI", ["NVO", "AMGN", "VRTX", "REGN"]),
    "Banks": ("KBWB", ["JPM", "GS", "MS", "BAC"]),
    "Robotics & automation": ("BOTZ", ["ISRG", "SYM", "TER", "ROK"]),
    "South Korea": ("EWY", ["EWY", "CPNG"]),
    "Taiwan": ("EWT", ["TSM", "UMC", "ASX"]),
    "China": ("KWEB", ["BABA", "PDD", "JD", "BIDU"]),
    "India": ("INDA", ["INFY", "HDB", "IBN", "WIT"]),
    "Europe": ("VGK", ["ASML", "SAP", "NVO", "UL"]),
    "Brazil/EM": ("EWZ", ["VALE", "PBR", "ITUB", "MELI"]),
}

BENCH = "SPY"


class ScreenCtx:
    """Per-symbol context wrapping Yahoo price history + info + theme-hot map."""
    def __init__(self, symbol, series, info, theme_hot, insider=None, earnings=None, fin=None, volume=None):
        self.symbol = symbol
        self.s = series  # pandas Series indexed by date, sorted asc
        self.volume = volume
        self.info = info or {}
        self.theme_hot = theme_hot
        self.insider = insider      # insider-transaction frame from Yahoo (or None)
        self.earnings = earnings    # earnings-dates frame from Yahoo (or None)
        self.fin = fin              # tuple: (balance_sheet, income_stmt, cashflow)
        self.peer_value_result = None

    def perf(self, n):
        if self.s is None or len(self.s) < 2:
            return None
        try:
            return float(self.s.iloc[-1] / self.s.iloc[-n - 1] - 1)
        except Exception:
            return None

    def rsi(self, n=14):
        s = self.s
        if s is None or len(s) < n + 1:
            return None
        try:
            delta = s.diff()
            up = delta.clip(lower=0).ewm(alpha=1 / n).mean()
            down = (-delta.clip(upper=0)).ewm(alpha=1 / n).mean()
            rs = up / down.replace(0, np.nan)
            return float(100 - 100 / (1 + rs.iloc[-1])) if np.isfinite(rs.iloc[-1]) else None
        except Exception:
            return None

    def sma(self, n):
        if self.s is None or len(self.s) < n:
            return None
        try:
            return float(self.s.rolling(n).mean().iloc[-1])
        except Exception:
            return None

    def info_num(self, *keys):
        for k in keys:
            v = (self.info or {}).get(k)
            try:
                v = float(v)
                if np.isfinite(v):
                    return v
            except Exception:
                pass
        return None

    def in_hot_theme(self, theme):
        return self.theme_hot.get(theme)

    def avg_dollar_volume(self, days=20):
        if self.s is None or self.volume is None:
            return None
        try:
            frame = pd.concat(
                [self.s.rename("close"), self.volume.rename("volume")], axis=1
            ).dropna()
            dollar_volume = frame["close"] * frame["volume"]
            if len(dollar_volume) < days:
                return None
            return float(dollar_volume.tail(days).mean())
        except Exception:
            return None

    def next_earnings_date(self):
        if self.earnings is None or len(self.earnings) == 0:
            return None
        future = []
        try:
            for value in self.earnings.index:
                ts = pd.to_datetime(value, errors="coerce", utc=True)
                if pd.isna(ts):
                    continue
                day = ts.tz_convert(None).date()
                if day >= date.today():
                    future.append(day)
        except Exception:
            return None
        return min(future) if future else None

    def short_interest_pct_float(self):
        value = self.info_num("shortPercentOfFloat")
        return None if value is None or value < 0 else value * 100

    # ---- smart-money / event helpers (2026-09: insider clusters, PEAD, F-score) ----

    def insider_cluster(self, days=45):
        """Distinct insiders with open-market purchases in the last `days`."""
        df = self.insider
        if df is None or len(df) == 0 or "Start Date" not in getattr(df, "columns", []):
            return None
        try:
            d = df.copy()
            d["Start Date"] = pd.to_datetime(d["Start Date"], errors="coerce", utc=True)
            cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
            cols = [c for c in ("Text", "Transaction") if c in d.columns]
            if not cols:
                return None
            blob = d[cols].fillna("").astype(str).agg(" ".join, axis=1).str.lower()
            m = blob.str.contains("purchase|buy", regex=True)
            d = d[m & (d["Start Date"] >= cutoff)]
            who = {str(x).strip().lower() for x in d.get("Insider", []) if str(x).strip()}
            return sorted(who)
        except Exception:
            return None

    def last_earnings_beat(self, min_surprise=5.0, max_days=60):
        """Latest reported quarter: EPS surprise ≥ min%, within max_days, drift intact."""
        df = self.earnings
        if df is None or len(df) == 0 or "Reported EPS" not in getattr(df, "columns", []):
            return None
        try:
            d = df[df["Reported EPS"].notna()].sort_index(ascending=False)
            if len(d) == 0:
                return False
            ts = pd.Timestamp(d.index[0])
            if ts.tzinfo is not None:
                ts = ts.tz_convert(None)
            d0 = ts.date()
            days = (date.today() - d0).days
            if days < 0:
                return None
            if days > max_days:
                return False
            sur = None
            if "Surprise(%)" in d.columns:
                try:
                    sur = float(d["Surprise(%)"].iloc[0])
                except Exception:
                    sur = None
            if sur is None or not np.isfinite(sur):
                est = d["EPS Estimate"].iloc[0]
                rep = d["Reported EPS"].iloc[0]
                if est is None or float(est) <= 0:
                    return None
                sur = (float(rep) - float(est)) / abs(float(est)) * 100
            if not np.isfinite(sur):
                return None
            if sur < min_surprise:
                return False
            # drift intact: price has not broken below the print-day close (-2% guard)
            base = None
            if self.s is not None:
                for i in range(len(self.s)):
                    if self.s.index[i].date() >= d0:
                        base = float(self.s.iloc[i])
                        break
            if base is None:
                return None
            if float(self.s.iloc[-1]) < base * 0.98:
                return False
            return {"days": int(days), "surprise": round(float(sur), 1)}
        except Exception:
            return None

    def _fv(self, stmt, *keys, col=0):
        try:
            if stmt is None or stmt.empty or len(stmt.columns) <= col:
                return None
            for k in keys:
                if k in stmt.index:
                    v = stmt.loc[k].iloc[col]
                    if v is not None and np.isfinite(float(v)):
                        return float(v)
        except Exception:
            pass
        return None

    def f_score(self):
        """Piotroski F-score over the last two annual statements -> (points, items)."""
        if self.fin is None:
            return None
        bs, inc, cf = self.fin
        ni0 = self._fv(inc, "Net Income", "Net Income Common Stockholders", col=0)
        ni1 = self._fv(inc, "Net Income", "Net Income Common Stockholders", col=1)
        ta0 = self._fv(bs, "Total Assets", col=0)
        ta1 = self._fv(bs, "Total Assets", col=1)
        cfo0 = self._fv(cf, "Operating Cash Flow", "Total Cash From Operating Activities", col=0)
        if ni0 is None or ta0 is None or cfo0 is None or ta0 == 0:
            return None
        pts = n = 0
        n += 1
        pts += 1 if ni0 > 0 else 0                                   # 1. ROA > 0
        n += 1
        pts += 1 if cfo0 > 0 else 0                                  # 2. CFO > 0
        if ta1 and ni1 is not None:                                  # 3. ΔROA > 0
            n += 1
            pts += 1 if (ni0 / ta0) > (ni1 / ta1) else 0
        n += 1
        pts += 1 if cfo0 > ni0 else 0                                # 4. accruals: CFO > NI
        ltd0 = self._fv(bs, "Long Term Debt", "Total Debt", col=0)
        ltd1 = self._fv(bs, "Long Term Debt", "Total Debt", col=1)
        if ltd0 is not None and ltd1 is not None and ta1:            # 5. Δleverage < 0
            n += 1
            pts += 1 if (ltd0 / ta0) < (ltd1 / ta1) else 0
        ca0 = self._fv(bs, "Current Assets", col=0)
        cl0 = self._fv(bs, "Current Liabilities", col=0)
        ca1 = self._fv(bs, "Current Assets", col=1)
        cl1 = self._fv(bs, "Current Liabilities", col=1)
        if ca0 and cl0 and ca1 and cl1:                              # 6. Δcurrent ratio > 0
            n += 1
            pts += 1 if (ca0 / cl0) > (ca1 / cl1) else 0
        sh0 = self._fv(bs, "Ordinary Shares Number", "Share Issued", col=0)
        sh1 = self._fv(bs, "Ordinary Shares Number", "Share Issued", col=1)
        if sh0 is not None and sh1 is not None:                      # 7. no dilution
            n += 1
            pts += 1 if sh0 <= sh1 * 1.001 else 0
        gp0 = self._fv(inc, "Gross Profit", col=0)
        rev0 = self._fv(inc, "Total Revenue", col=0)
        gp1 = self._fv(inc, "Gross Profit", col=1)
        rev1 = self._fv(inc, "Total Revenue", col=1)
        if gp0 and rev0 and gp1 and rev1:                            # 8. Δgross margin > 0
            n += 1
            pts += 1 if (gp0 / rev0) > (gp1 / rev1) else 0
        if rev0 and ta0 and rev1 and ta1:                            # 9. Δasset turnover > 0
            n += 1
            pts += 1 if (rev0 / ta0) > (rev1 / ta1) else 0
        return (pts, n)


SCREENS = {}


def screen(name, category):
    def deco(fn):
        SCREENS[name] = (category, fn)
        return fn
    return deco


def filter_screens(screens, selected_names):
    """Return the registered checks selected by name, preserving registry order."""
    if not selected_names:
        return screens
    if len(set(selected_names)) != len(selected_names):
        raise ValueError("--check names must not be repeated")
    unknown_checks = [name for name in selected_names if name not in screens]
    if unknown_checks:
        raise ValueError("unknown check name(s): " + ", ".join(unknown_checks))
    selected = set(selected_names)
    return {name: check for name, check in screens.items() if name in selected}


# ---- Momentum ----
@screen("6m momentum leader (vs SPY)", "momentum")
def _(c, b):
    value, benchmark = c.perf(130), b.perf(130) if b is not None else None
    return None if value is None or benchmark is None else value > benchmark


@screen("12m outperformer (vs SPY)", "momentum")
def _(c, b):
    value, benchmark = c.perf(252), b.perf(252) if b is not None else None
    return None if value is None or benchmark is None else value > benchmark


@screen("short-term re-acceleration", "momentum")
def _(c, b):
    m1 = c.perf(22); m3 = c.perf(66)
    if None in (m1, m3):
        return None
    return m1 > 0.02 and m1 > m3


@screen("dip within uptrend", "momentum")
def _(c, b):
    m3, m1 = c.perf(66), c.perf(22)
    return None if m3 is None or m1 is None else m3 > 0.05 and m1 < -0.02


# ---- Technical ----
@screen("uptrend structure (20>50>200 SMA)", "technical")
def _(c, b):
    sma20, sma50, sma200 = c.sma(20), c.sma(50), c.sma(200)
    if None in (sma20, sma50, sma200):
        return None
    return sma20 > sma50 > sma200


@screen("RSI between 30 and 50", "technical")
def _(c, b):
    r = c.rsi(14)
    return None if r is None else 30 <= r <= 50


@screen("proximity to 52w high", "technical")
def _(c, b):
    s = c.s
    if s is None or len(s) < 252:
        return None
    return float(s.iloc[-1]) >= 0.9 * float(s.tail(252).max())


@screen("recovered from 52w low", "technical")
def _(c, b):
    s = c.s
    if s is None or len(s) < 252:
        return None
    return float(s.iloc[-1]) >= 1.3 * float(s.tail(252).min())


# ---- Valuation ----
@screen("cheap fwd P/E (<15)", "valuation")
def _(c, b):
    pe = c.info_num("forwardPE")
    return None if pe is None else 0 < pe < 15


@screen("low P/B (<2)", "valuation")
def _(c, b):
    pb = c.info_num("priceToBook")
    return None if pb is None else 0 < pb < 2


@screen("low P/S (<2)", "valuation")
def _(c, b):
    ps = c.info_num("priceToSalesTrailing12Months")
    return None if ps is None else 0 < ps < 2


@screen("GARP (P/E <25; growth >10%; PEG <2.5)", "valuation")
def _(c, b):
    pe = c.info_num("forwardPE"); g = c.info_num("earningsGrowth")
    if pe is None or g is None:
        return None
    if pe <= 0 or g <= 0:
        return False
    peg = pe / (g * 100)
    return pe < 25 and g > 0.10 and peg < 2.5


@screen("sector relative value (≥20% below peers)", "valuation")
def _(c, b):
    result = c.peer_value_result
    if result is None or not result["evaluated"]:
        return None
    return bool(result["passed"])


# ---- Fundamental ----
@screen("high revenue growth (>20%)", "fundamental")
def _(c, b):
    g = c.info_num("revenueGrowth")
    return None if g is None else g > 0.20


@screen("high ROE (>15%)", "fundamental")
def _(c, b):
    roe = c.info_num("returnOnEquity")
    return None if roe is None else roe > 0.15


@screen("net margin >8%", "fundamental")
def _(c, b):
    nm = c.info_num("profitMargins")
    return None if nm is None else nm > 0.08


# ---- Theme rotation ----
def _theme_rotation_hit(c, theme):
    if c.symbol not in THEME_ETFS[theme][1]:
        return False
    hot = c.in_hot_theme(theme)
    return None if hot is None else bool(hot)


@screen("theme: semis/AI rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "semis/AI")


@screen("theme: defense rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "Defense")


@screen("theme: oil & gas rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "Oil & gas")


@screen("theme: dividend/income rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "Dividend/income")


@screen("theme: Japan rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "Japan")


@screen("theme: small-cap value rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "small-cap value")


@screen("theme: healthcare/biotech rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "Healthcare")


@screen("theme: gold & miners rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "Gold & miners")


@screen("theme: nuclear/power rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "Nuclear/power")


@screen("theme: cybersecurity rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "Cybersecurity")


@screen("theme: space & defense-tech rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "Space & defense-tech")


@screen("theme: copper/electrification rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "Copper/electrification")


@screen("theme: memory/AI hardware rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "Memory/AI hardware")


@screen("theme: AI grid & cooling rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "AI grid & cooling")


@screen("theme: biotech rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "Biotech")


@screen("theme: banks rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "Banks")


@screen("theme: robotics & automation rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "Robotics & automation")


@screen("theme: south korea rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "South Korea")


@screen("theme: taiwan rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "Taiwan")


@screen("theme: china rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "China")


@screen("theme: india rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "India")


@screen("theme: europe rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "Europe")


@screen("theme: brazil/em rotation in", "theme")
def _(c, b):
    return _theme_rotation_hit(c, "Brazil/EM")


# ---- Smart money / events / quality (added 2026-09) ----
@screen("insider cluster buy (≥2 insiders, 45d)", "insider")
def _(c, b):
    cluster = c.insider_cluster()
    return None if cluster is None else len(cluster) >= 2


@screen("earnings beat drift (PEAD)", "earnings")
def _(c, b):
    beat = c.last_earnings_beat()
    return None if beat is None else bool(beat)


@screen("Piotroski F-score ≥7/9 + cheap", "quality")
def _(c, b):
    f = c.f_score()
    if f is None:
        return None
    pts, n = f
    if n < 9:
        return None
    pe = c.info_num("trailingPE", "forwardPE")
    return None if pe is None else pts >= 7 and 0 < pe < 20


@screen("gross profitability high (GP/assets >33%)", "quality")
def _(c, b):
    if c.fin is None:
        return None
    bs, inc, _cf = c.fin
    gp = c._fv(inc, "Gross Profit", col=0)
    ta = c._fv(bs, "Total Assets", col=0)
    if gp is None or ta is None or ta == 0:
        return None
    return (gp / ta) > 0.33


@screen("cash-backed earnings (accruals <5% assets)", "quality")
def _(c, b):
    if c.fin is None:
        return None
    bs, inc, cf = c.fin
    ni = c._fv(inc, "Net Income", "Net Income Common Stockholders", col=0)
    cfo = c._fv(cf, "Operating Cash Flow", "Total Cash From Operating Activities", col=0)
    ta = c._fv(bs, "Total Assets", col=0)
    if ni is None or cfo is None or ta is None or ta == 0:
        return None
    if ni <= 0:
        return False
    return abs(ni - cfo) / ta <= 0.05


@screen("buyback acceleration (≥2× YoY, ≥2% mcap)", "quality")
def _(c, b):
    if c.fin is None:
        return None
    _bs, _inc, cf = c.fin
    rp0 = c._fv(cf, "Repurchase Of Capital Stock", col=0)
    rp1 = c._fv(cf, "Repurchase Of Capital Stock", col=1)
    if rp0 is None or rp1 is None:
        return None
    rp0, rp1 = abs(rp0), abs(rp1)
    mcap = c.info_num("marketCap")
    if not mcap:
        return None
    return rp0 >= 0.02 * mcap and rp0 >= 2 * rp1


@screen("capital discipline (capex ≤+5% YoY, FCF+)", "quality")
def _(c, b):
    if c.fin is None:
        return None
    _bs, _inc, cf = c.fin
    capex0 = c._fv(cf, "Capital Expenditure", col=0)
    capex1 = c._fv(cf, "Capital Expenditure", col=1)
    cfo0 = c._fv(cf, "Operating Cash Flow", "Total Cash From Operating Activities", col=0)
    if capex0 is None or capex1 is None or cfo0 is None:
        return None
    if cfo0 <= 0:
        return False
    capex0, capex1 = abs(capex0), abs(capex1)
    if cfo0 - capex0 <= 0:
        return False
    return capex0 <= capex1 * 1.05


@screen("growth efficiency (revenue up; op/FCF margin +1pp)", "quality")
def _(c, b):
    if c.fin is None:
        return None
    _bs, inc, cf = c.fin
    rev0 = c._fv(inc, "Total Revenue", col=0)
    rev1 = c._fv(inc, "Total Revenue", col=1)
    if rev0 is None or rev1 is None:
        return None
    if rev0 <= 0 or rev1 <= 0 or rev0 <= rev1:
        return False

    improvements = []
    op0 = c._fv(inc, "Operating Income", "Operating Income Loss", col=0)
    op1 = c._fv(inc, "Operating Income", "Operating Income Loss", col=1)
    if op0 is not None and op1 is not None:
        improvements.append((op0 / rev0) - (op1 / rev1))

    cfo0 = c._fv(cf, "Operating Cash Flow", "Total Cash From Operating Activities", col=0)
    cfo1 = c._fv(cf, "Operating Cash Flow", "Total Cash From Operating Activities", col=1)
    capex0 = c._fv(cf, "Capital Expenditure", col=0)
    capex1 = c._fv(cf, "Capital Expenditure", col=1)
    if None not in (cfo0, cfo1, capex0, capex1):
        fcf_margin0 = (cfo0 - abs(capex0)) / rev0
        fcf_margin1 = (cfo1 - abs(capex1)) / rev1
        improvements.append(fcf_margin0 - fcf_margin1)

    if not improvements:
        return None
    return any(change >= 0.01 for change in improvements)


def annotate_peer_valuation(data, min_peers=4, discount_threshold=0.20):
    """Compare positive forward P/E or P/S with same-sector peers in this universe."""
    metrics = ("forwardPE", "priceToSalesTrailing12Months")
    by_sector = {}
    for symbol, ctx in data.items():
        sector = (ctx.info or {}).get("sector")
        if not sector:
            continue
        for metric in metrics:
            value = ctx.info_num(metric)
            if value is not None and value > 0:
                by_sector.setdefault((sector, metric), []).append((symbol, value))

    for symbol, ctx in data.items():
        sector = (ctx.info or {}).get("sector")
        tested = []
        passed = []
        if sector:
            for metric in metrics:
                value = ctx.info_num(metric)
                peers = [
                    peer_value
                    for peer_symbol, peer_value in by_sector.get((sector, metric), [])
                    if peer_symbol != symbol
                ]
                if value is None or value <= 0 or len(peers) < min_peers:
                    continue
                median = float(np.median(peers))
                if median <= 0:
                    continue
                discount = 1 - value / median
                label = "forward P/E" if metric == "forwardPE" else "P/S"
                tested.append((label, value, median, discount))
                if discount >= discount_threshold:
                    passed.append((label, value, median, discount))

        best = max(passed, key=lambda item: item[3]) if passed else None
        ctx.peer_value_result = {
            "evaluated": bool(tested),
            "passed": bool(passed),
            "detail": best,
        }


SCREEN_FAMILIES = (
    ("price action", frozenset(("momentum", "technical"))),
    ("valuation", frozenset(("valuation",))),
    ("business quality", frozenset(("fundamental", "quality"))),
    ("earnings", frozenset(("earnings",))),
    ("insider activity", frozenset(("insider",))),
)


def family_breadth(hits):
    hit_categories = {SCREENS[name][0] for name in hits}
    return sum(bool(hit_categories & categories) for _label, categories in SCREEN_FAMILIES)


def core_hit_count(hits):
    return sum(1 for name in hits if SCREENS[name][0] != "theme")


def load_universe(path):
    """Selection input only: optional CSV of (ticker, name, theme) rows.

    Defaults to the built-in curated universe; no Knowledge Graph reads.
    """
    if path and os.path.exists(path):
        rows = []
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append((r.get("ticker", "").strip(), r.get("name", "").strip(), r.get("theme", "").strip()))
        if rows:
            return rows
    return DEFAULT_UNIVERSE


def _client_for(provider):
    """Return a YahooClient-compatible object (injected stub or live client)."""
    if provider is None:
        return yahoo_client
    if hasattr(provider, "get_history") and hasattr(provider, "get_info"):
        return provider
    if callable(provider):
        return yahoo_client.YahooClient(provider=provider)
    raise TypeError("provider must be a YahooClient, a stub with "
                    "get_history/get_info, or a provider callable")


def _closes_from_history(frame):
    """Close series from a Yahoo history frame; None when unavailable."""
    try:
        if frame is None or getattr(frame, "empty", True):
            return None
        columns = list(getattr(frame, "columns", []) or [])
        lowered = {str(c).strip().lower(): c for c in columns}
        key = next((lowered[name] for name in ("close", "adj close") if name in lowered), None)
        series = frame[key].dropna() if key is not None else frame.iloc[:, 0].dropna()
        return series if len(series) else None
    except Exception:
        return None


def _is_yahoo_rate_limit(message):
    text = str(message).lower()
    return any(token in text for token in ("429", "too many requests", "rate limit", "yfratelimit"))


def theme_rotation(batch_size=8, pause_seconds=15, provider=None):
    """Return (theme -> hot/unavailable, rate_limited) with cooldowns between ETF batches.

    Basket status comes from Yahoo ETF histories via ``yahoo_client``;
    a stub ``provider`` may be injected for tests.
    """
    client = _client_for(provider)
    hot = {}
    rate_limited = False
    try:
        frame = client.get_history(BENCH, "6mo")
        sp = _closes_from_history(frame)
        sp1 = float(sp.iloc[-1] / sp.iloc[-22] - 1) if sp is not None and len(sp) > 22 else None
    except RuntimeError:
        sp1 = None
        rate_limited = True
    except Exception:
        sp1 = None
        rate_limited = False
    themes = list(THEME_ETFS.items())
    for index, (theme, (etf, _members)) in enumerate(themes):
        if rate_limited:
            hot[theme] = None
            continue
        if sp1 is None:
            hot[theme] = None
            continue
        try:
            frame = client.get_history(etf, "6mo")
            e = _closes_from_history(frame)
            if e is None or len(e) < 66:
                hot[theme] = None
                continue
            m1 = float(e.iloc[-1] / e.iloc[-22] - 1)
            m3 = float(e.iloc[-1] / e.iloc[-66] - 1)
            hot[theme] = (m1 - sp1 > 0.02) and (m3 > 0)
        except RuntimeError:
            hot[theme] = None
            rate_limited = True
        except Exception:
            hot[theme] = None
        if (
            not rate_limited
            and pause_seconds
            and batch_size > 0
            and (index + 1) % batch_size == 0
            and index + 1 < len(themes)
        ):
            print(f"Yahoo cooldown: waiting {pause_seconds}s after {index + 1} theme ETFs")
            time.sleep(pause_seconds)
    for theme, _ in themes:
        hot.setdefault(theme, None)
    return hot, rate_limited


def main():
    global SCREENS
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default=None,
                    help="optional CSV of (ticker, name, theme) rows used as selection input only")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--check", action="append", default=[],
                    help="run only this registered check; repeat to select multiple")
    ap.add_argument("--result-json", help="write a machine-readable ranking for the CLI dashboard")
    ap.add_argument("--workers", type=int, choices=(1, 2), default=1,
                    help="parallel ticker fetches; 1 is safest for Yahoo (default: 1)")
    ap.add_argument("--batch-size", type=int, default=8,
                    help="tickers fetched before a Yahoo cooldown (default: 8)")
    ap.add_argument("--batch-pause-seconds", type=int, choices=range(10, 31), default=15,
                    help="cooldown between Yahoo fetch batches, 10–30 seconds (default: 15)")
    args = ap.parse_args()
    if args.top < 1:
        ap.error("--top must be at least 1")
    if args.batch_size < 1:
        ap.error("--batch-size must be at least 1")
    try:
        SCREENS = filter_screens(SCREENS, args.check)
    except ValueError as exc:
        ap.error(str(exc))

    universe = load_universe(args.universe)
    universe_syms = [t for t, _, _ in universe]
    universe_label = (
        os.path.basename(args.universe)
        if args.universe and os.path.exists(args.universe) and universe != DEFAULT_UNIVERSE
        else "curated default"
    )
    client = _client_for(None)
    theme_hot, theme_rate_limited = theme_rotation(
        batch_size=args.batch_size,
        pause_seconds=args.batch_pause_seconds,
        provider=client,
    )
    if theme_rate_limited:
        print("Yahoo rate limit detected during theme fetch; stopping before writing a partial screen.")
        raise SystemExit(2)

    bench = None
    try:
        bench_close = _closes_from_history(client.get_history(BENCH, "18mo"))
        bench = ScreenCtx(BENCH, bench_close, {}, theme_hot) if bench_close is not None else None
    except RuntimeError:
        print("Yahoo rate limit detected during benchmark fetch; stopping before writing a partial screen.")
        raise SystemExit(2)
    except Exception:
        bench = None

    from concurrent.futures import ThreadPoolExecutor

    def _build_ctx(sym):
        errors = []
        history = None
        try:
            history = client.get_history(sym, "18mo")
        except RuntimeError:
            raise
        except Exception as e:
            errors.append(f"price history: {e}")
        close = _closes_from_history(history)
        volume = None
        try:
            if history is not None and close is not None and "Volume" in getattr(history, "columns", []):
                volume = history["Volume"].reindex(close.index)
        except Exception:
            volume = None

        info = {}
        try:
            info = client.get_info(sym) or {}
        except RuntimeError:
            raise
        except Exception as e:
            errors.append(f"company info: {e}")
        ctx = ScreenCtx(sym, close, info, theme_hot, volume=volume)
        insider_getter = getattr(client, "get_insider_transactions", None)
        if callable(insider_getter):
            try:
                ctx.insider = insider_getter(sym)
            except RuntimeError:
                raise
            except Exception as e:
                errors.append(f"insider data: {e}")
        else:
            ctx.insider = None
        try:
            ctx.earnings = client.get_earnings_dates(sym)
        except RuntimeError:
            raise
        except Exception as e:
            errors.append(f"earnings dates: {e}")
        financials = []
        for label, kind in (
            ("balance sheet", "balance"),
            ("income statement", "income"),
            ("cash flow", "cashflow"),
        ):
            try:
                financials.append(client.get_financials(sym, kind))
            except RuntimeError:
                raise
            except Exception as e:
                financials.append(None)
                errors.append(f"{label}: {e}")
        ctx.fin = tuple(financials)
        return sym, ctx, errors

    batch_count = (len(universe_syms) + args.batch_size - 1) // args.batch_size
    print(
        f"fetching {len(universe_syms)} symbols in {batch_count} batches "
        f"(workers={args.workers}, batch size={args.batch_size}) ..."
    )
    data = {}
    data_errors = []
    for batch_index, start in enumerate(range(0, len(universe_syms), args.batch_size), start=1):
        batch_symbols = universe_syms[start:start + args.batch_size]
        try:
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                batch_results = list(ex.map(_build_ctx, batch_symbols))
        except RuntimeError:
            print(
                f"Yahoo rate limit detected in batch {batch_index}; "
                "stopping before writing a partial screen."
            )
            raise SystemExit(2)
        for sym, ctx, errors in batch_results:
            data[sym] = ctx
            data_errors.extend(f"{sym}: {error}" for error in errors)
        rate_limit_errors = [error for error in data_errors if _is_yahoo_rate_limit(error)]
        if rate_limit_errors:
            print(
                f"Yahoo rate limit detected in batch {batch_index}; "
                "stopping before writing a partial screen."
            )
            raise SystemExit(2)
        if batch_index < batch_count:
            print(
                f"Yahoo cooldown: waiting {args.batch_pause_seconds}s "
                f"after batch {batch_index}/{batch_count}"
            )
            time.sleep(args.batch_pause_seconds)

    if data_errors:
        print(f"data warnings: {len(data_errors)} unavailable fields; first 5: {data_errors[:5]}")

    annotate_peer_valuation(data)

    markdown_rows = []
    rotation_by_theme = {}
    screen_hits = {name: [] for name in SCREENS}
    screen_outcomes = {name: {} for name in SCREENS}
    screen_errors = []
    for sym, name, theme in universe:
        c = data.get(sym)
        if c is None:
            for sname in SCREENS:
                screen_outcomes[sname][sym] = None
            continue
        hits = []
        for sname, (cat, fn) in SCREENS.items():
            try:
                result = fn(c, bench)
                result = None if result is None else bool(result)
                screen_outcomes[sname][sym] = result
                if result is True:
                    hits.append(sname)
                    screen_hits[sname].append(sym)
            except Exception as e:
                screen_outcomes[sname][sym] = None
                screen_errors.append(f"{sym}/{sname}: {type(e).__name__}: {e}")
        markdown_rows.append((sym, name, theme, hits))

    markdown_rows.sort(
        key=lambda r: (-family_breadth(r[3]), -core_hit_count(r[3]), -len(r[3]), r[0])
    )
    if screen_errors:
        print(f"screen warnings: {len(screen_errors)} errors treated as unavailable; first 5: {screen_errors[:5]}")

    # Rotation read (theme counts) -> append to rotation_history.csv
    for theme in THEME_ETFS:
        n = len([r for r in markdown_rows if r[2] == theme and len(r[3]) >= 5])
        rotation_by_theme[theme] = (n, theme_hot.get(theme))

    today = date.today().isoformat()
    _append_rotation(today, rotation_by_theme)

    report_path = _write_note(
        today, markdown_rows, screen_hits, rotation_by_theme, universe_syms,
        screen_outcomes, data, universe_label, args.top, len(data_errors), len(screen_errors),
    )
    _print_summary(markdown_rows, rotation_by_theme, args.top)
    if args.result_json:
        _write_result_json(args.result_json, markdown_rows, args.top, report_path, data)


def _append_rotation(today, rotation_by_theme, path=None):
    """Append this run's theme counts to the rotation history (run record).

    Writes atomically and replaces today's existing row. ``path`` defaults
    to the repo-local rotation_history.csv; tests may inject a temp path.
    """
    path = path or ROTATION_CSV
    themes = list(rotation_by_theme)
    header = ["date"] + themes + [f"{k}_hot" for k in themes]
    row = [today] + [rotation_by_theme[k][0] for k in themes]
    row += ["" if rotation_by_theme[k][1] is None else int(rotation_by_theme[k][1]) for k in themes]
    existing_rows = []
    try:
        if os.path.exists(path):
            with open(path, newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            if rows:
                old_header = rows[0]
                legacy_themes = themes[:8]
                legacy_header = ["date"] + legacy_themes + [f"{k}_hot" for k in legacy_themes]
                for old_row in rows[1:]:
                    if not old_row:
                        continue
                    if old_row[0] == today:
                        continue
                    if len(old_row) == len(header):
                        normalized = old_row
                    elif len(old_row) == len(old_header):
                        values = dict(zip(old_header, old_row))
                        normalized = [values.get(column, "") for column in header]
                    elif len(old_row) == len(legacy_header):
                        values = dict(zip(legacy_header, old_row))
                        normalized = [values.get(column, "") for column in header]
                    else:
                        raise ValueError(
                            f"unexpected row width {len(old_row)} in {path}; expected "
                            f"{len(header)} or a recognized legacy layout"
                        )
                    existing_rows.append(normalized)

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", newline="", encoding="utf-8", dir=os.path.dirname(os.path.abspath(path)), delete=False
            ) as f:
                temp_path = f.name
                w = csv.writer(f, lineterminator="\n")
                w.writerow(header)
                w.writerows(existing_rows)
                w.writerow(row)
            os.replace(temp_path, path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
    except Exception as e:
        print(f"rotation history update failed; existing file left unchanged: {e}")


def _format_dollar_volume(value):
    if value is None or not np.isfinite(value):
        return "n/a"
    if value >= 1e9:
        return f"${value / 1e9:.2f}B"
    if value >= 1e6:
        return f"${value / 1e6:.1f}M"
    return f"${value / 1e3:.0f}K"


def _format_earnings(ctx, today):
    event_date = ctx.next_earnings_date()
    if event_date is None:
        return "n/a"
    days = (event_date - today).days
    note = " — near" if days <= 14 else ""
    return f"{event_date.isoformat()} (+{days}d){note}"


def _format_short_interest(ctx):
    value = ctx.short_interest_pct_float()
    if value is None or not np.isfinite(value):
        return "n/a"
    if value >= 20:
        return f"{value:.1f}% (high)"
    if value >= 10:
        return f"{value:.1f}% (elevated)"
    return f"{value:.1f}%"


def _write_note(
    today, rows, screen_hits, rotation_by_theme, universe_syms,
    screen_outcomes, data, universe_label, top_count, data_warning_count, screen_error_count,
    notes_dir=None,
):
    """Write the run-record note. Tickers are plain symbols (no KG links).

    ``notes_dir`` defaults to the Finance Knowledge Graph Notes folder;
    tests may inject a temp directory.
    """
    notes_dir = notes_dir or KG_NOTES
    os.makedirs(notes_dir, exist_ok=True)
    topn = rows[:top_count]
    companies = []
    for sym, _name, _theme, _hits in topn:
        companies.append(sym)
    names_hit = sum(1 for _sym, _name, _theme, hits in rows if hits)
    front = (
        "---\n"
        f'type: "research-note"\n'
        f'date: "{today}"\n'
        f'topic: {json.dumps(f"Meta-screen — {len(SCREENS)} checks / {names_hit} names with hits")}\n'
        f'universe: {json.dumps(universe_label)}\n'
        f'companies: {json.dumps(list(dict.fromkeys(companies)), ensure_ascii=False)}\n'
        f'themes: []\n'
        f'context: ["[[Risk appetite]]"]\n'
        f'sources: ["Yahoo Finance via yahoo_client"]\n'
        f'status: "open"\n'
        f'importance: 5\n'
        f'idea_source: "meta-screen"\n'
        "---\n\n"
    )
    cats_used = "/".join(sorted({category for category, _fn in SCREENS.values()}))
    core_screens = [name for name, (category, _fn) in SCREENS.items() if category != "theme"]
    body = [
        f"# Meta-Screen {today}\n",
        "## Method",
        (
            f"Ran **{len(SCREENS)} checks** across categories ({cats_used}) on the **{universe_label}** universe. "
            "Ranks use breadth across five signal families (price action, valuation, business quality, earnings, insider activity); "
            "theme hits are context and do not add score. Raw hit totals remain visible. Missing inputs and evaluation errors are "
            "reported as unavailable rather than failed. Peer value requires at least four same-sector peers and a ≥20% discount "
            "on forward P/E or P/S. Growth efficiency requires rising revenue and ≥1 percentage point improvement in operating or FCF margin.\n"
        ),
        "## Top meta-list (family breadth)",
        "| # | Ticker | Families / 5 | Raw hits | Core coverage | Category profile |\n|---|---|---:|---:|---:|---|",
    ]
    for i, (sym, _name, _theme, hits) in enumerate(topn, 1):
        cats = sorted({SCREENS[h][0] for h in hits})
        covered = sum(screen_outcomes[name].get(sym) is not None for name in core_screens)
        coverage = f"{covered}/{len(core_screens)}"
        body.append(
            f"| {i} | {sym} | {family_breadth(hits)} | {len(hits)} | {coverage} | {', '.join(cats)} |"
        )

    body.append("\n## Execution and event context — top names only\n")
    body.append("Liquidity, earnings timing, and short interest are context only; they do not add to the score. Yahoo earnings dates within 14 calendar days are marked near and should be confirmed with company IR. Short interest ≥10% / ≥20% of float is labeled elevated / high.\n")
    body.append("| Ticker | 20d average dollar volume | Next earnings (Yahoo) | Short % float |\n|---|---:|---|---:|")
    for sym, _name, _theme, _hits in topn:
        ctx = data.get(sym)
        if ctx is None:
            adv, earnings, short_pct = "n/a", "n/a", "n/a"
        else:
            adv = _format_dollar_volume(ctx.avg_dollar_volume())
            earnings = _format_earnings(ctx, date.fromisoformat(today))
            short_pct = _format_short_interest(ctx)
        body.append(f"| {sym} | {adv} | {earnings} | {short_pct} |")

    body.append("\n## Data and audit notes\n")
    body.append(f"- {data_warning_count} field-fetch exceptions caught; Yahoo can also return missing fields without raising exceptions, so use each check's unavailable count.")
    body.append(f"- {screen_error_count} screen-evaluation errors; treated as unavailable.")
    body.append("- Raw screen hits overlap: momentum and technical checks are grouped, as are fundamentals and quality; theme exposure is excluded from family breadth.")
    body.append("- The existing technical checks use 6m/12m momentum, moving averages, RSI, and 52-week levels; these are descriptive signals, not independent confirmation.")
    body.append("- The F-score check now requires all 9 components to be available before applying its ≥7/9 rule.")

    body.append("\n## What's still open\n- Which meta names have a fundamental thesis, not just statistical fit.\n- Cross-check top meta names with the research agent before acting.\n")
    body.append("## Market context — theme rotation read\n")
    for theme, (n, hot) in rotation_by_theme.items():
        status = "hot" if hot is True else "not hot" if hot is False else "unavailable"
        body.append(f"- **{theme}** — {n} names in the theme label had ≥5 raw hits; basket status: {status}")

    body.append("\n## Checks run (by category)\n")
    bycat = {}
    for sname, (cat, _fn) in SCREENS.items():
        bycat.setdefault(cat, []).append(sname)
    for cat, names in bycat.items():
        body.append(f"### {cat}")
        for sname in names:
            outcomes = list(screen_outcomes[sname].values())
            passed = sum(result is True for result in outcomes)
            evaluated = sum(result is not None for result in outcomes)
            unavailable = sum(result is None for result in outcomes)
            passers = ", ".join(screen_hits.get(sname, [])[:8])
            body.append(
                f"- **{sname}** ({passed} pass; {evaluated} evaluated; {unavailable} unavailable)"
                f"{': ' + passers if passers else ''}"
            )
    body.append("\n--\nTotal checks: " + str(len(SCREENS)))
    title = os.path.join(notes_dir, f"{today} Meta-Screen.md")
    with open(title, "w", encoding="utf-8") as f:
        f.write(front + "\n".join(body) + "\n")
    print("wrote", title)
    return title


def _write_result_json(path, rows, top_count, report_path, data=None):
    contexts = data or {}
    top = []
    for rank, (ticker, name, _theme, hits) in enumerate(rows[:top_count], 1):
        display_name = name
        if not display_name or display_name.strip().casefold() == ticker.casefold():
            context = contexts.get(ticker)
            info = context.info if context is not None else {}
            for key in ("longName", "shortName"):
                candidate = info.get(key) if isinstance(info, dict) else None
                if isinstance(candidate, str) and candidate.strip():
                    display_name = candidate.strip()
                    break
        if not display_name:
            display_name = ticker
        top.append({
            "rank": rank,
            "ticker": ticker,
            "name": display_name,
            "detail": f"{family_breadth(hits)}/5 signal families, {len(hits)} raw checks",
        })
    payload = {
        "summary": f"{len(top)} names ranked by signal-family breadth across {len(SCREENS)} checks",
        "report_path": str(report_path),
        "top": top,
    }
    absolute_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=os.path.dirname(absolute_path),
            prefix=".meta-screen-", suffix=".tmp", delete=False,
        ) as handle:
            temporary_path = handle.name
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_path, absolute_path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def _print_summary(rows, rotation_by_theme, top_count):
    print("\n=== META-SCREEN TOP OVERLAP ===")
    for i, (sym, name, _theme, hits) in enumerate(rows[:top_count], 1):
        print(
            f"{i}. {sym} ({name}) — {family_breadth(hits)}/5 families, "
            f"{len(hits)} raw hits: {', '.join(hits[:4])}{'…' if len(hits)>4 else ''}"
        )
    print("\nTheme rotation:", {k: v[0] for k, v in rotation_by_theme.items() if v[1] is True})

if __name__ == "__main__":
    main()
