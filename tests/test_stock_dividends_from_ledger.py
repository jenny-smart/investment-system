import unittest

from datetime import date

from sync_stock_dividends_from_ledger import (
    NoteItem, build_stock_index, default_years, ledger_items, parse_note, plan, resolve,
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
        self.assertEqual(resolve("00740B", INDEX), ("00740B", "代碼"))
        self.assertEqual(resolve("盟立", INDEX), ("2464", "名稱"))
        self.assertEqual(resolve("鈺齊", INDEX), ("9802", "簡稱"))
        self.assertEqual(resolve("世紀", INDEX), ("5608", "名稱"))      # 完全相同優先於「世紀乙」
        self.assertEqual(resolve("富邦特選", INDEX), ("00900", "簡稱"))
        self.assertEqual(resolve("00936", INDEX), ("00936", "代碼"))    # 不在持倉也接受
        self.assertEqual(resolve("2344華邦電", INDEX), ("2344", "代碼"))
        self.assertEqual(resolve("740B", INDEX), ("00740B", "別名"))
        self.assertEqual(resolve("富邦投等", INDEX), ("00740B", "別名"))
        self.assertEqual(resolve("科技優息", INDEX), ("00929", "別名"))
        self.assertEqual(resolve("折讓", INDEX), ("", "費用"))
        self.assertEqual(resolve("手續費", INDEX), ("", "費用"))
        self.assertEqual(resolve("某某", INDEX), ("", ""))


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
        self.assertEqual(problems, ["2026/11 備註加總 90 ≠ 儲存格 100（可能含手續費等扣項）"])

    def test_formula_fees_are_not_errors(self):
        # 1 月：=890+100+338+140+324+4310-20+1790-20+700-20-5313-2765-1297（儲存格 -843）
        header = ["", "", "2026-1"] + [f"2026-{m:02d}" for m in range(2, 13)]
        values = [header, ["股利-台股", "", "-843"]]
        notes = [[""] * 3, ["", "", "00919 4310\n富邦特選 140\n長華 700\n00936 100\n00940 890\n富邦投等 324\n科技優息 1790"]]
        formulas = [[""] * 3, ["", "", "=890+100+338+140+324+4310-20+1790-20+700-20-5313-2765-1297"]]
        items, problems = ledger_items(values, notes, 2026, INDEX, formulas)
        self.assertEqual(len(items), 7)
        self.assertEqual(len(problems), 1)
        self.assertIn("備註加總 8,254 ≠ 公式正數加總 8,592", problems[0])
        self.assertIn("備註沒寫到的金額：338", problems[0])
        # 備註齊全時扣項不算錯
        notes[1][2] += "\n盟立 338"
        self.assertEqual(ledger_items(values, notes, 2026, INDEX, formulas)[1], [])


class YearTests(unittest.TestCase):
    def test_default_years(self):
        self.assertEqual(default_years(date(2026, 11, 7)), [2025, 2026])
        self.assertEqual(default_years(date(2027, 6, 1)), [2026, 2027])   # 2026 晚補的也抓得到


class PlanTests(unittest.TestCase):
    def test_actions(self):
        items = [
            NoteItem((2026, 10), "盟立", 1404, "2464"),
            NoteItem((2026, 10), "00919", 8790, "00919"),
            NoteItem((2026, 10), "鈺齊", 3090, "9802"),
            NoteItem((2026, 10), "世紀", 38, "5608"),
            NoteItem((2026, 10), "折讓", 23, "", "費用"),
            NoteItem((2026, 10), "某某", 5, ""),
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
                               "世紀": ("補登", None), "折讓": ("費用／折讓", None),
                               "某某": ("無法對應", None)})

    def test_late_note_is_found_again_without_duplicates(self):
        # 2026/10 的股利 2027 才補備註：第一次補登，之後再跑因為已有相同金額的記錄 → 已一致
        item = NoteItem((2026, 10), "盟立", 1404, "2464")
        self.assertEqual(plan([item], [])[0]["action"], "補登")
        rec = {"id": 5, "ticker": "2464.TW", "ex_date": "", "cash_pay_date": "2026/10/01",
               "is_cash_received": True, "actual_cash_total": 1404}
        self.assertEqual(plan([item], [rec])[0]["action"], "已一致")

    def test_each_record_used_once(self):
        items = [NoteItem((2026, 7), "00919", 100, "00919"), NoteItem((2026, 10), "00919", 120, "00919")]
        records = [{"id": 9, "ticker": "00919.TW", "ex_date": "2026/06/17", "cash_pay_date": "2026/07/14",
                    "is_cash_received": False}]
        got = [(s["item"].month, s["action"]) for s in plan(items, records)]
        self.assertEqual(got, [((2026, 7), "確認入帳"), ((2026, 10), "補登")])


if __name__ == "__main__":
    unittest.main()
