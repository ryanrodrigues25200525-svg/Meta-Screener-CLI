#!/usr/bin/env python3
"""ticker_nodes.py — create company/ETF nodes for tickers the vault links but has no node for.

~78 tickers are referenced in notes (410 links) with no node to resolve to. Profiles come from
openbb equity_profile (ticker,name,sector,industry); price comes from the History layer; back-references
are found in the vault itself. Nothing is invented: a ticker with no profile row is skipped, not stubbed.

Usage:
  python3 ~/Documents/finance-ai/ticker_nodes.py                 # dry run
  python3 ~/Documents/finance-ai/ticker_nodes.py --apply
"""
import argparse, collections, csv, glob, os, re

VAULT = next(c for c in (os.environ.get("KG_VAULT"), "/documents/Finance Knowledge Graph",
                         os.path.expanduser("~/Documents/Finance Knowledge Graph"))
             if c and os.path.isdir(c))
PROFILES = "/workspace/history/work/profiles.csv"
# Only name patterns that genuinely indicate a fund. A MISSING sector must not imply "etf": that
# mislabelled Fiserv (old ticker FISV) and Bed Bath & Beyond as funds on an earlier run.
ETF_HINT = re.compile(r"\bETF\b|\bTrust\b|\bFund\b|\bShares\b|\bIndex\b|\bUltraShort\b|\bUltraPro\b", re.I)
MARKER = "Created from the openbb equity_profile fetch"
# Former/alternate tickers, each verified against the provider profile, which states the rename:
# equity_profile for XYZ returns "formerly known as Square, Inc. ... changed its name to Block,
# Inc. in December 2021". Needed because the vault's notes link [[SQ]].
EXTRA_ALIASES = {"XYZ": ["SQ"]}


LEGAL = re.compile(r"[,\s]+(inc|incorporated|corp|corporation|company|co|ltd|limited|plc|p\.l\.c|"
                    r"holdings|group|sa|nv|ag|se|spa|n\.v|a\.s)\.?$", re.I)


def short_title(name):
    """Vault-style node title, with the failure modes this rule actually hit removed.

    Iterating the trim destroyed names ('Nu Holdings Ltd.' -> 'Nu', 'Deere & Company' -> 'Deere &'), so:
    strip a LEADING 'The ' (vault titles don't carry it), collapse '& Company' to the bare stem, then
    remove AT MOST ONE trailing legal suffix, and never leave a dangling connector or a stub.
    """
    t = re.sub(r"\s+", " ", name).strip()
    t = re.sub(r"^the\s+", "", t, flags=re.I)
    t = re.sub(r"\s*&\s*company\.?$", "", t, flags=re.I)
    # Keep stripping legal suffixes while at least two words would remain, so
    # 'American Electric Power Company, Inc.' -> 'American Electric Power' but
    # 'Nu Holdings Ltd.' stops at 'Nu Holdings' instead of collapsing to 'Nu'.
    # A lone GENERIC word is ambiguous ('Southern' could be several issuers), so the last removal is
    # skipped when it would leave one of those. Distinctive single words (Adobe, NIO, AES, BP) are fine:
    # the vault already titles nodes that way.
    generic = {"southern", "general", "american", "national", "united", "first", "pacific",
               "northern", "central", "western", "eastern", "consolidated", "standard", "global"}
    for _ in range(4):
        m = LEGAL.search(t)
        if not m:
            break
        cand = t[: m.start()].strip().rstrip(",")
        if len(cand.split()) < 2:
            allow = bool(cand) and cand.lower() not in generic and t.lower().startswith(cand.lower()) and (
                len(cand) >= 3 or cand.isupper())   # 'BP'/'GE' read as brands; 'Nu' does not
            if allow:
                t = cand          # single distinctive word: allow it (Adobe, NIO, AES, BP)
            break
        if cand.endswith(("&", "-", ",", " of")):
            break
        t = cand
    return t or name


def slug(name):
    s = name.replace("/", "-").replace("\\", "-").replace(":", " -")
    return re.sub(r"\s+", " ", s).strip().rstrip(".")


def norm(name):
    """Loose name key: case/punctuation/spacing-insensitive, so 'Alphabet Inc.' matches 'Alphabet Inc'.

    Needed because the provider appends periods and suffixes that the vault's node titles drop. Two
    different share classes of one company (GOOG / GOOGL) must land on ONE node, so a loose match here
    is deliberate: it turns a would-be duplicate into an alias addition.
    """
    return re.sub(r"[^a-z0-9]", "", name.lower())


def load_profiles():
    out = {}
    paths = [PROFILES] + [p for p in sorted(glob.glob("/workspace/history/work/profiles*.csv"))
                          if p != PROFILES]
    for path in paths:
        if not os.path.exists(path):
            continue
        for r in csv.DictReader(open(path, encoding="utf-8")):
            t = (r.get("ticker") or "").strip().upper()
            n = (r.get("name") or "").strip()
            if t and n:
                out[t] = {"name": n, "sector": (r.get("sector") or "").strip(),
                          "industry": (r.get("industry") or "").strip()}
    return out


def last_price(ticker):
    p = os.path.join(VAULT, "Datasets/History/prices_monthly", f"{ticker}.csv")
    if not os.path.exists(p):
        return None
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    if not rows:
        return None
    try:
        last = float(rows[-1]["close"])
        prior = float(rows[-2]["close"]) if len(rows) > 1 else None
    except (KeyError, ValueError):
        return None
    chg = f" ({(last / prior - 1) * 100:+.1f}% 1m)" if prior else ""
    return f"{last:,.2f}{chg} as-of {rows[-1]['date'][:10]}"


def backrefs(ticker):
    """Files that already link this ticker — the node's real inbound context."""
    out = collections.defaultdict(int)
    pat = re.compile(r"\[\[" + re.escape(ticker) + r"(\||\]\])")
    for p in glob.glob(os.path.join(VAULT, "**", "*.md"), recursive=True):
        if "/.git/" in p or "/.archive/" in p or p.startswith(os.path.join(VAULT, "Templates")):
            continue
        rel = os.path.relpath(p, VAULT)
        if rel.startswith("Companies/") or rel.startswith("Funds/"):
            continue
        try:
            txt = open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        n = len(pat.findall(txt))
        if n:
            folder = rel.split(os.sep)[0]
            out[(os.path.basename(p)[:-3], folder)] += n
    return sorted(out.items(), key=lambda kv: -kv[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--max-refs", type=int, default=12)
    ap.add_argument("--provider", default="yfinance",
                    help="Provider the profile data actually came from. Recorded in sources/notes; do not "
                         "leave it at the default if a run used another provider (a 55-ticker run used fmp "
                         "after yfinance returned no usable fields).")
    a = ap.parse_args()

    prof = load_profiles()
    existing = {}
    for p in glob.glob(os.path.join(VAULT, "Companies", "*.md")):
        txt = open(p, encoding="utf-8", errors="ignore").read()
        fm = txt.split("---", 2)[1] if txt.count("---") >= 2 else ""
        mt = re.search(r'ticker:\s*"?([A-Z0-9.\-]+)"?', fm)
        if mt:
            existing[mt.group(1).upper()] = os.path.basename(p)
        existing.setdefault(os.path.basename(p)[:-3].upper(), os.path.basename(p))

    made, aliased = [], []
    by_norm = {norm(k): k for k in existing}   # keys are tickers or titles; values are filenames with .md
    for tick, d in sorted(prof.items()):
        if tick in existing:
            cand = os.path.join(VAULT, "Companies", existing[tick])
            try:
                ours_here = MARKER in open(cand, encoding="utf-8").read()
            except OSError:
                ours_here = False
            if not ours_here:
                aliased.append((tick, d["name"], existing[tick], "hand-written node - left alone"))
                continue
            # Ours: drop it and fall through to regenerate (picks up price/themes/title changes).
            if a.apply:
                os.remove(cand)
            base = os.path.basename(cand)
            for k in [k for k, v in existing.items() if v == base]:   # purge EVERY key pointing at it
                existing.pop(k, None)
        hit = by_norm.get(norm(d["name"]))
        if hit is not None and hit not in existing:
            hit = None          # its file was just regenerated from under us; treat as new
        ours = None
        if hit:
            cand = os.path.join(VAULT, "Companies", existing[hit])
            try:
                if MARKER in open(cand, encoding="utf-8").read():
                    ours = cand
            except OSError:
                pass
        if hit and ours is None:
            # A hand-written node already covers this company (dual listing / share class):
            # add the ticker as an alias instead of creating a duplicate.
            target = existing[hit]
            why = "alias added" if a.apply else "would add alias"
            if a.apply and os.path.exists(os.path.join(VAULT, "Companies", target)):
                path = os.path.join(VAULT, "Companies", target)
                cur = open(path, encoding="utf-8").read()
                m = re.search(r'^aliases:\s*\[(.*?)\]', cur, re.M)
                if m and tick not in m.group(1):
                    inner = m.group(1).strip().rstrip(",")
                    sep = ", " if inner else ""
                    cur = cur[:m.start()] + f'aliases: [{inner}{sep}"{tick}"]' + cur[m.end():]
                    open(path, "w", encoding="utf-8").write(cur)
                    why = "alias added"
                elif m:
                    why = "already an alias"
                else:
                    why = "NO aliases field - left alone"
            aliased.append((tick, d["name"], target, why))
            continue
        name = slug(short_title(d["name"]))
        is_etf = bool(ETF_HINT.search(d["name"]))   # name-based only; see ETF_HINT comment
        kind = "etf" if is_etf else "company"
        pr = last_price(tick)
        allrefs = backrefs(tick)
        refs = [(n, f, c) for (n, f), c in allrefs][: a.max_refs]
        theme_refs = [n for (n, f), c in allrefs if f == "Themes"][:8]
        note_refs = [n for (n, f), c in allrefs if f == "Notes"][:8]
        alias_list = [tick] + EXTRA_ALIASES.get(tick, [])
        L = ["---", f'type: "{kind}"', f'ticker: "{tick}"',
             "aliases: [" + ", ".join(f'"{x}"' for x in alias_list) + "]",
             f'name: "{d["name"]}"']
        if d["sector"]:
            L.append(f'sector: "{d["sector"]}"')
        if d["industry"]:
            L.append(f'industry: "{d["industry"]}"')
        L.append("themes: [" + ", ".join(f'"{t}"' for t in theme_refs) + "]")
        L.append("research: [" + ", ".join(f'"{t}"' for t in note_refs) + "]")
        src = "[[yfinance]]" if a.provider == "yfinance" else "[[OpenBB]]"
        L.append(f'sources: ["{src}"]')
        L.append(f'provider: "{a.provider}"')
        L.append('notes: "Created from the openbb equity_profile fetch because the vault already links this '
                 f'ticker ({sum(c for _, _, c in refs)} links across the notes below). Name/sector/industry '
                 f'are as returned by the {a.provider} provider."')
        if pr:
            L.append(f'price: "{pr}"')
        L += ["---", "", f"# {d['name']}", "",
              f"{tick} — {d['sector'] or 'unclassified'}{(' / ' + d['industry']) if d['industry'] else ''}.",
              ""]
        if refs:
            L += ["## Referenced in", "",
                  "The vault already links this ticker from these notes (count = link occurrences):", ""]
            for note, folder, n in refs:
                L.append(f"- [[{note}]] ({n}){'' if folder == 'Notes' else ' — ' + folder}")
            L.append("")
        if pr:
            L += ["## Price", "", f"{pr} — from the stored monthly series "
                  f"(`Datasets/History/prices_monthly/{tick}.csv`).", ""]
        L += ["## Sources", "- openbb `equity_profile` (yfinance) — name/sector/industry", ""]
        body = "\n".join(L)
        if a.apply:
            out = os.path.join(VAULT, "Companies", name + ".md")
            if ours and os.path.abspath(ours) != os.path.abspath(out) and os.path.exists(ours):
                os.remove(ours)   # superseded long-title file
            open(out, "w", encoding="utf-8").write(body)
        made.append((tick, name, kind, sum(c for _, _, c in refs), bool(pr)))

    print(f"{'WROTE' if a.apply else 'WOULD WRITE'}: {len(made)} nodes "
          f"({sum(1 for m in made if m[2] == 'company')} company, {sum(1 for m in made if m[2] == 'etf')} etf)")
    for t, n, k, r, has_p in made:
        print(f"   {t:7} {k:8} {r:3} backrefs | {'price' if has_p else 'no price':8} | {n[:52]}")
    if aliased:
        print(f"\nNOT NEW (existing node covers this company): {len(aliased)}")
        for t, n, f, why in aliased:
            print(f"   {t:7} {n[:44]:46} -> {f} ({why})")


if __name__ == "__main__":
    main()
