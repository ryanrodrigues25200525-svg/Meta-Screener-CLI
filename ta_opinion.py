#!/usr/bin/env python3
"""
ta_opinion.py — connector that runs TradingAgents (multi-agent LLM research firm)
on a ticker you've already researched in the knowledge graph, and banks its
decision into the KG as an independent signal source.

WHY: your PM is deterministic/rule-based. TradingAgents is an independent
multi-agent LLM reasoner (fundamental + sentiment + news + technical analysts,
bull/bear debate, trader, risk, PM). Running it on a shortlist name gives you a
genuinely independent 4th/5th source whose opinion you weight like any other —
plus you track ITS hit-rate from the grade feedback loop.

USE: this runs via the active Python interpreter with langchain +
your TradingAgents install. Each propagate() is ~10+ LLM calls (slow, minutes)
and uses OpenRouter FREE models (rate-limited). Run bounded: 1 ticker to test,
a handful weekly on the shortlist.

HANDLING ITS OUTPUT AS A CLAIM: per the repo, results depend on model/temperature/
data and are "research scaffold, not a strategy." So we treat the TA verdict as
a CLAIM (like Twitter/analyst) — written as evidence_for/evidence_against on the
company's research note + a Sources/TradingAgents node — never as ground truth.
Its hit-rate accumulates from the same grade feedback loop.

Usage:
  python3 ta_opinion.py GM          # run on GM, bank to KG
  python3 ta_opinion.py GM --date 2026-08-20 --dry-run
  python3 ta_opinion.py --shortlist  # loop top-5 shortlist names
"""
import sys, os, json, argparse, re

FINANCE_AI = os.path.dirname(os.path.abspath(__file__))


def _first_existing_dir(*paths):
    for path in paths:
        if os.path.isdir(path):
            return path
    return paths[0]


# The container sees the mounted repositories under /documents. Keep the old
# Mac path only as a host-side fallback for existing launchers.
TA_PROJECT = os.environ.get("TRADINGAGENTS_PROJECT") or _first_existing_dir(
    os.path.join(FINANCE_AI, ".ta-src"),
    "/documents/finance-ai/.ta-src",
    "/Users/ryanrodrigues/Projects Active/TradingAgents",
)
# TradingAgents' __init__ loads .env via find_dotenv(usecwd=True) — it walks from
# CWD. So we must chdir into the TA project BEFORE importing tradingagents, or it
# never finds the OPENROUTER_API_KEY in that project's .env (-> 401). Keep the
# original cwd so relative paths still resolve, then restore it after input.
_orig_cwd = os.getcwd()
if os.path.isdir(TA_PROJECT):
    os.chdir(TA_PROJECT)
    # Load the key from either the finance-ai mount or the TA source checkout.
    # This makes the import independent of the process's original cwd.
    try:
        from dotenv import dotenv_values
        for _dotenv_path in (
            os.path.join(FINANCE_AI, ".env"),
            os.path.join(TA_PROJECT, ".env"),
        ):
            _env = dotenv_values(_dotenv_path)
            for _k, _v in _env.items():
                if _k == "OPENROUTER_API_KEY" and (_v or "") not in (None, ""):
                    os.environ.setdefault("OPENROUTER_API_KEY", _v)
    except Exception:
        pass
sys.path.insert(0, FINANCE_AI)
sys.path.insert(0, TA_PROJECT)

KG_ROOT = os.environ.get("FINANCE_KG_ROOT") or _first_existing_dir(
    "/documents/Finance Knowledge Graph",
    os.path.expanduser("~/Documents/Finance Knowledge Graph"),
)
KG_NOTES = os.path.join(KG_ROOT, "Notes")
KG_COMP = os.path.join(KG_ROOT, "Companies")
KG_SRC = os.path.join(KG_ROOT, "Sources")

# Keep reports, cache, and memory on the mounted finance-ai repo instead of
# volatile /tmp. TradingAgents reads these variables when its config loads.
TA_RUNTIME_DIR = os.environ.get(
    "TRADINGAGENTS_RUNTIME_DIR", os.path.join(FINANCE_AI, ".ta-runtime")
)
TA_RESULTS_DIR = os.path.join(TA_RUNTIME_DIR, "logs")
TA_CACHE_DIR = os.path.join(TA_RUNTIME_DIR, "cache")
TA_MEMORY_PATH = os.path.join(TA_RUNTIME_DIR, "memory", "trading_memory.md")
os.environ.setdefault("TRADINGAGENTS_RESULTS_DIR", TA_RESULTS_DIR)
os.environ.setdefault("TRADINGAGENTS_CACHE_DIR", TA_CACHE_DIR)
os.environ.setdefault("TRADINGAGENTS_MEMORY_LOG_PATH", TA_MEMORY_PATH)

import kg_links  # noqa: E402


def _read_note(title):
    for p in os.listdir(KG_NOTES):
        if title.lower() in p.lower():
            path = os.path.join(KG_NOTES, p)
            return path, open(path, encoding="utf-8").read()
    return None, None


def find_company_note(ticker):
    """Find the research note + company node for a ticker."""
    tmap = kg_links.load_ticker_map()
    ctitle = tmap.get(ticker.upper())
    for p in os.listdir(KG_NOTES):
        if ctitle and ctitle.lower() in p.lower():
            return os.path.join(KG_NOTES, p), ctitle
        if not ctitle and ticker.upper() in p.upper() and "research" in p.lower():
            return os.path.join(KG_NOTES, p), None
    return None, ctitle


def _extract_decision(result):
    """Best-effort parse of propagate()'s decision into a compact verdict."""
    # result is whatever propagate returns (object/dict/str). Try common shapes.
    if result is None:
        return None
    if isinstance(result, dict):
        return json.dumps(result, indent=2, default=str)[:6000]
    # object: look for a repr / decision text
    s = str(result)
    return s[:6000]


def run_ta(ticker, trade_date, dry_run=False):
    """Call TradingAgents.propagate for a ticker. Returns (decision_text, decision_obj)."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG
    config = DEFAULT_CONFIG.copy()
    # force OpenRouter with free models that are RESPONDING (verified HTTP 200
    # at config time). gpt-oss + glm/gemma were shared-pool throttled; Nvidia
    # Nemotron free models are passing traffic now.
    config["llm_provider"] = "openrouter"
    config["backend_url"] = "https://openrouter.ai/api/v1"
    config["deep_think_llm"] = "nvidia/nemotron-3-super-120b-a12b:free"   # 120B, 256k ctx, verified live
    config["quick_think_llm"] = "nvidia/nemotron-3-super-120b-a12b:free"  # use same verified model for quick
    # free-tier runs hit transient 429s/502s; retry so capacity blips don't abort
    config["llm_max_retries"] = 5
    # fewer debate rounds = fewer LLM calls = faster + less likely to hit throttle
    config["max_debate_rounds"] = 1
    config["max_risk_discuss_rounds"] = 1

    if dry_run:
        print(f"[dry-run] would run TradingAgents on {ticker} as of {trade_date}")
        return None, None
    ta = TradingAgentsGraph(debug=False, config=config)
    print(f"[running] TradingAgents on {ticker} as of {trade_date} ... (this takes minutes, ~10+ LLM calls)")
    try:
        state, decision = ta.propagate(ticker, trade_date)
        return _extract_decision(decision), decision
    except Exception as e:
        print(f"[error] {ticker}: {type(e).__name__}: {e}")
        return None, None


def bank_opinion(ticker, decision_text, dry_run=False):
    """Append the TA opinion as evidence + a dated rider on the company's note."""
    note_path, ctitle = find_company_note(ticker)
    if not note_path and not dry_run:
        print(f"  ! no research note found for {ticker} — creating a TA opinion stub")
        note_path = os.path.join(KG_NOTES, f"{__import__('datetime').date.today()} TRADINGAGENTS {ticker} opinion.md")
    rider = (
        f"\n\n## TradingAgents opinion ({ticker}) — {__import__('datetime').date.today()}\n"
        "> Independent multi-agent LLM verdict (OpenRouter free). Treated as a CLAIM — "
        "weighted like any source, its hit-rate tracked by the grade loop.\n"
        f"```\n{decision_text[:2500]}\n```\n"
    )
    if dry_run:
        print(f"[dry-run] would append TA opinion to {note_path}")
        return note_path
    with open(note_path, "a", encoding="utf-8") as f:
        f.write(rider)
    print(f"  -> TA opinion banked on {os.path.basename(note_path)}")
    return note_path


def ensure_source_node():
    sp = os.path.join(KG_SRC, "TradingAgents.md")
    if os.path.exists(sp):
        return sp
    body = (
        "---\ntype: \"source\"\nname: \"TradingAgents\"\nkind: \"AI-framework\"\n"
        "origin: \"https://github.com/TauricResearch/TradingAgents\"\nreliability: 3\n"
        "topics: [\"Multi-agent LLM analysis\"]\n"
        "notes: \"Multi-agent LLM trading framework (analyst team, bull/bear debate, trader, risk, PM). "
        "Run via OpenRouter free models. Output is a CLAIM, not ground truth — its hit-rate is tracked "
        "by the grade feedback loop and used as an independent source weight.\"\n---\n"
        "# TradingAgents\n\n## What it is\nIndependent multi-agent LLM research firm (fundamental/sentiment/news/technical "
        "analysts + bull/bear debate + trader + risk + PM) producing a decision per ticker.\n\n"
        "## How we use it\nSecond/independent opinion on shortlist names. Its verdict is banked as "
        "evidence_for/evidence_against on the company note, weighted like any source, hit-rate-graded.\n\n"
        "## Access\nOpenRouter free models (gpt-oss-120b:free / gpt-oss-20b:free), OPENROUTER_API_KEY. "
        "Slow (~minutes/ticker, ~10+ LLM calls) and rate-limited on free tier.\n"
    )
    with open(sp, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"  created {sp}")
    return sp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", nargs="?", default=None)
    ap.add_argument("--date", default="2026-08-20")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--shortlist", action="store_true")
    args = ap.parse_args()

    ensure_source_node()

    if args.shortlist:
        # top cross-source shortlist names with company notes
        tmap = kg_links.load_ticker_map()
        targets = [t for t in tmap if t in ("GM", "ADBE", "SOFI", "NUVB", "MU", "VZ", "MPC", "VLO", "COP", "CVX")]
        for tk in targets:
            print(f"\n===== {tk} =====")
            dt, _ = run_ta(tk, args.date, dry_run=args.dry_run)
            if dt:
                bank_opinion(tk, dt, dry_run=args.dry_run)
        return

    ticker = (args.ticker or "").upper()
    if not ticker:
        ap.error("provide a ticker (or --shortlist)")
    dt, _ = run_ta(ticker, args.date, dry_run=args.dry_run)
    if dt:
        bank_opinion(ticker, dt, dry_run=args.dry_run)
    else:
        print("no decision returned")


if __name__ == "__main__":
    main()
