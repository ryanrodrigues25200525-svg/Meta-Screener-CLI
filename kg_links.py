#!/usr/bin/env python3
"""
Knowledge-graph link helper — shared by meta_screen.py, monitor.py,
catalyst_scan.py, reason.py, frontier_scan.py, analyst_scan.py.

Auto-resolves a ticker to its company-note title by scanning the Finance
Knowledge Graph Companies/ folder. Each company note's frontmatter carries
`ticker:`; we map ticker -> filename (the note title), so a name only becomes
linkable once its company note exists. No hardcoded dict to maintain.

Also provides the graph-quality helpers: staleness_report (research notes whose
market-context has moved on), track_record_report + grade_performance
(B+ -> A grading: does the pick beat SPY), upcoming_catalysts (Important Dates
calendar), and credibility_read (Claim-note support rate by entity).
"""
import os, re, glob, json
from datetime import date, datetime

KG_ROOT = os.path.expanduser("~/Documents/Finance Knowledge Graph")
COMPANIES_DIR = os.path.join(KG_ROOT, "Companies")
NOTES_DIR = os.path.join(KG_ROOT, "Notes")
CLAIMS_DIR = os.path.join(KG_ROOT, "Claims")
IMPORTANT_DIR = os.path.join(KG_ROOT, "Important Dates")
CONTEXT_DIR = os.path.join(KG_ROOT, "Market Context")


def _frontmatter_fields(text):
    """Return dict of top-level YAML key: value from a note's frontmatter."""
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    block = m.group(1)
    fields = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        # strip inline wikilink wrappers / trailing
        val = re.sub(r"^\[\[(.*?)\]\]$", r"\1", val)
        fields[key] = val
    return fields


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def get_frontmatter(path):
    try:
        with open(path, encoding="utf-8") as f:
            return _frontmatter_fields(f.read())
    except Exception:
        return {}


def load_ticker_map(root=KG_ROOT):
    """ticker -> company-note title (filename sans .md)."""
    tmap = {}
    companies_dir = os.path.join(os.fspath(root), "Companies")
    for path in glob.glob(os.path.join(companies_dir, "*.md")):
        fm = get_frontmatter(path)
        ticker = (fm.get("ticker") or "").strip().upper()
        if ticker:
            tmap[ticker] = os.path.splitext(os.path.basename(path))[0]
    return tmap


def company_link(sym, ticker_map=None):
    """Return [[CompanyTitle]] for a ticker, or the bare ticker if unresolved."""
    sym = sym.strip().upper()
    tmap = load_ticker_map() if ticker_map is None else ticker_map
    title = tmap.get(sym)
    if title:
        return f"[[{title}]]"
    return sym


def resolve_company_links(companies_list, ticker_map=None):
    """Map a list of raw tickers/company titles to [[wikilinks]] via the map."""
    tmap = ticker_map or load_ticker_map()
    out = []
    for c in companies_list or []:
        c = c.strip().strip("[]")
        upper = c.upper()
        if upper in tmap:
            out.append(f"[[{tmap[upper]}]]")
        elif c:
            out.append(f"[[{c}]]")
    return out


def search_vault(pattern, folder=None, root=KG_ROOT):
    """Return list of (path, frontmatter) matching a regex over frontmatter+title."""
    import fnmatch
    base = os.path.join(root, folder) if folder else root
    hits = []
    for path in glob.glob(os.path.join(base, "**", "*.md"), recursive=True):
        if os.sep + ".obsidian" + os.sep in path:
            continue
        text = open(path, encoding="utf-8").read()
        title = os.path.splitext(os.path.basename(path))[0]
        if re.search(pattern, text, re.I) or re.search(pattern, title, re.I):
            hits.append((path, get_frontmatter(path)))
    return hits


# ---------------------------------------------------------------------------
# Staleness — research notes whose Market Context has moved on since the note
# ---------------------------------------------------------------------------
def staleness_report(root=KG_ROOT, stale_days=45, context_dir="Market Context"):
    from datetime import date
    def parse_date(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            return None
    ctx_updated = {}
    for path in glob.glob(os.path.join(root, context_dir, "*.md")):
        fm = get_frontmatter(path)
        d = parse_date(fm.get("last_updated", ""))
        if d:
            ctx_updated[fm.get("topic") or os.path.splitext(os.path.basename(path))[0]] = d
    rows = []
    for path in glob.glob(os.path.join(NOTES_DIR, "*.md")):
        fm = get_frontmatter(path)
        note_date = parse_date(fm.get("date", ""))
        if not note_date:
            continue
        for topic in ("Rates", "Inflation", "Dollar", "Risk appetite", "Growth recession risk"):
            ctx_date = ctx_updated.get(topic)
            if ctx_date and ctx_date > note_date:
                gap = (ctx_date - note_date).days
                if gap > stale_days:
                    rows.append((os.path.basename(path), topic, gap))
    rows.sort(key=lambda r: -r[2])
    return rows


# ---------------------------------------------------------------------------
# Track record — grade picks vs SPY
# ---------------------------------------------------------------------------
def track_record_report(root=KG_ROOT):
    rows = []
    for path in glob.glob(os.path.join(NOTES_DIR, "*.md")):
        fm = get_frontmatter(path)
        if fm.get("outcome") and fm.get("outcome") != "open":
            rows.append({
                "note": os.path.splitext(os.path.basename(path))[0],
                "decision": fm.get("decision"),
                "outcome": fm.get("outcome"),
                "realized_return": fm.get("realized_return"),
                "vs_spy": fm.get("vs_spy"),
                "model_source": fm.get("model_source"),
                "track_updated": fm.get("track_updated"),
            })
    return rows


def grade_performance(root=KG_ROOT):
    """Aggregate realized_return vs vs_spy across closed picks -> B+->A picture."""
    def to_float(s):
        if not s:
            return None
        try:
            return float(str(s).replace("%", "").strip())
        except Exception:
            return None
    recs = track_record_report(root)
    wins = losses = 0
    tot_ret = tot_spy = 0.0
    n = 0
    for r in recs:
        rv = to_float(r.get("realized_return"))
        vs = to_float(r.get("vs_spy"))
        if rv is None and vs is None:
            continue
        if r.get("outcome") == "win":
            wins += 1
        elif r.get("outcome") == "loss":
            losses += 1
        tot_ret += rv if rv is not None else 0
        tot_spy += vs if vs is not None else 0
        n += 1
    return {
        "picks": n,
        "wins": wins,
        "losses": losses,
        "avg_realized": (tot_ret / n) if n else None,
        "avg_vs_spy": (tot_spy / n) if n else None,
    }


# ---------------------------------------------------------------------------
# Upcoming catalysts — Important Dates calendar
# ---------------------------------------------------------------------------
def upcoming_catalysts(root=KG_ROOT, folder="Important Dates", from_days=0, horizon_days=45):
    today = date.today()
    events = []
    for path in glob.glob(os.path.join(root, folder, "*.md")):
        fm = get_frontmatter(path)
        dstr = fm.get("date") or re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
        if not dstr or (isinstance(dstr, re.Match)):
            continue
        try:
            d = datetime.strptime(fm.get("date") or "", "%Y-%m-%d").date()
        except Exception:
            m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
            if not m:
                continue
            try:
                d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            except Exception:
                continue
        delta = (d - today).days
        if from_days <= delta <= horizon_days:
            events.append({
                "date": d.isoformat(),
                "event": fm.get("event") or "event",
                "company": fm.get("company") or "",
                "importance": fm.get("importance", 3),
                "theses": fm.get("theses", ""),
                "notes": fm.get("notes", ""),
                "path": path,
            })
    events.sort(key=lambda e: e["date"])
    return events


# ---------------------------------------------------------------------------
# Credibility read — Claims/ support rate by entity
# ---------------------------------------------------------------------------
def credibility_read(root=KG_ROOT):
    from collections import OrderedDict
    persons = OrderedDict()
    for path in glob.glob(os.path.join(CLAIMS_DIR, "*.md")):
        fm = get_frontmatter(path)
        speaker = fm.get("speaker") or ""
        conf = fm.get("confidence")
        status = (fm.get("status") or "").lower()
        try:
            conf = float(conf) if conf else None
        except Exception:
            conf = None
        p = persons.setdefault(speaker, {"claims": 0, "n": 0, "conf_sum": 0.0, "supported": 0, "contradicted": 0})
        p["claims"] += 1
        if status in ("supported", "open", ""):
            p["n"] += 1
        if status == "supported":
            p["supported"] += 1
        if status == "contradicted":
            p["contradicted"] += 1
        if conf is not None:
            p["conf_sum"] += conf
    out = []
    for speaker, p in persons.items():
        out.append({
            "entity": speaker,
            "claims": p["claims"],
            "support_rate": (p["supported"] / p["n"]) if p["n"] else None,
            "contradicted": p["contradicted"],
            "avg_conf": (p["conf_sum"] / p["claims"]) if p["claims"] else None,
        })
    out.sort(key=lambda r: -(r["support_rate"] or 0))
    return out


def _fmt_pct(x):
    return f"{x*100:.0f}%" if x is not None else ""


if __name__ == "__main__":
    print(load_ticker_map())
    print("\n=== Staleness report ===")
    for row in staleness_report()[:10]:
        print(" ", row)
    print("\n=== Track record ===")
    tr = track_record_report()
    if tr:
        for r in tr:
            print(" ", r["note"], "|", r["outcome"], "| ret", r["realized_return"], "| vsSPY", r["vs_spy"])
    else:
        print("  (no resolved picks yet)")
    print("\n=== Upcoming catalysts (60d) ===")
    for e in upcoming_catalysts(horizon_days=60):
        print(" ", e["date"], e["event"], e["company"], "imp", e["importance"])
    print("\n=== Credibility read ===")
    for r in credibility_read():
        print(" ", r["entity"], "| claims", r["claims"], "| support", _fmt_pct(r["support_rate"]), "| conf", r["avg_conf"])
