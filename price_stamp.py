#!/usr/bin/env python3
"""
price_stamp.py — stamp Companies/*.md frontmatter with live yfinance price.
"""
import re
import glob
import os
import time
import datetime

COMPANIES_DIR = "/documents/Finance Knowledge Graph/Companies"
TODAY = datetime.date.today().isoformat()

FM_RE = re.compile(r'\A---\s*\n(.*?)\n---\s*\n?', re.DOTALL)
TICKER_DQ = re.compile(r'^\s*ticker:\s*"([^"]*)"', re.MULTILINE)
TICKER_SQ = re.compile(r"^\s*ticker:\s*'([^']*)'", re.MULTILINE)
TICKER_BARE = re.compile(r'^\s*ticker:\s*([^\s#"\']+)', re.MULTILINE)
PRICE_LINE_RE = re.compile(r'^\s*price:\s*".*?"\s*$', re.MULTILINE)

def extract_ticker(fm_text):
    m = TICKER_DQ.search(fm_text)
    if m:
        return m.group(1).strip()
    m = TICKER_SQ.search(fm_text)
    if m:
        return m.group(1).strip()
    m = TICKER_BARE.search(fm_text)
    if m:
        v = m.group(1).strip().strip('"').strip("'")
        return v
    return None

def format_mcap(mcap):
    if mcap is None or mcap == 0:
        return "n/a"
    try:
        mcap = float(mcap)
    except:
        return "n/a"
    if mcap >= 1e12:
        return f"${mcap/1e12:.1f}T"
    elif mcap >= 1e9:
        return f"${mcap/1e9:.1f}B"
    elif mcap >= 1e6:
        return f"${mcap/1e6:.1f}M"
    else:
        return f"${mcap:,.0f}"

def fetch_data(ticker_str, yf):
    last_exc = None
    for attempt in range(2):
        try:
            t = yf.Ticker(ticker_str)
            # history for 1 month
            hist = t.history(period="1mo", auto_adjust=False)
            if hist is None or hist.empty or len(hist) < 1:
                raise ValueError("empty history")
            # handle Close column
            if "Close" not in hist.columns:
                raise ValueError("no Close col")
            # drop NaN closes
            closes = hist["Close"].dropna()
            if len(closes) < 1:
                raise ValueError("no valid closes")
            last_close = float(closes.iloc[-1])
            first_close = float(closes.iloc[0])
            if first_close == 0:
                raise ValueError("first close zero")
            pct_1m = (last_close - first_close) / first_close * 100.0

            mcap = None
            # try fast_info first (cheaper / faster)
            try:
                fi = t.fast_info
                # fast_info may be dict-like or object
                if isinstance(fi, dict):
                    mcap = fi.get("market_cap") or fi.get("marketCap")
                else:
                    mcap = getattr(fi, "market_cap", None)
                    if mcap is None:
                        mcap = getattr(fi, "marketCap", None)
            except Exception:
                pass
            if not mcap:
                try:
                    info = t.info
                    if isinstance(info, dict):
                        mcap = info.get("marketCap")
                except Exception:
                    pass
            return last_close, pct_1m, mcap
        except Exception as e:
            last_exc = e
            if attempt == 0:
                time.sleep(0.6)
                continue
            else:
                raise last_exc

def main():
    import yfinance as yf
    start = time.time()
    files = sorted(glob.glob(os.path.join(COMPANIES_DIR, "*.md")))
    stamped = 0
    skipped = []
    total = len(files)

    for path in files:
        fname = os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"SKIP {fname}: read error {e}")
            skipped.append(f"{fname}: read error")
            time.sleep(0.4)
            continue

        m = FM_RE.search(content)
        if not m:
            print(f"SKIP {fname}: no frontmatter")
            skipped.append(f"{fname}: no frontmatter")
            time.sleep(0.4)
            continue

        fm_text = m.group(1)
        ticker = extract_ticker(fm_text)
        if ticker is None or ticker.strip() == "":
            print(f"SKIP {fname}: ticker missing/empty")
            skipped.append(f"{fname}: ticker missing/empty")
            time.sleep(0.4)
            continue

        ticker = ticker.strip()
        # yfinance tickers are generally uppercase, keep as is
        try:
            last_close, pct_1m, mcap = fetch_data(ticker, yf)
        except Exception as e:
            print(f"SKIP {ticker} ({fname}): no quote / fetch failed ({e})")
            skipped.append(f"{ticker} ({fname}): no quote / {e}")
            time.sleep(0.4)
            continue

        mcap_str = format_mcap(mcap)
        price_line = f'price: "{last_close:.2f} ({pct_1m:+.1f}% 1m, mktcap {mcap_str}) as-of {TODAY}"'

        # add/update frontmatter
        if PRICE_LINE_RE.search(fm_text):
            new_fm_text = PRICE_LINE_RE.sub(price_line, fm_text)
        else:
            # insert before closing ---
            new_fm_text = fm_text.rstrip() + "\n" + price_line

        # reconstruct file
        new_content = "---\n" + new_fm_text.strip("\n") + "\n---\n" + content[m.end():]
        # If original had no trailing newline after ---, ensure we keep rest correctly
        # content[m.end():] already starts after the matched block

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"STAMP {ticker} ({fname}): {price_line}")
            stamped += 1
        except Exception as e:
            print(f"SKIP {ticker} ({fname}): write error {e}")
            skipped.append(f"{ticker} ({fname}): write error {e}")

        time.sleep(0.4)

    elapsed = time.time() - start
    print(f"\nDONE: stamped={stamped} skipped={len(skipped)} total={total} elapsed={elapsed:.1f}s")
    if skipped:
        print("SKIP LIST:")
        for s in skipped:
            print("  ", s)

if __name__ == "__main__":
    main()
