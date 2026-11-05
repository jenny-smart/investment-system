import unittest
from datetime import datetime

from monthly_roll import (TAIPEI, auto_jobs, find_layout, find_refs, fund_deadline, fund_navs_ready,
                          is_live, last_business_day, month_key, parse_header_month, plan_freeze,
                          plan_roll, row_kind)

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
        self.assertEqual([(c["cell"], c["kind"], c["value"]) for c in changes],
                         [("D3", "stock", 20), ("D4", "fund", 21)])
        self.assertEqual(problems, [])

    def test_stock_and_fund_rows_separately(self):
        values, formulas = ledger()
        lay = find_layout(values, "right")
        self.assertEqual([c["cell"] for c in plan_freeze(values, formulas, lay, OCT, ("stock",))[0]], ["D3"])
        self.assertEqual([c["cell"] for c in plan_freeze(values, formulas, lay, OCT, ("fund",))[0]], ["D4"])

    def test_row_kind(self):
        self.assertEqual(row_kind("台股"), "stock")
        self.assertEqual(row_kind("美股-渣打"), "stock")
        self.assertEqual(row_kind("基富通"), "fund")
        self.assertEqual(row_kind("渣打基金"), "fund")

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


class FundNavTests(unittest.TestCase):
    NAME_A = "富蘭克林華美新興國家 新臺幣"
    NAME_B = "柏瑞新興邊境"

    def overview(self, date_a, date_b):
        return [
            ["", "", "", "", "", "基金", "日期", "淨值"],
            ["", "", "", "", "", self.NAME_A, date_a, 10.1],
            ["", "", "", "", "", self.NAME_B, date_b, 8.2],
            ["", "", "", "", "", "美股", "", ""],
            ["", "", "", "", "", "pypl", "2026/10/29", 70],  # not a fund, ignored
        ]

    def test_last_business_day_skips_weekend(self):
        self.assertEqual(str(last_business_day(OCT)), "2026-10-30")  # 10/31 is a Saturday
        self.assertEqual(str(last_business_day(NOV)), "2026-11-30")

    def test_waits_until_every_fund_has_month_end_nav(self):
        ready, pending, checked = fund_navs_ready(self.overview("2026/10/30", "2026/10/29"), OCT)
        self.assertFalse(ready)
        self.assertEqual(checked, 2)
        self.assertEqual(len(pending), 1)
        self.assertIn("F3", pending[0])

    def test_ready_when_on_or_after_month_end(self):
        self.assertTrue(fund_navs_ready(self.overview("2026/10/30", "2026/11/2"), OCT)[0])

    def test_no_funds_found_is_not_ready(self):
        self.assertFalse(fund_navs_ready([["", "", "", "", "", "x", "", ""]], OCT)[0])


class AutoTests(unittest.TestCase):
    def at(self, *args):
        return auto_jobs(datetime(*args, tzinfo=TAIPEI))

    def test_month_end_freezes_stocks_late_evening_only(self):
        self.assertEqual(self.at(2026, 10, 31, 23, 50), [("freeze-stock", OCT)])
        self.assertEqual(self.at(2026, 10, 31, 23, 10), [])
        self.assertEqual(self.at(2026, 10, 30, 23, 50), [])

    def test_first_week_checks_funds_then_rolls(self):
        self.assertEqual(self.at(2026, 11, 1, 0, 10),
                         [("freeze-stock", OCT), ("freeze-fund", OCT), ("roll", NOV)])
        self.assertEqual(self.at(2027, 1, 1, 0, 10),
                         [("freeze-stock", DEC), ("freeze-fund", DEC), ("roll", JAN)])
        self.assertEqual(self.at(2026, 11, 3, 16, 10), [("freeze-fund", OCT), ("roll", NOV)])
        self.assertEqual(self.at(2026, 11, 8, 0, 10), [])

    def test_fund_deadline_is_last_run_of_the_7th(self):
        self.assertTrue(fund_deadline(datetime(2026, 11, 7, 23, 50, tzinfo=TAIPEI)))
        self.assertFalse(fund_deadline(datetime(2026, 11, 7, 20, 10, tzinfo=TAIPEI)))
        self.assertFalse(fund_deadline(datetime(2026, 11, 6, 23, 50, tzinfo=TAIPEI)))


if __name__ == "__main__":
    unittest.main()
