import unittest
from datetime import date

from sync_dividend_amounts import plan, sheet_funds

GRID = [
    ["投資分類", "日期", "現值", "累積配息原幣", "配息金額"],
    ["台新-南非", "", "", "", ""],
    ["高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)", "", "", 230056.25, 11772],
    ["東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)", "", "", 290177.81, 22423],
    ["", "", "", "", ""],
    ["渣打-美金", "", "", "", ""],
    ["東方匯理基金新興市場債券A美元(穩定月配息)", "", "", 3170.95, 282.02],
    ["東方匯理基金新興市場債券A美元(穩定月配息)", "", "", 4745.41, 0],
]


def rec(name, platform, currency, pay, units, per, paid=True):
    return {"fund_name": name, "platform": platform, "currency": currency, "pay_date": pay,
            "units_at_ex": units, "actual_div_amount": per, "is_paid": paid}


class PlanTests(unittest.TestCase):
    def test_updates_column_o_when_actual_differs(self):
        funds = sheet_funds(GRID)
        records = [
            rec("高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)", "台新基金", "ZAR", "2026/11/06", 840.89, 14.5),  # 12,192.905
            rec("東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)", "台新基金", "ZAR", "2026/11/01", 4966.65, 4.515),  # 一致
            rec("東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)", "台新基金", "ZAR", "2026/08/01", 4966.65, 9.0),  # 太舊
            rec("高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)", "台新基金", "ZAR", "2026/12/06", 1, 1),          # 未來
            rec("東方匯理基金新興市場債券A美元(穩定月配息)", "渣打基金", "USD", "2026/11/07", 100, 3.0),       # 分批：只提醒
        ]
        updates, warnings = plan(funds, records, date(2026, 11, 7))
        self.assertEqual([(u["cell"], u["new"]) for u in updates], [("E3", 12192.91)])
        self.assertEqual(len(warnings), 1)

    def test_unpaid_records_ignored(self):
        funds = sheet_funds(GRID)
        r = rec("高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)", "台新基金", "ZAR", "2026/11/06", 840.89, 20, paid=False)
        self.assertEqual(plan(funds, [r], date(2026, 11, 7)), ([], []))


if __name__ == "__main__":
    unittest.main()
