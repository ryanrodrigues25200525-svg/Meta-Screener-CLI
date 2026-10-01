#!/usr/bin/env python3
"""
ta_lite.py — lightweight TradingAgents-style research for the Finance KG.

Why: the full TradingAgents graph fires ~10+ LLM calls per ticker (10-20 min on
free models). ta_lite keeps the SPIRIT — analyst synthesis -> adversarial
red-team -> verdict — in 2 LLM calls on top of a deterministic yfinance data
pack: ~2-4 min per ticker, and it banks a fully-conformed research note
(findings with numbers, bull/bear, falsifiable kill-switches, catalysts,
track-record stubs) that the grade loop can score.

Output:
  Notes/<date> <TICKER> TradingAgents research.md   (model_source: ta-lite)
  + a short opinion rider appended to the company note, if one exists.

Usage:
  python3 ta_lite.py MU
  python3 ta_lite.py MU AMD SOFI NUVB
  python3 ta_lite.py MU --dry                 # data pack only, no LLM, no writes
  python3 ta_lite.py MU --passes 1            # skip red-team (1 call)
  python3 ta_lite.py MU --model google/gemini-2.5-flash
  python3 ta_lite.py MU --bank-from /tmp/mu.json
      # bank a JSON produced elsewhere (e.g. a Hermes agent doing the 2-pass
      # synthesis itself when OpenRouter credits/free models are unavailable).
      # JSON schema = the same one the LLM passes use; optional "revisions" key.
"""
import argparse, json, math, os, re, sys, time
from datetime import date

FINANCE_AI = os.path.dirname(os.path.abspath(__file__))


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
KG_COMP = os.path.join(KG_ROOT, "Companies")

MODEL_CHAIN_DEFAULT = [
    "google/gemini-2.5-flash",
    "deepseek/deepseek-chat",
    "minimax/minimax-m3",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
]


def load_key():
    k = os.environ.get("OPENROUTER_API_KEY")
    if k:
        return k
    for p in (os.path.join(FINANCE_AI, ".env"), os.path.join(FINANCE_AI, ".ta-src", ".env")):
        try:
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line.startswith("OPENROUTER_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return None


# ---------------- data pack ----------------

def _f(x, nd=2):
    try:
        return round(float(x), nd)
    except Exception:
        return None


def build_pack(ticker):
    try:
        import yfinance as yf
    except ImportError:
        print("! yfinance not installed for this interpreter", file=sys.stderr)
        sys.exit(2)

    pack = {"ticker": ticker, "asof": date.today().isoformat()}
    t = yf.Ticker(ticker)
    try:
        info = t.info or {}
    except Exception:
        info = {}

    def g(*keys):
        for k in keys:
            v = info.get(k)
            if v not in (None, ""):
                return v
        return None

    pack["name"] = g("shortName", "longName")
    pack["sector"] = g("sector")
    pack["industry"] = g("industry")
    mc = g("marketCap")
    pack["market_cap_bn"] = round(mc / 1e9, 1) if isinstance(mc, (int, float)) else None
    pack["pe_fwd"] = _f(g("forwardPE"), 1)
    pack["pe_ttm"] = _f(g("trailingPE"), 1)
    pack["ps"] = _f(g("priceToSalesTrailing12Months"), 1)
    pm = g("profitMargins")
    pack["profit_margin_pct"] = round(pm * 100, 1) if isinstance(pm, (int, float)) else None
    rg = g("revenueGrowth")
    pack["rev_growth_yoy_pct"] = round(rg * 100, 1) if isinstance(rg, (int, float)) else None
    eg = g("earningsGrowth")
    pack["eps_growth_yoy_pct"] = round(eg * 100, 1) if isinstance(eg, (int, float)) else None
    tgt = g("targetMeanPrice")
    cur = g("currentPrice", "regularMarketPrice")
    if isinstance(tgt, (int, float)) and isinstance(cur, (int, float)) and cur:
        pack["analyst_target_upside_pct"] = round((tgt / cur - 1) * 100, 1)

    try:
        hist = t.history(period="1y", interval="1d")
    except Exception:
        hist = None
    if hist is not None and len(hist) > 5:
        closes = hist["Close"].dropna()
        if len(closes) > 5:
            px = float(closes.iloc[-1])
            pack["price"] = round(px, 2)

            def ret(days):
                if len(closes) > days:
                    return round((px / float(closes.iloc[-days - 1]) - 1) * 100, 1)
                return None

            pack["ret_1m_pct"] = ret(21)
            pack["ret_3m_pct"] = ret(63)
            pack["ret_6m_pct"] = ret(126)
            if len(closes) >= 200:
                sma200 = float(closes.tail(200).mean())
                pack["vs_sma200_pct"] = round((px / sma200 - 1) * 100, 1)
            hi52 = float(closes.max())
            pack["pct_off_52w_high"] = round((px / hi52 - 1) * 100, 1)
            rr = closes.pct_change().dropna().tail(20)
            if len(rr) > 5:
                pack["vol_20d_ann_pct"] = round(float(rr.std()) * math.sqrt(252) * 100, 0)

    try:
        cal = t.calendar or {}
        ed = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if ed:
            pack["next_earnings"] = str(ed[0] if isinstance(ed, list) else ed)[:10]
    except Exception:
        pass

    news = []
    try:
        for n in (t.news or [])[:8]:
            c = n.get("content", n) if isinstance(n, dict) else {}
            title = (c.get("title") or n.get("title") or "").strip()
            prov = c.get("provider") or {}
            pub = (prov.get("displayName") if isinstance(prov, dict) else None) or n.get("publisher") or ""
            when = c.get("pubDate") or n.get("providerPublishTime") or ""
            if title:
                news.append({"title": title[:160], "publisher": str(pub)[:40], "date": str(when)[:10]})
    except Exception:
        pass
    pack["news"] = news
    return pack


def kg_context(ticker):
    ctx = {}
    try:
        for p in os.listdir(KG_COMP):
            if not p.endswith(".md"):
                continue
            fp = os.path.join(KG_COMP, p)
            try:
                head = open(fp, encoding="utf-8").read(1500)
            except Exception:
                continue
            m = re.search(r'^ticker:\s*"?([A-Za-z0-9.\-]+)"?', head, re.M)
            if m and m.group(1).upper() == ticker:
                ctx["company_note_title"] = p[:-3]
                nb = re.search(r'^notes:\s*"(.+)"\s*$', head, re.M)
                if nb:
                    ctx["company_brief"] = nb.group(1)[:300]
                break
    except Exception:
        pass
    lp = os.path.join(KG_ROOT, "Research-Lessons.md")
    if os.path.exists(lp):
        try:
            ctx["lessons"] = open(lp, encoding="utf-8").read()[:1200]
        except Exception:
            pass
    return ctx


# ---------------- LLM ----------------

def llm(model, messages, api_key, max_tokens=1500, temperature=0.25, timeout=180, json_mode=True):
    import requests
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
            "HTTP-Referer": "https://nautiluscapital.org",
            "X-Title": "ta_lite",
        },
        json=payload,
        timeout=timeout,
    )
    if r.status_code != 200:
        # some models reject response_format — retry once without it
        if json_mode and r.status_code in (400, 404, 422):
            return llm(model, messages, api_key, max_tokens=max_tokens,
                       temperature=temperature, timeout=timeout, json_mode=False)
        raise RuntimeError("HTTP %s: %s" % (r.status_code, r.text[:180]))
    j = r.json()
    choice = (j.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = msg.get("content")
    if not content:
        raise RuntimeError("empty message content (finish_reason=%s)" % choice.get("finish_reason"))
    return content


def extract_json(text):
    if not text:
        raise ValueError("empty reply")
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("no JSON object in reply")
    cands = [s[i:j + 1]]
    for off in range(1, 6):
        if i + off < j:
            cands.append(s[i + off:j + 1])
    for cand in cands:
        cand = re.sub(r",\s*([}\]])", r"\1", cand)
        try:
            return json.loads(cand)
        except Exception:
            try:
                return json.loads(cand, strict=False)
            except Exception:
                continue
    raise ValueError("unparseable JSON object")


def ask_json(models, messages, key, **kw):
    errs = []
    for m in models:
        print("  [llm] trying %s" % m, flush=True)
        raws = []
        base_messages = list(messages)
        for attempt in (1, 2):
            out = None
            try:
                out = llm(m, base_messages, key, json_mode=True, **kw)
            except Exception as e:
                errs.append("%s: %s" % (m, str(e)[:200]))
                break
            try:
                return extract_json(out), m
            except Exception as e:
                raws.append(out[:280].replace("\n", " "))
                if attempt == 1:
                    base_messages = base_messages + [{"role": "user",
                        "content": "Your reply was not valid JSON. Reply with ONLY the JSON object — nothing else."}]
                    continue
                errs.append("%s: bad JSON twice | %s | raw1: %s || raw2: %s"
                            % (m, str(e)[:130], raws[0] if raws else "", raws[-1] if len(raws) > 1 else ""))
        time.sleep(1)
    raise RuntimeError("all models failed => " + " | ".join(errs))


SYS = ("You are the research desk of a small equity fund. Terse, data-driven, no fluff, "
       "no boilerplate hedging. Use ONLY the provided data pack and context; if something "
       "is unknown, write 'not in data'. Never fabricate numbers.")

SCHEMA = (
    '{"findings":[{"point":"...","support":"<number or source from the pack>"}],'
    '"bull":["..."],"bear":["..."],'
    '"kill_switches":["if <observable condition>, <thesis> breaks"],'
    '"catalysts":[{"what":"...","when":"..."}],'
    '"verdict":{"label":"ATTRACTIVE|NEUTRAL|AVOID","conviction":1,"one_line":"...","what_would_change":"..."},'
    '"open_questions":["..."]}'
)


def p1_messages(ticker, pack):
    return [
        {"role": "system", "content": SYS},
        {"role": "user", "content": (
            "DATA PACK (live, from yfinance + vault context):\n" + json.dumps(pack, indent=1) +
            "\n\nWrite a compact research read on %s as a JSON object with EXACTLY this schema:\n%s\n\n"
            "Rules: 3-5 findings (each MUST cite a number/source from the pack); 2-3 bull; 2-3 bear; "
            "1-3 kill_switches, each falsifiable (observable future condition); 0-3 catalysts; "
            "verdict conviction 1-5. Reply with ONLY the JSON object." % (ticker, SCHEMA)
        )},
    ]


def p2_messages(ticker, pack, draft):
    return [
        {"role": "system", "content": SYS + " You are now the adversarial reviewer: your job is to BREAK this draft."},
        {"role": "user", "content": (
            "DATA PACK:\n" + json.dumps(pack, indent=1) +
            "\n\nDRAFT (pass 1):\n" + json.dumps(draft, indent=1) +
            "\n\nAttack it: (a) claims not supported by the pack, (b) what a short-seller would add, "
            "(c) kill-switches that are not actually falsifiable, (d) overconfidence in the verdict. "
            'Return REVISED JSON with this shape: {"revisions":["..."], ' + SCHEMA[1:] +
            " Reply with ONLY the JSON object."
        )},
    ]


# ---------------- banking ----------------

def _arr(items):
    out = []
    for s in items or []:
        s = str(s).replace('"', "'").replace("\n", " ").strip()
        if s:
            out.append('"%s"' % s)
    return "[" + ", ".join(out) + "]"


def _bullets(items):
    items = [str(x) for x in (items or []) if str(x).strip()]
    return "\n".join("- " + x for x in items) if items else "- (none)"


def bank(ticker, pack, core, revisions, ctx, meta):
    today = date.today().isoformat()
    v = core.get("verdict", {}) if isinstance(core, dict) else {}
    comp_link = '["[[%s]]"]' % ctx["company_note_title"] if ctx.get("company_note_title") else "[]"
    ks = core.get("kill_switches", []) or []
    cats = core.get("catalysts", []) or []
    cat_strs = [(str(c.get("when", "")) + " — " + str(c.get("what", ""))).strip(" —") if isinstance(c, dict) else str(c) for c in cats]
    head = (
        "---\ntype: \"research-note\"\n"
        'date: "%s"\n'
        'topic: "TradingAgents-lite research — %s"\n'
        "companies: %s\nthemes: []\ncontext: []\n"
        'sources: ["[[yfinance]]", "[[TradingAgents]]"]\n'
        'status: "open"\nimportance: 3\nidea_source: "AI-routed"\n'
        "catalysts: %s\ninvalidations: %s\nstrengthens_when: []\n"
        "evidence_for: []\nevidence_against: []\n"
        'decision: ""\nentry: ""\nexit: ""\nrealized_return: ""\nvs_spy: ""\n'
        'holding_days: ""\nmodel_source: "ta-lite"\noutcome: ""\ntrack_updated: ""\n'
        "---\n" % (today, ticker, comp_link, _arr(cat_strs), _arr(ks))
    )
    body = [head]
    body.append("# TradingAgents-lite research — %s (%s)\n" % (ticker, today))
    body.append("> 2-pass LLM research (synthesis -> red-team) on a live data pack. A CLAIM to be "
                "graded vs SPY by the feedback loop — not ground truth. %s\n" % meta.get("stamp", ""))
    body.append("## Question\nWhat does the current data imply for %s right now?\n" % ticker)
    findings = core.get("findings", []) or []
    body.append("## What we found\n" + ("\n".join(
        "- %s — support: %s" % (f.get("point", ""), f.get("support", "?")) if isinstance(f, dict) else "- " + str(f)
        for f in findings) or "- (none)") + "\n")
    body.append("## Bull case\n" + _bullets(core.get("bull")) + "\n")
    body.append("## Bear case\n" + _bullets(core.get("bear")) + "\n")
    body.append("## Kill-switches\n" + _bullets(ks) + "\n")
    body.append("## Catalysts\n" + _bullets(cat_strs) + "\n")
    body.append("## Verdict\n**%s** (conviction %s/5) — %s\nWould change on: %s\n" % (
        v.get("label", "?"), v.get("conviction", "?"), v.get("one_line", ""), v.get("what_would_change", "")))
    body.append("## What's still open\n" + _bullets(core.get("open_questions")) + "\n")
    if revisions:
        body.append("## Red-team revisions\n" + _bullets(revisions) + "\n")
    body.append("---\n*ta_lite.py — %s. A claim; hit-rate graded via the feedback loop.*\n" % meta.get("stamp", ""))

    note_path = os.path.join(KG_NOTES, "%s %s TradingAgents research.md" % (today, ticker))
    os.makedirs(KG_NOTES, exist_ok=True)
    with open(note_path, "w", encoding="utf-8") as f:
        f.write("\n".join(body))

    if ctx.get("company_note_title"):
        cp = os.path.join(KG_COMP, ctx["company_note_title"] + ".md")
        rider = (
            "\n\n## TradingAgents-lite opinion (%s) — %s\n"
            "> 2-pass LLM research (synthesis -> red-team). A CLAIM — hit-rate graded by the loop.\n"
            "```\nVERDICT: %s (conviction %s/5) — %s\n```\n" % (
                ticker, today, v.get("label", "?"), v.get("conviction", "?"), v.get("one_line", ""))
        )
        try:
            with open(cp, "a", encoding="utf-8") as f:
                f.write(rider)
            print("  -> rider appended to %s" % ctx["company_note_title"])
        except Exception as e:
            print("  ! rider failed: %s" % e)
    return note_path


# ---------------- main ----------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="+")
    ap.add_argument("--model", default=None, help="force a single OpenRouter model id")
    ap.add_argument("--passes", type=int, default=2, choices=[1, 2])
    ap.add_argument("--dry", action="store_true", help="data pack only — no LLM, no writes")
    ap.add_argument("--bank-from", default=None,
                    help="bank a JSON file (same schema; optional 'revisions') produced elsewhere, e.g. by a Hermes agent")
    args = ap.parse_args()

    key = load_key()
    if not args.dry and not args.bank_from and not key:
        print("! OPENROUTER_API_KEY not found (checked env + finance-ai/.env)")
        sys.exit(2)
    chain = [args.model] if args.model else MODEL_CHAIN_DEFAULT

    for tk in args.tickers:
        ticker = tk.upper()
        t0 = time.time()
        print("===== ta_lite: %s =====" % ticker, flush=True)
        try:
            if args.bank_from:
                payload = json.load(open(args.bank_from, encoding="utf-8"))
                revisions = payload.pop("revisions", []) if isinstance(payload, dict) else []
                ctx = kg_context(ticker)
                stamp = "agent-synthesized (2-pass) | banked by ta_lite | %.0fs" % (time.time() - t0)
                note_path = bank(ticker, None, payload, revisions, ctx, {"stamp": stamp})
                print("  -> %s  [%s]" % (os.path.basename(note_path), stamp), flush=True)
                continue
            pack = build_pack(ticker)
            ctx = kg_context(ticker)
            pack["kg_context"] = ctx
            if args.dry:
                print(json.dumps(pack, indent=1)[:4500])
                continue
            msgs = p1_messages(ticker, pack)
            core, m1 = ask_json(chain, msgs, key, max_tokens=3000)
            revisions = []
            if args.passes >= 2:
                core2, m2 = ask_json(chain, p2_messages(ticker, pack, core), key, max_tokens=3500)
                revisions = core2.pop("revisions", []) if isinstance(core2, dict) else []
                core = core2
                m1 = m2
            stamp = "Passes: %d | model: %s | %.0fs" % (args.passes, m1, time.time() - t0)
            note_path = bank(ticker, pack, core, revisions, ctx, {"stamp": stamp})
            print("  -> %s  [%s]" % (os.path.basename(note_path), stamp), flush=True)
        except Exception as e:
            print("  ! %s FAILED: %s: %s" % (ticker, type(e).__name__, str(e)[:400]), flush=True)


if __name__ == "__main__":
    main()
