#!/usr/bin/env python3
"""fund_nodes_from_letters.py — create Funds/ nodes from BuySide Digest letter coverage.

The vault named 575 funds in its BuySide Digest letters but held only 14 fund nodes, so fund names in
notes and briefs did not resolve. This creates a node for every fund with real recurring coverage of the
tickers we follow, built ONLY from the harvested letters (no invented AUM/CIK/strategy).

Existing fund nodes are never overwritten — they come from 13F data and have richer fields; they are
listed in the report for a manual merge instead.

Usage: python3 ~/Documents/finance-ai/fund_nodes_from_letters.py [--min-letters 10] [--min-tickers 3] [--apply]
"""
import argparse, collections, csv, glob, os, re

VAULT = next(c for c in (os.environ.get("KG_VAULT"), "/documents/Finance Knowledge Graph",
                         os.path.expanduser("~/Documents/Finance Knowledge Graph"))
             if c and os.path.isdir(c))
LETTERS = os.path.join(VAULT, "Datasets/BuySideDigest/bsd_letters.csv")
FUND_DIR = os.path.join(VAULT, "Funds")


def clean_name(name):
    """Recover the real fund name from harvest artefacts.

    Some rows captured a markdown link instead of a name, e.g.
    '[Mairs and Power - Growth Fund](https---www.buysidedigest.com-tickers-nvda-#)'.
    Take the link text and drop anything URL-shaped. Returns None if nothing usable remains.
    """
    m = re.match(r"^\s*\[([^\]]+)\]\([^)]*\)\s*$", name)
    if m:
        name = m.group(1)
    name = re.sub(r"\s+", " ", name).strip()
    if not name or "http" in name.lower() or "#" in name or len(name) > 90:
        return None
    return name


def slug(name):
    """Filename-safe fund name: no path separators, no filesystem-hostile characters."""
    s = name.replace("/", "-").replace("\\", "-").replace(":", "-")
    return re.sub(r"\s+", " ", s).strip().rstrip(".")


def ticker_nodes():
    m = {}
    for p in glob.glob(os.path.join(VAULT, "Companies", "*.md")):
        fm = open(p, encoding="utf-8", errors="ignore").read().split("---", 2)[1]
        mt = re.search(r'ticker:\s*"?([A-Z0-9.\-]+)"?', fm)
        if mt:
            m[mt.group(1)] = os.path.basename(p)[:-3]
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-letters", type=int, default=10)
    ap.add_argument("--min-tickers", type=int, default=3)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(LETTERS, encoding="utf-8")))
    by = collections.defaultdict(list)
    for r in rows:
        f = (r.get("fund") or "").strip()
        if f:
            by[f].append(r)

    tick = ticker_nodes()
    existing = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(FUND_DIR, "*.md"))}
    made, skipped, nolink = [], [], []
    for fund_raw, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        fund = clean_name(fund_raw)
        if fund is None:
            nolink.append(fund_raw[:60])
            continue
        tickers = sorted({r["ticker"] for r in rs})
        if len(rs) < a.min_letters and len(tickers) < a.min_tickers:
            continue
        name = slug(fund)
        if name in existing:
            skipped.append(name)
            continue
        latest = collections.defaultdict(list)
        for r in rs:
            latest[r["ticker"]].append(r)
        lines = ["---", "type: fund", f'fund_name: "{fund}"',
                 f"letters: {len(rs)}", f"tickers_covered: {len(tickers)}",
                 'sources: ["[[BuySide Digest]]"]',
                 f'notes: "Letter coverage on {len(tickers)} tickers we follow, from the BuySide Digest letter corpus. '
                 'Fund size/strategy not established here — see the 13F layer where available."',
                 "---", "", f"# {fund}", "",
                 f"Fund with {len(rs)} letters in the [[BuySide Digest]] corpus covering {len(tickers)} of our tickers. "
                 "Built from harvested letters only: no AUM, CIK or 13F position is asserted here.", "",
                 "## Coverage", "", "| Ticker | Letters | Latest | Latest take (excerpt) |", "|---|---:|---|---|"]
        for t in tickers:
            rr = sorted(latest[t], key=lambda r: r.get("date") or "")
            last = rr[-1]
            comm = re.sub(r"\s+", " ", (last.get("commentary") or "").strip())[:220]
            link = f"[[{tick[t]}]]" if t in tick else t
            lines.append(f"| {link} | {len(rr)} | {last.get('date', '—')} | {comm}{'…' if comm else ''} |")
        lines += ["", "## Sources", "- BuySide Digest letter corpus — "
                      f"`Datasets/BuySideDigest/bsd_letters.csv` ({len(rs)} rows for this fund)", ""]
        body = "\n".join(lines)
        if a.apply:
            open(os.path.join(FUND_DIR, name + ".md"), "w", encoding="utf-8").write(body)
        made.append((name, len(rs), len(tickers)))

    print(f"{'WROTE' if a.apply else 'WOULD WRITE'}: {len(made)} fund nodes")
    for n, ln, tk in made[:50]:
        print(f"   {ln:4} letters | {tk:2} tickers | {n}")
    if nolink:
        print(f"\nSKIPPED (unusable name from harvest): {len(nolink)}")
        for s_ in nolink:
            print(f"   {s_}")
    if skipped:
        print(f"\nSKIPPED (existing node, needs manual merge): {len(skipped)}")
        for s in skipped:
            print(f"   {s}")


if __name__ == "__main__":
    main()
