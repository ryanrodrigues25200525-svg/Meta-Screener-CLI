#!/usr/bin/env python3
"""
source_corr.py — fights fake source diversification (feedback-loop gap #4).

The cross-source alpha shortlist counts how many screens a name appears in. But
if several screens read the SAME underlying data (e.g. meta-screen momentum,
deep-value, and the sector rundowns all derive from the same yfinance price
series), those aren't independent signals — counting them as 3 "sources" is
fake diversification. This script maps every screen/scan to its UNDERLYING data
lineage and computes an EFFECTIVE independent-source count per name.

Data lineage (screen -> underlying data source):
  - price/technical screens      -> yfinance price series
  - valuation/fundamental screens -> yfinance fundamentals (+ SEC where noted)
  - analyst actions                -> sell-side consensus (independent)
  - hedge-fund letters / BuySide   -> fund positioning (independent)
  - Reddit / social scans          -> retail sentiment (independent, noisy)
  - biotech pipeline               -> ClinicalTrials.gov + SEC filings (independent)
  - SEC-filing financials          -> SEC/EDGAR (audited, independent)

A name in 2 correlated screens (both price-derived) is NOT stronger than one in
1 truly independent screen. Effective-sources drops correlated groups to one.

Output: prints a table of names ranked by EFFECTIVE independent sources, and
flags which "cross-source" names were actually overcounted. Writes
~/<profile>/.. /finance-ai/source_correlation.json for downstream use.

Usage:
  python3 source_corr.py [--csv source_scores.csv]
"""
import os, sys, json, re, glob
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kg_links  # noqa: E402

FINANCE_AI = os.path.expanduser("~/Documents/finance-ai")
KG_NOTES = os.path.expanduser("~/Documents/Finance Knowledge Graph/Notes")
OUT_JSON = os.path.join(FINANCE_AI, "source_correlation.json")

# Underlying data lineages. Independent lineages == genuinely different info.
LINEAGES = {
    "price": "yfinance price",            # momentum/technical/some valuation
    "fundamentals": "yfinance+SEC fundamentals",
    "analyst": "sell-side consensus",
    "fundletters": "hedge-fund positioning",
    "reddit": "retail sentiment (noisy)",
    "biotech": "ClinicalTrials.gov + SEC pipeline",
    "sec": "SEC/EDGAR audited filings",
    "tradingagents": "multi-agent LLM verdict",
}

# screen/scan -> lineage
SCREEN_LINEAGE = {
    # meta_screen.py
    "6m momentum leader (vs SPY)": "price",
    "12m outperformer (vs SPY)": "price",
    "short-term re-acceleration": "price",
    "dip within uptrend": "price",
    "uptrend structure (20>50>200 SMA)": "price",
    "RSI oversold-recovering": "price",
    "proximity to 52w high": "price",
    "recovered from 52w low": "price",
    "cheap fwd P/E (<15)": "fundamentals",
    "low P/B (<2)": "fundamentals",
    "low P/S (<2)": "fundamentals",
    "GARP (cheap + growth)": "fundamentals",
    "high revenue growth (>20%)": "fundamentals",
    "high ROE (>15%)": "fundamentals",
    "net margin >8%": "fundamentals",
    "theme: *": "price",  # theme rotation reads price of basket ETFs
    # alpha scans
    "sell-side analyst": "analyst",
    "analyst consensus": "analyst",
    "hedge fund letter": "fundletters",
    "fund letter": "fundletters",
    "buyside digest": "fundletters",
    "reddit": "reddit",
    "WSB": "reddit",
    "small-cap": "reddit",
    "value Reddit": "reddit",
    "biotech": "biotech",
    "deep value": "fundamentals",
    "sector rundown": "price",
    "TradingAgents": "tradingagents",
    "tradingagents": "tradingagents",
    "cross-source shortlist": "price",  # derived from the above -> not independent itself
}


def lineage_of(note_title):
    tl = note_title.lower()
    # note filenames contain the scan type
    for frag, lineage in SCREEN_LINEAGE.items():
        f = frag.lower()
        if frag.endswith("*"):
            if tl.startswith(f.rstrip("*")):
                return lineage
        elif f in tl:
            return lineage
    return "price"  # default assume price-derived if unknown


def scan_notes():
    """Return list of {title, lineage} for all research/scan notes since a date."""
    # focus on note titles that are scans/screens (alpha scans, Meta-Screen, etc.)
    patterns = ["alpha scan", "Meta-Screen", "sector rundown", "deep value",
                "reddit", "analyst", "hedge fund letter", "biotech", "cross-source"]
    out = []
    for p in sorted(glob.glob(os.path.join(KG_NOTES, "*.md"))):
        title = os.path.splitext(os.path.basename(p))[0]
        if any(pat.lower() in title.lower() for pat in patterns):
            out.append({"title": title, "lineage": lineage_of(title)})
    return out


def parse_overlap_notes():
    """Extract (ticker, set_of_screens) from the cross-source + alpha scan notes.

    Only counts REAL tracked companies: any ticker with a company node in the
    graph, an entry in the meta-screen universe, or on the curated alpha-candidate
    set — so noise words (THAT, AND, AI, PM, ...) never count as a 'source'."""
    tmap = kg_links.load_ticker_map()
    # known stocks that appear as scanners/analysts without full nodes yet
    CANDIDATES = set("""VTRS PBR SM CAG HPQ GIS NVO VALE PRU PFE ADBE GM SOFI NUVB CAPR MU NVDA AMD
    AVGO META GOOGL NFLX DIS T VZ TMUS ROKU SPOT CHRD OVV PBF ET EPD NEM STLD CLF CE OLN
    CX VALE TC Rio PI CHKP JD UWMC CROX PYPL POET TNDM VECO MNDY ENPH ACM ADBE VST NVO HCI
    INGN CHPT PSFE LFVN YJ HAL DVN SLB OXY EOG FANG XOM COP CVX MPC VLO PSX""".split())
    known = set(tmap.keys()) | CANDIDATES
    ticker_sources = {}
    for p in sorted(glob.glob(os.path.join(KG_NOTES, "*.md"))):
        title = os.path.splitext(os.path.basename(p))[0]
        if not any(pat in title for pat in ["alpha scan", "shortlist", "sector rundown", "deep value by GICS", "screener"]):
            continue
        text = open(p, encoding="utf-8").read()
        for m in re.finditer(r"\b([A-Z]{2,5})\b", text):
            tk = m.group(1)
            if tk in known:
                ticker_sources.setdefault(tk, set()).add(title)
    return ticker_sources


def compute_effective(ticker_sources, scan_list):
    """Effective independent lineage-count per ticker."""
    # lineages covered by each source note
    note_lineage = {n["title"]: n["lineage"] for n in scan_list}
    out = []
    for tk, srcs in ticker_sources.items():
        lineages = set()
        for s in srcs:
            lg = note_lineage.get(s, "price")
            lineages.add(lg)
        # effective = number of distinct independent lineages
        eff = len(lineages)
        out.append({
            "ticker": tk,
            "sources_total": len(srcs),
            "effective_sources": eff,
            "lineages": sorted(lineages),
            "overcounted": len(srcs) - eff,  # correlated (same lineage) redundancy
        })
    out.sort(key=lambda r: -r["effective_sources"])
    return out


def main():
    scan_list = scan_notes()
    ticker_sources = parse_overlap_notes()
    eff = compute_effective(ticker_sources, scan_list)

    print("=== SOURCE-CORRELATION / EFFECTIVE-INDEPENDENT-SOURCES ===")
    print(f"{len(scan_list)} scan notes | {len(ticker_sources)} tickers with overlaps\n")
    print("Lineages in play:")
    used_lineages = {}
    for n in scan_list:
        used_lineages[n["lineage"]] = used_lineages.get(n["lineage"], 0) + 1
    for lg, c in used_lineages.items():
        print(f"  {lg} ({LINEAGES.get(lg, lg)}): {c} notes")
    print("\nTop names by EFFECTIVE independent sources:")
    print("| Ticker | Sources | Effective | Overcounted | Lineages |")
    print("|---|---|---|---|---|")
    for r in eff[:20]:
        if r["effective_sources"] < 2:
            break
        print(f"| {r['ticker']} | {r['sources_total']} | {r['effective_sources']} | {r['overcounted']} | {', '.join(r['lineages'])} |")
    # save
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(eff, f, indent=2)
    print(f"\nSaved {OUT_JSON} ({len(eff)} tickers)")


if __name__ == "__main__":
    main()
