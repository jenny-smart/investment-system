import unittest

import pandas as pd

from sync_fund_dividend_totals import plan


def positions(rows):
    return pd.DataFrame([{"asset_type": "基金", "id": i + 1, **r} for i, r in enumerate(rows)])


class PlanTests(unittest.TestCase):
    def test_follows_overview_n_column(self):
        sheet = [
            {"分類": "基富通-日", "基金名稱": "安聯收益成長基金-AMgi月收總收益類股(日圓避險", "總帳配息原幣": 129599.68},
            {"分類": "台新-南非", "基金名稱": "高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)", "總帳配息原幣": 230056.25},
            {"分類": "渣打-南非", "基金名稱": "東方匯理基金新興市場債券U 南非幣(穩定月配息)", "總帳配息原幣": 228680.17},
            {"分類": "基富通-日", "基金名稱": "富蘭克林坦伯頓-穩定月收益基金", "總帳配息原幣": 0.0},   # N 空白：不動
        ]
        pos = positions([
            {"platform": "基富通", "currency": "JPY", "name": "安聯收益成長基金-AMgi月收總收益類股(日圓避險",
             "dividend_received_original_total": 119958.43},
            {"platform": "台新基金", "currency": "ZAR", "name": "高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)",
             "dividend_received_original_total": 219615.48},
            {"platform": "渣打基金", "currency": "ZAR", "name": "東方匯理基金新興市場債券U 南非幣(穩定月配息)",
             "dividend_received_original_total": 228680.06},   # 差 0.11：不到 0.5 不改
        ])
        todo = plan(sheet, pos)
        self.assertEqual([(r["_position_id"], r["總帳配息原幣"]) for r in todo], [(1, 129599.68), (2, 230056.25)])


if __name__ == "__main__":
    unittest.main()
