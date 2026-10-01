#!/usr/bin/env python3
"""
ta_research.py — run TradingAgents as a GENERAL research engine and bank the
full multi-agent report set into the knowledge graph.

Extends ta_opinion.py (which only captured the verdict label) by reading the
complete report set TradingAgents writes to TRADINGAGENTS_RESULTS_DIR:
  - fundamentals_report.md      (fundamental analyst)
  - sentiment_report.md         (sentiment analyst)
  - news_report.md              (news analyst)
  - market_report.md            (technical + market)
  - trader_investment_plan.md   (trader)
  - final_trade_decision.md     (trader decision)
  - trading_memory.md           (persistent decision log w/ entry/stop/target)
  - full_states_log_*.json      (every agent's final state)

Usage (MUST run with the interpreter that has langchain + your TA install):
  python3 ta_research.py GM
      # run full pipeline + bank every report into Notes/<date> GM TradingAgents.md
  python3 ta_research.py GM --method "TA fundamental only"
      # still runs full pipeline (TA is one graph), but you can request a focus
  python3 ta_research.py GM ADBE SOFI NUVB
      # loop several names (slow on free tier — a few min each)

WITH $10 CREDITS + free calls this is now viable as a standing research arm.
"""
import sys, os, json, glob, argparse, time, threading
from datetime import date

FINANCE_AI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, FINANCE_AI)

import ta_opinion as TA  # reuse the loader + key injection + run/back helpers

KG_NOTES = TA.KG_NOTES
TA_LOGS = TA.TA_RESULTS_DIR


def _run_ta(ticker, trade_date, retries=3):
    """Run TA with whole-run retries for transient provider/backend failures."""
    last = (None, None)
    for attempt in range(1, retries + 1):
        # Hermes cron has an idle-output watchdog. Keep it informed while the
        # non-streaming provider call is working so a healthy long run is not
        # mistaken for a hung backend.
        stop = threading.Event()
        heartbeat = threading.Thread(
            target=_heartbeat, args=(ticker, attempt, stop), daemon=True
        )
        heartbeat.start()
        try:
            last = TA.run_ta(ticker, trade_date, dry_run=False)
        finally:
            stop.set()
            heartbeat.join(timeout=2)
        if last[0]:
            return last
        if attempt < retries:
            delay = 30 * attempt
            print(f"[retry] {ticker}: no decision; retrying in {delay}s", flush=True)
            time.sleep(delay)
    return last


def _heartbeat(ticker, attempt, stop, interval=45):
    while not stop.wait(interval):
        print(f"[heartbeat] {ticker}: TradingAgents still running (attempt {attempt})", flush=True)


def gather_reports(ticker, trade_date):
    """Collect all report .md files TradingAgents wrote, PLUS the rich
    full_states_log JSON (which free-tier runs write even when the per-report
    .md bundle isn't emitted — it carries the full judge/trader decision)."""
    base = os.path.join(TA_LOGS, ticker, trade_date, "reports")
    reports = {}
    if os.path.isdir(base):
        for f in sorted(os.listdir(base)):
            if f.endswith(".md"):
                p = os.path.join(base, f)
                reports[f] = open(p, encoding="utf-8").read()
    # full_states_log (states-based runs) — carry the richest decision fields
    for f in glob.glob(os.path.join(TA_LOGS, ticker, "**", "full_states_log_*.json"), recursive=True):
        try:
            d = json.load(open(f, encoding="utf-8"))
            if d:
                reports["full_states_log_" + os.path.basename(f)] = json.dumps(d, indent=2, default=str)[:20000]
        except Exception:
            pass
    # trading memory (persistent decision)
    mem = TA.TA_MEMORY_PATH
    if os.path.exists(mem):
        reports["trading_memory.md"] = open(mem, encoding="utf-8").read()
    return reports


def bank_full_report(ticker, trade_date, reports, decision_text):
    """Write one comprehensive research note with all TA reports + the verdict."""
    today = date.today().isoformat()
    note_path = os.path.join(KG_NOTES, f"{today} {ticker} TradingAgents research.md")
    from datetime import datetime
    head = (
        "---\ntype: \"research-note\"\n"
        f'date: "{today}"\n'
        f'topic: "TradingAgents multi-agent research — {ticker}"\n'
        f'companies: []\n'
        f'themes: []\n'
        'context: ["[[Risk appetite]]"]\n'
        'sources: ["[[TradingAgents]]"]\n'
        'status: "open"\nimportance: 4\n'
        'idea_source: "AI-routed"\n'
        'catalysts: []\ninvalidations: []\nstrengthens_when: []\n'
        'evidence_for: []\nevidence_against: []\n'
        f'decision: ""\nentry: ""\nexit: ""\nrealized_return: ""\nvs_spy: ""\n'
        f'holding_days: ""\nmodel_source: "tradingagents"\noutcome: ""\ntrack_updated: ""\n'
        "---\n"
        f"# TradingAgents research — {ticker} ({trade_date})\n\n"
        "> Full multi-agent LLM report set (Nvidia Nemotron 120B free). Treated as research "
        "(claims), hit-rate-tracked. Generated by ta_research.py.\n\n"
    )
    body = [head]
    if decision_text:
        body.append("## Final decision\n")
        body.append(f"```\n{decision_text[:1500]}\n```\n")
    for name in ("fundamentals_report.md", "trader_investment_plan.md",
                 "sentiment_report.md", "news_report.md", "market_report.md"):
        if name in reports:
            body.append(f"## {name.replace('_report.md','').replace('_',' ').title()}\n")
            body.append(reports[name][:4000] + "\n")
    body.append("\n---\n*Banked by ta_research.py — independent multi-agent LLM research, "
                "a claim to be graded against SPY via the feedback loop.*\n")
    os.makedirs(os.path.dirname(note_path), exist_ok=True)
    with open(note_path, "w", encoding="utf-8") as f:
        f.write("\n".join(body))
    print(f"  -> FULL TA research banked to {os.path.basename(note_path)}")
    return note_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="+")
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()

    for tk in args.tickers:
        ticker = tk.upper()
        print(f"\n===== TradingAgents research: {ticker} =====")
        dt, _ = _run_ta(ticker, args.date)
        reports = gather_reports(ticker, args.date)
        # also bank the short opinion on any existing company note (like ta_opinion)
        if dt:
            TA.bank_opinion(ticker, dt, dry_run=False)
        bank_full_report(ticker, args.date, reports, dt)
        print(f"  [{len(reports)} report files captured]")


if __name__ == "__main__":
    main()
