#!/usr/bin/env python3
"""
podcast_scan.py — pulls the latest N days of episodes from tracked investing
podcasts (RSS) and writes ~/Documents/Finance Knowledge Graph/Notes/
<today> Podcast Signals.md, flagging decision-relevant episodes by signal
category (rates/macro, AI/capex, M&A, smart-money, commodities/fx, risks,
mgmt/estimates, growth/recession).

Usage: python3 podcast_scan.py [--days 7]
"""
import os, sys, re, argparse, html, urllib.request
from datetime import date, timedelta
from email.utils import parsedate_to_datetime

KG_NOTES = os.path.expanduser("~/Documents/Finance Knowledge Graph/Notes")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# Verified podcast feeds (name -> RSS URL). All three re-verified 2026-08-20.
# (Guessed simplecast URLs 404 — the Colossus/Ritholtz feeds are megaphone.)
MAJOR_PODCASTS = {
    "The Compound (WAYT / Compound & Friends)": "https://feeds.megaphone.fm/TCP4771071679",
    "Animal Spirits (Batnick/Carlson)": "https://feeds.megaphone.fm/TCP6464651487",
    "Invest Like the Best": "https://feeds.megaphone.fm/CLS2859450455",
    "Founders": "https://feeds.megaphone.fm/DSLLC6297708582",
    "David Senra": "https://feeds.megaphone.fm/david-senra",
}

# Signal keywords by category
SIGNALS = {
    "rates/macro": ["fed", "rate", "yield", "inflation", "treasury", "recession", "gdp", "econ"],
    "AI/capex": ["ai", "capex", "semiconductor", "nvidia", "compute", "data center", "hyperscaler"],
    "M&A/corporate": ["merger", "acquisition", "m&a", "buyout", "deal", "takeover"],
    "smart-money": ["hedge", "warren buffett", "ackman", "activist", "13f", "berkshire"],
    "commodities/fx": ["oil", "gold", "commodity", "copper", "energy", "dollar", "currency"],
    "risks/bear": ["bear", "crash", "bubble", "risk", "fragile", "correction"],
    "mgmt/estimates": ["earnings", "guidance", "ceo", "cf", "estimate", "margin"],
    "growth/recession": ["growth", "slowdown", "soft landing", "recession", "consumer"],
}


def fetch_rss(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "ignore")


def parse_items(xml_text, podcast_name):
    items = []
    for m in re.finditer(r"<item>(.*?)</item>", xml_text, re.S):
        block = m.group(1)
        t = re.search(r"<title>(.*?)</title>", block, re.S)
        p = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
        if not t:
            continue
        items.append({
            "podcast": podcast_name,
            "title": html.unescape(t.group(1)).strip(),
            "pubDate": html.unescape(p.group(1)).strip() if p else "",
        })
    return items


def classify(title):
    tl = title.lower()
    flags = []
    for cat, kws in SIGNALS.items():
        if any(k in tl for k in kws):
            flags.append(cat)
    return flags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    since = date.today() - timedelta(days=args.days)
    all_items, scanned = [], 0
    for name, url in MAJOR_PODCASTS.items():
        try:
            xml = fetch_rss(url)
            items = parse_items(xml, name)
            scanned += len(items)
            for it in items:
                dt = None
                try:
                    dt = parsedate_to_datetime(it["pubDate"]).date()
                except Exception:
                    continue
                if dt and dt >= since:
                    flags = classify(it["title"])
                    if flags:
                        all_items.append({**it, "signals": flags})
        except Exception as e:
            print(f"  (feed fail {name}: {e})")

    _write_note(date.today().isoformat(), all_items, scanned, args.days)


def _write_note(today, items, scanned, days):
    import collections
    os.makedirs(KG_NOTES, exist_ok=True)
    theme_counts = collections.Counter(s for it in items for s in it["signals"])
    front = (
        "---\n"
        f'type: "research-note"\n'
        f'date: "{today}"\n'
        f'topic: "Podcast signals — {len(items)} flagged across podcasts ({scanned} episodes scanned)"\n'
        'companies: []\n'
        'themes: [""]\n'
        'context: [""]\n'
        'sources: ["[[The Compound]]"]\n'
        'status: "open"\n'
        'importance: 4\n'
        "---\n\n"
    )
    body = [f"# Podcast Signals {today}\n",
            f"Scanned {scanned} episodes across {len(MAJOR_PODCASTS)} podcasts (last {days}d). {len(items)} flagged as decision-relevant.\n",
            "**Most-active signal themes:** " + ", ".join(f"`{k}`" for k, _ in theme_counts.most_common()) + "\n",
            "## Flagged episodes (worth a listen / verify)\n"]
    if not items:
        body.append("- No episodes flagged in window (or feeds unavailable).")
    for it in items:
        body.append(f"### [{it['podcast']}] {it['title']}\n_{it['pubDate']}_ · signals: {it['signals']}\n")
    title = os.path.join(KG_NOTES, f"{today} Podcast Signals.md")
    with open(title, "w", encoding="utf-8") as f:
        f.write(front + "\n".join(body) + "\n")
    print("wrote", title)
    print(f"scanned {scanned} episodes, {len(items)} flagged")


if __name__ == "__main__":
    main()
