import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sync_tw_stock_prices import (
    find_fixed_targets,
    find_na_targets,
    normalize_tw_code,
    recent_date,
    resolve_auto_mode,
    update_cell_request,
    valid_price,
)


class StockSyncTests(unittest.TestCase):
    def test_match_fixed_codes_after_row_insert_and_keep_duplicates(self):
        column = [["代號"], ["3312"], ["00740B"], ["5478"], ["6244"], ["6244"]]
        self.assertEqual(
            find_fixed_targets(column),
            [(3, "00740B"), (4, "5478"), (5, "6244"), (6, "6244")],
        )

    def test_find_only_restorable_na_targets_from_row_7(self):
        rows = [
            ["股票甲", "", "2330", "", "", "", "", "", "", "#N/A"],
            ["股票乙", "", "0050", "", "", "", "", "", "", "123"],
            ["", "", "2317", "", "", "", "", "", "", "#N/A"],
            ["股票丙", "", "00740B", "", "", "", "", "", "", "#N/A"],
            ["股票丁", "", "", "", "", "", "", "", "", "#N/A"],
        ]
        formulas = [["=F7"], ["=F8"], ["=F9"], ["=F10"], ["=F11"]]
        self.assertEqual(
            find_na_targets(rows, formulas),
            ([
                {"row": 7, "code": "2330", "formula": "=F7"},
                {"row": 10, "code": "00740B", "formula": "=F10"},
            ], [11]),
        )

    def test_na_without_formula_is_not_safe_to_replace(self):
        rows = [["股票甲", "", "2330", "", "", "", "", "", "", "#N/A"]]
        self.assertEqual(find_na_targets(rows, [["#N/A"]]), ([], [7]))

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

    def test_auto_schedule_uses_taipei_hours(self):
        tz = ZoneInfo("Asia/Taipei")
        self.assertEqual(resolve_auto_mode(datetime(2026, 10, 12, 14, 5, tzinfo=tz)), "fixed")
        self.assertEqual(resolve_auto_mode(datetime(2026, 10, 12, 7, 45, tzinfo=tz)), "temporary")
        self.assertEqual(resolve_auto_mode(datetime(2026, 10, 12, 19, 45, tzinfo=tz)), "temporary")
        self.assertEqual(resolve_auto_mode(datetime(2026, 10, 12, 8, 45, tzinfo=tz)), "restore")
        self.assertEqual(resolve_auto_mode(datetime(2026, 10, 12, 21, 45, tzinfo=tz)), "restore")
        self.assertIsNone(resolve_auto_mode(datetime(2026, 10, 12, 15, 0, tzinfo=tz)))

    def test_restore_request_writes_formula_and_background(self):
        request = update_cell_request(
            123, 9, {"formulaValue": "=GOOGLEFINANCE(C9)"},
            {"backgroundColor": {"red": 0.5}}, restore=True,
        )["updateCells"]
        self.assertEqual(request["range"]["startRowIndex"], 8)
        self.assertIn("formulaValue", request["rows"][0]["values"][0]["userEnteredValue"])
        self.assertIn("backgroundColor", request["fields"])


if __name__ == "__main__":
    unittest.main()
