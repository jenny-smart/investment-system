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


class TwLedgerTests(unittest.TestCase):
    def test_price_vs_shares(self):
        from invest_app.overview_reconcile import ledger_stocks, tw_ledger_diff
        #        C        D  E  F  G  H   I       J
        rows = [["2317", "", "", "", "", "", 10000, 225.0],
                ["6505", "", "", "", "", "", 1000, 85.7],
                ["1560", "", "", "", "", "", 1000, 650.0], ["1560", "", "", "", "", "", 1000, 650.0],
                ["9999", "", "", "", "", "", 500, 10.0], ["代碼", "", "", "", "", "", "股數", "市價"]]
        ledger = ledger_stocks(rows)
        self.assertEqual(ledger["1560"], {"units": 2000.0, "price": 650.0})
        df = pd.DataFrame([
            {"asset_type": "台股", "ticker": "2317.TW", "name": "鴻海", "units": 10000, "即時價格/淨值": 224.5, "台幣市值": 2245000},
            {"asset_type": "台股", "ticker": "6505.TW", "name": "台塑化", "units": 1100, "即時價格/淨值": 85.7, "台幣市值": 94270},
            {"asset_type": "台股", "ticker": "1560.TW", "name": "中砂", "units": 2000, "即時價格/淨值": 650.0, "台幣市值": 1300000},
        ])
        out = tw_ledger_diff(ledger, df).set_index("代號")
        self.assertIn("價格不同", out.loc["2317", "差在哪裡"])
        self.assertIn("股數不同", out.loc["6505", "差在哪裡"])
        self.assertNotIn("1560", out.index)
        self.assertEqual(out.loc["9999", "差在哪裡"], "App 沒有這檔持倉")


class UnifyTests(unittest.TestCase):
    def test_same_columns_for_stock_and_fund(self):
        from invest_app.overview_reconcile import UNIFIED, item_diff, overview_items, unify
        grid = [["投資分類", "日期", "現值", "損益", "台幣成本", "台幣市值"], ["基富通-日", "", "", "", "", ""],
                ["富蘭克林坦伯頓-穩定月收益日幣避險A(Mdis)H1", "", "", "", "", 0],     # 已贖回、0：不列
                ["貝萊德全球智慧數據股票入息Hedged A6日圓穩定配息", "11/6", 1050.0, 0, 0, 50102]]
        df = pd.DataFrame([{"asset_type": "基金", "platform": "基富通", "currency": "JPY", "ticker": "",
                            "name": "貝萊德全球智慧數據股票入息Hedged A6日圓穩定配息", "市值股數": 232.09,
                            "即時價格/淨值": 1050.0, "匯率": 0.2056, "台幣市值": 50104.0}])
        fund = unify("基富通-日", item_diff("基富通-日", overview_items(grid), df, {"JPY": 0.2056}))
        self.assertEqual(list(fund.columns), UNIFIED)
        self.assertEqual(len(fund), 1)
        self.assertAlmostEqual(fund.loc[0, "總帳股數／單位"], 50102 / (1050 * 0.2056))
        stock = unify("台股total", pd.DataFrame([{"名稱": "鴻海", "總帳市價": 225.0, "App 價格": 224.5, "總帳股數": 10000,
                                                  "App 股數": 10000, "總帳市值": 2250000, "App 市值": 2245000,
                                                  "差額": -5000, "差在哪裡": "價格不同"}]))
        self.assertEqual(list(stock.columns), UNIFIED)
        self.assertEqual(stock.loc[0, "App 匯率"], 1.0)


class TradeColumnsTests(unittest.TestCase):
    def test_kifutong_twd_layout_uses_j(self):
        from invest_app.core import fund_name_key, trade_units
        header = ["", "", "", "", "", "FALSE", "觀察成本", "現在市值", "單位成本", "投資成本", "總市值", "單位數"]
        total = ["div/section", "", "", "", "", "FALSE", "", "", "", 31000000, 28555111, ""]
        r1 = ["富蘭克林華美", "acft94", "", "2024/07/10", "", "TRUE", 3.86, 3.2684, 3.9349, 10000, 8306, 2541.3606]
        r2 = ["富蘭克林華美", "acft94", "", "", "", "FALSE", 3.91, 3.2684, 3.4, 543958, 522904, 159987.74]
        units = trade_units([header, total, r1, r2])
        self.assertEqual(units[fund_name_key("富蘭克林華美")], round(10000 / 3.9349, 4))

    def test_foreign_layout_uses_investment_currency(self):
        from invest_app.core import fund_name_key, trade_units
        header = ["", "", "", "", "", "FALSE", "觀察成本", "現在市值", "單位成本", "投資台幣", "市值台幣", "投資美金", "市值美金", "單位數"]
        row = ["東方匯理基金新興市場債券U 美元(穩定月配息)", "", "PUF6", "2025/9/", "", "TRUE", "", 16.57, 19.3, "", 148017, 5266, 4521, 272.8497]
        units = trade_units([header, row])
        self.assertEqual(units[fund_name_key("東方匯理基金新興市場債券Ｕ(美金)(穩定月配息)")], 272.8497)   # 美金＝美元


class LotUnitsTests(unittest.TestCase):
    HEADER_TW = ["", "", "", "", "", "FALSE", "觀察成本", "現在市值", "單位成本", "投資成本", "總市值", "單位數"]

    def row(self, name, tick, price, amount):
        return [name, "", "", "", "", tick, "", "", price, amount, "", ""]

    def test_each_lot_uses_its_trade_row(self):
        from invest_app.core import apply_trade_units, fund_name_key, fund_units, match_trade_units, trade_rows
        sheet = trade_rows([self.HEADER_TW, self.row("富蘭克林華美B-新臺幣", "TRUE", 3.9349, 10000),
                            self.row("富蘭克林華美B-新臺幣", "TRUE", 3.9062, 30000),
                            self.row("富蘭克林華美B-新臺幣", "FALSE", 3.4, 543958)])
        df = pd.DataFrame([
            {"asset_type": "基金", "platform": "基富通", "currency": "TWD", "name": "富蘭克林華美B-新臺幣",
             "original_units": 2541.36, "units": 0, "total_cost_input": 10000, "note": ""},
            {"asset_type": "基金", "platform": "基富通", "currency": "TWD", "name": "富蘭克林華美B-新臺幣",
             "original_units": 7680.1, "units": 0, "total_cost_input": 30000, "note": ""},
        ])
        item = match_trade_units(df, [sheet])[0]
        expected = round(round(10000 / 3.9349, 4) + round(30000 / 3.9062, 4), 4)
        self.assertEqual(item["trade_units"], expected)
        self.assertEqual(item["after_units"], expected)
        self.assertTrue(item["status"].startswith("一致"))
        out = apply_trade_units(df, [sheet])
        self.assertEqual(fund_units(out.iloc[0])[0], round(10000 / 3.9349, 4))

    def test_taishin_zar_lot_with_usd_label_and_wrong_avg_cost(self):
        from invest_app.core import match_trade_units, trade_rows
        header = ["", "", "", "", "", "", "觀察成本", "現在市值", "單位成本", "投資台幣", "市值台幣", "投資南非", "市值南非", "單位數"]
        name = "東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)"
        r = lambda price, amount: [name, "", "", "", "", "TRUE", "", 211.23, price, "", "", amount, "", ""]
        sheet = trade_rows([header, r(260.51, 60842), r(236.23, 62446)])
        df = pd.DataFrame([
            {"asset_type": "基金", "platform": "台新基金", "currency": "ZAR", "name": name, "original_units": 233.55,
             "units": 0, "total_cost_input": 60842, "note": ""},
            {"asset_type": "基金", "platform": "台新基金", "currency": "USD", "name": name, "original_units": 264.34,
             "units": 0, "total_cost_input": 62446, "note": ""},
        ])
        items = match_trade_units(df, [sheet])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["after_units"], round(round(60842 / 260.51, 4) + round(62446 / 236.23, 4), 4))

    def test_scb_and_taishin_same_name_kept_apart(self):
        from invest_app.core import fund_name_key, match_trade_units
        n1, n2 = "東方匯理基金新興市場債券U 南非幣(穩定月配息)", "東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)"
        df = pd.DataFrame([
            {"asset_type": "基金", "platform": "渣打基金", "currency": "ZAR", "name": n1, "original_units": 1817.04,
             "units": 0, "total_cost_input": 542004, "note": ""},
            {"asset_type": "基金", "platform": "台新基金", "currency": "ZAR", "name": n2, "original_units": 85.4,
             "units": 0, "total_cost_input": 22175, "note": ""},
        ])
        sheets = [{fund_name_key(n1): [(542004.0, 1817.0385)]}, {fund_name_key(n2): [(22175.0, 85.3968)]}]
        items = {i["platform"]: i for i in match_trade_units(df, sheets)}
        self.assertEqual(items["渣打基金"]["after_units"], 1817.0385)
        self.assertEqual(items["台新基金"]["after_units"], 85.3968)


class GvizValuesTests(unittest.TestCase):
    def test_uses_actual_cell_values_not_display(self):
        from unittest import mock
        import invest_app.core as core
        body = ('/*O_o*/\ngoogle.visualization.Query.setResponse({"status":"ok","table":{"cols":['
                '{"label":"高盛"},{"label":""},{"label":""},{"label":""},{"label":""},{"label":""},{"label":"觀察成本"},'
                '{"label":"現在市值"},{"label":"單位成本"},{"label":"投資台幣"},{"label":"市值台幣"},{"label":"投資南非"}],'
                '"rows":[{"c":[{"v":"高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)"},null,null,null,null,{"v":true},null,'
                '{"v":624.83},{"v":819.62,"f":"819.6200"},null,null,{"v":270987.72,"f":"270,988"}]}]}});')
        resp = mock.Mock(text=body); resp.raise_for_status = lambda: None
        with mock.patch.object(core.requests, "get", return_value=resp):
            rows = core.gviz_values("x", "958127137", "A1:Q500")
        self.assertEqual(rows[1][11], 270987.72)
        units = core.trade_units(rows)
        self.assertEqual(list(units.values()), [round(270987.72 / 819.62, 4)])   # 330.626


