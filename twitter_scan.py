#!/usr/bin/env python3
"""
twitter_scan.py — pulls recent posts from ~12 curated finance accounts (short
researchers, semi analysts, quant/macro) and writes
~/Documents/Finance Knowledge Graph/Notes/<today> Twitter Claims.md, flagging
decision-relevant tweets by signal category.

EVERY TWEET IS A CLAIM, NOT A FACT — short/activist accounts are inherently
biased per their disclaimers. This feeds the Claims/ credibility layer.

Fetch methods (first working one wins, per account):
  1. `twitter` CLI on PATH: `twitter posts <handle> --limit N`
     (install + auth per the CLI's own docs; cron PATH must include it)
  2. Exa Search API fallback: set EXA_API_KEY in the environment or in
     finance-ai/.env (single line: EXA_API_KEY=...). Queries are
     domain-restricted to x.com per handle. No key = method skipped.
If neither is available the run records an explicit per-account fetch gap
instead of silently reporting "0 posts" (root cause of the Aug-Sep 2026
silent-zero runs: `twitter` binary was never reinstalled after the
finance-ai stack was recreated, and fetch_account() swallowed the
FileNotFoundError into []).

Usage: python3 twitter_scan.py [--limit 5]   (run bounded — CLI is slow)
"""
import os, sys, json, argparse, shutil, urllib.request
from datetime import date

KG_NOTES = os.path.expanduser("~/Documents/Finance Knowledge Graph/Notes")
HERE = os.path.dirname(os.path.abspath(__file__))

SIGNAL_CATS = {
    "short/thesis": ["short", "fraud", "mislead", "overvalue", "red flag"],
    "earnings/guidance": ["earnings", "guidance", "eps", "revenue"],
    "M&A/corporate": ["merger", "acquisition", "deal", "buyout"],
    "filing/regulatory": ["8-k", "10-k", "sec", "fda", "regulatory", "lawsuit"],
    "semi/AI": ["ai", "gpu", "semiconductor", "nvidia", "cuda", "capex"],
    "rates/macro": ["fed", "rates", "inflation", "yield"],
    "valuation": ["p/e", "valuation", "multiple"],
    "ownership/13f": ["13f", "stake", "position", "buys", "sells"],
}

ACCOUNTS = {
    "muddywatersre": ("Muddy Waters (Carson Block)", "short/activist"),
    "sprucepointcap": ("Spruce Point Capital (Ben Axler)", "short/activist"),
    "culperresearch": ("Culper Research", "short/activist"),
    "fuzzypandafund": ("Fuzzy Panda Research", "short/activist"),
    "wolfpackresearch": ("Wolfpack Research", "short/activist"),
    "jcapitalresearch": ("J Capital Research", "short/activist"),
    "viceroyresearch": ("Viceroy Research", "short/activist"),
    "bonnerresearch": ("Bonner Research", "short/activist"),
    "semi_analysis": ("SemiAnalysis", "semi/AI"),
    "dylanpatel": ("Dylan Patel (SemiAnalysis)", "semi/AI"),
    "dergigi": ("dergigi (macro/quant)", "quant/macro"),
    "mikerecane": ("Mike Recane", "quant/macro"),
    "gregoryblotnick": ("Gregory Blotnick (Valiant Research)", "equity researcher"),
}

TWITTER_BIN = shutil.which("twitter")


def _load_dotenv():
    for name in (os.path.join(HERE, ".env"), os.path.expanduser("~/.env")):
        try:
            with open(name, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))
        except OSError:
            pass


_load_dotenv()
EXA_KEY = os.environ.get("EXA_API_KEY", "").strip()


def classify(text):
    tl = (text or "").lower()
    return [cat for cat, kws in SIGNAL_CATS.items() if any(k in tl for k in kws)]


def fetch_via_cli(handle, limit):
    if not TWITTER_BIN:
        return [], "twitter-cli binary not on PATH"
    import subprocess
    out = []
    try:
        r = subprocess.run(
            ["env", "-u", "PYTHONPATH", "twitter", "posts", handle, "--limit", str(limit)],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            err = (r.stderr or "").strip().splitlines()
            return [], "twitter-cli exit %s: %s" % (r.returncode, err[0][:160] if err else "no stderr")
        try:
            data = json.loads(r.stdout)
        except Exception:
            return [], "twitter-cli returned non-JSON output"

        def walk(x):
            if isinstance(x, list):
                for i in x:
                    walk(i)
            elif isinstance(x, dict):
                if "text" in x and ("created_at" in x or "id" in x):
                    out.append({"handle": handle, "text": x["text"],
                                "created_at": x.get("created_at", ""),
                                "id": x.get("id", ""), "url": x.get("url", "")})
                for v in x.values():
                    walk(v)
        walk(data)
    except FileNotFoundError:
        return [], "twitter-cli binary not on PATH"
    except Exception as e:
        return [], "twitter-cli error: %s" % str(e)[:160]
    if not out:
        return [], "twitter-cli returned 0 posts (auth/rate-limit/empty?)"
    return out, None


def fetch_via_exa(handle, limit):
    if not EXA_KEY:
        return [], "no EXA_API_KEY (env or finance-ai/.env)"
    out = []
    try:
        payload = json.dumps({
            "query": "recent X posts from @%s" % handle,
            "includeDomains": ["x.com"],
            "numResults": max(limit, 5),
            "contents": {"text": {"maxCharacters": 600}, "highlights": True},
        }).encode()
        req = urllib.request.Request(
            "https://api.exa.ai/search", data=payload,
            headers={"Content-Type": "application/json", "x-api-key": EXA_KEY},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        for r in data.get("results", []):
            url = r.get("url", "")
            if handle.lower() not in url.lower():
                continue
            hl = r.get("highlights") or []
            text = " ".join(hl)[:600] if hl else (r.get("text") or "")[:600]
            if not text.strip():
                continue
            out.append({"handle": handle, "text": text.strip(),
                        "created_at": r.get("publishedDate", ""),
                        "id": "", "url": url})
            if len(out) >= limit:
                break
    except Exception as e:
        return [], "exa error: %s" % str(e)[:160]
    if not out:
        return [], "exa returned 0 x.com results for this handle"
    return out, None


def fetch_account(handle, limit):
    posts, gap = fetch_via_cli(handle, limit)
    if posts:
        return posts, "twitter-cli", None
    cli_gap = gap
    posts, gap = fetch_via_exa(handle, limit)
    if posts:
        return posts, "exa", None
    return [], "none", "cli: %s; exa: %s" % (cli_gap, gap)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()

    all_flagged, scanned, gaps, methods = [], 0, {}, set()
    for handle, (disp, bias) in ACCOUNTS.items():
        posts, method, gap = fetch_account(handle, args.limit)
        if gap:
            gaps[handle] = gap
            print("  @%s: GAP (%s)" % (handle, gap))
        else:
            methods.add(method)
        scanned += len(posts)
        for p in posts:
            flags = classify(p["text"])
            if flags:
                all_flagged.append({**p, "display": disp, "bias": bias, "signals": flags})

    _write_note(date.today().isoformat(), all_flagged, scanned, gaps, methods)


def _write_note(today, items, scanned, gaps, methods):
    os.makedirs(KG_NOTES, exist_ok=True)
    method_str = ", ".join(sorted(methods)) if methods else "none (all accounts gap)"
    front = (
        "---\n"
        'type: "research-note"\n'
        'date: "%s"\n' % today +
        'topic: "Twitter claims — %d flagged across %d curated accounts"\n' % (len(items), len(ACCOUNTS)) +
        'companies: []\n'
        'themes: [""]\n'
        'context: [""]\n'
        'sources: ["[[X Twitter accounts]]"]\n'
        'status: "open"\n'
        'importance: 4\n'
        "---\n\n"
    )
    body = ["# Twitter Claims %s\n" % today,
            "Scanned %d posts across %d curated accounts (fetch: %s). %d flagged as decision-relevant claims.\n" % (scanned, len(ACCOUNTS), method_str, len(items)),
            "**Every tweet is a CLAIM, not a fact.** Short/activist accounts are both directions biased.\n"]
    if not items:
        body.append("- No flagged tweets in this run (see fetch gaps below — coverage may be zero).")
    for it in items:
        body.append("### @%s (%s, %s)\n_%s_ \u00b7 signals: %s" % (it['handle'], it['display'], it['bias'], it['created_at'], it['signals']))
        text = (it["text"] or "").strip()
        body.append("> %s" % text[:400])
        if it.get("url"):
            body.append("<%s>" % it['url'])
        if it.get("id"):
            body.append("<https://x.com/%s/status/%s>" % (it['handle'], it['id']))
        body.append("")
    body.append("\n## Fetch gaps (honest coverage)\n")
    if gaps:
        for h, g in gaps.items():
            body.append("- @%s: %s" % (h, g))
    else:
        body.append("- None — all accounts returned posts.")
    if not TWITTER_BIN:
        body.append("- Setup: `twitter` CLI not on PATH. Install it (with auth) OR add EXA_API_KEY to finance-ai/.env for the Exa fallback.")
    elif not EXA_KEY:
        body.append("- Setup: no EXA_API_KEY in env or finance-ai/.env — Exa fallback disabled; CLI-only coverage.")
    title = os.path.join(KG_NOTES, "%s Twitter Claims.md" % today)
    with open(title, "w", encoding="utf-8") as f:
        f.write(front + "\n".join(body) + "\n")
    print("wrote", title)
    print("scanned %d posts, %d flagged, %d gaps" % (scanned, len(items), len(gaps)))


if __name__ == "__main__":
    main()
