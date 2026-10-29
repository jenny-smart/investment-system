import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sync_tw_stock_prices import (
    in_update_window,
    normalize_tw_code,
    plan_rows,
    recent_date,
    valid_price,
)


class StockSyncTests(unittest.TestCase):
    def test_duplicate_codes_reference_first_j_cell(self):
        column = [["2330"], [""], ["0050"], ["2330.0"], [], ["AAPL"], ["0050"], ["2330"]]
        prices, duplicates, skipped = plan_rows(column)
        self.assertEqual(prices, [(7, "2330"), (9, "0050")])
        self.assertEqual(duplicates, [(10, "=J7"), (13, "=J9"), (14, "=J7")])
        self.assertEqual(skipped, [12])

    def test_normalize_dynamic_taiwan_ticker(self):
        self.assertEqual(normalize_tw_code("2330.0"), "2330")
        self.assertEqual(normalize_tw_code(" 00740b "), "00740B")
        self.assertIsNone(normalize_tw_code("AAPL"))

    def test_reject_invalid_prices_and_stale_or_future_dates(self):
        for value in (None, "-", 0, -1, "nan", "inf"):
            self.assertIsNone(valid_price(value))
        self.assertTrue(recent_date("20261006", date(2026, 10, 7)))
        self.assertFalse(recent_date("20260901", date(2026, 10, 7)))
        self.assertFalse(recent_date("20261008", date(2026, 10, 7)))

    def test_update_window_is_0730_to_1430_taipei(self):
        tz = ZoneInfo("Asia/Taipei")
        at = lambda h, m: datetime(2026, 10, 29, h, m, tzinfo=tz)
        self.assertFalse(in_update_window(at(7, 20)))
        self.assertTrue(in_update_window(at(7, 30)))
        self.assertTrue(in_update_window(at(11, 0)))
        self.assertTrue(in_update_window(at(14, 35)))  # delayed 14:30 trigger
        self.assertFalse(in_update_window(at(14, 40)))
        self.assertFalse(in_update_window(at(19, 30)))


if __name__ == "__main__":
    unittest.main()
