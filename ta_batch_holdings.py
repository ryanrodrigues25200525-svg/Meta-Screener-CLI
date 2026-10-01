#!/usr/bin/env python3
"""TradingAgents research on PM holdings.
Defaults to one ticker at a time because OpenRouter free-tier calls are
rate-limited; parallel workers can be requested explicitly when appropriate.

Each completed ticker banks its full report into the KG automatically.
"""
import subprocess, os, sys, glob, time, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

FINANCE_AI = os.path.dirname(os.path.abspath(__file__))
KG_ROOT = os.environ.get("FINANCE_KG_ROOT") or (
    "/documents/Finance Knowledge Graph"
    if os.path.isdir("/documents/Finance Knowledge Graph")
    else os.path.expanduser("~/Documents/Finance Knowledge Graph")
)
KG_NOTES = os.path.join(KG_ROOT, "Notes")
TODAY = date.today().isoformat()

# current PM holdings (ADBE + GM already done; everything else gets researched)
HOLDINGS = ["PBR", "VTRS", "SM", "VALE", "PRU", "GIS", "CAG", "PFE", "NVO", "HPQ", "GM", "ADBE"]


def already_done(t):
    return bool(glob.glob(os.path.join(KG_NOTES, f"{TODAY} {t} TradingAgents research.md")) or
                glob.glob(os.path.join(KG_NOTES, f"* {t} TradingAgents research.md")))


def run_one(t):
    print(f"[start] {t}", flush=True)
    t0 = time.time()
    try:
        r = subprocess.run(
            [sys.executable, os.path.join(FINANCE_AI, "ta_research.py"), t, "--date", TODAY],
            cwd=FINANCE_AI, timeout=2400, capture_output=True, text=True,
        )
        # surface the last few lines of output for status
        tail = (r.stdout or "").strip().splitlines()[-3:]
        print(f"[done] {t} ({(time.time()-t0)/60:.1f} min, exit {r.returncode})", flush=True)
        for line in tail:
            print(f"    {line}", flush=True)
        return t, r.returncode
    except Exception as e:
        print(f"[fail] {t}: {e}", flush=True)
        return t, -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=1, help="parallel concurrency (default: 1 for free-tier stability)")
    ap.add_argument("--tickers", nargs="*", default=None)
    args = ap.parse_args()

    targets = [t.upper() for t in (args.tickers or HOLDINGS)]
    to_run = [t for t in targets if not already_done(t)]
    workers = max(1, args.workers)
    print(f"=== TA holdings: {len(to_run)} to run (workers={workers}) ===", flush=True)
    if not to_run:
        print("all done", flush=True)
        return
    results = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(run_one, t): t for t in to_run}
        for fut in as_completed(futs):
            t, rc = fut.result()
            results[t] = rc
    ok = sum(1 for rc in results.values() if rc == 0)
    print(f"\n=== batch complete: {ok}/{len(to_run)} succeeded ===", flush=True)
    for t, rc in results.items():
        print(f"  {t}: {'OK' if rc==0 else 'FAIL'}", flush=True)


if __name__ == "__main__":
    main()
