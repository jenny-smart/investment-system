import unittest

from sync_us_stock_prices import find_tickers, normalize_ticker


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


if __name__ == "__main__":
    unittest.main()
