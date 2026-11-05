import unittest
from datetime import datetime

from monthly_roll import (TAIPEI, auto_jobs, default_month, find_layout, find_refs, fund_deadline,
                          fund_navs_ready, last_business_day, ledger_layout, month_key, parse_header_month,
                          parse_rows, plan_freeze, plan_roll, row_kind, slot_time)

SEP, OCT, NOV, DEC, JAN = (month_key(2026, 9), month_key(2026, 10), month_key(2026, 11),
                           month_key(2026, 12), month_key(2027, 1))
INVEST, EXTRA = [4, 5, 6, 7], [9, 10]


def ledger():
    """Jennyall like the real sheet: pairs (detail, subtotal) B/C=9月, D/E=10月, F/G=11月.
    Row 1 dates on the subtotal column, row 3 dates on the detail column (must not be
    taken as the date row). Invest rows 4–7 (台股, 基富通-台, 渣打-美股), extra rows 9–10."""
    values = [
        ["", "", "2026/9/1", "", "2026/10/1", "", "2026/11/1"],
        ["", "", 100, "", 200, "", 300],
        ["", "2026/9/1", -1, "2026/10/1", -2, "2026/11/1", -3],
        ["台股", 10, 11, 20, 21, 30, 31],
        ["", 1, 2, 3, 4, 5, 6],
        ["基富通-台", 12, 13, 22, 23, 32, 33],
        ["渣打-美股", 14, 15, 24, 25, 34, 35],
        ["零用金-淨值", 0, 0, 0, 0, 0, 0],
        ["匯率", 7, 8, 9, 10, 11, 12],
        ["", 1, 1, 2, 2, 3, 3],
    ]
    formulas = [row[:] for row in values]
    for r in (4, 5, 6, 7, 9, 10):          # every month cell in those rows is a formula
        for c in range(1, 7):
            formulas[r - 1][c] = f"=X{r}C{c}"
    formulas[5][2] = 13                    # 9月 基富通-台 already a value
    formulas[7][4] = "='2026細帳'!C5"      # row 8: outside both ranges
    return values, formulas


def frozen(kinds, month=OCT, values=None, formulas=None):
    v, f = ledger()
    v, f = values or v, formulas or f
    changes, problems = plan_freeze(v, f, ledger_layout(v), month, kinds, INVEST, EXTRA)
    return [(c["cell"], c["kind"]) for c in changes], problems


class LayoutTests(unittest.TestCase):
    def test_header_formats(self):
        self.assertEqual(parse_header_month("2026/11/1"), NOV)
        self.assertEqual(parse_header_month("2026-11"), NOV)
        self.assertEqual(parse_header_month("2026年11月"), NOV)
        self.assertEqual(parse_header_month("11月", 2026), NOV)
        self.assertIsNone(parse_header_month("11月"))
        self.assertEqual(parse_header_month(46327), NOV)  # 2026/11/1 serial
        self.assertIsNone(parse_header_month("台股"))

    def test_ledger_date_row_is_row_one(self):
        lay = ledger_layout(ledger()[0])
        self.assertEqual(lay.header_row, 1)
        self.assertEqual([lay.month_of(c) for c in range(8)], [None, SEP, SEP, OCT, OCT, NOV, NOV, None])
        self.assertEqual(lay.offset(3), -1)

    def test_parse_rows(self):
        self.assertEqual(parse_rows("4:36")[:2], [4, 5])
        self.assertEqual(len(parse_rows("4:36")), 33)
        self.assertEqual(parse_rows("64-67,70"), [64, 65, 66, 67, 70])

    def test_left_anchored_blocks(self):
        rows = [["項目", "9月", "", "", "10月", "", "", "11月", "", ""]]
        lay = find_layout(rows, "left", default_year=2026)
        self.assertEqual([lay.month_of(c) for c in range(11)],
                         [None, SEP, SEP, SEP, OCT, OCT, OCT, NOV, NOV, NOV, None])


class RefTests(unittest.TestCase):
    def test_finds_quoted_and_ranges_but_not_strings(self):
        f = "=SUM('2026細帳'!$D3:D9)+Jennyall!GA5&\"Jennyall!A1\""
        self.assertEqual([n for _, n in find_refs(f)], ["2026細帳", "Jennyall"])


class FreezeTests(unittest.TestCase):
    def test_month_end_freezes_stock_blocks_and_extra_rows(self):
        cells, problems = frozen(("stock", "extra"))
        self.assertEqual(cells, [("D4", "stock"), ("E4", "stock"), ("D5", "stock"), ("E5", "stock"),
                                 ("D7", "stock"), ("E7", "stock"),
                                 ("D9", "extra"), ("E9", "extra"), ("D10", "extra"), ("E10", "extra")])
        self.assertEqual(problems, [])

    def test_fund_blocks_only(self):
        self.assertEqual(frozen(("fund",))[0], [("D6", "fund"), ("E6", "fund")])

    def test_values_are_the_current_results(self):
        v, f = ledger()
        changes, _ = plan_freeze(v, f, ledger_layout(v), OCT, ("fund",), INVEST, EXTRA)
        self.assertEqual([c["value"] for c in changes], [22, 23])

    def test_already_frozen_cells_are_skipped(self):
        self.assertEqual(frozen(("fund",), SEP)[0], [("B6", "fund")])

    def test_rows_outside_ranges_untouched(self):
        cells = [c for c, _ in frozen(("stock", "fund", "extra"))[0]]
        self.assertFalse(any(c.endswith("8") for c in cells))

    def test_row_kind(self):
        self.assertEqual(row_kind("台股"), "stock")
        self.assertEqual(row_kind("渣打-美股"), "stock")
        self.assertEqual(row_kind("基富通-台"), "fund")
        self.assertEqual(row_kind("渣打-基金大華"), "fund")
        self.assertEqual(row_kind("富邦奈米投"), "fund")

    def test_error_values_are_kept_and_reported(self):
        v, f = ledger()
        v[5][3] = "#N/A"
        cells, problems = frozen(("fund",), values=v)
        self.assertEqual(cells, [("E6", "fund")])
        self.assertEqual(len(problems), 1)

    def test_missing_month_raises(self):
        with self.assertRaises(RuntimeError):
            frozen(("fund",), DEC)


def detail_layouts():
    return {
        "Jennyall": ledger_layout(ledger()[0]),
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


class ScheduleTests(unittest.TestCase):
    def at(self, *args):
        return auto_jobs(datetime(*args, tzinfo=TAIPEI))

    def test_auto_month_end_late_evening_only(self):
        self.assertEqual(self.at(2026, 10, 31, 23, 50), [("month-end", OCT)])
        self.assertEqual(self.at(2026, 10, 31, 23, 10), [])
        self.assertEqual(self.at(2026, 10, 30, 23, 50), [])

    def test_auto_first_week(self):
        self.assertEqual(self.at(2026, 11, 1, 0, 10),
                         [("month-end", OCT), ("fund", OCT), ("roll", NOV)])
        self.assertEqual(self.at(2027, 1, 1, 0, 10),
                         [("month-end", DEC), ("fund", DEC), ("roll", JAN)])
        self.assertEqual(self.at(2026, 11, 3, 16, 10), [("fund", OCT), ("roll", NOV)])
        self.assertEqual(self.at(2026, 11, 8, 0, 10), [])

    def test_default_month(self):
        t = lambda *a: datetime(*a, tzinfo=TAIPEI)
        self.assertEqual(default_month("month-end", t(2026, 10, 31, 23, 50)), OCT)
        self.assertEqual(default_month("month-end", t(2026, 11, 1, 0, 30)), OCT)
        self.assertEqual(default_month("fund", t(2026, 11, 3, 9, 30)), OCT)
        self.assertEqual(default_month("fund", t(2027, 1, 4, 9, 30)), DEC)
        self.assertEqual(default_month("roll", t(2026, 11, 1, 0, 10)), NOV)

    def test_fund_deadline_from_the_7th_23_00(self):
        t = lambda *a: datetime(*a, tzinfo=TAIPEI)
        self.assertTrue(fund_deadline(t(2026, 11, 7, 23, 30)))
        self.assertFalse(fund_deadline(t(2026, 11, 7, 22, 30)))
        self.assertFalse(fund_deadline(t(2026, 11, 6, 23, 30)))

    def test_slot_time(self):
        self.assertEqual(slot_time("20261031T2350-invest_month_end"),
                         datetime(2026, 10, 31, 23, 50, tzinfo=TAIPEI))
        self.assertIsNone(slot_time(""))


if __name__ == "__main__":
    unittest.main()
