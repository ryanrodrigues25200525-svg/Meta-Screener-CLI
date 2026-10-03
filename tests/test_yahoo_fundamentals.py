"""Yahoo-backed fundamental screens (fake provider only, no network, no KG reads)."""

from __future__ import annotations

import os
import tempfile
import unittest
import unittest.mock

import pandas as pd


def quarterly_frame(revenues, label="Total Revenue"):
    cols = [f"2024Q{i + 1}" for i in range(len(revenues))]
    return pd.DataFrame({c: {label: v} for c, v in zip(cols, revenues)})


class FakeYahoo:
    """Minimal YahooClient-compatible stub: financials + info only."""

    def __init__(self, frames, infos=None):
        # ticker -> DataFrame (quarterly; reused for annual) or (annual, quarterly)
        self.frames = {k.upper(): v for k, v in frames.items()}
        self.infos = infos or {}

    def _frame(self, ticker, kind):
        entry = self.frames.get(ticker.upper())
        if entry is None:
            return pd.DataFrame()
        if isinstance(entry, tuple):
            annual, quarterly = entry
            return quarterly if kind.startswith("quarterly") else annual
        return entry

    def get_financials(self, ticker, kind="income"):
        return self._frame(ticker, kind)

    def get_info(self, ticker):
        return dict(self.infos.get(ticker.upper(), {
            "shortName": ticker.upper(),
            "marketCap": 10_000_000_000,
            "currency": "USD",
            "financialCurrency": "USD",
        }))


def accelerating_quarterly():
    # QoQ: +10.0%, +13.6%, +20.0%, +25.0% -> accelerating, latest positive
    return quarterly_frame(
        [80_000_000, 88_000_000, 100_000_000, 120_000_000, 150_000_000],
        "Total Revenue",
    )


class RotationYahooTests(unittest.TestCase):
    def test_rotation_yahoo_financials_with_blank_on_missing(self):
        from screeners.discovery import rotation_screen

        fake = {"AAPL": accelerating_quarterly(), "MSFT": pd.DataFrame()}
        payload = rotation_screen.build_rotation_payload(
            ["AAPL", "MSFT"], provider=FakeYahoo(fake)
        )
        self.assertEqual(payload["top"][0]["ticker"], "AAPL")
        self.assertIn(
            "blank",
            payload["top"][1]["detail"].lower() + payload["summary"].lower(),
        )

    def test_rotation_works_with_temp_dirs_and_stub_provider(self):
        from screeners.discovery import rotation_screen

        with tempfile.TemporaryDirectory() as tmp:
            env = {k: v for k, v in os.environ.items() if k != "KG_VAULT"}
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with unittest.mock.patch.dict(os.environ, env, clear=True):
                    payload = rotation_screen.build_rotation_payload(
                        ["AAPL"], provider=FakeYahoo({"AAPL": accelerating_quarterly()})
                    )
            finally:
                os.chdir(old_cwd)
        self.assertEqual(payload["top"][0]["ticker"], "AAPL")

    def test_rotation_does_not_read_kg_or_call_yfinance_directly(self):
        import pathlib

        src = pathlib.Path("screeners/discovery/rotation_screen.py").read_text(encoding="utf-8")
        for banned in ("Companies", "Themes", "fundamentals_", "KG_VAULT",
                       "import yfinance", "from yfinance",
                       "yfinance.Ticker", "yf.Ticker("):
            self.assertNotIn(banned, src)


class GrowthMomentumYahooTests(unittest.TestCase):
    def test_growth_yahoo_with_blank_on_missing(self):
        from screeners.discovery import growth_momentum

        fake = {"AAPL": accelerating_quarterly(), "MSFT": pd.DataFrame()}
        payload = growth_momentum.build_result_payload(
            ["AAPL", "MSFT"], provider=FakeYahoo(fake)
        )
        self.assertEqual(payload["top"][0]["ticker"], "AAPL")
        self.assertIn(
            "blank",
            payload["top"][1]["detail"].lower() + payload["summary"].lower(),
        )

    def test_growth_works_with_temp_dirs_and_stub_provider(self):
        from screeners.discovery import growth_momentum

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                payload = growth_momentum.build_result_payload(
                    ["AAPL"], provider=FakeYahoo({"AAPL": accelerating_quarterly()})
                )
            finally:
                os.chdir(old_cwd)
        self.assertEqual(payload["top"][0]["ticker"], "AAPL")

    def test_growth_does_not_read_kg_or_call_yfinance_directly(self):
        import pathlib

        src = pathlib.Path("screeners/discovery/growth_momentum.py").read_text(encoding="utf-8")
        for banned in ("Companies", "Themes", "fundamentals_", "KG_VAULT",
                       "import yfinance", "from yfinance",
                       "yfinance.Ticker", "yf.Ticker("):
            self.assertNotIn(banned, src)


class ScreenUniverseTests(unittest.TestCase):
    def test_screens_share_demo_universe(self):
        import demo_universe
        from screeners.discovery import growth_momentum
        from screeners.discovery import rotation_screen

        self.assertEqual(rotation_screen.DEFAULT_TICKERS, demo_universe.ROTATION_TICKERS)
        self.assertEqual(growth_momentum.DEFAULT_TICKERS, demo_universe.GROWTH_TICKERS)
        self.assertTrue(demo_universe.ROTATION_TICKERS)
        self.assertTrue(demo_universe.GROWTH_TICKERS)


class RotationRowsPayloadTests(unittest.TestCase):
    def test_rotation_rows_payload_includes_blanks(self):
        from screeners.discovery import rotation_screen

        fake = FakeYahoo({"AAPL": accelerating_quarterly(), "MSFT": pd.DataFrame()})
        rows = rotation_screen.screen_tickers(["AAPL", "MSFT"], provider=fake)
        payload = rotation_screen.payload_from_rows(rows, "rotation.csv")

        tickers = [row["ticker"] for row in payload["top"]]
        self.assertEqual(tickers[0], "AAPL")
        self.assertIn("MSFT", tickers)
        blank = next(row for row in payload["top"] if row["ticker"] == "MSFT")
        self.assertIn("blank", blank["detail"].lower())
        self.assertIn("blank", payload["summary"].lower())


class GrowthSequentialTests(unittest.TestCase):
    def test_growth_rows_payload_recomputes_sequential_with_provider(self):
        from screeners.discovery import growth_momentum

        fake = FakeYahoo({"AAPL": accelerating_quarterly()})
        rows = growth_momentum.screen_tickers(["AAPL"], provider=fake)
        payload = growth_momentum.build_result_payload(rows, provider=fake)

        self.assertEqual(payload["top"][0]["ticker"], "AAPL")
        self.assertIn("sequential QoQ +", payload["top"][0]["detail"])
        self.assertNotIn("sequential QoQ n/a", payload["top"][0]["detail"])

    def test_growth_rows_payload_accepts_sequential_map(self):
        from screeners.discovery import growth_momentum

        fake = FakeYahoo({"AAPL": accelerating_quarterly()})
        rows = growth_momentum.screen_tickers(["AAPL"], provider=fake)
        payload = growth_momentum.build_result_payload(
            rows, sequential={"AAPL": (0.25, "accelerating (+10.0%, +25.0%)")}
        )

        self.assertIn("+25.0%", payload["top"][0]["detail"])


class FinancialsKindTests(unittest.TestCase):
    def test_yahoo_client_accepts_annual_quarterly_spellings(self):
        from yahoo_client import _financials_attr

        self.assertEqual(_financials_attr("annual"), "financials")
        self.assertEqual(_financials_attr("quarterly"), "quarterly_financials")
        self.assertEqual(_financials_attr("income"), "financials")
        self.assertEqual(_financials_attr("quarterly-income"), "quarterly_financials")


if __name__ == "__main__":
    unittest.main()
