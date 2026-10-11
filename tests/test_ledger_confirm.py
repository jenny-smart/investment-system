import unittest

import pandas as pd

from invest_app.sheet_compare import ledger_confirm_suggestions


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


if __name__ == "__main__":
    unittest.main()
