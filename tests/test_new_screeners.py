"""New Yahoo-only screeners: smart money, insider, Altman-Z, cash return, dividend growth."""

from __future__ import annotations

import unittest


def _frame(rows, cols):
    import pandas as pd

    return pd.DataFrame(rows, columns=cols)


class SmartMoneyTests(unittest.TestCase):
    def test_ranks_by_institutional_pct(self):
        import smart_money

        holders = _frame(
            [["BlackRock", 100, "2026-09-30", 0.08, 1000]],
            ["Holder", "Shares", "Date Reported", "% Out", "Value"],
        )

        class Fake:
            def get_holders(self, ticker):
                return holders if ticker == "AAPL" else holders.iloc[0:0]

        payload = smart_money.build_result_payload(
            smart_money.screen_tickers(["AAPL", "ZZZ"], provider=Fake()), "r"
        )
        self.assertEqual(payload["top"][0]["ticker"], "AAPL")
        self.assertIn("8", payload["top"][0]["detail"])
        self.assertIn("blank", payload["top"][1]["detail"].lower())

    def test_blank_when_no_holders(self):
        import smart_money

        class Fake:
            def get_holders(self, ticker):
                return None

        payload = smart_money.build_result_payload(
            smart_money.screen_tickers(["AAPL"], provider=Fake()), "r"
        )
        self.assertIn("blank", payload["top"][0]["detail"].lower())

    def test_pctheld_column_variant(self):
        import smart_money

        holders = _frame(
            [["BlackRock", 0.0797], ["Vanguard", 0.0657]],
            ["Holder", "pctHeld"],
        )

        class Fake:
            def get_holders(self, ticker):
                return holders

        payload = smart_money.build_result_payload(
            smart_money.screen_tickers(["AAPL"], provider=Fake()), "r"
        )
        self.assertAlmostEqual(float(payload["top"][0]["detail"].split("%")[0].split()[-1]), 14.5, places=1)
        import smart_money

        class Fake:
            def get_holders(self, ticker):
                return None

        payload = smart_money.build_result_payload(
            smart_money.screen_tickers(["AAPL"], provider=Fake()), "r"
        )
        self.assertIn("blank", payload["top"][0]["detail"].lower())


class InsiderActivityTests(unittest.TestCase):
    def test_text_column_fallback_and_grant_filter(self):
        import insider_activity

        rows = _frame(
            [["X", "CEO", None, 100, 10000, "2026-09-01", "Direct",
              "Sale at price 100 per share."],
             ["Y", "Director", None, 50, 0, "2026-09-02", "Direct",
              "Stock Award(Grant) at price 0.00 per share."]],
            ["Insider", "Position", "Transaction", "Shares", "Value",
             "Start Date", "Ownership", "Text"],
        )

        class Fake:
            def get_insider(self, ticker):
                return rows

        data = insider_activity.screen_tickers(["AAPL"], provider=Fake())
        self.assertEqual(data[0]["sellers"], 1)
        self.assertEqual(data[0]["buyers"], 0)

    def test_cluster_buys_rank_first(self):
        import insider_activity

        buys = _frame(
            [["A. Exec", "CEO", "Purchase", 1000, 100000, "2026-09-01", "Direct"],
             ["B. Dir", "Director", "Purchase", 500, 50000, "2026-09-02", "Direct"]],
            ["Insider", "Position", "Transaction", "Shares", "Value", "Start Date", "Ownership"],
        )

        class Fake:
            def get_insider(self, ticker):
                return buys if ticker == "AAPL" else buys.iloc[0:0]

        payload = insider_activity.build_result_payload(
            insider_activity.screen_tickers(["AAPL", "ZZZ"], provider=Fake()), "r"
        )
        self.assertEqual(payload["top"][0]["ticker"], "AAPL")
        self.assertIn("2", payload["top"][0]["detail"])
        self.assertIn("blank", payload["top"][1]["detail"].lower())


class AltmanZTests(unittest.TestCase):
    def test_z_score_and_zones(self):
        import altman_z

        income = _frame(
            [[100.0, 90.0], [1000.0, 900.0]],
            ["2025-12-31", "2024-12-31"],
        )
        income.index = ["EBIT", "Total Revenue"]
        balance = _frame(
            [[200.0, 180.0], [300.0, 280.0], [1000.0, 900.0], [400.0, 380.0]],
            ["2025-12-31", "2024-12-31"],
        )
        balance.index = ["Working Capital", "Retained Earnings", "Total Assets",
                         "Total Liabilities Net Minority Interest"]

        class Fake:
            def get_financials(self, ticker, kind="income"):
                return income if kind == "income" else balance

            def get_info(self, ticker):
                return {"marketCap": 600.0}

        payload = altman_z.build_result_payload(
            altman_z.screen_tickers(["AAPL"], provider=Fake()), "r"
        )
        # Z = 1.2*.2 + 1.4*.3 + 3.3*.1 + 0.6*1.5 + 1.0*1.0 = 2.89 -> grey
        self.assertAlmostEqual(payload["top"][0]["z"], 2.89, places=2)
        self.assertIn("grey", payload["top"][0]["detail"].lower())

    def test_blank_on_missing_statements(self):
        import altman_z

        class Fake:
            def get_financials(self, ticker, kind="income"):
                return None

            def get_info(self, ticker):
                return {}

        payload = altman_z.build_result_payload(
            altman_z.screen_tickers(["AAPL"], provider=Fake()), "r"
        )
        self.assertIn("blank", payload["top"][0]["detail"].lower())


class CashReturnTests(unittest.TestCase):
    def test_buyback_outflow_reports_positive_yield(self):
        import cash_return

        cf = _frame(
            [[100.0], [-20.0]],
            ["2025-12-31"],
        )
        cf.index = ["Free Cash Flow", "Repurchase Of Capital Stock"]

        class Fake:
            def get_financials(self, ticker, kind="cashflow"):
                return cf

            def get_info(self, ticker):
                return {"marketCap": 1000.0}

        payload = cash_return.build_result_payload(
            cash_return.screen_tickers(["AAPL"], provider=Fake()), "r"
        )
        self.assertIn("buyback 2.0%", payload["top"][0]["detail"])

    def test_fcf_and_buyback_yields(self):
        import cash_return

        cf = _frame(
            [[100.0, 90.0], [20.0, 10.0]],
            ["2025-12-31", "2024-12-31"],
        )
        cf.index = ["Free Cash Flow", "Repurchase Of Capital Stock"]

        class Fake:
            def get_financials(self, ticker, kind="cashflow"):
                return cf

            def get_info(self, ticker):
                return {"marketCap": 1000.0}

        payload = cash_return.build_result_payload(
            cash_return.screen_tickers(["AAPL"], provider=Fake()), "r"
        )
        self.assertIn("10", payload["top"][0]["detail"])
        self.assertIn("2", payload["top"][0]["detail"])


class DividendGrowthTests(unittest.TestCase):
    def test_streak_counts_consecutive_annual_increases(self):
        import dividend_growth
        import pandas as pd

        divs = pd.Series(
            [0.5, 0.5, 0.6, 0.6, 0.7, 0.7, 0.8, 0.8],
            index=pd.to_datetime(["2022-02-01", "2022-05-01", "2023-02-01", "2023-05-01",
                                  "2024-02-01", "2024-05-01", "2025-02-01", "2025-05-01"]),
        )

        class Fake:
            def get_dividends(self, ticker):
                return divs

        payload = dividend_growth.build_result_payload(
            dividend_growth.screen_tickers(["AAPL"], provider=Fake()), "r"
        )
        self.assertIn("3-year", payload["top"][0]["detail"])


if __name__ == "__main__":
    unittest.main()
