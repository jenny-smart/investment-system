import unittest
from datetime import date

from month_end_ledger import new_year_due
from yearly_ledger import (
    income_layout, plan_detail_sheet, plan_income_columns, retarget_column, retarget_detail,
    serial, split_terms, strip_literals,
)


class StripLiteralsTests(unittest.TestCase):
    def test_running_balances_keep_references_only(self):
        cases = {
            "=B43-C102+C116+C127+C115+C44+130000+566-60000": "=B43-C102+C116+C127+C115+C44",
            "=B40+C33+C41-281485": "=B40+C33+C41",
            "=G98+32*15960+4.7*5000": "=G98",
            "=K95+80000+60000": "=K95",
            "=B141+C33+C34-C139-59682": "=B141+C33+C34-C139",
            "=B28+195+1200+680+2340": "=B28",
            "=H83+I120+0.05": "=H83+I120",
            "=E88+F122+F123-1176.89": "=E88+F122+F123",
        }
        for before, after in cases.items():
            self.assertEqual(strip_literals(before), after, before)

    def test_pure_numbers_are_cleared(self):
        for value in ("=195+70+105+78", "=1699*7+1597*9", "=+264", "=-4752+4752",
                      "=-(485000+233000)-(67000+93000)", 129095, 8203.58,
                      "-414719-200285-36852", "=420"):
            self.assertEqual(strip_literals(value), "", value)

    def test_structural_formulas_unchanged(self):
        for value in ('=$A1&"-1"', "=SUM(C38:C62)-C39-C44", "=C88*$P$123", "=C99++C103+C113",
                      "=C25-C26", "=(H4-I4)*L4", "=I5*N5*1.006", "=B66", "=$C36*$I$6/12"):
            self.assertEqual(strip_literals(value), value, value)

    def test_text_labels_kept(self):
        self.assertEqual(strip_literals("零用金-餐費"), "零用金-餐費")
        self.assertEqual(strip_literals(True), True)

    def test_split_terms_handles_signs_and_strings(self):
        self.assertEqual(split_terms("C99++C103+C113"), ["C99", "++C103", "+C113"])
        self.assertEqual(split_terms('$A1&"-1"'), ['$A1&"-1"'])
        self.assertEqual(split_terms("A1*-3+B2"), ["A1*-3", "+B2"])


class DetailSheetTests(unittest.TestCase):
    def test_copy_of_2026_becomes_2027(self):
        formulas = [
            [2026, 45992, '=$A1&"-1"', '=$A1&"-02"'],
            ["零用金-餐費", "='2025細帳'!N2", "=195+70+105", "=50+50+10"],
            ["零用金", "='2025細帳'!N3", "=B28+195+1200", "=C28+60000"],
            ["薪資入帳", "='2025細帳'!N4", 281477, "=119910+300000"],
            [""],
            ["借出+投資", "='2025細帳'!N94", "=B6", "=C6"],
        ]
        cells = plan_detail_sheet(formulas, 2027)
        self.assertEqual(cells[(1, 0)], 2027)
        self.assertEqual(cells[(1, 1)], serial(date(2026, 12, 1)))
        self.assertEqual(cells[(2, 1)], "='2026細帳'!N2")
        self.assertEqual(cells[(6, 1)], "='2026細帳'!N6")        # same row, not the old offset
        self.assertEqual(cells[(2, 2)], "")
        self.assertEqual(cells[(3, 2)], "=B28")
        self.assertEqual(cells[(3, 3)], "=C28")
        self.assertEqual(cells[(4, 2)], "")
        self.assertNotIn((1, 2), cells)                        # month labels stay
        self.assertNotIn((6, 2), cells)
        self.assertNotIn((5, 1), cells)                        # empty B stays empty


class RetargetTests(unittest.TestCase):
    def test_ledger_and_income_references(self):
        jennyall = "=sum(filter('2026細帳'!$L:$L, regexmatch('2026細帳'!$A:$A, $A40)))"
        self.assertEqual(retarget_detail(jennyall, 2027, 1),
                         "=sum(filter('2027細帳'!$C:$C, regexmatch('2027細帳'!$A:$A, $A40)))")
        income = "=sumif('2026細帳'!$A:$A,$A20,'2026細帳'!Z:Z)*'總覽'!$R$5"
        self.assertEqual(retarget_detail(income, 2027, 12),
                         "=sumif('2027細帳'!$A:$A,$A20,'2027細帳'!N:N)*'總覽'!$R$5")
        self.assertEqual(retarget_detail("='2025細帳'!N2", 2027, 1), "='2025細帳'!N2")  # single cells untouched

    def test_retarget_column_only_changes_needed_cells(self):
        formulas = [["=sum(filter('2026細帳'!$M:$M, regexmatch('2026細帳'!$A:$A, $A40)))"],
                    ["=GC48-GA48"], [""],
                    ["=sum(filter('2026細帳'!$L:$L, regexmatch('2026細帳'!$A:$A, $A42)))"]]
        updates = retarget_column(formulas, 2026, 11, "GB", 40)
        self.assertEqual([u["range"] for u in updates], ["GB43"])
        self.assertIn("$M:$M", updates[0]["values"][0][0])


class IncomeTests(unittest.TestCase):
    ROW1 = ([False] * 10 + [2025] + [serial(date(2025, m, 1)) for m in range(1, 13)]
            + [2026] + [serial(date(2026, m, 1)) for m in range(1, 13)] + [2027, 2028, 2029])

    def test_layout(self):
        total, months, has_year = income_layout(self.ROW1, 2027)
        self.assertEqual(total, 36)                    # AK
        self.assertEqual(months, list(range(24, 36)))  # Y..AJ
        self.assertFalse(has_year)
        self.assertTrue(income_layout(self.ROW1, 2026)[2])

    def test_pasted_columns_get_dates_new_sheet_and_no_typed_numbers(self):
        formulas = [
            [0] * 12,
            ["=SUM(AL4:AL6)"] * 12,
            ["=sumif('2026細帳'!$A:$A,$A20,'2026細帳'!P:P)"] * 12,
            [2000000, "=SUMIFS(AM$19:AM,$J$19:$J,\"true\",$A$19:$A,$A11)"] + [""] * 10,
            [302.35, "標記"] + [""] * 10,
        ]
        updates = {u["range"]: u["values"][0][0] for u in plan_income_columns(formulas, 2027, 37)}
        self.assertEqual(updates["AL1"], serial(date(2027, 1, 1)))
        self.assertEqual(updates["AW1"], serial(date(2027, 12, 1)))
        self.assertEqual(updates["AL3"], "=sumif('2027細帳'!$A:$A,$A20,'2027細帳'!C:C)")
        self.assertEqual(updates["AW3"], "=sumif('2027細帳'!$A:$A,$A20,'2027細帳'!N:N)")
        self.assertEqual(updates["AL4"], "")
        self.assertEqual(updates["AL5"], "")
        self.assertNotIn("AM4", updates)
        self.assertNotIn("AM5", updates)
        self.assertNotIn("AL2", updates)

    def test_new_year_runs_on_december_first(self):
        self.assertEqual(new_year_due(date(2026, 12, 1)), 2027)
        self.assertIsNone(new_year_due(date(2026, 12, 2)))
        self.assertIsNone(new_year_due(date(2027, 1, 1)))


if __name__ == "__main__":
    unittest.main()
