#!/usr/bin/env python3
"""
Position + peer-news monitor. Pulls Google News RSS for each position and its
peer set over a window and writes ~/Documents/Finance Knowledge Graph/Notes/
<today> Positions Monitor.md.

Usage: python3 monitor.py [--days 7]
"""
import os, sys, json, html, re, argparse, urllib.request
from datetime import date, timedelta
from email.utils import parsedate_to_datetime

FINANCE_AI = os.path.expanduser("~/Documents/finance-ai")
KG_NOTES = os.path.expanduser("~/Documents/Finance Knowledge Graph/Notes")
POSITIONS_FILE = os.path.join(FINANCE_AI, "positions.json")

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

sys.path.insert(0, FINANCE_AI)
import kg_links  # noqa: E402


def load_positions():
    with open(POSITIONS_FILE, encoding="utf-8") as f:
        d = json.load(f)
    return d


def fetch_rss(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "ignore")


def parse_entries(xml_text):
    entries = []
    blocks = re.findall(r"<item>(.*?)</item>", xml_text, re.S)
    is_rss = bool(blocks)
    if not blocks:  # Atom fallback
        blocks = re.findall(r"<entry>(.*?)</entry>", xml_text, re.S)
    for block in blocks:
        t = re.search(r"<title>(.*?)</title>", block, re.S)
        if is_rss:
            l = re.search(r"<link>(.*?)</link>", block, re.S)
            p = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
        else:
            l = re.search(r'<link href="(.*?)"', block, re.S)
            p = re.search(r"<published>(.*?)</published>", block, re.S)
        src = re.search(r"<source[^>]*>(.*?)</source>", block, re.S)
        title = html.unescape(t.group(1)).strip() if t else ""
        link = l.group(1) if l else ""
        published = p.group(1) if p else ""
        source = html.unescape(re.sub(r"<[^>]+>", "", src.group(1))).strip() if src else ""
        entries.append({"title": title, "link": link, "published": published, "source": source})
    return entries


def dedupe(entries):
    seen, out = set(), []
    for e in entries:
        key = re.sub(r"[^a-z0-9]", "", e["title"].lower())[:80]
        if key and key not in seen:
            seen.add(key)
            out.append(e)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    positions = load_positions()
    held = [p["symbol"] for p in positions["positions"] if p.get("qty", 0)]
    peers = positions.get("peers", {})
    if not held:
        # positions.json carries qty=0 placeholders only -> monitor the PM book
        pm_file = os.path.join(FINANCE_AI, "pm_portfolio.json")
        if os.path.exists(pm_file):
            with open(pm_file, encoding="utf-8") as f:
                pm = json.load(f)
            held = sorted({p.get("symbol") for p in pm.get("positions", []) if p.get("qty", 0)})
            print(f"[monitor] positions.json held empty -> PM book symbols: {held}")
    since = date.today() - timedelta(days=args.days)

    tmap = kg_links.load_ticker_map()
    sections = []
    for sym in held:
        grp = [sym] + peers.get(sym, [])
        all_entries = []
        for q in grp:
            try:
                xml = fetch_rss(GOOGLE_NEWS_RSS.format(q=urllib.parse.quote(f'"{q}" stock')))
                all_entries += parse_entries(xml)
            except Exception:
                continue
        entries = dedupe(all_entries)
        # filter to window + tag by which symbol
        material = []
        for e in entries:
            dt = None
            try:
                dt = parsedate_to_datetime(e["published"]).date()
            except Exception:
                continue
            if dt and dt >= since:
                material.append(e)
        sections.append((sym, grp, material))

    _write_note(date.today().isoformat(), sections, tmap)


def _fmt_date(s):
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).strftime("%a, %d %b %Y %H:%M:%S GMT")
    except Exception:
        return s


def _write_note(today, sections, tmap):
    os.makedirs(KG_NOTES, exist_ok=True)
    companies = []
    seen = set()
    for sym, grp, mat in sections:
        cl = kg_links.company_link(sym, tmap)
        if cl not in seen:
            seen.add(cl)
            companies.append(cl)
    front = (
        "---\n"
        f'type: "research-note"\n'
        f'date: "{today}"\n'
        f'topic: "Automated position + peer news monitoring digest"\n'
        f'companies: {json.dumps(companies, ensure_ascii=False)}\n'
        'themes: [""]\n'
        'sources: ["[[Google News]]"]\n'
        'status: "follow-up"\n'
        'importance: 4\n'
        "---\n\n"
    )
    body = [f"# Positions Monitor {today}\n"]
    for sym, grp, mat in sections:
        body.append(f"## {sym} ({', '.join(grp[1:])})\n")
        if not mat:
            body.append("- No material news in window (or source unavailable).\n")
            continue
        for e in mat[:8]:
            src = f" _{e.get('source','')}_" if e.get("source") else ""
            body.append(f"- **{e['title']}**{src} {_fmt_date(e['published'])}\n  <{e['link']}>")
        body.append("")
    title = os.path.join(KG_NOTES, f"{today} Positions Monitor.md")
    with open(title, "w", encoding="utf-8") as f:
        f.write(front + "\n".join(body) + "\n")
    print("wrote", title)


if __name__ == "__main__":
    main()
