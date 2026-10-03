#!/usr/bin/env python3
"""
screen_tracker.py — Meta-Screen tracker workbook (Trackers.xlsx).

Reads EVERY prior Meta-Screen run note (screen outputs, not research
inputs), resolves each flagged ticker symbol, computes each pick's return
SINCE THE FLAG DATE and vs SPY (Yahoo Finance via yahoo_client, the only
allowed Yahoo path), and writes a multi-sheet workbook.

This is an outcome tracker, not a candidate screener: it reports measured
returns only and invents no rankings.

Usage:
  python3 screen_tracker.py                       # -> notes dir / Trackers.xlsx
  python3 screen_tracker.py --out /path/Trackers.xlsx
  python3 screen_tracker.py --dry                 # print tables, no xlsx

Requires: yfinance (via yahoo_client); officecli (for the xlsx step) at
~/.local/bin/officecli or on PATH.
"""
import argparse, glob, json, os, re, shutil, subprocess, sys, tempfile, time
from datetime import date, datetime

FINANCE_AI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, FINANCE_AI)


def _default_notes_dir():
    override = os.environ.get("SCREEN_NOTES_DIR")
    if override:
        return override
    legacy = os.environ.get("FINANCE_KG_ROOT")
    if legacy:
        return os.path.join(legacy, "Notes")
    return os.path.join(FINANCE_AI, "reports", "Notes")


KG_NOTES = _default_notes_dir()
DEFAULT_OUT = os.path.join(os.path.dirname(KG_NOTES), "Trackers.xlsx")

ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*$")


def _client_for(provider):
    """Return a YahooClient-compatible object (injected stub or live client)."""
    if provider is None:
        import yahoo_client
        return yahoo_client
    if hasattr(provider, "get_history"):
        return provider
    if callable(provider):
        from yahoo_client import YahooClient
        return YahooClient(provider=provider)
    raise TypeError("provider must be a YahooClient, a stub with "
                    "get_history, or a provider callable")


def resolve_ticker(token, title_map=None):
    """Ticker-style symbol -> (TICKER, display); anything else is blank.

    Only unambiguous ticker-style tokens resolve (e.g. ``AAPL``, ``BRK.B``).
    Former company-name lookups against local company notes are gone: names
    that are not ticker-style return (None, display) and skip price lookup
    rather than guessing.
    """
    t = token.strip()
    t = re.sub(r"^\[\[|\]\]$", "", t).strip()
    if not t:
        return None, None
    display = t
    if title_map:
        hit = title_map.get(t.lower())
        if hit:
            return hit, display
    # all-caps short token = ticker-style
    if re.fullmatch(r"[A-Z0-9.\-]{1,6}", t) and t.upper() == t:
        return t, display
    return None, display  # unresolved name; price lookup will be skipped


def load_meta_runs(notes_dir=None):
    notes_dir = notes_dir or KG_NOTES
    runs = []
    for p in sorted(glob.glob(os.path.join(notes_dir, "*Meta-Screen.md"))):
        base = os.path.basename(p)
        m = re.match(r"(\d{4}-\d{2}-\d{2})", base)
        if not m:
            continue
        d = m.group(1)
        try:
            txt = open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        rows = []
        for line in txt.splitlines():
            mm = ROW_RE.match(line)
            if mm:
                rows.append((int(mm.group(1)), mm.group(2), int(mm.group(3)), mm.group(4)))
        if rows:
            runs.append((d, rows))
    return runs


def post_process_inline_strings(path):
    """officecli writes literal strings as t="str" (technically the 'formula string' type).
    Rewrite to canonical inlineStr so every reader (Excel / Numbers / Sheets) shows them."""
    import zipfile
    try:
        zin = zipfile.ZipFile(path, "r")
        items = {n: zin.read(n) for n in zin.namelist()}
        zin.close()
    except Exception as e:
        print("! post-process: cannot read:", e)
        return False
    pat = re.compile(r'(<x:c r="[A-Z]+\d+"(?: s="\d+")?) t="str"><x:v>(.*?)</x:v></x:c>', re.S)
    n_fixed = 0

    def _sub(m):
        nonlocal n_fixed
        n_fixed += 1
        return '%s t="inlineStr"><x:is><x:t>%s</x:t></x:is></x:c>' % (m.group(1), m.group(2))

    for name in list(items):
        if not name.startswith("xl/worksheets/sheet"):
            continue
        xml = items[name].decode("utf-8")
        items[name] = pat.sub(_sub, xml).encode("utf-8")
    if not n_fixed:
        print("  (post-process: no t=str cells found)")
        return False
    zout = zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED)
    for n, data in items.items():
        zout.writestr(n, data)
    zout.close()
    print("  post-process: %d strings -> inlineStr" % n_fixed)
    return True


def build_xlsx_openpyxl(out, tables):
    """Canonical xlsx via openpyxl (importable from a vendored .xlsx-deps dir)."""
    vend = os.path.join(FINANCE_AI, ".xlsx-deps")
    if os.path.isdir(vend) and vend not in sys.path:
        sys.path.insert(0, vend)
    try:
        import openpyxl as _opx
    except Exception:
        return False
    from openpyxl.utils import get_column_letter as _gcl
    wb = _opx.Workbook()
    wb.remove(wb.active)
    from openpyxl.styles import Alignment as _AL, Border as _B, Side as _S
    thin = _S(style="thin", color="D0D7DE")
    box = _B(left=thin, right=thin, top=thin, bottom=thin)
    med_top = _B(top=_S(style="medium", color="9FB3C8"), left=thin, right=thin, bottom=thin)
    hdr_font = _opx.styles.Font(bold=True, color="FFFFFF", size=11)
    hdr_fill = _opx.styles.PatternFill("solid", fgColor="1F4E5F")
    tot_fill = _opx.styles.PatternFill("solid", fgColor="E9EFF5")
    GREEN, RED = "1E7B34", "C0392B"
    PCT = '+0.0"%";-0.0"%";0.0"%"'
    TABS = {"Picks": "1F4E5F", "Fundamental": "2E5E8C", "Momentum": "2E7D32",
            "Technical": "B7791F", "Theme": "6B4FA0", "Valuation": "8C4A52",
            "Summary": "5A6B7B", "Runs": "5A6B7B"}
    TOT_ON = ("Picks", "Fundamental", "Momentum", "Technical", "Theme", "Valuation")

    def nf_col(hl):
        if "price" in hl or "last" in hl:
            return "#,##0.00"
        if "%" in hl or "spy" in hl or "vs" in hl:
            return PCT
        if hl in ("rank", "screens", "times", "picks"):
            return "0"
        return None

    def tint(c):
        if isinstance(c.value, (int, float)):
            if c.value > 0:
                c.font = _opx.styles.Font(color=GREEN, bold=c.font.bold)
            elif c.value < 0:
                c.font = _opx.styles.Font(color=RED, bold=c.font.bold)

    for name, header, rows_ in tables:
        ws = wb.create_sheet(name)
        ws.sheet_properties.tabColor = TABS.get(name, "5A6B7B")
        ws.sheet_view.showGridLines = False
        ws.append([str(h) for h in header])
        for r in rows_:
            ws.append([round(v, 4) if isinstance(v, float) else v for v in r])
        pctj = [j for j, h in enumerate(header) if nf_col(str(h).lower()) == PCT]
        for j in range(1, len(header) + 1):
            h = str(header[j - 1])
            hc = ws.cell(row=1, column=j)
            hc.font = hdr_font
            hc.fill = hdr_fill
            hc.alignment = _AL(horizontal="center", vertical="center")
            hc.border = box
            wid = len(h)
            for r in rows_[:200]:
                v = r[j - 1]
                if v is None:
                    continue
                if isinstance(v, float):
                    v = round(v, 4)
                wid = max(wid, len(str(v)))
            ws.column_dimensions[_gcl(j)].width = min(58, max(8, wid + 2))
        ws.row_dimensions[1].height = 22
        ncols = len(header)
        nrows = ws.max_row
        for j2 in range(1, ncols + 1):
            h2 = str(header[j2 - 1]).lower()
            for i2 in range(2, nrows + 1):
                c = ws.cell(row=i2, column=j2)
                c.border = box
                if h2 in ("rank", "screens", "times", "picks"):
                    c.alignment = _AL(horizontal="center")
                elif isinstance(c.value, (int, float)):
                    c.alignment = _AL(horizontal="right")
                else:
                    c.alignment = _AL(horizontal="left")
                if nf_col(h2):
                    c.number_format = nf_col(h2)
                if (j2 - 1) in pctj:
                    tint(c)
        if name in TOT_ON and pctj:
            tot = [None] * ncols
            tot[0] = "AVERAGE"
            for j0 in pctj:
                vals = [r[j0] for r in rows_ if isinstance(r[j0], (int, float))]
                if vals:
                    tot[j0] = round(sum(vals) / len(vals), 2)
            ws.append(tot)
            tr = ws.max_row
            for j2 in range(1, ncols + 1):
                c = ws.cell(row=tr, column=j2)
                c.border = med_top
                c.fill = tot_fill
                c.font = _opx.styles.Font(bold=True)
                c.number_format = nf_col(str(header[j2 - 1]).lower()) or "General"
                if (j2 - 1) in pctj:
                    tint(c)
        try:
            ws.auto_filter.ref = "A1:%s%d" % (_gcl(ncols), nrows)
        except Exception:
            pass
        ws.freeze_panes = "A2"
    try:
        try:
            os.path.exists(out) and os.remove(out)
        except Exception:
            pass
        wb.save(out)
        print("wrote", out, "(openpyxl)")
        return True
    except Exception as e:
        print("! openpyxl save failed:", e)
        return False


def write_markdown(out, *tables):
    """Native Obsidian-renderable view of the same tables."""
    p = os.path.splitext(out)[0] + ".md"
    try:
        mp = ["# Trackers — Meta-Screen", "",
              "_Regenerated weekly by screen_tracker.py — picks are graded vs SPY since the date they were flagged._", ""]
        for name, header, rows_ in tables:
            mp.append("## %s" % name)
            mp.append("")
            mp.append("| " + " | ".join(str(h) for h in header) + " |")
            mp.append("|" + "|".join(["---"] * len(header)) + "|")
            for r in rows_:
                mp.append("| " + " | ".join("" if v is None else str(v) for v in r) + " |")
            mp.append("")
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(mp) + "\n")
        print("  wrote", os.path.basename(p))
    except Exception as e:
        print("! markdown", e)


def write_csvs(out, *tables):
    import csv as _csv
    base = os.path.splitext(out)[0]
    for name, header, rows_ in tables:
        p = "%s-%s.csv" % (base, name)
        try:
            with open(p, "w", newline="", encoding="utf-8") as f:
                w = _csv.writer(f)
                w.writerow(header)
                w.writerows(rows_)
            print("  wrote", os.path.basename(p))
        except Exception as e:
            print("! csv", name, e)


def write_html(out, *tables):
    import html as _html
    p = os.path.splitext(out)[0] + ".html"
    css = (
        "<style>body{font-family:inherit;color:var(--foreground,#111);background:transparent;margin:0}"
        "h2{font-size:14px;margin:14px 0 6px}table{border-collapse:collapse;font-size:11.5px}"
        "th,td{border:1px solid var(--border,#ddd);padding:3px 7px;text-align:left;white-space:nowrap}"
        "th{background:var(--card,#f6f6f6);font-weight:600}td.num{text-align:right;font-variant-numeric:tabular-nums}"
        ".wrap{max-height:70vh;overflow:auto}</style>"
    )
    parts = ["<html><head><meta charset='utf-8'>" + css + "</head><body>"]
    for name, header, rows_ in tables:
        parts.append("<h2>%s <span style='font-weight:400;opacity:.6'>(%d rows)</span></h2><div class='wrap'><table>" % (name, len(rows_)))
        parts.append("<tr>" + "".join("<th>%s</th>" % _html.escape(str(h)) for h in header) + "</tr>")
        for r in rows_:
            tds = []
            for v in r:
                if v is None or v == "":
                    tds.append("<td></td>")
                    continue
                cls = " class='num'" if isinstance(v, (int, float)) else ""
                tds.append("<td%s>%s</td>" % (cls, _html.escape(str(v))))
            parts.append("<tr>" + "".join(tds) + "</tr>")
        parts.append("</table></div>")
    parts.append("</body></html>")
    try:
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(parts))
        print("  wrote", os.path.basename(p))
    except Exception as e:
        print("! html", e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--dry", action="store_true", help="print tables only, no xlsx")
    args = ap.parse_args()

    title_map = {}
    print(f"title map entries: {len(title_map)} (ticker-style symbols only; no local company-note lookups)")

    runs = load_meta_runs()
    if not runs:
        print("no Meta-Screen notes found in", KG_NOTES)
        sys.exit(1)
    print(f"meta-screen runs found: {len(runs)}  ({runs[0][0]} .. {runs[-1][0]})")

    # ---- assemble pick rows (dedupe per run — historical notes listed GD twice) ----
    picks = []  # dicts
    tickers = set()
    seen_run = set()
    for d, rows in runs:
        for rank, token, screens, cats in rows:
            tk, disp = resolve_ticker(token, title_map)
            key = (d, str(tk or disp).upper())
            if key in seen_run:
                continue
            seen_run.add(key)
            if tk:
                tickers.add(tk.upper())
            picks.append({"date": d, "rank": rank, "token": token, "ticker": tk,
                          "display": disp, "screens": screens, "cats": cats})

    # ---- price history (one fetch per ticker + SPY, via yahoo_client) ----
    print(f"resolving prices for {len(tickers)} tickers + SPY ...")
    closes = {}
    client = _client_for(None)

    def fetch(sym):
        try:
            h = client.get_history(sym, period="6mo")
            s = h["Close"].dropna()
            return s
        except RuntimeError:
            raise
        except Exception:
            return None

    spy = fetch("SPY")
    for i, tk in enumerate(sorted(tickers), 1):
        closes[tk] = fetch(tk)

    def close_asof(series, d):
        """Latest close ON OR BEFORE date d (the price as of when the screen ran)."""
        if series is None or len(series) == 0:
            return None
        try:
            idx = series.index[series.index <= d]
            if len(idx) == 0:
                return None
            return float(series.loc[idx[-1]])
        except Exception:
            return None

    def rets(tk, flag_date):
        s = closes.get(tk)
        last = float(s.iloc[-1]) if s is not None and len(s) else None
        flag = close_asof(s, flag_date)
        spy_last = float(spy.iloc[-1]) if spy is not None and len(spy) else None
        spy_flag = close_asof(spy, flag_date)
        r = (last / flag - 1) * 100 if (last and flag) else None
        sr = (spy_last / spy_flag - 1) * 100 if (spy_last and spy_flag) else None
        vs = (r - sr) if (r is not None and sr is not None) else None
        return flag, last, r, sr, vs

    for p in picks:
        tk = (p["ticker"] or "").upper()
        p["flag"], p["last"], p["ret"], p["spy"], p["vs"] = (
            rets(tk, p["date"]) if tk in closes and closes[tk] is not None else (None, None, None, None, None)
        )

    # ---- summary per ticker ----
    summary = {}
    for p in picks:
        tk = (p["ticker"] or "").upper()
        if not tk:
            continue
        e = summary.setdefault(tk, {"first": p["date"], "name": p["display"], "times": 0,
                                    "best": 0, "flag": None, "last": None, "ret": None, "spy": None, "vs": None})
        e["times"] += 1
        e["best"] = max(e["best"], p["screens"])
        if p["date"] < e["first"]:
            e["first"] = p["date"]
            e["name"] = p["display"]
        # store first-seen metrics
        if p["date"] == e["first"] and e["flag"] is None:
            e["flag"], e["last"], e["ret"], e["spy"], e["vs"] = p["flag"], p["last"], p["ret"], p["spy"], p["vs"]

    # ---- per-run cohort stats ----
    run_stats = []
    for d, rows in runs:
        rp = [p for p in picks if p["date"] == d and p["ret"] is not None]
        avg = sum(p["ret"] for p in rp) / len(rp) if rp else None
        avg_vs = sum(p["vs"] for p in rp if p["vs"] is not None) / max(1, len([p for p in rp if p["vs"] is not None])) if rp else None
        top = max(rows, key=lambda r: r[2])[1] if rows else ""
        run_stats.append({"date": d, "n": len(rows), "top": re.sub(r"[\[\]]", "", top), "avg": avg, "avg_vs": avg_vs})

    # ---- print (always) ----
    def f(x, nd=1):
        return "-" if x is None else f"{x:.{nd}f}"
    print("\n== PICKS (newest first) ==")
    for p in sorted(picks, key=lambda x: (-int(x["date"].replace("-", "")), x["rank"]))[:20]:
        print(f"  {p['date']}  #{p['rank']:<2} {p['ticker'] or p['display']:<6} screens={p['screens']:<3} ret={f(p['ret'])}% vs SPY={f(p['vs'])}%")
    print("\n== RUN COHORTS ==")
    for r in run_stats:
        print(f"  {r['date']}  names={r['n']:<3} top={r['top']:<22} avgRet={f(r['avg'])}%  avgVsSPY={f(r['avg_vs'])}%")
    print("\n== TOP SUMMARY (by vs SPY) ==")
    for tk, e in sorted(summary.items(), key=lambda kv: (kv[1]["vs"] is None, -(kv[1]["vs"] or 0)))[:12]:
        print(f"  {tk:<6} first={e['first']} times={e['times']} ret={f(e['ret'])}% vsSPY={f(e['vs'])}%")

    if args.dry:
        return

    # ---- build xlsx via officecli ----
    ocli = shutil.which("officecli") or os.path.expanduser("~/.local/bin/officecli")
    if not os.path.exists(ocli):
        print("! officecli not found — printed tables only")
        sys.exit(2)
    out = args.out
    tmp = out + ".tmp.xlsx"
    for f_ in (tmp,):
        try:
            os.path.exists(f_) and os.remove(f_)
        except Exception as e:
            print("! cannot replace", f_, e)
            sys.exit(2)

    def run_ocli(*cmd, input_json=None):
        c = [ocli] + list(cmd)
        r = subprocess.run(c, capture_output=True, text=True,
                           input=json.dumps(input_json) if input_json else None)
        if r.returncode != 0:
            print("! officecli", cmd[0], "failed:", (r.stdout or "")[-300:], (r.stderr or "")[-300:])
        return r

    def col(i):  # 0 -> A
        s = ""
        i += 1
        while i:
            i, rem = divmod(i - 1, 26)
            s = chr(65 + rem) + s
        return s

    # (officecli kickoff deferred — only runs if openpyxl is unavailable; its resident
    #  process rewrites files asynchronously, so we avoid starting it unnecessarily)

    def sheet_ops(sheet, header, data_rows):
        ops = []
        for j, h in enumerate(header):
            ops.append({"command": "set", "path": f"/{sheet}/{col(j)}1", "props": {"value": str(h)}})
        for i, row in enumerate(data_rows, start=2):
            for j, v in enumerate(row):
                if v is None:
                    continue
                ops.append({"command": "set", "path": f"/{sheet}/{col(j)}{i}", "props": {"value": str(v)}})
        ops.append({"command": "set", "path": f"/{sheet}/A1:{col(len(header)-1)}1", "props": {"font.bold": "true"}})
        ops.append({"command": "set", "path": f"/{sheet}", "props": {"freeze": "A2"}})
        return ops

    # Picks sheet (newest first)
    picks_sorted = sorted(picks, key=lambda x: (-int(x["date"].replace("-", "")), x["rank"]))
    header_p = ["Date", "Rank", "Ticker", "Name", "Screens", "Categories", "Price@Flag", "Last", "Ret %", "SPY %", "vs SPY %"]
    rows_p = []
    for p in picks_sorted:
        rows_p.append([p["date"], p["rank"], p["ticker"] or "", p["display"], p["screens"], p["cats"],
                       round(p["flag"], 2) if p["flag"] else None,
                       round(p["last"], 2) if p["last"] else None,
                       round(p["ret"], 2) if p["ret"] is not None else None,
                       round(p["spy"], 2) if p["spy"] is not None else None,
                       round(p["vs"], 2) if p["vs"] is not None else None])

    header_s = ["Ticker", "Name", "First Seen", "Times", "Best Screens", "Price@First", "Last", "Ret %", "SPY %", "vs SPY %"]
    rows_s = []
    for tk, e in sorted(summary.items(), key=lambda kv: (kv[1]["vs"] is None, -(kv[1]["vs"] or 0))):
        rows_s.append([tk, e["name"], e["first"], e["times"], e["best"],
                       round(e["flag"], 2) if e["flag"] else None,
                       round(e["last"], 2) if e["last"] else None,
                       round(e["ret"], 2) if e["ret"] is not None else None,
                       round(e["spy"], 2) if e["spy"] is not None else None,
                       round(e["vs"], 2) if e["vs"] is not None else None])

    header_r = ["Date", "Names", "Top Pick", "Avg Ret %", "Avg vs SPY %"]
    rows_r = []
    for r in sorted(run_stats, key=lambda x: x["date"], reverse=True):
        rows_r.append([r["date"], r["n"], r["top"],
                       round(r["avg"], 2) if r["avg"] is not None else None,
                       round(r["avg_vs"], 2) if r["avg_vs"] is not None else None])

    # ---- sheets: Picks + one sheet per screen family + Summary + Runs ----
    pref = ["Fundamental", "Momentum", "Technical", "Theme", "Valuation", "Insider", "Earnings", "Quality"]
    seen = []
    for r in rows_p:
        for cc in str(r[5] or "").split(","):
            cc = cc.strip().title()
            if cc and cc not in seen:
                seen.append(cc)
    cat_tables = []
    for cname in [c for c in pref if c in seen] + [c for c in seen if c not in pref]:
        sel = [r for r in rows_p if cname.lower() in str(r[5] or "").lower()]
        if sel:
            cat_tables.append((cname, header_p, sel))
    core_tables = (("Picks", header_p, rows_p), ("Summary", header_s, rows_s), ("Runs", header_r, rows_r))
    tables = (("Picks", header_p, rows_p), *cat_tables, ("Summary", header_s, rows_s), ("Runs", header_r, rows_r))
    if build_xlsx_openpyxl(args.out, tables):
        try:
            os.path.exists(tmp) and os.remove(tmp)
        except Exception:
            pass
        write_csvs(args.out, *core_tables)
        write_html(args.out, *tables)
        write_markdown(args.out, *tables)
        return
    if not os.path.exists(ocli):
        print("! no xlsx writer available — csv/html/md only")
        write_csvs(args.out, *core_tables)
        write_html(args.out, *tables)
        write_markdown(args.out, *tables)
        return

    # ---- officecli fallback path ----
    run_ocli("create", tmp)
    run_ocli("set", tmp, "/Sheet1", "--prop", "name=Picks")
    for _tn, _, _ in tables[1:]:
        run_ocli("add", tmp, "/", "--type", "sheet", "--prop", "name=" + _tn)

    for sheet, header, rows_ in tables:
        ops = sheet_ops(sheet, header, rows_)
        t0 = time.time()
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            json.dump(ops, tf)
            tf_path = tf.name
        run_ocli("batch", tmp, "--input", tf_path)
        os.remove(tf_path)
        print(f"  sheet {sheet}: {len(rows_)} rows ({time.time()-t0:.0f}s)")

    run_ocli("close", tmp)
    post_process_inline_strings(tmp)
    try:
        os.replace(tmp, out)
        print("wrote", out)
    except Exception as e:
        print("! could not move into place:", e, "-> kept", tmp)
        out = tmp
    write_csvs(out, *core_tables)
    write_html(out, *tables)
    write_markdown(out, *tables)


if __name__ == "__main__":
    main()
