import unittest

import pandas as pd

from invest_app.sheet_compare import compare_fund_dividends, sheet_fund_dividends

GRID = [
    ["", "投資分類", "日期", "現值", "累積配息原幣"],
    ["", "pypl", "", "55", ""],
    [],
    ["", "台新-南非", "", "", "845,422"],
    ["", "高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)", "10/07", "631", "398,338"],
    ["", "東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)", "10/09", "217", "447,084"],
    [],
    ["", "渣打-美金", "", "", "831,496"],
    ["", "東方匯理基金新興市場債券A美元(穩定月配息)", "10/09", "18", "94,395"],
    ["", "東方匯理基金新興市場債券A美元(穩定月配息)", "10/09", "18", "143,611"],
    [],
    ["", "1298406.757"],
]


class SheetCompareTests(unittest.TestCase):
    def test_reads_sections_and_merges_duplicate_lots(self):
        rows = sheet_fund_dividends(GRID)
        self.assertEqual([(r["分類"], r["總帳配息原幣"]) for r in rows],
                         [("台新-南非", 398338), ("台新-南非", 447084), ("渣打-美金", 238006)])

    def test_compare_matches_names_and_lists_db_only_funds(self):
        enriched = pd.DataFrame([
            {"asset_type": "基金", "platform": "台新基金", "currency": "ZAR",
             "name": "高盛新興市場債券基金 Y (南非幣對沖)(月配息)", "累計配息原幣": 400000},
            {"asset_type": "基金", "platform": "台新基金", "currency": "ZAR",
             "name": "東方匯理基金新興市場債券 U (南非幣)(穩定月配息)", "累計配息原幣": 454167},
            {"asset_type": "基金", "platform": "渣打基金", "currency": "USD",
             "name": "東方匯理基金新興市場債券A美元(穩定月配息)", "累計配息原幣": 238006},
            {"asset_type": "基金", "platform": "渣打基金", "currency": "USD",
             "name": "大華銀新加坡房地產收益基金", "累計配息原幣": 593490},
            {"asset_type": "台股", "platform": "台股", "currency": "TWD", "name": "台積電", "累計配息原幣": 5},
        ])
        df = compare_fund_dividends(sheet_fund_dividends(GRID), enriched)
        diffs = {r["基金名稱"]: r["差額"] for _, r in df.iterrows()}
        self.assertEqual(diffs, {
            "高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)": 400000 - 398338,
            "東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)": 454167 - 447084,
            "大華銀新加坡房地產收益基金": 593490,  # 資料庫有、總帳沒有
        })  # 東方匯理A美元兩批合計相同，不列出


if __name__ == "__main__":
    unittest.main()
