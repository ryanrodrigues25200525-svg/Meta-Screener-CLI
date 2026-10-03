"""Events/research Yahoo-only tests (fake providers only, no network, no KG reads).

Covers Task 6: catalyst earnings via Yahoo, macro-calendar retirement,
frontier Yahoo news, holdings/analyst screens on --tickers or the shared
demo universe (no pm_portfolio.json, no Companies/*.md), and screeners.json
metadata where every entry is Yahoo-backed.
"""

from __future__ import annotations

import json
import os
import unittest
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


def earnings_frame(dates):
    """Yahoo-style get_earnings_dates frame indexed by earnings date."""
    idx = pd.to_datetime(list(dates))
    return pd.DataFrame({"Earnings Date": list(idx)}, index=idx)


class FakeYahooEarnings:
    """Stub client: ticker -> list of upcoming earnings dates."""

    def __init__(self, by_ticker):
        self.by_ticker = {k.upper(): list(v) for k, v in by_ticker.items()}

    def get_earnings_dates(self, ticker, limit=12):
        return earnings_frame(self.by_ticker.get(ticker.upper(), []))


class FakeYahooNews:
    """Stub client: ticker -> list of Yahoo news dicts."""

    def __init__(self, by_ticker):
        self.by_ticker = {k.upper(): list(v) for k, v in by_ticker.items()}

    def get_news(self, ticker):
        return list(self.by_ticker.get(ticker.upper(), []))


class FakeYahooInfo:
    """Stub client: ticker -> Yahoo info dict."""

    def __init__(self, infos):
        self.infos = {k.upper(): dict(v) for k, v in infos.items()}

    def get_info(self, ticker):
        return dict(self.infos.get(ticker.upper(), {}))


class FakeYahooOptions(FakeYahooInfo):
    """Stub client: info plus options expirations and chains."""

    def __init__(self, infos, chains):
        super().__init__(infos)
        self.chains = chains

    def get_options(self, ticker):
        entry = self.chains.get(ticker.upper())
        return list(entry["expirations"]) if entry else []

    def get_option_chain(self, ticker, expiry=None):
        entry = self.chains.get(ticker.upper())
        if not entry:
            return {"calls": pd.DataFrame(), "puts": pd.DataFrame()}
        return {"calls": entry["calls"], "puts": entry["puts"]}


def sample_news(title="Apple reports strong quarter", publisher="Yahoo Finance"):
    return {
        "title": title,
        "link": "https://finance.yahoo.com/news/example-1.html",
        "publisher": publisher,
        "providerPublishTime": 1767225600,
    }


class CatalystYahooTests(unittest.TestCase):
    def test_catalyst_uses_yahoo_earnings_only(self):
        import catalyst_scan

        coming = date.today() + timedelta(days=5)
        payload = catalyst_scan.build_catalyst_payload(
            ["AAPL"], provider=FakeYahooEarnings({"AAPL": [coming]})
        )
        self.assertTrue(
            any("earnings" in r["detail"].lower() for r in payload["top"])
            or "earnings" in payload["summary"].lower()
        )
        self.assertEqual(payload["top"][0]["ticker"], "AAPL")

    def test_catalyst_blank_when_yahoo_has_no_earnings_dates(self):
        import catalyst_scan

        payload = catalyst_scan.build_catalyst_payload(
            ["AAPL"], provider=FakeYahooEarnings({})
        )
        self.assertIn("blank", payload["summary"].lower())
        self.assertIn("blank", payload["top"][0]["detail"].lower())

    def test_catalyst_does_not_read_kg_or_call_yfinance_directly(self):
        src = Path("catalyst_scan.py").read_text(encoding="utf-8")
        for banned in ("kg_links", "upcoming_catalysts", "Important Dates",
                       "Finance Knowledge Graph", "pm_portfolio",
                       "import yfinance", "from yfinance",
                       "yfinance.Ticker", "yf.Ticker("):
            self.assertNotIn(banned, src)


class MacroRetirementTests(unittest.TestCase):
    def test_macro_retired_or_yahoo_only(self):
        registry = json.loads(Path("screeners.json").read_text(encoding="utf-8"))
        ids = [s["id"] for s in registry["screeners"]]
        # yfinance has no macro calendar, so the static calendar retires.
        yahoo_has_no_macro = True
        if yahoo_has_no_macro:
            self.assertNotIn("macro-calendar", ids)
        self.assertNotIn("econ_calendar.py",
                         [s.get("file") for s in registry["screeners"]])

    def test_econ_calendar_archived_not_active(self):
        self.assertFalse(Path("econ_calendar.py").exists())
        self.assertTrue(Path("archive/econ_calendar.py").is_file())


class FrontierYahooTests(unittest.TestCase):
    def test_frontier_lists_yahoo_news_per_ticker(self):
        import frontier_scan

        payload = frontier_scan.build_frontier_payload(
            ["AAPL"], provider=FakeYahooNews({"AAPL": [sample_news()]})
        )
        self.assertEqual(payload["top"][0]["ticker"], "AAPL")
        self.assertIn("apple reports strong quarter",
                      payload["top"][0]["detail"].lower())
        self.assertIn("finance.yahoo.com", payload["top"][0]["detail"])

    def test_frontier_blank_when_no_yahoo_news(self):
        import frontier_scan

        payload = frontier_scan.build_frontier_payload(
            ["AAPL"], provider=FakeYahooNews({})
        )
        self.assertIn("blank", payload["summary"].lower())

    def test_frontier_does_not_read_notes_or_rank_importance(self):
        src = Path("frontier_scan.py").read_text(encoding="utf-8")
        for banned in ("kg_links", "What's still open", "Important Dates",
                       "Finance Knowledge Graph", "glob.glob",
                       "import yfinance", "from yfinance",
                       "yfinance.Ticker", "yf.Ticker("):
            self.assertNotIn(banned, src)


class HoldingsUniverseTests(unittest.TestCase):
    def test_screens_share_demo_holdings_universe(self):
        import demo_universe
        import analyst_scan
        import short_interest
        import dividend_analysis
        import unusual_options

        self.assertTrue(demo_universe.HOLDINGS_TICKERS)
        self.assertEqual(analyst_scan.default_tickers(),
                         demo_universe.HOLDINGS_TICKERS)
        self.assertEqual(short_interest.default_tickers(),
                         demo_universe.HOLDINGS_TICKERS)
        self.assertEqual(dividend_analysis.default_tickers(),
                         demo_universe.HOLDINGS_TICKERS)
        self.assertEqual(unusual_options.default_tickers(),
                         demo_universe.HOLDINGS_TICKERS)

    def test_holdings_modules_do_not_read_portfolio_or_kg(self):
        for module in ("analyst_scan.py", "short_interest.py",
                       "dividend_analysis.py", "unusual_options.py"):
            src = Path(module).read_text(encoding="utf-8")
            for banned in ("pm_portfolio", "Companies", "kg_links",
                           "load_ticker_map", "Finance Knowledge Graph",
                           "Important Dates", "import yfinance",
                           "from yfinance", "yfinance.Ticker", "yf.Ticker("):
                self.assertNotIn(banned, src, f"{module} contains {banned!r}")


class HoldingsFactsTests(unittest.TestCase):
    def test_analyst_consensus_from_yahoo_info(self):
        import analyst_scan

        provider = FakeYahooInfo({"AAPL": {
            "recommendationKey": "buy", "targetMeanPrice": 200.0,
            "targetHighPrice": 250.0, "targetLowPrice": 150.0,
            "numberOfAnalystOpinions": 30, "currentPrice": 180.0,
        }})
        payload = analyst_scan.build_result_payload(
            analyst_scan.screen_tickers(["AAPL"], provider=provider),
            "analyst.md",
        )
        self.assertEqual(payload["top"][0]["ticker"], "AAPL")
        self.assertIn("buy", payload["top"][0]["detail"].lower())

    def test_short_interest_from_yahoo_info(self):
        import short_interest

        provider = FakeYahooInfo({"AAPL": {
            "shortPercentOfFloat": 0.25, "shortRatio": 3.0, "sharesShort": 10,
        }})
        payload = short_interest.build_result_payload(
            short_interest.screen_tickers(["AAPL"], provider=provider), "s.md"
        )
        self.assertEqual(payload["top"][0]["ticker"], "AAPL")
        self.assertIn("25", payload["top"][0]["detail"])

    def test_dividend_from_yahoo_info(self):
        import dividend_analysis

        provider = FakeYahooInfo({"VZ": {
            "dividendYield": 0.06, "dividendRate": 2.6, "payoutRatio": 0.6,
            "currentPrice": 43.0,
        }})
        payload = dividend_analysis.build_result_payload(
            dividend_analysis.screen_tickers(["VZ"], provider=provider), "d.md"
        )
        self.assertEqual(payload["top"][0]["ticker"], "VZ")
        self.assertIn("yield", payload["top"][0]["detail"].lower())

    def test_unusual_options_from_yahoo_chain(self):
        import unusual_options

        calls = pd.DataFrame({"volume": [100, 5], "openInterest": [10, 10]})
        puts = pd.DataFrame({"volume": [1, 1], "openInterest": [50, 50]})
        provider = FakeYahooOptions(
            {"AAPL": {}}, {"AAPL": {"expirations": ["2026-10-17"],
                                    "calls": calls, "puts": puts}})
        payload = unusual_options.build_result_payload(
            unusual_options.screen_tickers(["AAPL"], provider=provider), "o.md"
        )
        self.assertEqual(payload["top"][0]["ticker"], "AAPL")
        self.assertIn("unusual", payload["top"][0]["detail"].lower())


class ScreenTrackerTests(unittest.TestCase):
    def test_tracker_resolves_ticker_symbols_without_kg(self):
        import screen_tracker

        ticker, _display = screen_tracker.resolve_ticker("AAPL", {})
        self.assertEqual(ticker, "AAPL")

    def test_tracker_source_has_no_kg_reads(self):
        src = Path("screen_tracker.py").read_text(encoding="utf-8")
        for banned in ("kg_links", "load_ticker_map", "Companies",
                       "Finance Knowledge Graph", "pm_portfolio",
                       "Important Dates", "import yfinance", "from yfinance",
                       "yfinance.Ticker", "yf.Ticker("):
            self.assertNotIn(banned, src)


class RegistryYahooTests(unittest.TestCase):
    def test_every_entry_is_yahoo_backed_with_matching_provider(self):
        registry = json.loads(Path("screeners.json").read_text(encoding="utf-8"))
        self.assertTrue(registry["screeners"])
        for entry in registry["screeners"]:
            self.assertTrue(entry.get("yahoo"), entry.get("id"))
            self.assertIn("yahoo", entry.get("provider", "").lower(),
                          entry.get("id"))

    def test_task6_entries_list_yahoo_facts_only(self):
        registry = json.loads(Path("screeners.json").read_text(encoding="utf-8"))
        by_id = {s["id"]: s for s in registry["screeners"]}
        for entry_id in ("analyst-consensus", "short-interest",
                         "dividend-analysis", "options-activity",
                         "catalyst-calendar", "research-frontier",
                         "screen-history"):
            blob = json.dumps(by_id[entry_id])
            for banned in ("pm_portfolio", "Important Dates", "Knowledge Graph"):
                self.assertNotIn(banned, blob, entry_id)

    def test_screen_history_stays_opt_in(self):
        registry = json.loads(Path("screeners.json").read_text(encoding="utf-8"))
        by_id = {s["id"]: s for s in registry["screeners"]}
        self.assertIn("screen-history", by_id)
        self.assertFalse(by_id["screen-history"]["default_enabled"])


if __name__ == "__main__":
    unittest.main()
