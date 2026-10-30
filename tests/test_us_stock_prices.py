import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from sync_us_stock_prices import find_tickers, in_update_window, normalize_ticker


class UsStockSyncTests(unittest.TestCase):
    def test_tickers_are_read_below_header_until_blank(self):
        column = [["投資分類"], ["美股 "], ["pypl"], ["xyz"], [""], ["基富通-台"], ["abc"]]
        self.assertEqual(find_tickers(column), [(3, "PYPL"), (4, "XYZ")])

    def test_no_header_means_no_tickers(self):
        self.assertEqual(find_tickers([["pypl"], ["xyz"]]), [])

    def test_normalize_ticker(self):
        self.assertEqual(normalize_ticker(" brk.b "), "BRK.B")
        self.assertIsNone(normalize_ticker("富蘭克林"))
        self.assertIsNone(normalize_ticker("2330"))

    def test_window_is_weekday_nights_taipei(self):
        tz = ZoneInfo("Asia/Taipei")
        at = lambda d, h, m: datetime(2026, 11, d, h, m, tzinfo=tz)  # 2 = Monday
        self.assertFalse(in_update_window(at(2, 5, 0)))    # Monday early = Sunday US
        self.assertFalse(in_update_window(at(2, 20, 30)))
        self.assertTrue(in_update_window(at(2, 21, 0)))
        self.assertTrue(in_update_window(at(3, 3, 0)))
        self.assertTrue(in_update_window(at(3, 6, 5)))     # delayed 06:00 trigger
        self.assertFalse(in_update_window(at(3, 6, 30)))
        self.assertTrue(in_update_window(at(7, 6, 0)))     # Saturday morning = Friday US
        self.assertFalse(in_update_window(at(7, 21, 0)))   # Saturday night


if __name__ == "__main__":
    unittest.main()
