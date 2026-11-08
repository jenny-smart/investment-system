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


class TwStockDiffTests(unittest.TestCase):
    def test_lists_only_differing_stocks(self):
        from invest_app.overview_reconcile import sheet_name_values, tw_stock_diff
        sheet = sheet_name_values([["名稱", "市值"], ["鴻海", "2,250,000"], ["中砂", "1,320,000"], ["智冠", "93,800"],
                                   ["賣掉的", "5,000"], ["加總", "999"]])
        df = pd.DataFrame([
            {"asset_type": "台股", "name": "鴻海", "units": 10000, "即時價格/淨值": 224.5, "價格來源": "收盤價", "台幣市值": 2245000},
            {"asset_type": "台股", "name": "中砂", "units": 1000, "即時價格/淨值": 650, "價格來源": "TWSE買賣價備援", "台幣市值": 650000},
            {"asset_type": "台股", "name": "中砂", "units": 1000, "即時價格/淨值": 650, "價格來源": "TWSE買賣價備援", "台幣市值": 650000},
            {"asset_type": "台股", "name": "智冠", "units": 1000, "即時價格/淨值": 93.8, "價格來源": "收盤價", "台幣市值": 93800},
        ])
        out = tw_stock_diff(sheet, df)
        self.assertEqual(list(out["名稱"]), ["賣掉的", "中砂", "鴻海"])
        self.assertEqual(out.loc[1, "差額"], -20000)
        self.assertEqual(out.loc[1, "總帳推算價格"], "660.00")


class ItemDiffTests(unittest.TestCase):
    def test_reason_nav_fx_rounding(self):
        from invest_app.overview_reconcile import item_diff, overview_items
        grid = [["投資分類", "日期", "現值", "損益", "台幣成本", "台幣市值"],
                ["基富通-日", "", "", "", "", ""],
                ["貝萊德全球智慧數據股票入息Hedged A6日圓穩定配息", "11/6", 1050.0, 0, 0, 50102],
                ["安聯收益成長基金-AMgi月收總收益類股(日圓避險", "11/5", 1708.81, 0, 0, 236198],
                ["台新-美金", "", "", "", "", ""],
                ["高盛新興市場債券基金Y股美元", "11/5", 71.67, 0, 0, 130457]]
        items = overview_items(grid)
        self.assertEqual(len(items), 3)
        df = pd.DataFrame([
            {"asset_type": "基金", "platform": "基富通", "currency": "JPY", "ticker": "", "name": "貝萊德全球智慧數據股票入息Hedged A6日圓穩定配息",
             "市值股數": 232.09, "即時價格/淨值": 1050.0, "匯率": 0.2056, "台幣市值": 50104.0},
            {"asset_type": "基金", "platform": "基富通", "currency": "JPY", "ticker": "", "name": "安聯收益成長基金-AMgi月收總收益類股(日圓避險",
             "市值股數": 680.0, "即時價格/淨值": 1694.24, "匯率": 0.2056, "台幣市值": 236873.0},
        ])
        out = item_diff("基富通-日", items, df, {"JPY": 0.2056}).set_index("名稱")
        self.assertIn("四捨五入", out.iloc[0]["差在哪裡"])
        self.assertIn("淨值／價格不同", out.loc["安聯收益成長基金-AMgi月收總收益類股(日圓避險", "差在哪裡"])
