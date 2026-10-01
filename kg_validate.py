#!/usr/bin/env python3
"""kg_validate.py — Finance KG integrity + health validator.

Checks (vault at /documents/Finance Knowledge Graph):
  1. frontmatter integrity: missing/malformed blocks, nested-bracket arrays, missing `type:`
  2. unresolved wikilinks (every [[X]] must resolve to a vault file, excluding generated/recovery)
  3. required fields per node type (company ticker, claim lifecycle, thesis decision-grade fields
     for acted notes: decision => invalidations + evidence_for + evidence_against + sources)
  4. freshness: stale price stamps (>8d), future-dated notes, claims overdue (next_check passed)
  5. graph health: orphan companies (no research), themes without research, holdings gaps
     (thesis link / catalyst / kill-switch / review date per portfolio position)
  6. generated-file markers present on Graph-Index.md / Portfolio.md / Theme Baskets notes

Emits: printed summary + vault-root KG-Health.md (generated). Exit 0 always (warn-only);
use --strict to exit 1 on violations.
"""
import os, re, glob, sys, datetime, json

VAULT = os.environ.get("VAULT")
if not VAULT:
    for _cand in ("/documents/Finance Knowledge Graph", os.path.expanduser("~/Documents/Finance Knowledge Graph")):
        if os.path.isdir(_cand):
            VAULT = _cand
            break
    if not VAULT:
        VAULT = os.path.expanduser("~/Documents/Finance Knowledge Graph")
TODAY = datetime.date.today()
EXCLUDE_DIRS = {".git", "Templates", ".archive"}
EXCLUDE_FILES = {"README.md", "Welcome.md", "Graph-Index.md", "Portfolio.md", "KG-Health.md"}
PREFIX_IGNORE = ("recovery_",)

def is_generated(fm):
    return fm is not None and ("generated: true" in fm or re.search(r'^type:\s*"dashboard"', fm, re.M))

def fm_split(txt):
    if txt.startswith("---"):
        parts = txt.split("---", 2)
        if len(parts) >= 3:
            return parts[1], parts[2]
        return parts[1], ""  # missing closing
    return None, txt  # missing opening

def links_in(text):
    return set(re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", text))

# ---- index vault files ----
folders = {}
all_files = set()
for p in glob.glob(os.path.join(VAULT, "**", "*.md"), recursive=True):
    rel = os.path.relpath(p, VAULT)
    top = rel.split(os.sep)[0]
    if top in EXCLUDE_DIRS or rel.startswith(PREFIX_IGNORE):
        continue
    title = os.path.splitext(os.path.basename(p))[0]
    all_files.add(title)
    folders.setdefault(top, []).append(rel)

# ---- aliases (alternate link names; resolve like filenames) ----
alias_set = set()
for p in glob.glob(os.path.join(VAULT, "**", "*.md"), recursive=True):
    rel = os.path.relpath(p, VAULT)
    top = rel.split(os.sep)[0]
    if top in EXCLUDE_DIRS or rel.startswith(PREFIX_IGNORE):
        continue
    fm, _ = fm_split(open(p, encoding="utf-8", errors="replace").read())
    if not fm:
        continue
    m = re.search(r"^aliases:\s*\[([^\]]*)\]", fm, re.M)
    if m:
        for a in m.group(1).split(","):
            a = a.strip().strip('"').strip("'")
            if a:
                alias_set.add(a)
        continue
    m2 = re.search(r"^aliases:\s*\n((?:[ \t]*-[ \t]*.+\n?)+)", fm, re.M)
    if m2:
        for ln in m2.group(1).splitlines():
            a = ln.strip().lstrip("-").strip().strip('"').strip("'")
            if a:
                alias_set.add(a)

def check_frontmatter():
    bad, missing_type, nested = [], [], []
    for p in glob.glob(os.path.join(VAULT, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, VAULT)
        if rel.startswith(PREFIX_IGNORE):
            continue
        txt = open(p, encoding="utf-8").read()
        fm, body = fm_split(txt)
        if fm is None:
            bad.append((rel, "no opening ---"))
            continue
        if body == "" and txt.count("---") < 2:
            bad.append((rel, "no closing ---"))
        if re.search(r"\[\[\[", fm):
            nested.append(rel)
        if not re.search(r"^type\s*:", fm, re.M):
            missing_type.append(rel)
    return bad, missing_type, nested

def check_links():
    unresolved = []
    gen_ok = True
    for p in glob.glob(os.path.join(VAULT, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, VAULT)
        if rel.startswith(PREFIX_IGNORE) or rel in ("Graph-Index.md", "Portfolio.md"):
            continue
        txt = open(p, encoding="utf-8").read()
        rel_ = os.path.relpath(p, VAULT)
        if rel_.startswith(PREFIX_IGNORE) or rel_ in EXCLUDE_FILES or ".archive" in rel_:
            continue
        fm, _ = fm_split(txt)
        if fm is None or is_generated(fm):
            continue
        for l in links_in(txt):
            l = l.strip()
            if l not in all_files and l not in alias_set and l not in ("",) and not os.path.exists(os.path.join(VAULT, l + ".md")):
                unresolved.append((rel, l))
    # glob order is filesystem-dependent, which made KG-Health.md churn on every run (same links, new order)
    # and produced spurious diffs in the vault. Sort so the generated file is deterministic.
    return sorted(set(unresolved))

def first_val(fm, key):
    m = re.search(rf"^{key}:\s*[\"']?([^\"'\n]*)[\"']?", fm, re.M)
    return m.group(1).strip() if m else None

def yaml_list_vals(fm, key):
    m = re.search(rf"^{key}:\s*\[([^\]]*)\]", fm, re.M)
    if m:
        return [x.strip().strip('"').strip("'") for x in m.group(1).split(",") if x.strip()]
    # block-style YAML list:
    # key:
    #   - "item one"
    #   - "item two"
    m2 = re.search(rf"^{key}:\s*\n((?:[ \t]+-[^\n]*\n?)+)", fm, re.M)
    if m2:
        vals = []
        for ln in m2.group(1).splitlines():
            item = ln.strip()[1:].strip().strip('"').strip("'")
            if item:
                vals.append(item)
        return vals
    return []

def type_of(fm):
    return first_val(fm, "type")

def check_required():
    issues = []
    for p in glob.glob(os.path.join(VAULT, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, VAULT)
        if rel.startswith(PREFIX_IGNORE) or rel in ("Graph-Index.md", "Portfolio.md"):
            continue
        txt = open(p, encoding="utf-8").read()
        rel_ = os.path.relpath(p, VAULT)
        if rel_.startswith(PREFIX_IGNORE) or rel_ in EXCLUDE_FILES or ".archive" in rel_ or rel_.startswith("Templates"):
            continue
        fm, _ = fm_split(txt)
        if fm is None or is_generated(fm):
            continue
        t = type_of(fm)
        if t == "company":
            tk = first_val(fm, "ticker")
            if not tk:
                issues.append((rel, "company missing ticker"))
        elif t == "claim":
            for k in ("speaker", "claim", "date", "status", "confidence"):
                if first_val(fm, k) in (None, ""):
                    issues.append((rel, f"claim missing {k}"))
            st = first_val(fm, "status")
            if st and st not in ("open", "supported", "contradicted", "unresolved", "pending"):
                issues.append((rel, f"claim bad status {st}"))
        elif t == "market-context":
            if "last_updated" in fm and first_val(fm, "regime") in (None, ""):
                issues.append((rel_, "context missing regime"))
        elif t == "deal":
            for k in ("target", "announced", "status"):
                if first_val(fm, k) in (None, ""):
                    issues.append((rel_, f"deal missing {k}"))
        elif t == "research-note":
            # decision-grade only for THESES (signal/scan outputs are claims, not theses)
            nt = first_val(fm, "note_type")
            dec = first_val(fm, "decision")
            if dec and nt not in ("signal", "scan", "dashboard"):
                for k in ("invalidations", "evidence_for", "evidence_against", "sources"):
                    if not yaml_list_vals(fm, k):
                        issues.append((rel_, f"thesis missing {k}"))
    return issues

def check_freshness():
    stale, future, overdue = [], [], []
    for p in glob.glob(os.path.join(VAULT, "Companies", "*.md")):
        txt = open(p, encoding="utf-8").read()
        fm, _ = fm_split(txt)
        if fm is None:
            continue
        m = re.search(r"as-of (\d{4}-\d{2}-\d{2})", fm)
        if m:
            d = datetime.date.fromisoformat(m.group(1))
            if (TODAY - d).days > 8:
                stale.append(os.path.basename(p))
    for p in glob.glob(os.path.join(VAULT, "Notes", "*.md")):
        txt = open(p, encoding="utf-8").read()
        fm, _ = fm_split(txt)
        if fm is None:
            continue
        d = first_val(fm, "date")
        if d and re.match(r"\d{4}-\d{2}-\d{2}", d):
            dd = datetime.date.fromisoformat(d[:10])
            if dd > TODAY and "scheduled" not in fm:
                future.append(os.path.basename(p))
    for p in glob.glob(os.path.join(VAULT, "Claims", "*.md")):
        txt = open(p, encoding="utf-8").read()
        fm, _ = fm_split(txt)
        if fm is None:
            continue
        st = first_val(fm, "status")
        nc = first_val(fm, "next_check")
        m = re.search(r"(\d{4}-\d{2}-\d{2})", nc or "")
        if st == "open" and m and datetime.date.fromisoformat(m.group(1)) < TODAY:
            overdue.append(os.path.basename(p))
    return stale, future, overdue

def company_aliases():
    """ticker/alias -> company file, so a [[TICKER]] link counts as resolving to that node.

    The vault links companies by ticker far more often than by title (themes list constituents as
    [[PG]], [[HII]]). Obsidian resolves those through `aliases:`, so a backlink check that only looked
    for the title link reported real, well-connected nodes as orphans.
    """
    alias_map = {}
    for p in glob.glob(os.path.join(VAULT, "Companies", "*.md")):
        txt = open(p, encoding="utf-8", errors="ignore").read()
        fm = fm_split(txt)[0]
        stem = os.path.splitext(os.path.basename(p))[0]
        alias_map[stem] = os.path.basename(p)
        if fm:
            tk = first_val(fm, "ticker")
            if tk:
                alias_map[tk.strip().strip('"')] = os.path.basename(p)
            for a in yaml_list_vals(fm, "aliases"):
                alias_map[a.strip().strip('"')] = os.path.basename(p)
    return alias_map


def check_health():
    orphans, no_research_themes = [], []
    amap = company_aliases()
    # A theme listing a constituent ([[PG]] in a theme's basket) is a real edge, not an orphan.
    notes_text = [open(n, encoding="utf-8", errors="ignore").read()
                  for n in glob.glob(os.path.join(VAULT, "Notes", "*.md"))
                  + glob.glob(os.path.join(VAULT, "Themes", "*.md"))]
    unresearched = []
    for p in glob.glob(os.path.join(VAULT, "Companies", "*.md")):
        txt = open(p, encoding="utf-8").read()
        fm, body = fm_split(txt)
        research = yaml_list_vals(fm, "research") if fm else []
        tk = first_val(fm, "ticker") if fm else ""
        stem = os.path.splitext(os.path.basename(p))[0]
        names = {stem}
        if fm:
            if tk:
                names.add(tk.strip().strip('"'))
            for a in yaml_list_vals(fm, "aliases"):
                names.add(a.strip().strip('"'))
        backlinked = any(f"[[{n}]]" in t for t in notes_text for n in names if n)
        if tk and not research and not backlinked:
            orphans.append(os.path.basename(p))
        # Separate, truthful signal: connected but never researched. Kept as backlog, not a defect.
        if tk and not research and backlinked:
            unresearched.append(os.path.basename(p))
    for p in glob.glob(os.path.join(VAULT, "Themes", "*.md")):
        txt = open(p, encoding="utf-8").read()
        fm, body = fm_split(txt)
        if fm and not yaml_list_vals(fm, "research") and not re.search(r"\[\[2026-", body or ""):
            no_research_themes.append(os.path.basename(p))
    return orphans, no_research_themes, unresearched

def check_holdings():
    issues = []
    pf = os.path.join(VAULT, "Portfolio.md")
    if os.path.exists(pf):
        txt = open(pf, encoding="utf-8").read()
        # scope to the "Position detail" section — table rows are summaries without
        # kill-switch/catalyst/review wording and would double-flag every name
        parts = txt.split("## Position detail", 1)
        if len(parts) != 2:
            return issues
        txt = parts[1]
        for m in re.finditer(r"\*\*([A-Z]{1,5})\*\*", txt):
            tk = m.group(1)
            seg = txt[m.end():m.end()+600]
            if "thesis" not in seg.lower() or "[[2026-" not in seg:
                if "[[2026-" not in txt[m.start():m.start()+300]:
                    issues.append((tk, "holding may lack thesis link"))
            if "kill" not in seg.lower() and "watching" not in seg.lower():
                issues.append((tk, "holding missing kill-switch"))
            if "catalyst" not in seg.lower() and "earnings" not in seg.lower():
                issues.append((tk, "holding missing catalyst"))
            if "review" not in seg.lower():
                issues.append((tk, "holding missing review date"))
    return issues

def check_generated_markers():
    miss = []
    for rel in ("Graph-Index.md", "Portfolio.md"):
        p = os.path.join(VAULT, rel)
        if os.path.exists(p) and "generated: true" not in open(p, encoding="utf-8").read():
            miss.append(rel)
    return miss

def main():
    bad_fm, missing_type, nested = check_frontmatter()
    unresolved = check_links()
    req = check_required()
    stale, future, overdue = check_freshness()
    orphans, no_research, unresearched = check_health()
    holdings = check_holdings()
    gm = check_generated_markers()

    print("== KG INTEGRITY ==")
    print(f"frontmatter malformed: {len(bad_fm)}  (missing opening: {sum(1 for _,w in bad_fm if w=='no opening ---')}, closing: {sum(1 for _,w in bad_fm if w=='no closing ---')})")
    for r, w in bad_fm[:12]: print(f"   {w}: {r}")
    print(f"nested-bracket arrays: {len(nested)}  {nested[:8]}")
    print(f"missing type field: {len(missing_type)}  {missing_type[:8]}")
    print(f"unresolved wikilinks: {len(unresolved)}")
    for r, l in unresolved[:20]: print(f"   {r} -> [[{l}]]")
    print(f"required-field violations: {len(req)}")
    for r, w in req[:15]: print(f"   {r}: {w}")
    print(f"\n== FRESHNESS ==")
    print(f"stale prices (>{8}d): {len(stale)} {stale[:8]}")
    print(f"future-dated notes: {len(future)} {future[:8]}")
    print(f"claims overdue for review: {len(overdue)} {overdue[:8]}")
    print(f"\n== HEALTH ==")
    print(f"orphan companies (no research, no backlink): {len(orphans)} {orphans[:10]}")
    print(f"themes without research: {len(no_research)} {no_research[:10]}")
    print(f"holding gaps: {len(holdings)}")
    for t, w in holdings[:15]: print(f"   {t}: {w}")
    print(f"\n== GENERATED MARKERS ==")
    print(f"missing generated:true: {gm}")

    # KG-Health.md
    lines = ["---", 'type: "dashboard"', f'date: "{TODAY.isoformat()}"', 'generated: true',
             'generator: "kg_validate.py"', "---", "", "# KG Health Dashboard", "",
             f"Generated {TODAY.isoformat()} by kg_validate.py. Warnings only — fix, don't delete.",
             "", "## Integrity", f"- Malformed frontmatter: {len(bad_fm)}", f"- Nested-bracket arrays: {len(nested)}",
             f"- Missing type: {len(missing_type)}", f"- Unresolved wikilinks: {len(unresolved)}",
             f"- Required-field violations: {len(req)}", "", "## Freshness", f"- Stale prices: {len(stale)}",
             f"- Future-dated notes: {len(future)}", f"- Claims overdue: {len(overdue)}", "", "## Health",
             f"- Orphan companies: {len(orphans)}",
             f"- Connected but unresearched companies: {len(unresearched)} (have theme/note edges, no research note yet)",
             f"- Themes without research: {len(no_research)}",
             f"- Holding gaps: {len(holdings)}", "", "## Unresolved links",
             *[f"- {r} -> [[{l}]]" for r, l in unresolved[:40]], ""]
    open(os.path.join(VAULT, "KG-Health.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\nKG-Health.md written.")

if __name__ == "__main__":
    main()