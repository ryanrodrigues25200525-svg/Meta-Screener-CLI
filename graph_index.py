#!/usr/bin/env python3
"""
Graph-Index registry — scans the Finance KG vault and regenerates Graph-Index.md.

Vault: /documents/Finance Knowledge Graph
Output: /documents/Finance Knowledge Graph/Graph-Index.md

Idempotent: safe to re-run; overwrites output each time.
Tolerant: malformed frontmatter is skipped and counted in warnings.
"""
from pathlib import Path
import re
from datetime import datetime, timezone

VAULT = Path("/documents/Finance Knowledge Graph")
OUTPUT = VAULT / "Graph-Index.md"

# Folders to scan (order matters for report)
FOLDERS = [
    "Companies",
    "Notes",
    "Themes",
    "Claims",
    "Funds",
    "Deals",
    "People",
    "Market Context",
    "Important Dates",
    "References",
    "Sources",
    "Templates",
]

# Folders that get title-only linked lists (not table)
LINKED_LIST_FOLDERS = ["Claims", "Funds", "Deals", "People", "Market Context", "Important Dates", "References", "Sources"]

def extract_frontmatter(text: str):
    """Return (raw_frontmatter_str or None, error_str or None)."""
    if not text.startswith("---"):
        return None, "missing opening ---"
    # split on ---, expect 3 parts: empty, frontmatter, rest
    # Use split with limit 2 on the string after first ---
    # The file starts with ---\n so we split into 3: before first, fm, after second
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, "missing closing ---"
    raw = parts[1]
    return raw, None

def parse_frontmatter_tolerant(raw: str):
    """
    Very tolerant YAML-ish parser handling:
    - scalar key: "value" or value
    - inline arrays: key: ["a", "b"]
    - block lists:
        key:
          - "a"
          - "b"
    - mixed styles, missing quotes, empty values.
    Returns dict. Raises on severe malformation? We catch and let caller count.
    """
    data = {}
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if ":" not in line:
            # Possible continuation or garbage line — skip
            i += 1
            continue
        colon = line.find(":")
        key = line[:colon].strip()
        # skip empty keys
        if not key:
            i += 1
            continue
        # Remove possible leading dash? keys shouldn't have dash
        val = line[colon+1:].strip()
        # Handle block list: val empty and next lines are "- ..."
        # Also handle "[]" explicit empty
        if val == "" or val == "[]":
            lst = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                nxt_stripped = nxt.strip()
                if nxt_stripped.startswith("-"):
                    item = nxt_stripped[1:].strip()
                    # strip surrounding quotes
                    if len(item) >= 2 and ((item[0] == '"' and item[-1] == '"') or (item[0] == "'" and item[-1] == "'")):
                        item = item[1:-1]
                    # also strip trailing comments? not needed
                    lst.append(item)
                    j += 1
                elif nxt_stripped == "":
                    j += 1
                    # peek further - if next non-empty is indented dash, continue
                    # else break if blank followed by new key
                    # Look ahead one more
                    k = j
                    while k < len(lines) and lines[k].strip() == "":
                        k += 1
                    if k < len(lines) and lines[k].strip().startswith("-"):
                        continue
                    else:
                        # if next is a key at column 0, break
                        if k < len(lines) and ":" in lines[k] and not lines[k].startswith(" ") and not lines[k].startswith("\t"):
                            break
                        # otherwise continue
                        continue
                else:
                    # If next line looks like a new key (contains colon and starts at 0 indent), break
                    if ":" in nxt and not nxt.startswith(" ") and not nxt.startswith("\t"):
                        break
                    # If indented but not dash, it's not a block list entry
                    break
            if lst:
                data[key] = lst
                i = j
                continue
            else:
                if val == "[]":
                    data[key] = []
                else:
                    # Keep as empty string, but also check if it might be a multiline scalar? treat as ""
                    data[key] = ""
                i += 1
                continue

        # Inline array
        if val.startswith("["):
            # Find last ] to handle extra trailing brackets from malformed like: ["[[NVDA ...\"]]\"]]\"]]\"]]\"]
            last = val.rfind("]")
            if last == -1:
                # malformed, treat as scalar
                if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
                    val = val[1:-1]
                data[key] = val
                i += 1
                continue
            inner = val[1:last]
            # Extract wiki links first
            wiki = re.findall(r'\[\[.*?\]\]', inner)
            if wiki:
                # If inner contains wiki links, use them (handles the malformed funds field where single quoted string contains commas)
                # For funds: "[[Bridgewater]], [[Citadel]], ..." inside one quoted string, wiki will extract all
                items = wiki
                data[key] = items
            else:
                if inner.strip() == "":
                    data[key] = []
                else:
                    # split by comma respecting quotes (simple)
                    # Use a manual split that respects double quotes
                    parts = []
                    cur = ""
                    in_dq = False
                    in_sq = False
                    for ch in inner:
                        if ch == '"' and not in_sq:
                            in_dq = not in_dq
                            cur += ch
                        elif ch == "'" and not in_dq:
                            in_sq = not in_sq
                            cur += ch
                        elif ch == "," and not in_dq and not in_sq:
                            parts.append(cur.strip())
                            cur = ""
                        else:
                            cur += ch
                    if cur.strip():
                        parts.append(cur.strip())
                    cleaned = []
                    for p in parts:
                        p = p.strip()
                        if len(p) >= 2 and ((p[0] == '"' and p[-1] == '"') or (p[0] == "'" and p[-1] == "'")):
                            p = p[1:-1]
                        if p:
                            cleaned.append(p)
                    data[key] = cleaned
            i += 1
            continue
        else:
            # Scalar
            # Strip surrounding quotes
            if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
                val = val[1:-1]
            data[key] = val
            i += 1
            continue
    return data

def safe_read(path: Path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return None

def title_from_path_and_data(path: Path, data: dict):
    # Prefer frontmatter name/title/topic, fallback to stem
    for k in ["name", "title", "topic", "fund_name", "event"]:
        if k in data and data[k]:
            v = data[k]
            if isinstance(v, list):
                v = ", ".join(v)
            # strip any remaining wiki brackets?
            # Keep as is
            if v and v != "":
                # limit length
                return str(v).strip()
    return path.stem

def escape_pipe(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ").replace("\r", " ")

def main():
    warnings = []
    malformed_count = 0
    node_counts = {}
    # Collect per folder
    all_data = {}  # folder -> list of (path, data_or_none, error_or_none)

    for folder in FOLDERS:
        dir_path = VAULT / folder
        if not dir_path.exists():
            node_counts[folder] = 0
            all_data[folder] = []
            warnings.append(f"Folder missing: {folder}")
            continue
        files = sorted([p for p in dir_path.iterdir() if p.is_file() and p.suffix == ".md"], key=lambda p: p.name.lower())
        node_counts[folder] = len(files)
        entries = []
        for p in files:
            text = safe_read(p)
            if text is None:
                warnings.append(f"Could not read {folder}/{p.name}")
                entries.append((p, {}, "read error"))
                continue
            raw, err = extract_frontmatter(text)
            if err:
                # No frontmatter or missing closing — count as malformed but still index by title
                malformed_count += 1
                warnings.append(f"Malformed frontmatter {folder}/{p.name}: {err}")
                entries.append((p, {}, err))
                continue
            try:
                data = parse_frontmatter_tolerant(raw)
                entries.append((p, data, None))
            except Exception as e:
                malformed_count += 1
                warnings.append(f"Parse error {folder}/{p.name}: {e}")
                entries.append((p, {}, str(e)))
        all_data[folder] = entries

    # Also count vault-root md files (README etc) for awareness but not in table? We'll add a total
    # Build markdown
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    out_lines = []
    out_lines.append("# Finance Knowledge Graph — Index")
    out_lines.append("")
    out_lines.append(f"_Auto-generated: {now} — run `{Path(__file__).name}` to regenerate. Do not edit by hand._")
    out_lines.append("")
    out_lines.append(f"_Vault: `{VAULT}` — {sum(node_counts.values())} nodes across {len([k for k,v in node_counts.items() if v>0])} folders — warnings: {malformed_count} malformed frontmatter._")
    out_lines.append("")

    # Node counts
    out_lines.append("## Node Counts")
    out_lines.append("")
    out_lines.append("| Folder | Count |")
    out_lines.append("|---|---:|")
    for f in FOLDERS:
        out_lines.append(f"| {f} | {node_counts.get(f,0)} |")
    total = sum(node_counts.values())
    out_lines.append(f"| **Total** | **{total}** |")
    out_lines.append("")

    # Companies table
    out_lines.append("## Companies")
    out_lines.append("")
    companies = all_data.get("Companies", [])
    out_lines.append(f"_({len(companies)} nodes — title | ticker | price | fundamentals)_")
    out_lines.append("")
    out_lines.append("| Title | Ticker | Price | Fundamentals |")
    out_lines.append("|---|---|---|---|")
    # Sort by title (name or stem)
    def comp_sort_key(item):
        p, data, err = item
        t = title_from_path_and_data(p, data if data else {}).lower()
        return t
    for p, data, err in sorted(companies, key=comp_sort_key):
        title = escape_pipe(title_from_path_and_data(p, data if data else {}))
        # also consider file stem as title if name is not informative? We'll use stem for link display but keep title from data
        # Actually title column should be linked: [[Title]]
        link_title = p.stem
        # Display linked title
        title_cell = f"[[{link_title}]]"
        ticker = ""
        price = ""
        fundamentals = ""
        if data:
            ticker = str(data.get("ticker", "") or "").strip()
            price = str(data.get("price", "") or "").strip()
            # fundamentals: check several possible keys
            for fk in ["fundamentals", "fundamental", "valuation", "fundamental_line", "fundamentals_line"]:
                if fk in data and data[fk]:
                    v = data[fk]
                    if isinstance(v, list):
                        v = "; ".join(v)
                    fundamentals = str(v).strip()
                    break
        # Only include fundamentals if present; otherwise empty cell
        out_lines.append(f"| {title_cell} | {escape_pipe(ticker)} | {escape_pipe(price)} | {escape_pipe(fundamentals)} |")
    out_lines.append("")

    # Themes table
    out_lines.append("## Themes")
    out_lines.append("")
    themes = all_data.get("Themes", [])
    out_lines.append(f"_({len(themes)} nodes — title | last_perf | tracked)_")
    out_lines.append("")
    out_lines.append("| Title | Last Perf | Tracked |")
    out_lines.append("|---|---|---|")
    for p, data, err in sorted(themes, key=lambda x: title_from_path_and_data(x[0], x[1] if x[1] else {}).lower()):
        link_title = p.stem
        title_cell = f"[[{link_title}]]"
        last_perf = ""
        tracked = ""
        if data:
            # last_perf may be under last_perf, performance_1m, performance_ytd
            for k in ["last_perf", "performance_1m", "performance_ytd", "lastPerf"]:
                if k in data and data[k]:
                    v = data[k]
                    if isinstance(v, list):
                        v = "; ".join(v)
                    last_perf = str(v).strip()
                    if last_perf:
                        break
            # tracked
            if "tracked" in data:
                v = data["tracked"]
                if isinstance(v, bool):
                    tracked = str(v).lower()
                elif isinstance(v, list):
                    tracked = ", ".join(str(x) for x in v)
                else:
                    tracked = str(v).strip().lower()
                # normalize true/false/empty
                if tracked in ["true", "True", "1"]:
                    tracked = "true"
                elif tracked in ["false", "False", "0", ""]:
                    tracked = tracked if tracked else ""
        out_lines.append(f"| {title_cell} | {escape_pipe(last_perf)} | {escape_pipe(tracked)} |")
    out_lines.append("")

    # Linked title-only lists for other folders
    for folder in LINKED_LIST_FOLDERS:
        entries = all_data.get(folder, [])
        out_lines.append(f"## {folder}")
        out_lines.append("")
        out_lines.append(f"_({len(entries)} nodes)_")
        out_lines.append("")
        if not entries:
            out_lines.append("_No nodes._")
            out_lines.append("")
            continue
        # Sort alphabetically by stem
        for p, data, err in sorted(entries, key=lambda x: x[0].stem.lower()):
            stem = p.stem
            # Use wiki link
            out_lines.append(f"- [[{stem}]]")
        out_lines.append("")

    # Notes index
    out_lines.append("## Notes Index")
    out_lines.append("")
    notes = all_data.get("Notes", [])
    out_lines.append(f"_({len(notes)} nodes — title | topic | companies)_")
    out_lines.append("")
    out_lines.append("| Title | Topic | Companies |")
    out_lines.append("|---|---|---|")
    for p, data, err in sorted(notes, key=lambda x: x[0].stem.lower()):
        stem = p.stem
        title_cell = f"[[{stem}]]"
        topic = ""
        companies_str = ""
        if data:
            # topic may be under topic / title / name
            for k in ["topic", "title", "name"]:
                if k in data and data[k]:
                    v = data[k]
                    if isinstance(v, list):
                        v = "; ".join(v)
                    topic = str(v).strip()
                    if topic:
                        break
            # companies
            if "companies" in data and data["companies"]:
                v = data["companies"]
                if isinstance(v, list):
                    # already wiki links like [[AMD]]
                    companies_str = ", ".join(str(x).strip() for x in v if str(x).strip())
                else:
                    companies_str = str(v).strip()
        out_lines.append(f"| {title_cell} | {escape_pipe(topic)} | {escape_pipe(companies_str)} |")
    out_lines.append("")

    # Templates (already in counts but also list)
    # Already not in linked list but we should optionally show? Keep counts only for Templates as per node_counts, but also list for completeness
    out_lines.append("## Templates")
    out_lines.append("")
    templates = all_data.get("Templates", [])
    out_lines.append(f"_({len(templates)} nodes)_")
    out_lines.append("")
    for p, data, err in sorted(templates, key=lambda x: x[0].stem.lower()):
        out_lines.append(f"- [[{p.stem}]]")
    out_lines.append("")

    # How to read this graph
    out_lines.append("## How to read this graph")
    out_lines.append("")
    out_lines.append("This vault is a typed reasoning graph. Nodes are markdown files; edges are wiki-links (`[[...]]`) and frontmatter arrays. An LLM should orient via this index first, then follow links surgically rather than scanning hundreds of files.")
    out_lines.append("")
    out_lines.append("### Typing (edge semantics)")
    out_lines.append("")
    out_lines.append("- **Market Context — `threatens` / `strengthens` (reasoning edges):** Each `Market Context/` node (Rates, Inflation, Dollar, Risk appetite, Growth recession risk, Volatility) declares typed edges to research theses/notes:")
    out_lines.append("  - `threatens: [[Note]]` — if this regime moves adversely (e.g., Rates tightening, Risk appetite flipping risk-off), the linked thesis weakens or invalidates. Walk these on a regime change to find at-risk positions.")
    out_lines.append("  - `strengthens: [[Note]]` — if the regime holds or improves, the linked thesis is confirmed. Walk these to find tailwinds.")
    out_lines.append("  - `impacts: [[Theme/Company/Note]]` — loose coupling (regime conditions the thesis without a directional bet). Start with threatens/strengthens for machine propagation; use `reason.py` as the propagation engine.")
    out_lines.append("  - Example: `Rates.md` threatens `[[2026-08-18 Small-cap value AVUV research]]` and strengthens `[[2026-08-18 NVIDIA research]]`; `Risk appetite.md` threatens AI-infra notes and strengthens defensives.")
    out_lines.append("")
    out_lines.append("- **Notes — `invalidations` / `strengthens_when` (kill-switches):** Every `Notes/` research note should carry machine-checkable conditions:")
    out_lines.append("  - `invalidations: [\"if X happens, this thesis breaks\"]` — one bullet per condition (e.g., \"if DC revenue decelerates below ~40% y/y\", \"if non-GAAP GM slips under 54%\"). On a trigger, the thesis is void; next step is Notion/position review.")
    out_lines.append("  - `strengthens_when: [\"if Y happens, this thesis is confirmed\"]` — positive mirror. `evidence_for` / `evidence_against` arrays link to Claims/Evidence that support or undercut the kill-switches.")
    out_lines.append("  - Pattern: `grade.py` / `verdict.py` walk invalidations against `Important Dates` outcomes to auto-grade WIN/LOSS/TABLE.")
    out_lines.append("")
    out_lines.append("- **Claims → Credibility:** `Claims/` are testable, dated assertions with `speaker`, `company`, `claim`, `date`, `source`, `confidence` (0–1), `status` (open/supported/contradicted), `supported_by` / `contradicted_by` links, and `related_themes`. They accrue to `People/` and `Sources/` credibility:")
    out_lines.append("  - `People/*.md` tracks `credibility` (0–1) and `bias` (e.g., short/activist) and accumulates `claims: [[Claim]]`. Over time, outcomes validate or contradict short-seller claims (e.g., Culper, J Capital, Fuzzy Panda) → credibility score updates.")
    out_lines.append("  - Anti-comp manipulation: `idea_source` + `source independence` (distinct data lineages: price, fundamentals, analyst, fund-letters, reddit, biotech) are collapsed so correlated Claims do not inflate confidence.")
    out_lines.append("")
    out_lines.append("- **Deals → Event-driven:** `Deals/` nodes are M&A catalysts (target, acquirer, announced, deal_value_usd, premium_pct, status: announced|pending|closed|broken). They link to affected `Companies/` and `Themes/`; watch HSR/CFIUS/UK CMA, financing, and break fees. Status flips drive event-driven re-rating or arb spread moves — grade against close/break outcomes, not price alone.")
    out_lines.append("")
    out_lines.append("- **References → Canonical frameworks:** `References/` are distilled, source-grounded frameworks (CFA Textbooks, PM risk framework, Verdict layer, Source independence, Data quality gate, etc.) with `scope`, `summary`, `distilled` (key concepts), and `used_by` backlinks.")
    out_lines.append("  - Ground every thesis on a Reference before sizing: e.g., DCF for valuation, Quantitative Methods for stats, Portfolio Management for risk, Ethics for governance reads, Screen engine for idea provenance.")
    out_lines.append("  - `Sources/` are the data lineage (yfinance, SEC filings, FRED, podcasts, X/Twitter, TradingAgents) with `reliability` (1–5) and `topics`; use to judge evidence weight, not just count.")
    out_lines.append("")
    out_lines.append("### Navigation workflow for an LLM")
    out_lines.append("")
    out_lines.append("1. Start here (Graph-Index.md) → pick the candidate folder (Companies/Themes/Notes) via counts and tables.")
    out_lines.append("2. Open only the linked nodes you need; follow `research`, `themes`, `companies`, `context`, `catalysts` edges one hop at a time.")
    out_lines.append("3. Before reasoning or sizing, run the Data quality gate (live quote reachable, note freshness <30d, price divergence <15%, fundamentals sanity).")
    out_lines.append("4. On a regime or catalyst trigger, walk `threatens`/`strengthens` and check `invalidations` before changing a View.")
    out_lines.append("")

    # Warnings
    out_lines.append("## Warnings & Parse Stats")
    out_lines.append("")
    out_lines.append(f"- Malformed frontmatter skipped: **{malformed_count}**")
    out_lines.append(f"- Total warnings: {len(warnings)}")
    out_lines.append("")
    if warnings:
        out_lines.append("| File | Issue |")
        out_lines.append("|---|---|")
        for w in warnings[:50]:  # cap at 50 to keep index readable
            # warnings are already "folder/file: issue"
            # split on first colon
            if ":" in w:
                # keep as is but escape pipes
                parts = w.split(":", 1)
                # Actually keep full warning in first column, issue in second? Simpler: one column
                out_lines.append(f"| {escape_pipe(w)} |  |")
            else:
                out_lines.append(f"| {escape_pipe(w)} |  |")
        if len(warnings) > 50:
            out_lines.append(f"| _... and {len(warnings)-50} more_ |  |")
        out_lines.append("")
    else:
        out_lines.append("_No warnings — all frontmatter parsed cleanly._")
        out_lines.append("")

    out_lines.append("---")
    out_lines.append(f"_Generated by `{Path(__file__).name}` at {now} — vault `{VAULT}`._")
    out_lines.append("")

    OUTPUT.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(out_lines)} lines)")
    print(f"Node counts: {node_counts}")
    print(f"Warnings: {len(warnings)} (malformed {malformed_count})")
    for w in warnings:
        print(f"WARN: {w}")
    return node_counts, len(out_lines), warnings, malformed_count

if __name__ == "__main__":
    main()
