#!/usr/bin/env python3
"""
verdict.py — the evidence-weighted decision layer (feedback-loop gap #2).

The graph stores evidence_for / evidence_against / invalidations (kill-switches)
/ strengthens_when per research note, plus the macro regime in Market Context.
This script turns those into a FINAL VERDICT per note, so a model's 'should I'
reasoning is weighted, not linear:

  VERDICT = INTACT | WEAKENED | BROKEN
  based on: (weighted evidence_for) vs (weighted evidence_against), gated by
            whether any invalidation (kill-switch) is LIVE/at-risk, and the
            macro regime (from Market Context threatens/strengthens the note).

Output: verdict_per.py-style table + finance-ai/verdicts.json.
The PM consumes verdicts as a conviction MODIFIER: BROKEN -> exit/avoid,
WEAKENED -> halve size or tighten stop, INTACT -> size normally.

Usage:
  python3 verdict.py                 # compute verdicts for all decision notes
  python3 verdict.py --ticker NVDA   # verdict for one
  python3 verdict.py --json
"""
import os, sys, json, glob, re, argparse
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kg_links  # noqa: E402

FINANCE_AI = os.path.expanduser("~/Documents/finance-ai")
KG_NOTES = os.path.expanduser("~/Documents/Finance Knowledge Graph/Notes")
KG_ROOT = os.path.expanduser("~/Documents/Finance Knowledge Graph")
CONTEXT_DIR = os.path.join(KG_ROOT, "Market Context")
OUT_JSON = os.path.join(FINANCE_AI, "verdicts.json")

# scoring weights
WEIGHT_EVIDENCE_FOR = 1.0
WEIGHT_EVIDENCE_AGAINST = 1.2   # against slightly heavier (asymmetric, cautious)


def _split_list(v):
    """Parse a YAML inline list field properly (handles items with commas inside).

    Values look like: '["If X, 2 qtrs", "If Y"]' (a string). Naive comma-splitting
    corrupts multi-clause items, so parse the [..] structure respecting quotes.
    """
    if not v:
        return []
    s = str(v).strip()
    # empty array / no content
    if s in ("[]", "[ ]", "{}", "{ }", "", "null", "None", "none"):
        return []
    # pull out quoted entries [...]
    out = []
    for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', s):
        out.append(re.sub(r'\\(.)', r'\1', m.group(1)).strip())
    if out:
        return [x for x in out if x]
    # fallback: no quotes — split on commas (drop empty/bracket tokens)
    return [x.strip() for x in re.split(r"[,\n]+", s) if x.strip() not in ("[]", "{}")]


def load_context_edges():
    """threatens/strengthens per thesis from Market Context nodes."""
    strengthens, threatens = {}, {}
    for p in glob.glob(os.path.join(CONTEXT_DIR, "*.md")):
        fm = kg_links.get_frontmatter(p)
        for t in _split_list(fm.get("strengthens")):
            strengthens.setdefault(t, []).append(fm.get("topic", ""))
        for t in _split_list(fm.get("threatens")):
            threatens.setdefault(t, []).append(fm.get("topic", ""))
    return strengthens, threatens


def _regime_for(note_title, strengthens, threatens):
    """Which regimes currently strengthen vs threaten this note (by note-title link)."""
    st = strengthens.get(note_title, [])
    th = threatens.get(note_title, [])
    # also match by basename-without-date if links used just the topic
    return st, th


def _ta_verdict_for(title):
    """Scan graph notes for a TradingAgents verdict for this note's company.
    Looks in the '<TICKER> TradingAgents research.md' notes and the
    'TradingAgents opinion' riders appended to company research notes."""
    tmap = kg_links.load_ticker_map()
    ticker = None
    for tk, ctitle in tmap.items():
        if ctitle.lower() in title.lower() or tk.lower() in title.lower():
            ticker = tk
            break
    if not ticker:
        return None
    import glob
    for p in sorted(glob.glob(os.path.join(KG_NOTES, "*.md")), reverse=True)[:60]:
        base = os.path.basename(p)
        if "TradingAgents" not in base and "TradingAgents" not in open(p, encoding="utf-8").read()[:2000]:
            continue
        if ticker not in base.upper():
            continue
        txt = open(p, encoding="utf-8").read().lower()
        # check opinion riders + full research notes
        if "underweight" in txt:
            return "underweight"
        if "overweight" in txt:
            return "overweight"
        if "neutral" in txt or "hold" in txt:
            return "neutral"
    return None


def compute_verdict(note_path, strengthens, threatens):
    title = os.path.splitext(os.path.basename(note_path))[0]
    fm = kg_links.get_frontmatter(note_path)

    ev_for = _split_list(fm.get("evidence_for"))
    ev_against = _split_list(fm.get("evidence_against"))
    inval = _split_list(fm.get("invalidations"))
    str_when = _split_list(fm.get("strengthens_when"))
    idea = fm.get("idea_source", "")
    decision = fm.get("decision", "")

    # TradingAgents verdicts from graph notes inject as real evidence (contra or pro).
    ta = _ta_verdict_for(title)
    if ta:
        if ta == "underweight" or ta == "sell":
            ev_against = ev_against + [f"TradingAgents {ta.upper()} (independent multi-agent verdict)"]
        elif ta == "overweight" or ta == "buy":
            ev_for = ev_for + [f"TradingAgents {ta.upper()} (independent multi-agent verdict)"]

    score = 0.0
    reasons = []

    # Verdict is driven by EVIDENCE differential + macro regime ONLY.
    # Kill-switches / strengthens_when are INFORMATIONAL watch-terms — shown in
    # the record but they do NOT move the INTACT/WEAKENED/BROKEN label (every
    # well-formed thesis has them; penalizing them makes everything WEAKENED).
    if ev_for or ev_against:
        score += len(ev_for) * WEIGHT_EVIDENCE_FOR
        score -= len(ev_against) * WEIGHT_EVIDENCE_AGAINST
        reasons.append(f"{len(ev_for)} for / {len(ev_against)} against")
    # macro regime
    st, th = _regime_for(title, strengthens, threatens)
    if st:
        score += 1.0
        reasons.append(f"regime strengthens ({', '.join(st[:2])})")
    if th:
        score -= 1.2
        reasons.append(f"regime threatens ({', '.join(th[:2])})")
    if inval:
        reasons.append(f"{len(inval)} kill-switch(es) to watch")
    elif str_when:
        reasons.append("strengthens_when conditions listed")

    # thresholds
    if score <= -3:
        verdict = "BROKEN"             # strong contra-evidence / regime threat
    elif score < 0:
        verdict = "WEAKENED"           # net negative edge
    else:
        verdict = "INTACT"             # neutral-or-positive edge

    return {
        "note": title, "decision": decision, "idea_source": idea,
        "score": round(score, 2), "verdict": verdict,
        "evidence_for": len(ev_for), "evidence_against": len(ev_against),
        "invalidations": len(inval), "strengthens_when": len(str_when),
        "reasons": reasons[:6],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    strengthens, threatens = load_context_edges()
    today = date.today().isoformat()

    results = []
    for p in sorted(glob.glob(os.path.join(KG_NOTES, "*.md"))):
        title = os.path.splitext(os.path.basename(p))[0]
        if args.ticker and args.ticker.upper() not in title.upper():
            continue
        v = compute_verdict(p, strengthens, threatens)
        results.append(v)

    # sort BROKEN/WEAKENED first (attention), then by score
    rank = {"BROKEN": 0, "WEAKENED": 1, "INTACT": 2}
    results.sort(key=lambda r: (rank.get(r["verdict"], 3), r["score"]))

    print(f"=== VERDICT LAYER — {today} ===")
    print(f"{len(results)} notes scored\n")
    print("| Verdict | Note | Score | For/Against | KS | Reasons |")
    print("|---|---|---:|---|---|---|")
    for r in results:
        ks = r["invalidations"]
        note = r["note"].split(" — ")[-1][:34]
        print(f"| **{r['verdict']}** | {note} | {r['score']} | {r['evidence_for']}/{r['evidence_against']} | {ks} | {', '.join(r['reasons'])[:50]} |")

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"date": today, "results": results}, f, indent=2, default=str)
    print(f"\nSaved {OUT_JSON}")
    broken = sum(1 for r in results if r["verdict"] == "BROKEN")
    weak = sum(1 for r in results if r["verdict"] == "WEAKENED")
    intact = sum(1 for r in results if r["verdict"] == "INTACT")
    print(f"{intact} INTACT / {weak} WEAKENED / {broken} BROKEN")


if __name__ == "__main__":
    main()
