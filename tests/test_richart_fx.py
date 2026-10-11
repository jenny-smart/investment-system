import unittest

from richart_fx import parse_richart_rates
from sync_richart_fx import build_updates, find_rate_rows

HTML = """<html><body><table>
<tr><th>幣別</th><th>銀行買入</th><th>銀行賣出</th></tr>
<tr><td><img alt="flag">美元 USD</td><td>31.9614</td><td>32.0614</td></tr>
<tr><td>人民幣 CNY</td><td>4.7715</td><td>4.8015</td></tr>
<tr><td>日圓 JPY</td><td>0.2017</td><td>0.2057</td></tr>
<tr><td>南非幣 ZAR</td><td>1.9334</td><td>1.9934</td></tr>
</table><p>更新時間 2026.10.11 14:30</p></body></html>"""


class RichartFxTests(unittest.TestCase):
    def test_parses_sell_foreign_rate(self):
        self.assertEqual(parse_richart_rates(HTML), {"USD": 31.9614, "ZAR": 1.9334, "CNY": 4.7715, "JPY": 0.2017})

    def test_json_like_page(self):
        raw = '<script>var d=[{"ccy":"USD","buy":"31.95","sell":"32.05"},{"ccy":"JPY","buy":"0.2010","sell":"0.2050"}]</script>'
        self.assertEqual(parse_richart_rates(raw), {"USD": 31.95, "JPY": 0.201})

    def test_no_rates(self):
        self.assertEqual(parse_richart_rates("<html>loading…</html>"), {})

    def test_sheet_rows_and_updates(self):
        q = [["匯率"], ["美金"], ["南非"], ["人民"], ["日幣"], [], ["美金"], ["南非"]]
        rows = find_rate_rows(q)
        self.assertEqual(rows, {"USD": 2, "ZAR": 3, "CNY": 4, "JPY": 5})
        updates = build_updates("總覽", rows, {"USD": 31.9, "ZAR": 1.93, "CNY": 4.77, "JPY": 0.2})
        self.assertEqual([u["range"] for u in updates], ["'總覽'!R2", "'總覽'!R3", "'總覽'!R4", "'總覽'!R5"])


if __name__ == "__main__":
    unittest.main()
