"""Leaderboard: tickers appearing most consistently across screener tops."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import meta_screener_cli as cli


def _result(tmp, name, rows):
    path = Path(tmp) / f"{name}.json"
    path.write_text(json.dumps({
        "summary": name,
        "report_path": None,
        "top": [{"rank": i + 1, "ticker": t, "name": t, "detail": d}
                for i, (t, d) in enumerate(rows)],
    }), encoding="utf-8")
    return path


class LeaderboardTests(unittest.TestCase):
    def test_counts_appearances_tiebreak_best_rank(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            _result(tmp, "a", [("XOM", "ok"), ("AAPL", "ok")])
            _result(tmp, "b", [("AAPL", "ok"), ("XOM", "ok")])
            _result(tmp, "c", [("AAPL", "ok"), ("MSFT", "ok")])
            board = cli.compute_leaderboard(Path(tmp), top_n=10)
        self.assertEqual(board[0][:2], ("AAPL", 3))
        self.assertEqual(board[1][:2], ("XOM", 2))
        # MSFT and the rest appear once; best rank wins ties
        self.assertEqual(board[2][0], "MSFT")

    def test_blank_rows_do_not_count(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            _result(tmp, "a", [("AAPL", "blank — no data"), ("XOM", "ok")])
            board = cli.compute_leaderboard(Path(tmp), top_n=10)
        self.assertEqual(board, [("XOM", 1, 2)])

    def test_registry_has_no_meta_overlap(self):
        registry = cli.read_registry()
        ids = [s["id"] for s in registry["screeners"]]
        self.assertNotIn("meta-overlap", ids)
        fams = [i for i in ids if i.startswith("meta-")]
        self.assertEqual(len(fams), 8)


if __name__ == "__main__":
    unittest.main()
