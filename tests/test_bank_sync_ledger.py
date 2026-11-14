import unittest
from datetime import date

from bank_sync.ledger_sync import (FALLBACK_ROW, DEFAULT_RULES, ParsedFile, add_term, build_plan, categorize,
                                   merge_note, month_columns)
from bank_sync.statement_parser import note_text, parse
from pathlib import Path

# 合成的帳單文字（格式仿各銀行，內容虛構）
TAISHIN = """帳    務    資    訊
帳單結帳日 115/11/02
繳款截止日 115/11/17
上期應繳總額 1,000
=本期累計應繳金額 1,350
消費日 入帳起息日 消費明細 新臺幣金額 外幣折算日 消費地 幣別 外幣金額
115/10/19 115/10/19 台新銀行帳戶自動轉帳扣繳台新信用卡款 -1,000
  Richart卡 (卡號末四碼:1111)
115/10/02 115/10/05 範例咖啡店TAIPEI 150  TW
115/10/07 115/10/12 高鐵智慧型手機TAIPEI 700  TW
115/10/06 115/10/08 EXAMPLE SaaS SAN FR 491 1006 US USD 15.00
115/10/06 115/10/08 國外交易服務費－491.00 9
*若您要使用金融卡繳交信用卡款
"""
FUBON = """本期應繳總額 316元
115/11 250,000
25,000 115/11/02 115/11/18 6.46% ---% 0/0
消費日期 消費說明 入帳日期 外幣折算日/幣別 外幣金額/消費地 台幣金額
115/10/20 ACH自動扣繳 115/10/21 -500
MASTER鈦金正卡末４碼2222
115/10/27 11510電話費        866***89 115/10/27 TWD 289
115/11/02 數位卡現金回饋退款 115/11/02 -3
115/10/09 範例購物-EC 115/10/12 TWD 30
本期應繳金額 316
"""
DBS = """您本期的消費明細如下
消費日 入帳起息日 消費明細（含消費地） 外幣折算日 幣別金額/幣別 新台幣金額
2026/10/08 2026/10/12 銀行自動扣繳 -100
以下為範例卡 正卡（卡號末4碼 3333）新增消費小計 260
2026/09/21 2026/09/29 連支＊範例早午餐 / TW Taipei 60
2026/10/10 2026/10/13 範例商店 / TW Taipei 200
繳交截止日：2026年11月09日
應繳總金額
260
"""
CATHAY = """信用卡帳單 115年9月
消費日 入帳起息日 交易說明 新臺幣金額 卡號後四碼 行動卡號後四碼 消費國家 幣別 外幣金額 折算日
09/07 09/07 範例年費優惠 0 4444
本期應繳總額 0
"""


class ParserTest(unittest.TestCase):
    def test_taishin(self):
        st = parse("taishin", TAISHIN)
        self.assertEqual((st.due, st.total_due, st.ledger_month), (date(2026, 11, 17), 1350, "2026-11"))
        self.assertEqual([c.amount for c in st.purchases], [150, 700, 491, 9])
        self.assertEqual(st.purchases[0].card, "1111")
        self.assertEqual(st.warnings, [])

    def test_fubon(self):
        st = parse("fubon", FUBON)
        self.assertEqual((st.due, st.total_due), (date(2026, 11, 18), 316))
        self.assertEqual(sum(c.amount for c in st.purchases), 316)
        self.assertEqual(st.purchases[0].description, "11510電話費")
        self.assertTrue(st.charges[0].is_payment)

    def test_dbs(self):
        st = parse("dbs", DBS)
        self.assertEqual((st.due, st.total_due), (date(2026, 11, 9), 260))
        self.assertEqual([c.description for c in st.purchases], ["連支＊範例早午餐", "範例商店"])
        self.assertEqual(st.warnings, [])

    def test_cathay_zero(self):
        st = parse("cathay", CATHAY)
        self.assertEqual((st.ledger_month, st.total_due), ("2026-09", 0))

    def test_taishin_rows_after_page_break(self):
        text = TAISHIN.replace("*若您要使用金融卡繳交信用卡款\n",
                               "*若您要使用金融卡繳交信用卡款\n◎自動提款機繳款說明\n115/10/09 115/10/12 範例日本商店MIYAZA 100 1008 JP JPY 500.00\n")
        text = text.replace("=本期累計應繳金額 1,350", "=本期累計應繳金額 1,450")
        st = parse("taishin", text)
        self.assertEqual(sum(c.amount for c in st.purchases), 1450)
        self.assertEqual(st.warnings, [])

    def test_dbs_wrapped_row(self):
        text = DBS.replace("2026/10/10 2026/10/13 範例商店 / TW Taipei 200",
                           "2026/10/10 2026/10/13 範例很長的商店名稱 / TW\nTAIPEI\n200")
        st = parse("dbs", text)
        self.assertEqual([c.amount for c in st.purchases], [60, 200])
        self.assertEqual(st.purchases[1].description, "範例很長的商店名稱")

    def test_mismatch_warns(self):
        st = parse("dbs", DBS.replace("\n260\n", "\n999\n"))
        self.assertTrue(any("不同" in w for w in st.warnings))

    def test_note_has_stamp(self):
        note = note_text(parse("dbs", DBS), date(2026, 11, 14))
        self.assertIn("加註日期：2026-11-14", note)
        self.assertIn("09/21 連支＊範例早午餐 60", note)


class ScTest(unittest.TestCase):
    def test_sc_uses_purchase_total(self):
        u = lambda txt: "".join(f"/UNIC{ord(ch):04X}" for ch in txt)
        lines = [u("$ 12,719"), u("$ 12,719"), u("$ 0"), u("$ 14,292"), u("$ 9"), u("$ 14,301"), u("$ 14,301"),
                 u("2026"), u("04"), u("06"), u("NT$14,301")]
        st = parse("sc", "\n".join(lines))
        self.assertEqual(st.total_due, 14292)
        self.assertEqual(st.ledger_month, "2026-04")


class LedgerTest(unittest.TestCase):
    def test_add_term(self):
        self.assertEqual(add_term("", 120), "=120")
        self.assertEqual(add_term("=4289+12", 30), "=4289+12+30")
        self.assertEqual(add_term("1,000", 5), "=1000+5")
        self.assertEqual(add_term("=10", -3), "=10-3")

    def test_categorize(self):
        self.assertEqual(categorize("高鐵智慧型手機", DEFAULT_RULES)[0], "零用金-交通1")
        self.assertEqual(categorize("連支＊範例早午餐", DEFAULT_RULES)[0], "零用金-餐費")
        self.assertEqual(categorize("新光人壽保險 第02/12期", DEFAULT_RULES)[0], "保費支出")
        self.assertEqual(categorize("不知名商行", DEFAULT_RULES)[0], FALLBACK_ROW)
        self.assertEqual(categorize("連支＊ＷＴＣ　Ｃａｆ？Taipei", DEFAULT_RULES)[0], "零用金-餐費")  # 全形
        self.assertEqual(categorize("ｙｏｘｉTAIPEI", DEFAULT_RULES)[0], "零用金-交通1")

    def test_jenny_rules(self):
        self.assertEqual(categorize("彭園新店館New Ta", DEFAULT_RULES)[0], "零用金-公司代墊")
        self.assertEqual(categorize("連加＊ＬＩＮＥ 官方帳", DEFAULT_RULES)[0], "零用金-公司代墊")
        self.assertEqual(categorize("OPENAI *CHATGPT SUBSCRO9393SAN FR", DEFAULT_RULES)[0], "零用金-用品")
        self.assertEqual(categorize("＿支付連-女人夢想堂", DEFAULT_RULES)[0], "零用金-衣飾")
        self.assertEqual(categorize("綠界科技股＊ｐｄ　ｐｉｌａ 第01/06期/TW", DEFAULT_RULES)[0], "零用金-化妝保養＋按摩")
        self.assertEqual(categorize("JEIRINMEDICARLSENTEOA9131 PUSAN", DEFAULT_RULES)[0], "零用金-化妝保養＋按摩")
        self.assertEqual(categorize("MEGADONQUIJOTE MIYAZAK0985-2", DEFAULT_RULES)[0], "零用金-旅行")
        self.assertEqual(categorize("114年度綜所稅款 第01/12期 /TW", DEFAULT_RULES)[0], "（不列零用金）")

    def test_foreign_fee_follows_base_and_tax_skipped(self):
        text = TAISHIN.replace("=本期累計應繳金額 1,350", "=本期累計應繳金額 17,868").replace(
            "115/10/06 115/10/08 國外交易服務費－491.00 9\n",
            "115/10/06 115/10/08 國外交易服務費－491.00 9\n115/06/01 115/10/08 114年度綜所稅款 第05/12期 /TW 16,518  TW\n")
        values = [["2026", "2026-11"], ["零用金-餐費", ""], ["零用金-其他", ""], ["零用金-交通1", ""], ["零用金-用品", ""],
                  ["信用卡-台新 18", ""]]
        plan = build_plan([ParsedFile("taishin", Path("t.pdf"), parse("taishin", text))], values, date(2026, 11, 14), {})
        by = {s.charge.description: s for s in plan.spends}
        self.assertEqual(by["EXAMPLE SaaS SAN FR"].row_label, "零用金-其他")     # 美國線上服務不是旅行 → 待分類
        self.assertEqual(by["國外交易服務費－491.00"].row_label, "零用金-其他")   # 跟隨 491 那筆
        self.assertEqual(by["國外交易服務費－491.00"].reason, "跟隨對應消費")
        tax = by["114年度綜所稅款 第05/12期 /TW"]
        self.assertEqual((tax.row_label, tax.cell), ("（不列零用金）", ""))

    def test_merge_note_replaces_same_statement(self):
        old = "使用者自己的備註\n【星展 信用卡帳單】本期應繳 260\n繳款截止日 2026/11/09\n舊明細\n加註日期：2026-11-01（bank_sync）"
        new = "【星展 信用卡帳單】本期應繳 260\n繳款截止日 2026/11/09\n新明細\n加註日期：2026-11-14（bank_sync）"
        merged = merge_note(old, new)
        self.assertIn("使用者自己的備註", merged)
        self.assertIn("新明細", merged)
        self.assertNotIn("舊明細", merged)

    def test_month_columns(self):
        self.assertEqual(month_columns(["2026", "2026-10", "2026/11/1", "x"]), {"2026-10": 1, "2026-11": 2})

    def test_build_plan(self):
        values = [["2026", "2026-10", "2026-11"],
                  ["零用金-餐費", "", "100"],
                  ["零用金-其他", "", ""],
                  ["零用金-交通1", "", "=1000"],
                  ["信用卡-星展 08", "780", ""],
                  ["信用卡-台新 18", "", "1350"]]
        files = [ParsedFile("dbs", Path("dbs.pdf"), parse("dbs", DBS)),
                 ParsedFile("taishin", Path("ts.pdf"), parse("taishin", TAISHIN))]
        plan = build_plan(files, values, date(2026, 11, 14), {})
        self.assertEqual(plan.cards[0].cell, "C5")
        self.assertTrue(plan.cards[0].status.startswith("細帳空白"))
        self.assertEqual(plan.cards[1].cell, "C6")
        self.assertTrue(plan.cards[1].status.startswith("相符"))
        cells = {(s.charge.description, s.cell) for s in plan.spends}
        self.assertIn(("連支＊範例早午餐", "C2"), cells)
        self.assertIn(("範例商店", "C3"), cells)       # 對不到規則 → 零用金-其他
        self.assertIn(("高鐵智慧型手機TAIPEI", "C4"), cells)


if __name__ == "__main__":
    unittest.main()


class FakeSheet:
    def __init__(self, title, values, index=0, sid=1):
        self.title, self.values, self.index, self.id = title, [list(r) for r in values], index, sid
        self.notes = {}

    def get_values(self, value_render_option=None):
        return [list(r) for r in self.values]

    def get_notes(self):
        return [[self.notes.get((r, c), "") for c in range(len(row))] for r, row in enumerate(self.values)]

    def update_note(self, cell, text):
        from bank_sync.ledger_sync import _rc
        self.notes[_rc(cell)] = text

    def update(self, range_name, values, value_input_option=None):
        from bank_sync.ledger_sync import _rc
        r, c = _rc(range_name.split(":")[0])
        for i, row in enumerate(values):
            while len(self.values) <= r + i:
                self.values.append([""] * len(self.values[0]))
            for j, v in enumerate(row):
                while len(self.values[r + i]) <= c + j:
                    self.values[r + i].append("")
                self.values[r + i][c + j] = v


class FakeBook:
    def __init__(self, sheet):
        self.sheets = [sheet]

    def worksheets(self):
        return self.sheets

    def worksheet(self, title):
        return next(s for s in self.sheets if s.title == title)

    def duplicate_sheet(self, sid, insert_sheet_index, new_sheet_name):
        src = next(s for s in self.sheets if s.id == sid)
        copy = FakeSheet(new_sheet_name, src.values, insert_sheet_index, sid + 100)
        copy.notes = dict(src.notes)
        self.sheets.append(copy)
        return copy


class ApplyTest(unittest.TestCase):
    VALUES = [["2026", "2026-10", "2026-11"],
              ["零用金-餐費", "", "100"],
              ["零用金-其他", "", ""],
              ["零用金-交通1", "", "=1000"],
              ["零用金", "5000", "=4000+1000"],
              ["零用金--總支出", "=SUM(B2:B4)", "=SUM(C2:C4)"],
              ["零用金-淨值", "=B5-B6", "=C5-C6"],
              ["", "", ""],
              ["", "", ""],
              ["信用卡-星展 08", "780", "260"]]

    def test_apply_notes_only_on_detail_and_terms_on_copy(self):
        from bank_sync.ledger_sync import apply_plan
        detail = FakeSheet("2026細帳", self.VALUES)
        detail.notes[(9, 2)] = "我自己的備註"
        book = FakeBook(detail)
        files = [ParsedFile("dbs", Path("dbs.pdf"), parse("dbs", DBS))]
        stamp = date(2026, 11, 14)
        applied, events = {}, []
        plan = build_plan(files, detail.get_values(), stamp, applied)
        apply_plan(plan, book, stamp, applied, lambda *a: events.append(a))
        # 2026細帳：金額不動，只加備註（保留原備註）
        self.assertEqual(detail.values, self.VALUES)
        self.assertIn("我自己的備註", detail.notes[(9, 2)])
        self.assertIn("加註日期：2026-11-14", detail.notes[(9, 2)])
        # 含信用卡表：餐費 100 + 60；其他 + 200
        copy = book.worksheet("2026細帳(含信用卡)")
        self.assertEqual(copy.values[1][2], "=100+60")
        self.assertEqual(copy.values[2][2], "=200")
        self.assertIn("範例早午餐", copy.notes[(1, 2)])
        # 25 列同額加回（現金不變）；新增兩列統計
        self.assertEqual(copy.values[4][2], "=4000+1000+260")
        self.assertIn("抵銷，現金不變", copy.notes[(4, 2)])
        self.assertEqual(copy.values[7][0], "零用金-信用卡消費")
        self.assertEqual(copy.values[7][2], "=260")
        self.assertEqual(copy.values[8][0], "零用金-現金消費")
        self.assertEqual(copy.values[8][2], "=C6-C8")
        self.assertEqual(len(events), 4)
        # 重跑：同一份帳單不會再加一次
        plan2 = build_plan(files, detail.get_values(), stamp, applied)
        apply_plan(plan2, book, stamp, applied, lambda *a: events.append(a))
        self.assertEqual(copy.values[1][2], "=100+60")
        self.assertEqual(copy.values[4][2], "=4000+1000+260")
        self.assertEqual(copy.values[7][2], "=260")
        self.assertEqual(detail.notes[(9, 2)].count("【星展"), 1)


class NotesOnlyTest(unittest.TestCase):
    def test_notes_only_leaves_copy_alone(self):
        from bank_sync.ledger_sync import apply_plan
        detail = FakeSheet("2026細帳", ApplyTest.VALUES)
        book = FakeBook(detail)
        files = [ParsedFile("dbs", Path("dbs.pdf"), parse("dbs", DBS))]
        applied = {}
        plan = build_plan(files, detail.get_values(), date(2026, 11, 14), applied)
        apply_plan(plan, book, date(2026, 11, 14), applied, None, notes_only=True)
        self.assertEqual([s.title for s in book.sheets], ["2026細帳"])
        self.assertIn("加註日期", detail.notes[(9, 2)])
        self.assertEqual(applied, {})  # 含信用卡表還沒加過，之後 --apply 仍會加
        # 之後完整 apply 時含信用卡表照常加
        plan2 = build_plan(files, detail.get_values(), date(2026, 11, 14), applied)
        apply_plan(plan2, book, date(2026, 11, 14), applied, None)
        self.assertEqual(book.worksheet("2026細帳(含信用卡)").values[1][2], "=100+60")


class GoogleAuthTest(unittest.TestCase):
    def test_refresh_token_credentials(self):
        import json, tempfile
        from bank_sync.google_auth import credentials
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.json"
            p.write_text(json.dumps({"google": {"client_id": "x", "client_secret": "y", "refresh_token": "z"}}))
            creds = credentials(p)
            self.assertEqual(creds.refresh_token, "z")
