import unittest

import sync_fund_nav as nav

SHEET_NAMES = {
    7: ("富蘭克林華美新興國家固定收益基金B-新臺幣", "acft94"),
    8: ("柏瑞新興邊境非投資等級債券證券投資信託基金-B類型", "acai222"),
    11: ("富蘭克林華美新興國家固定收益證劵投資信託基金B-人民幣", "acft99"),
    14: ("貝萊德全球智慧數據股票入息Hedged A6日圓穩定配息", "shzx0"),
    16: ("安聯收益成長基金-AMgi月收總收益類股(日圓避險", "TLZO3"),
    19: ("大華銀新加坡房地產收益基金-美元月配(後收)", "acob36"),
    20: ("東方匯理基金新興市場債券A美元(穩定月配息)", "pizn8"),
    24: ("東方匯理基金新興市場債券U 南非幣(穩定月配息)", "pizm9"),
    27: ("高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)", "ANZH2"),
    28: ("東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)", "pizm9"),
    31: ("高盛新興市場債券基金Y股美元", "anzb6"),
    32: ("東方匯理基金新興市場債券U 美元(穩定月配息)", "pizo1"),
}


class FundNavTest(unittest.TestCase):
    def test_sheet_names_match_expected_codes(self):
        for name, code in SHEET_NAMES.values():
            self.assertEqual(nav.match_fund(name)["code"], code, name)

    def test_unknown_and_headers(self):
        self.assertIsNone(nav.match_fund("富蘭克林坦伯頓-穩定月收益日幣避險A(Mdis)H1"))
        self.assertIsNone(nav.match_fund("基富通-台"))

    def test_parse_cnyes_payload(self):
        payload = {"data": {"items": [{"tradeDate": 1761580800, "nav": "7.1234"}]}}
        self.assertEqual(nav.parse_cnyes_payload(payload), {"nav": 7.1234, "date": "2025/10/28"})
        self.assertIsNone(nav.parse_cnyes_payload({"data": {"items": [{"nav": 1}]}}))

    def test_parse_moneydj_html(self):
        html = ("<table><tr><td>淨值日期</td><td>最新淨值</td><td>每日變化</td></tr>"
                "<tr><td>2026/10/27</td><td>9.87</td><td>0.01</td></tr></table>")
        self.assertEqual(nav.parse_moneydj_html(html), {"nav": 9.87, "date": "2026/10/27"})

    def test_plan_updates(self):
        rows = [[""]] * 6 + [["基富通-台", "日期"], [SHEET_NAMES[7][0], "#N/A", "#N/A"],
                             ["富蘭克林坦伯頓-穩定月收益日幣避險A(Mdis)H1"], [SHEET_NAMES[19][0]], ["1304432.838"]]
        calls = []

        def fetch(fund):
            calls.append(fund["code"])
            return None if fund["code"] == "acob36" else {"nav": 10.5, "date": "2026/10/27", "source": "test"}

        updates, problems = nav.plan_updates(rows, fetch)
        self.assertEqual([u["row"] for u in updates], [8])
        self.assertEqual(calls, ["acft94", "acob36"])
        self.assertEqual(len(problems), 2)


if __name__ == "__main__":
    unittest.main()
