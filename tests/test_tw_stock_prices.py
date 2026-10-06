import unittest
from datetime import date

from sync_tw_stock_prices import build_updates, find_targets, recent_date, valid_price


class StockSyncTests(unittest.TestCase):
    def test_match_codes_after_row_insert_and_keep_duplicates(self):
        column = [["代號"], ["3312"], ["00740B"], ["00927"], ["6244"], ["6244"]]
        self.assertEqual(find_targets(column), [(3, "00740B"), (4, "00927"), (5, "6244"), (6, "6244")])

    def test_failed_quote_does_not_overwrite_and_only_j_is_written(self):
        self.assertEqual(build_updates("台股", [(34, "4401"), (40, "6261")],
                                       {"4401": {"price": 13.85}}),
                         [{"range": "'台股'!J34", "values": [[13.85]]}])

    def test_reject_invalid_prices_and_stale_or_future_dates(self):
        for value in (None, "-", 0, -1, "nan", "inf"):
            self.assertIsNone(valid_price(value))
        self.assertTrue(recent_date("20261006", date(2026, 10, 7)))
        self.assertFalse(recent_date("20260901", date(2026, 10, 7)))
        self.assertFalse(recent_date("20261008", date(2026, 10, 7)))


if __name__ == "__main__":
    unittest.main()
