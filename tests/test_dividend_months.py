import unittest
from datetime import date

from sync_dividend_months import cell_month, dividend_month, match_column, month_rows, plan, sheet_columns

# 配息月份 rows 1–3 as in the sheet
HEADER = [
    ["", "基富通-台", "基富通-台", "基富通-人民幣", "基富通-日", "基富通-日", "渣打-美金", "渣打-美金", "渣打-南非",
     "台新-美金", "台新-美金", "台新-南非", "台新-南非"],
    ["", "富蘭克林華美新興國家固定收益基金B-新臺幣", "柏瑞新興邊境非投資等級債券證券投資信託基金-B類型",
     "富蘭克林華美新興國家固定收益證劵投資信託基金B-人民幣", "貝萊德全球智慧數據股票入息Hedged A6日圓穩定配息",
     "安聯收益成長基金-AMgi月收總收益類股(日圓避險", "大華銀新加坡房地產收益基金-美元月配(後收)",
     "鋒裕匯理基金新興市場債券A美元(穩定月配息)", "鋒裕匯理基金新興市場債券U 南非幣(穩定月配息)",
     "高盛新興市場債券基金Y股美元", "鋒裕匯理基金新興市場債券U 美元(穩定月配息)",
     "高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)", "鋒裕匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)"],
    ["", "每月10日"] + ["每月7日"] * 11,
]
MONTHS = ["2026/08", "2026/09", "2026/10", "2026/11", "2026/12"]


def grid(fill=None):
    rows = [list(r) for r in HEADER]
    for m in MONTHS:
        rows.append([m] + [fill.get((m, c), "FALSE") if fill else "FALSE" for c in range(1, 13)])
    return rows


PRESETS = [  # (platform, currency, app fund name, expected column)
    ("基富通", "TWD", "富蘭克林華美新興國家固定收益B-新臺幣", 1),
    ("基富通", "TWD", "柏瑞新興邊境非投資等級債券基金-B類型", 2),
    ("基富通", "CNY", "富蘭克林華美新興國家固定收益B-人民幣", 3),
    ("基富通", "JPY", "貝萊德全球智慧數據股票入息A6日圓", 4),
    ("基富通", "JPY", "安聯收益成長AMgi月收（日圓避險）", 5),
    ("渣打基金", "USD", "大華銀新加坡房地產收益基金-美元月配", 6),
    ("渣打基金", "USD", "東方匯理新興市場債券A美元（月配）", 7),
    ("渣打基金", "USD", "東方匯理新興市場債券U美元（月配）", 10),
    ("渣打基金", "ZAR", "東方匯理新興市場債券U南非幣（月配）", 8),
    ("台新基金", "ZAR", "東方匯理新興市場債券U南非幣（月配）", 12),
    ("渣打基金", "USD", "高盛新興市場債券Y股美元", 9),
    ("台新基金", "ZAR", "高盛新興市場債券Y南非幣對沖（月配）", 11),
]


class MatchTests(unittest.TestCase):
    def test_every_fund_maps_to_its_column(self):
        cols = sheet_columns(grid())
        for platform, currency, name, expected in PRESETS:
            with self.subTest(name=name, platform=platform):
                self.assertEqual(match_column(cols, platform, currency, name), expected)

    def test_unknown_fund_is_skipped(self):
        self.assertIsNone(match_column(sheet_columns(grid()), "基富通", "EUR", "某歐元基金"))


class PlanTests(unittest.TestCase):
    TODAY = date(2026, 11, 7)

    def rec(self, name, platform, currency, pay, paid=True):
        return {"fund_name": name, "platform": platform, "currency": currency, "pay_date": pay, "is_paid": paid}

    def test_ticks_previous_month_of_payment(self):
        records = [
            self.rec("東方匯理新興市場債券U南非幣（月配）", "台新基金", "ZAR", "2026/11/01"),   # 10 月配息
            self.rec("高盛新興市場債券Y南非幣對沖（月配）", "台新基金", "ZAR", "2026/11/06", paid=False),
            self.rec("富蘭克林華美新興國家固定收益B-新臺幣", "基富通", "TWD", "2026-11-10"),   # 10 月配息
            self.rec("富蘭克林華美新興國家固定收益B-新臺幣", "基富通", "TWD", "2026/10/12"),   # 9 月：不動
            self.rec("富蘭克林華美新興國家固定收益B-新臺幣", "基富通", "TWD", "2027/01/10"),   # 未來不動
        ]
        updates, problems = plan(grid(), records, self.TODAY)
        self.assertEqual(problems, [])
        self.assertEqual({u["cell"]: u["value"] for u in updates}, {"M6": True, "B6": True})

    def test_dividend_month(self):
        self.assertEqual(dividend_month({"pay_date": "2026/11/10"}), (2026, 10))
        self.assertEqual(dividend_month({"pay_date": "2027-01-08"}), (2026, 12))
        # 沒有發放日、沒有歷史發放天數 → 不知道，不勾
        self.assertIsNone(dividend_month({"ex_date": "2026/11/01"}))
        self.assertIsNone(dividend_month({}))
        # 有歷史天數：11/01 除息＋6 天＝11/07 發放 → 10 月配息
        lags = {("x", "ZAR"): 6}
        self.assertEqual(dividend_month({"fund_name": "x", "currency": "ZAR", "ex_date": "2026/11/01"}, lags),
                         (2026, 10))

    def test_never_ticks_current_month(self):
        name = "東方匯理新興市場債券U南非幣（月配）"
        records = [
            self.rec(name, "台新基金", "ZAR", "2026/12/07"),   # 發放日在 12 月 → 11 月配息，本月不能勾
            dict(self.rec(name, "台新基金", "ZAR", ""), ex_date="2026/11/30"),
        ]
        updates, _ = plan(grid({("2026/11", 12): "FALSE"}), records, self.TODAY)
        self.assertEqual(updates, [])
        # 本月格子已被勾的，排程也不去動它（由你自己處理）
        updates, _ = plan(grid({("2026/11", 12): "TRUE"}), records, self.TODAY)
        self.assertEqual(updates, [])

    def test_missing_pay_date_uses_fund_history(self):
        name = "東方匯理新興市場債券U南非幣（月配）"
        records = [
            dict(self.rec(name, "台新基金", "ZAR", "2026/10/07"), ex_date="2026/10/01", is_paid=True),
            dict(self.rec(name, "台新基金", "ZAR", ""), ex_date="2026/11/01"),   # 推算 11/07 發放 → 10 月
        ]
        updates, problems = plan(grid(), records, self.TODAY)
        self.assertEqual(problems, [])
        self.assertEqual({u["cell"]: u["value"] for u in updates}, {"M6": True})

    def test_missing_pay_date_uses_pay_day_row(self):
        # 第 3 列「每月7日」：10/31 除息 → 11/07 發放 → 10 月；11/01 除息 → 11/07 → 也是 10 月；11/10 除息 → 12/07 → 11 月
        name = "東方匯理新興市場債券U南非幣（月配）"
        for ex, cell in (("2026/10/31", "M6"), ("2026/11/01", "M6")):
            with self.subTest(ex=ex):
                records = [dict(self.rec(name, "台新基金", "ZAR", ""), ex_date=ex)]
                updates, problems = plan(grid(), records, self.TODAY)
                self.assertEqual((problems, {u["cell"]: u["value"] for u in updates}), ([], {cell: True}))
        records = [dict(self.rec(name, "台新基金", "ZAR", ""), ex_date="2026/11/10")]
        self.assertEqual(plan(grid(), records, date(2026, 12, 9))[0][0]["cell"], "M7")

    def test_next_pay_date(self):
        from sync_dividend_months import next_pay_date
        self.assertEqual(next_pay_date(date(2026, 10, 31), 7), date(2026, 11, 7))
        self.assertEqual(next_pay_date(date(2026, 11, 7), 7), date(2026, 11, 7))
        self.assertEqual(next_pay_date(date(2026, 1, 31), 30), date(2026, 2, 28))

    def test_missing_pay_date_without_history_leaves_column_alone(self):
        name = "東方匯理新興市場債券U南非幣（月配）"
        records = [dict(self.rec(name, "台新基金", "ZAR", ""), ex_date="2026/11/01")]
        g = grid({("2026/10", 12): "TRUE"})
        g[2] = [""] * len(g[2])   # 第 3 列沒有每月發放日
        updates, problems = plan(g, records, self.TODAY)
        self.assertEqual(updates, [])   # 不勾也不取消原本的勾
        self.assertEqual(len(problems), 1)

    def test_cancelled_confirmation_unticks_but_old_months_stay(self):
        g = grid({("2026/10", 1): "TRUE", ("2026/08", 2): "TRUE"})
        updates, _ = plan(g, [], self.TODAY)
        self.assertEqual({u["cell"]: u["value"] for u in updates}, {"B6": False})

    def test_already_in_sync_is_noop(self):
        g = grid({("2026/10", 12): True})
        recs = [self.rec("東方匯理新興市場債券U南非幣（月配）", "台新基金", "ZAR", "2026/11/01")]
        self.assertEqual(plan(g, recs, self.TODAY), ([], []))

    def test_unmatched_fund_reported(self):
        _, problems = plan(grid(), [self.rec("某歐元基金", "基富通", "EUR", "2026/11/01")], self.TODAY)
        self.assertEqual(len(problems), 1)

    def test_date_serial_months(self):
        # Google 試算表的日期格用 UNFORMATTED_VALUE 讀到的是序號
        self.assertEqual(cell_month(46266), (2026, 9))
        self.assertEqual(cell_month("2026/10"), (2026, 10))
        self.assertEqual(cell_month("2026-11-01"), (2026, 11))
        self.assertIsNone(cell_month(""))
        g = [list(r) for r in HEADER] + [[46266] + ["FALSE"] * 12, [46296] + ["FALSE"] * 12]
        self.assertEqual(month_rows(g), {(2026, 9): 4, (2026, 10): 5})


if __name__ == "__main__":
    unittest.main()
