import unittest
from unittest import mock

import pandas as pd

from invest_app import dividends as d


class LedgerDatesUnitsTests(unittest.TestCase):
    def df(self):
        return pd.DataFrame([
            {"平台": "台新基金", "幣別": "ZAR", "基金名稱": "高盛新興市場債券Y南非幣對沖（月配）", "_確認前": True,
             "配息單位數": 840.89, "每單位配息": 14.0, "_sort_date": pd.Timestamp("2026-10-08"),
             "_ex_date": "2026/09/30", "_pay_date": "2026/10/08"},
            {"平台": "台新基金", "幣別": "ZAR", "基金名稱": "高盛新興市場債券Y南非幣對沖（月配）", "_確認前": False,
             "配息單位數": 986.6347, "每單位配息": 14.0, "_sort_date": pd.Timestamp("2026-11-08"),
             "_ex_date": "2026/10/30", "_pay_date": ""},
            {"平台": "台新基金", "幣別": "ZAR", "基金名稱": "東方匯理新興市場債券U南非幣（月配）", "_確認前": True,
             "配息單位數": 5000.0, "每單位配息": 4.4847, "_sort_date": pd.Timestamp("2026-10-31"),
             "_ex_date": "2026/10/31", "_pay_date": ""},
        ])

    def test_last_confirmed_units(self):
        self.assertEqual(d._last_confirmed_units(self.df()), {1: 840.89})

    def test_ledger_dates_from_pay_day_row(self):
        grid = [["", "台新-南非", "台新-南非"],
                ["", "高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)", "鋒裕匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)"],
                ["配息月份", "每月8日", "每月7日"]]
        with mock.patch.object(d, "_load_pay_day_grid", return_value=grid):
            dates = d._ledger_dates(self.df())
        self.assertEqual(dates, [pd.Timestamp("2026-10-08"), pd.Timestamp("2026-11-08"), pd.Timestamp("2026-11-07")])

    def test_apply_plan_units(self):
        df = self.df()
        d.apply_plan_units(df, [{"ok": True, "units": {1: 840.89}}], {1})
        self.assertAlmostEqual(df.loc[1, "實際配息原幣"], 11772.46, places=2)
        self.assertEqual(df.loc[1, "配息單位數"], 840.89)


if __name__ == "__main__":
    unittest.main()
