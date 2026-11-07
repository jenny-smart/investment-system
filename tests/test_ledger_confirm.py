import unittest

import pandas as pd

from invest_app.sheet_compare import ledger_confirm_plan, ledger_confirm_suggestions, sheet_fx_rates


def records():
    rows = [
        ("基富通", "TWD", "富蘭克林華美新興國家固定收益基金B-新臺幣", False, "2026-10-10"),
        ("基富通", "TWD", "柏瑞新興邊境非投資等級債券", False, "2026-10-10"),
        ("基富通", "TWD", "柏瑞新興邊境非投資等級債券", True, "2026-09-10"),
        ("基富通", "TWD", "舊月份未確認", False, "2026-09-10"),
        ("渣打基金", "USD", "大華銀新加坡房地產收益基金", False, "2026-10-09"),
        ("渣打基金", "USD", "東方匯理基金新興市場債券A美元", False, "2026-10-01"),
        ("台新基金", "ZAR", "高盛新興市場債券基金Y", False, "2026-10-07"),
    ]
    return pd.DataFrame([{"平台": p, "幣別": c, "基金名稱": n, "_確認前": paid, "_sort_date": pd.Timestamp(d)}
                         for p, c, n, paid, d in rows])


class LedgerConfirmTests(unittest.TestCase):
    def test_only_filled_ledger_rows_this_month_unconfirmed(self):
        ledger = [{"項目": "配息-基富通-台", "金額": 400597}, {"項目": "配息-渣打-美金", "金額": 9001},
                  {"項目": "配息-台新-南非", "金額": 0}, {"項目": "台幣-境外", "金額": 500000}]
        hits = ledger_confirm_suggestions(records(), ledger, (2026, 10))
        self.assertEqual(hits, {0: "配息-基富通-台", 1: "配息-基富通-台", 5: "配息-渣打-美金"})

    def test_daehwa_row_separate(self):
        hits = ledger_confirm_suggestions(records(), [{"項目": "配息-渣打-大華", "金額": 8426}], (2026, 10))
        self.assertEqual(hits, {4: "配息-渣打-大華"})

    def test_nothing_filled(self):
        self.assertEqual(ledger_confirm_suggestions(records(), [{"項目": "配息-基富通-台", "金額": 0}], (2026, 10)), {})

    def test_only_the_paid_record_matches_the_ledger_amount(self):
        # 台新-南非：兩筆待確認，總覽 43,910 只對得上其中一筆（22,423 ZAR × 1.9583）
        df = pd.DataFrame([
            {"平台": "台新基金", "幣別": "ZAR", "基金名稱": "東方匯理 U南非幣", "_確認前": False,
             "_sort_date": pd.Timestamp("2026-11-07")},
            {"平台": "台新基金", "幣別": "ZAR", "基金名稱": "高盛 Y南非幣對沖", "_確認前": False,
             "_sort_date": pd.Timestamp("2026-11-08")},
        ])
        twd = {0: 22423 * 1.9583, 1: 11773 * 1.9583}
        ledger = [{"項目": "配息-台新-南非", "金額": 43910}]
        self.assertEqual(ledger_confirm_suggestions(df, ledger, (2026, 11), twd.get), {0: "配息-台新-南非"})
        plan = ledger_confirm_plan(df, ledger, (2026, 11), twd.get)[0]
        self.assertTrue(plan["ok"])
        self.assertEqual((plan["candidates"], plan["matched"]), ([0, 1], [0]))
        # 都對不上就不預先選
        self.assertEqual(ledger_confirm_suggestions(df, [{"項目": "配息-台新-南非", "金額": 30000}], (2026, 11),
                                                    twd.get), {})
        # 兩筆都入帳
        self.assertEqual(sorted(ledger_confirm_suggestions(df, [{"項目": "配息-台新-南非", "金額": 66966}],
                                                           (2026, 11), twd.get)), [0, 1])

    def test_already_confirmed_amount_is_not_a_mismatch(self):
        # 11/7：東方匯理 U南非（22,423 ZAR）已確認、總覽 43,925 就是它；高盛 Y南非還沒入帳 → 不是對不上
        df = pd.DataFrame([
            {"平台": "台新基金", "幣別": "ZAR", "基金名稱": "東方匯理 U南非幣", "_確認前": True,
             "_sort_date": pd.Timestamp("2026-11-01")},
            {"平台": "台新基金", "幣別": "ZAR", "基金名稱": "高盛 Y南非幣對沖", "_確認前": False,
             "_sort_date": pd.Timestamp("2026-11-06")},
        ])
        twd = {0: 43925, 1: 23096}
        ledger = [{"項目": "配息-台新-南非", "金額": 43925}]
        plan = ledger_confirm_plan(df, ledger, (2026, 11), twd.get)[0]
        self.assertTrue(plan["ok"])
        self.assertEqual((plan["candidates"], plan["matched"]), ([1], []))
        # 之後高盛也入帳、總覽變 67,021 → 只選高盛
        plan = ledger_confirm_plan(df, [{"項目": "配息-台新-南非", "金額": 67021}], (2026, 11), twd.get)[0]
        self.assertEqual((plan["matched"], plan["ok"]), ([1], True))

    def test_sheet_fx_rates_first_occurrence(self):
        pad = [""] * 16
        grid = [pad + ["匯率", "賣出"], pad + ["美金", "31.9614"], pad + ["南非", "1.9334"],
                pad + ["人民", "4.7715"], pad + ["日幣", "0.2017"], pad + ["美金", "31.6380"], ["短列"]]
        self.assertEqual(sheet_fx_rates(grid), {"TWD": 1.0, "USD": 31.9614, "ZAR": 1.9334, "CNY": 4.7715, "JPY": 0.2017})


if __name__ == "__main__":
    unittest.main()


class MonthlyAmountAlertTests(unittest.TestCase):
    def test_alerts_when_actual_differs_from_column_o(self):
        from invest_app.sheet_compare import monthly_amount_alerts
        sheet = [{"分類": "台新-南非", "基金名稱": "高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)", "總帳配息原幣": 14.0},
                 {"分類": "台新-南非", "基金名稱": "東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)", "總帳配息原幣": 4.515}]
        df = pd.DataFrame([
            {"平台": "台新基金", "幣別": "ZAR", "基金名稱": "高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)",
             "每單位配息": 14.0, "確認入帳": False, "_sort_date": pd.Timestamp("2026-11-06")},
            {"平台": "台新基金", "幣別": "ZAR", "基金名稱": "東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)",
             "每單位配息": 4.3, "確認入帳": True, "_sort_date": pd.Timestamp("2026-11-01")},
            {"平台": "台新基金", "幣別": "ZAR", "基金名稱": "東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)",
             "每單位配息": 4.0, "確認入帳": True, "_sort_date": pd.Timestamp("2026-08-01")},   # 舊月份不提醒
        ])
        alerts = monthly_amount_alerts(sheet, df, {(2026, 11), (2026, 10)})
        self.assertEqual([(a["_index"], round(a["差額"], 3)) for a in alerts], [(1, -0.215)])
