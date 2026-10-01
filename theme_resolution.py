"""theme_resolution.py — resolve theme members to nodes/prices, once, correctly.

Theme member strings appear as [[TITLE]] or [[TICKER]]. The price layer is keyed by TICKER. Three earlier
attempts at this either compared titles against ticker-keyed sets, swept research-note links in as members,
or matched non-greedily into [[TICKER]] and silently returned one member. This resolves through one map.
"""
import glob, os, re, sys

V = "/documents/Finance Knowledge Graph"
H = V + "/Datasets/History"

# one map each way: title -> ticker, ticker -> title, plus aliases
title2tick, tick2title, alias2title = {}, {}, {}
for p in glob.glob(os.path.join(V, "Companies", "*.md")):
    stem = os.path.basename(p)[:-3]
    txt = open(p, encoding="utf-8", errors="ignore").read()
    fm = txt.split("---", 2)[1] if txt.count("---") >= 2 else ""
    m = re.search(r'^ticker:\s*"?([A-Z0-9.\-]+)"?', fm, re.M)
    if m:
        title2tick[stem] = m.group(1)
        tick2title[m.group(1)] = stem
    for g in re.findall(r'aliases:\s*\[(.*?)\]', fm):
        for a in g.split(","):
            a = a.strip().strip('"\'')
            if a:
                alias2title[a] = stem


def resolve(member):
    """member string -> (node title or None, ticker or None)"""
    if member in title2tick:
        return member, title2tick[member]
    if member in tick2title:
        return tick2title[member], member
    if member in alias2title:
        t = alias2title[member]
        return t, title2tick.get(t)
    return None, None


def members_of(theme):
    p = os.path.join(V, "Themes", theme + ".md")
    txt = open(p, encoding="utf-8", errors="ignore").read()
    fm = txt.split("---", 2)[1] if txt.count("---") >= 2 else ""
    m = re.search(r"^companies:\s*\[(.*)\]\s*$", fm, re.M)   # greedy: to end of line
    if not m:
        return []
    return [x.strip() for x in re.findall(r"\[\[([^\]|#\n]+)", m.group(1))]


if __name__ == "__main__":
    monthly = {os.path.basename(x)[:-4] for x in glob.glob(os.path.join(H, "prices_monthly", "*.csv"))}
    themes = sys.argv[1:] or sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(V, "Themes", "*.md")))
    no_node, no_price = [], []
    total = 0
    for name in themes:
        for mem in members_of(name):
            total += 1
            title, tk = resolve(mem)
            if not title:
                no_node.append((mem, name))
            elif not tk:
                no_price.append((mem, name, "node has no ticker"))
            elif tk not in monthly:
                no_price.append((mem, name, tk))
    print("theme members examined: %d" % total)
    print("  no company node:      %d" % len(no_node))
    print("  node but no price:    %d" % len(no_price))
    seen = set()
    print("\nnode but no monthly series (deduped):")
    for mem, name, tk in no_price:
        if tk in seen:
            continue
        seen.add(tk)
        print("   %-10s %-30s %s" % (tk, mem[:30], name))

# ---- explicit per-theme coverage table, using the single resolver above ----
def coverage_table(names):
    mon = {os.path.basename(x)[:-4] for x in glob.glob(os.path.join(H, "prices_monthly", "*.csv"))}
    day = {os.path.basename(x)[:-4] for x in glob.glob(os.path.join(H, "prices_daily", "*.csv"))}
    fa = {os.path.basename(x)[:-4] for x in glob.glob(os.path.join(H, "fundamentals_annual", "*.csv"))}
    print("\n%-26s %5s %5s %5s %5s %6s" % ("theme", "memb", "mon", "day", "fund", "node?"))
    for name in names:
        mem = members_of(name)
        if not mem:
            continue
        n_node = n_mon = n_day = n_fa = 0
        for m in mem:
            t, tk = resolve(m)
            if t:
                n_node += 1
                if tk in mon:
                    n_mon += 1
                if tk in day:
                    n_day += 1
                if tk in fa:
                    n_fa += 1
        print("%-26s %5d %5d %5d %5d %5d" % (name[:26], len(mem), n_mon, n_day, n_fa, n_node))
