#!/usr/bin/env python3
"""letter_coverage_sections.py — add a 'Letter coverage' section to company nodes.

The BuySide Digest letter corpus says who has written letters about each of our names (NVDA alone has
1,231 letters from 462 funds). That coverage lived only in the dataset CSV; this puts it on the company
node, next to the existing analyst-coverage and smart-money sections, so a query about a name sees it.

Letter-based coverage is NOT a holdings statement and it lags, so the section says both things outright.

Usage: python3 ~/Documents/finance-ai/letter_coverage_sections.py [--apply] [--top 15]
"""
import argparse, collections, csv, glob, os, re

VAULT = next(c for c in (os.environ.get("KG_VAULT"), "/documents/Finance Knowledge Graph",
                         os.path.expanduser("~/Documents/Finance Knowledge Graph"))
             if c and os.path.isdir(c))
LETTERS = os.path.join(VAULT, "Datasets/BuySideDigest/bsd_letters.csv")
HEADING = "## Letter coverage ([[BuySide Digest]])"
AFTER = "## Smart-money positioning ([[BuySide Digest]])"


def clean_name(name):
    m = re.match(r"^\s*\[([^\]]+)\]\([^)]*\)\s*$", name)
    if m:
        name = m.group(1)
    name = re.sub(r"\s+", " ", name).strip()
    if not name or "http" in name.lower() or "#" in name or len(name) > 90:
        return None
    return name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()

    fund_nodes = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(VAULT, "Funds", "*.md"))}
    tick_nodes = {}
    for p in glob.glob(os.path.join(VAULT, "Companies", "*.md")):
        fm = open(p, encoding="utf-8", errors="ignore").read().split("---", 2)[1]
        m = re.search(r'ticker:\s*"?([A-Z0-9.\-]+)"?', fm)
        if m:
            tick_nodes[m.group(1)] = p

    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in csv.DictReader(open(LETTERS, encoding="utf-8")):
        f = clean_name((r.get("fund") or "").strip())
        if f:
            by[r["ticker"]][f].append(r.get("date") or "")

    written = []
    for tick, funds in sorted(by.items(), key=lambda kv: -sum(len(v) for v in kv[1].values())):
        path = tick_nodes.get(tick)
        if not path:
            continue
        total = sum(len(v) for v in funds.values())
        latest = max((d for v in funds.values() for d in v if d), default="—")
        top = sorted(funds.items(), key=lambda kv: -len(kv[1]))[: a.top]
        L = [HEADING, "",
             f"{total} letters from {len(funds)} funds in the harvested [[BuySide Digest]] corpus; "
             f"latest {latest}. **This is who has written about the name, not who holds it** — letters lag, "
             "and a manager's letter can cover a name they do not own.", "",
             "| Fund | Letters | Latest |", "|---|---:|---|"]
        for f, dates in top:
            link = f"[[{f}]]" if f in fund_nodes else f
            d = max((x for x in dates if x), default="—")
            L.append(f"| {link} | {len(dates)} | {d} |")
        if len(funds) > a.top:
            L.append(f"| _+{len(funds) - a.top} more funds — see the dataset_ | | |")
        L.append("")
        block = "\n".join(L)

        txt = open(path, encoding="utf-8").read()
        if HEADING in txt:                      # idempotent: replace the existing block
            start = txt.index(HEADING)
            nxt = re.search(r"^## ", txt[start + len(HEADING):], re.M)
            end = start + len(HEADING) + (nxt.start() if nxt else len(txt) - start - len(HEADING))
            new = txt[:start] + block + "\n" + txt[end:]
        elif AFTER in txt:                       # place it right after the smart-money section
            start = txt.index(AFTER)
            nxt = re.search(r"^## ", txt[start + len(AFTER):], re.M)
            end = start + len(AFTER) + (nxt.start() if nxt else len(txt) - start - len(AFTER))
            new = txt[:end].rstrip() + "\n\n" + block + "\n" + txt[end:]
        else:
            new = txt.rstrip() + "\n\n" + block + "\n"
        if a.apply:
            open(path, "w", encoding="utf-8").write(new)
        written.append((tick, total, len(funds), os.path.basename(path)))

    print(f"{'WROTE' if a.apply else 'WOULD WRITE'}: {len(written)} company nodes")
    for w in written:
        print(f"   {w[0]:6} {w[1]:5} letters | {w[2]:3} funds | {w[3]}")


if __name__ == "__main__":
    main()
