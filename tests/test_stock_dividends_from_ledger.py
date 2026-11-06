import unittest

from sync_stock_dividends_from_ledger import (
    NoteItem, build_stock_index, ledger_items, parse_note, plan, resolve,
)

STOCKS = [
    {"code": "2464.TW", "name": "盟立"}, {"code": "5871.TW", "name": "中租-KY"},
    {"code": "9802.TW", "name": "鈺齊-KY"}, {"code": "2028.TW", "name": "威致"},
    {"code": "00900.TW", "name": "富邦特選高股息30"}, {"code": "00740B.TW", "name": "富邦全球投等債"},
    {"code": "00919.TW", "name": "群益台灣精選高息"}, {"code": "5608.TW", "name": "世紀"},
    {"code": "5608B.TW", "name": "世紀乙"},
]
INDEX = build_stock_index(STOCKS)


class ParseTests(unittest.TestCase):
    def test_note_like_the_sheet(self):
        items, bad = parse_note("盟立 1404\n折讓 23\n世紀 38\n00900 140\n00740B360\n鈺齊 3090\n00919 8790")
        self.assertEqual(bad, [])
        self.assertEqual(items, [("盟立", 1404), ("折讓", 23), ("世紀", 38), ("00900", 140),
                                 ("00740B", 360), ("鈺齊", 3090), ("00919", 8790)])
        self.assertEqual(sum(a for _, a in items), 13845)

    def test_separators_and_thousands(self):
        items, bad = parse_note("盟立:1,404、00919 8790；???")
        self.assertEqual(items, [("盟立", 1404), ("00919", 8790)])
        self.assertEqual(bad, ["???"])

    def test_resolve(self):
        self.assertEqual(resolve("00740B", INDEX), "00740B")
        self.assertEqual(resolve("盟立", INDEX), "2464")
        self.assertEqual(resolve("鈺齊", INDEX), "9802")       # 簡稱
        self.assertEqual(resolve("世紀", INDEX), "5608")       # 完全相同優先於「世紀乙」
        self.assertEqual(resolve("折讓", INDEX), "")


class LedgerTests(unittest.TestCase):
    def test_items_and_total_check(self):
        header = ["", "", "2026/1/1", "2026/2/1", "2026/3/1", "2026/4/1", "2026/5/1", "2026/6/1",
                  "2026/7/1", "2026/8/1", "2026/9/1", "2026/10/1", "2026/11/1", "2026/12/1"]
        values = [header, ["股利-台股", "19,752"] + [""] * 9 + ["13,845", "100", ""]]
        notes = [[""] * 14, [""] * 11 + ["盟立 1404\n折讓 23\n世紀 38\n00900 140\n00740B360\n鈺齊 3090\n00919 8790",
                                        "盟立 90", ""]]
        items, problems = ledger_items(values, notes, 2026, INDEX)
        self.assertEqual(len(items), 8)
        self.assertEqual({i.code for i in items if i.month == (2026, 10)} - {""},
                         {"2464", "5608", "00900", "00740B", "9802", "00919"})
        self.assertEqual(problems, ["2026/11 備註加總 90 ≠ 儲存格 100"])


class PlanTests(unittest.TestCase):
    def test_actions(self):
        items = [
            NoteItem((2026, 10), "盟立", 1404, "2464"),
            NoteItem((2026, 10), "00919", 8790, "00919"),
            NoteItem((2026, 10), "鈺齊", 3090, "9802"),
            NoteItem((2026, 10), "世紀", 38, "5608"),
            NoteItem((2026, 10), "折讓", 23, ""),
        ]
        records = [
            {"id": 1, "ticker": "2464.TW", "ex_date": "2026/08/20", "cash_pay_date": "", "is_cash_received": False},
            {"id": 2, "ticker": "00919.TW", "ex_date": "2026/09/16", "cash_pay_date": "2026/10/15",
             "is_cash_received": True, "actual_cash_total": 8790},
            {"id": 3, "ticker": "9802.TW", "ex_date": "2026/09/01", "cash_pay_date": "2026/10/05",
             "is_cash_received": True, "actual_cash_total": 3000},
            {"id": 4, "ticker": "5608.TW", "ex_date": "2025/08/01", "cash_pay_date": "", "is_cash_received": False},
        ]
        got = {s["item"].label: (s["action"], (s["record"] or {}).get("id")) for s in plan(items, records)}
        self.assertEqual(got, {"盟立": ("確認入帳", 1), "00919": ("已一致", 2), "鈺齊": ("金額不同", 3),
                               "世紀": ("補登", None), "折讓": ("無法對應", None)})

    def test_each_record_used_once(self):
        items = [NoteItem((2026, 7), "00919", 100, "00919"), NoteItem((2026, 10), "00919", 120, "00919")]
        records = [{"id": 9, "ticker": "00919.TW", "ex_date": "2026/06/17", "cash_pay_date": "2026/07/14",
                    "is_cash_received": False}]
        got = [(s["item"].month, s["action"]) for s in plan(items, records)]
        self.assertEqual(got, [((2026, 7), "確認入帳"), ((2026, 10), "補登")])


if __name__ == "__main__":
    unittest.main()
