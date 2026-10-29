import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sync_tw_stock_prices import (
    in_update_window,
    normalize_tw_code,
    parse_holidays,
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

    def test_update_window_is_weekday_0830_to_1430_taipei(self):
        tz = ZoneInfo("Asia/Taipei")
        at = lambda d, h, m: datetime(2026, 10, d, h, m, tzinfo=tz)  # 29 = Thursday
        self.assertFalse(in_update_window(at(29, 8, 20)))
        self.assertTrue(in_update_window(at(29, 8, 30)))
        self.assertTrue(in_update_window(at(29, 11, 0)))
        self.assertTrue(in_update_window(at(29, 14, 35)))  # delayed 14:30 trigger
        self.assertFalse(in_update_window(at(29, 14, 40)))
        self.assertFalse(in_update_window(at(31, 10, 0)))  # Saturday

    def test_holidays_exclude_first_and_last_trading_days(self):
        items = [
            {"Name": "中華民國開國紀念日", "Date": "1150101"},
            {"Name": "國曆新年開始交易日", "Date": "1150102", "Description": "國曆新年開始交易。"},
            {"Name": "農曆春節前最後交易日", "Date": "1150211"},
            {"Name": "市場無交易，僅辦理結算交割作業", "Date": "1150212"},
            {"Name": "國慶日", "Date": "20261010"},
        ]
        self.assertEqual(
            parse_holidays(items),
            {date(2026, 1, 1), date(2026, 2, 12), date(2026, 10, 10)},
        )


if __name__ == "__main__":
    unittest.main()
