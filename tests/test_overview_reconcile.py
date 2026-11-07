import unittest

import pandas as pd

from invest_app.overview_reconcile import compare, detail, overview_rows

GRID = [["加總Total", "115,916,843"], ["台股total", "43,993,724"], ["渣打-pypl", "1,679,571"],
        ["渣打-sq", "4,153,018"], ["基富通-台", "28,555,111"], ["渣打-大華", "1,115,745"], ["渣打-美金", "593,381"],
        ["銀行total", "7,090,093"], ["待還total", "-2,108,662"], ["加總Total", "999"]]

DF = pd.DataFrame([
    {"asset_type": "台股", "platform": "台股", "currency": "TWD", "name": "鴻海", "ticker": "2317.TW", "units": 10000,
     "即時價格/淨值": 224.5, "價格來源": "TWSE買賣價備援", "匯率": 1.0, "台幣市值": 2245000, "賣出稅費": 9934},
    {"asset_type": "美股", "platform": "美股", "currency": "USD", "name": "PayPal", "ticker": "NASDAQ:PYPL", "units": 1,
     "即時價格/淨值": 59.24, "匯率": 32.739, "台幣市值": 1679571, "賣出稅費": 0},
    {"asset_type": "美股", "platform": "美股", "currency": "USD", "name": "xyz", "ticker": "", "units": 1,
     "即時價格/淨值": 85.48, "匯率": 32.739, "台幣市值": 4153018, "賣出稅費": 0},
    {"asset_type": "基金", "platform": "渣打基金", "currency": "USD", "name": "大華銀新加坡房地產", "ticker": "", "units": 1,
     "台幣市值": 1115745},
    {"asset_type": "基金", "platform": "渣打基金", "currency": "USD", "name": "東方匯理A美元", "ticker": "", "units": 1,
     "台幣市值": 594032},
])
OTHER = {"categories": {"銀行total": {"total": 7090093}}, "deposits": 2108662, "other_total": 4981431}


class ReconcileTests(unittest.TestCase):
    def test_rows_stop_at_deposits(self):
        rows = overview_rows(GRID)
        self.assertEqual(rows[0], ("加總Total", 115916843.0))
        self.assertEqual(rows[-1], ("待還total", -2108662.0))

    def test_compare_maps_each_row(self):
        t = compare(overview_rows(GRID), DF, OTHER).set_index("分類")
        self.assertEqual(t.loc["台股total", "App"], 2245000 - 9934)
        self.assertEqual(t.loc["渣打-sq", "差額"], 0)                 # sq＝xyz（只有名稱）
        self.assertEqual(t.loc["渣打-pypl", "差額"], 0)               # NASDAQ:PYPL
        self.assertEqual(t.loc["渣打-大華", "差額"], 0)
        self.assertEqual(t.loc["渣打-美金", "差額"], 594032 - 593381)   # 大華另列
        self.assertEqual(t.loc["銀行total", "差額"], 0)
        self.assertEqual(t.loc["待還total", "差額"], 0)
        self.assertTrue(pd.isna(t.loc["基富通-台", "App"]) or t.loc["基富通-台", "App"] == 0)

    def test_detail_lists_price_source(self):
        d = detail("台股total", DF)
        self.assertEqual(d.loc[0, "價格來源"], "TWSE買賣價備援")
        self.assertEqual(d.loc[0, "價格／淨值"], "224.5000")


if __name__ == "__main__":
    unittest.main()
