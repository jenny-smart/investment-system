import unittest
from datetime import datetime

from monthly_roll import (TAIPEI, auto_jobs, find_layout, find_refs, is_live, month_key,
                          parse_header_month, plan_freeze, plan_roll)

SEP, OCT, NOV, DEC, JAN = (month_key(2026, 9), month_key(2026, 10), month_key(2026, 11),
                           month_key(2026, 12), month_key(2027, 1))


def ledger():
    """Jennyall: A labels; pairs (detail, subtotal-with-date) B/C=9月, D/E=10月, F/G=11月."""
    values = [
        ["", "", "2026/9/1", "", "2026/10/1", "", "2026/11/1"],
        ["加總", "", 100, "", 200, "", 300],
        ["台股", 10, "", 20, "", 30, ""],
        ["基金", 11, "", 21, "", 31, ""],
        ["小計", "", 21, "", 41, "", 61],
        ["零用金-淨值", 5, "", 5, "", 5, ""],
        ["台新銀行", 6, 11, 6, 11, 6, 11],
    ]
    formulas = [row[:] for row in values]
    formulas[2][3] = "=總覽!H12"                 # 10月 台股: live
    formulas[3][3] = "=GOOGLEFINANCE(\"0050\")"  # 10月 基金: live
    formulas[4][4] = "=SUM(D3:D4)"              # same-sheet sum stays
    formulas[2][1] = 10                         # 9月 already frozen
    formulas[5][3] = "='2026細帳'!C5"           # bank row: out of scope
    formulas[2][5] = "=總覽!H12"                 # 11月 (carried forward)
    return values, formulas


class LayoutTests(unittest.TestCase):
    def test_header_formats(self):
        self.assertEqual(parse_header_month("2026/11/1"), NOV)
        self.assertEqual(parse_header_month("2026-11"), NOV)
        self.assertEqual(parse_header_month("2026年11月"), NOV)
        self.assertEqual(parse_header_month("11月", 2026), NOV)
        self.assertIsNone(parse_header_month("11月"))
        self.assertEqual(parse_header_month(46327), NOV)  # 2026/11/1 serial
        self.assertIsNone(parse_header_month("台股"))

    def test_right_anchored_pairs(self):
        lay = find_layout(ledger()[0], "right")
        self.assertEqual(lay.header_row, 1)
        self.assertEqual([lay.month_of(c) for c in range(8)], [None, SEP, SEP, OCT, OCT, NOV, NOV, None])
        self.assertEqual(lay.offset(3), -1)

    def test_left_anchored_blocks(self):
        rows = [["項目", "9月", "", "", "10月", "", "", "11月", "", ""]]
        lay = find_layout(rows, "left", default_year=2026)
        self.assertEqual([lay.month_of(c) for c in range(11)],
                         [None, SEP, SEP, SEP, OCT, OCT, OCT, NOV, NOV, NOV, None])


class RefTests(unittest.TestCase):
    def test_finds_quoted_and_ranges_but_not_strings(self):
        f = "=SUM('2026細帳'!$D3:D9)+Jennyall!GA5&\"Jennyall!A1\""
        self.assertEqual([n for _, n in find_refs(f)], ["2026細帳", "Jennyall"])

    def test_live(self):
        self.assertTrue(is_live("=總覽!H3", "Jennyall"))
        self.assertTrue(is_live("=googlefinance(\"AAPL\")", "Jennyall"))
        self.assertFalse(is_live("=SUM(B3:B4)", "Jennyall"))
        self.assertFalse(is_live("=Jennyall!B3", "Jennyall"))
        self.assertFalse(is_live(123, "Jennyall"))


class FreezeTests(unittest.TestCase):
    def test_freezes_only_live_investment_cells_of_the_month(self):
        values, formulas = ledger()
        changes, problems = plan_freeze(values, formulas, find_layout(values, "right"), OCT)
        self.assertEqual([(c["cell"], c["value"]) for c in changes], [("D3", 20), ("D4", 21)])
        self.assertEqual(problems, [])

    def test_already_frozen_month_is_noop(self):
        values, formulas = ledger()
        self.assertEqual(plan_freeze(values, formulas, find_layout(values, "right"), SEP), ([], []))

    def test_error_values_are_kept_and_reported(self):
        values, formulas = ledger()
        values[2][3] = "#N/A"
        changes, problems = plan_freeze(values, formulas, find_layout(values, "right"), OCT)
        self.assertEqual([c["cell"] for c in changes], ["D4"])
        self.assertEqual(len(problems), 1)

    def test_missing_month_raises(self):
        values, formulas = ledger()
        with self.assertRaises(RuntimeError):
            plan_freeze(values, formulas, find_layout(values, "right"), DEC)


def detail_layouts():
    return {
        "Jennyall": find_layout(ledger()[0], "right"),
        "2026細帳": find_layout([["", "10月", "", "11月", "", "12月", ""]], "left", 2026),
        "2027細帳": find_layout([["", "1月", "", "2月", ""]], "left", 2027),
    }


class RollTests(unittest.TestCase):
    def test_moves_october_refs_to_november(self):
        overview = [
            ["加總", "=Jennyall!E2", "='2026細帳'!$C4", "=SUM('2026細帳'!B5:C9)"],
            ["", "=Jennyall!D3+Jennyall!D4", "=總覽!A1", "固定文字"],
        ]
        changes, notes, problems = plan_roll(overview, detail_layouts(), NOV)
        self.assertEqual(problems, [])
        self.assertEqual({c["cell"]: c["new"] for c in changes}, {
            "B1": "=Jennyall!G2",
            "C1": "='2026細帳'!$E4",
            "D1": "=SUM('2026細帳'!D5:E9)",
            "B2": "=Jennyall!F3+Jennyall!F4",
        })

    def test_already_rolled_is_noop(self):
        overview = [["=Jennyall!G2", "='2026細帳'!D4"]]
        changes, notes, problems = plan_roll(overview, detail_layouts(), NOV)
        self.assertEqual((changes, problems), ([], []))
        self.assertEqual(len(notes), 2)

    def test_year_change_switches_detail_sheet(self):
        overview = [["='2026細帳'!G4"]]
        changes, _, problems = plan_roll(overview, detail_layouts(), JAN)
        self.assertEqual(problems, [])
        self.assertEqual(changes[0]["new"], "='2027細帳'!C4")

    def test_older_refs_stay_unless_shift_all(self):
        overview = [["=Jennyall!E2-Jennyall!C2"]]
        changes, notes, _ = plan_roll(overview, detail_layouts(), NOV)
        self.assertEqual(changes[0]["new"], "=Jennyall!G2-Jennyall!C2")
        self.assertTrue(any("維持不動" in n for n in notes))
        changes, _, _ = plan_roll(overview, detail_layouts(), NOV, shift_all=True)
        self.assertEqual(changes[0]["new"], "=Jennyall!G2-Jennyall!E2")

    def test_missing_target_month_is_a_problem(self):
        overview = [["=Jennyall!G2"]]
        changes, _, problems = plan_roll(overview, detail_layouts(), DEC)
        self.assertEqual(changes, [])
        self.assertTrue(problems)

    def test_catches_up_several_months(self):
        overview = [["=Jennyall!C2"]]
        changes, _, _ = plan_roll(overview, detail_layouts(), NOV)
        self.assertEqual(changes[0]["new"], "=Jennyall!G2")


class AutoTests(unittest.TestCase):
    def at(self, *args):
        return auto_jobs(datetime(*args, tzinfo=TAIPEI))

    def test_month_end_freezes_late_evening_only(self):
        self.assertEqual(self.at(2026, 10, 31, 23, 50), [("freeze", OCT)])
        self.assertEqual(self.at(2026, 10, 31, 23, 10), [])
        self.assertEqual(self.at(2026, 10, 30, 23, 50), [])

    def test_first_day_catches_up_freeze_then_rolls(self):
        self.assertEqual(self.at(2026, 11, 1, 0, 10), [("freeze", OCT), ("roll", NOV)])
        self.assertEqual(self.at(2027, 1, 1, 0, 10), [("freeze", DEC), ("roll", JAN)])

    def test_roll_retried_first_week(self):
        self.assertEqual(self.at(2026, 11, 5, 0, 10), [("roll", NOV)])
        self.assertEqual(self.at(2026, 11, 8, 0, 10), [])


if __name__ == "__main__":
    unittest.main()
