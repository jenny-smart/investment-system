import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from month_end_ledger import (
    INCOME_REF, LEDGER_REF, auto_tasks, find_blocks, last_weekday, month_columns,
    overview_section, plan_freeze, price_status, retarget,
)

TZ = ZoneInfo("Asia/Taipei")
OCT = date(2026, 10, 1)

# Jennyall column A, rows 1-38, as in the sheet.
LABELS = {4: "台股", 9: "富邦奈米投", 11: "基富通-台", 14: "基富通-日", 18: "基富通-人民幣",
          21: "渣打-基金大華", 24: "渣打-美金", 27: "渣打-南非", 30: "渣打-美股",
          33: "台新-美金", 36: "台新-南非"}
COLUMN_A = [[LABELS.get(row, "")] for row in range(1, 39)]

# 總覽 F:H (dates as serials: 46324 = 2026/10/29, 46325 = 2026/10/30).
OVERVIEW = [[""] for _ in range(40)]
for row, line in {
    2: ["美股 "], 3: ["pypl", 46325, 57.09], 4: ["xyz", 46325, 75.35],
    6: ["基富通-台", "日期"], 7: ["富蘭克林華美新興國家固定收益基金B-新臺幣", 46325, 3.2],
    8: ["柏瑞新興邊境", 46325, 4.7],
    13: ["基富通-日"], 14: ["貝萊德", 46325, 1083], 15: ["富蘭克林坦伯頓-穩定月收益", "#N/A", "#N/A"],
    16: ["安聯", 46325, 1723],
    18: ["渣打-美金"], 19: ["大華銀新加坡房地產收益基金", 46324, 5.46],
    20: ["東方匯理A美元", 46325, 18.5], 21: ["東方匯理A美元", 46325, 18.5],
}.items():
    OVERVIEW[row - 1] = line


def grid(cells, rows=67, cols=2):
    """cells: {(row, col): value} with col 0 = detail, 1 = subtotal."""
    return [[cells.get((r, c), "") for c in range(cols)] for r in range(1, rows + 1)]


class DateTests(unittest.TestCase):
    def test_last_weekday(self):
        self.assertEqual(last_weekday(OCT), date(2026, 10, 30))       # 31st is Saturday
        self.assertEqual(last_weekday(date(2026, 11, 1)), date(2026, 11, 30))
        self.assertEqual(last_weekday(OCT, {date(2026, 10, 30)}), date(2026, 10, 29))

    def test_auto_tasks(self):
        self.assertEqual(auto_tasks(date(2026, 10, 29)), (None, None))
        self.assertEqual(auto_tasks(date(2026, 10, 30)), (OCT, None))
        self.assertEqual(auto_tasks(date(2026, 10, 31)), (OCT, None))
        self.assertEqual(auto_tasks(date(2026, 11, 1)), (OCT, date(2026, 11, 1)))
        self.assertEqual(auto_tasks(date(2026, 11, 10)), (OCT, None))
        self.assertEqual(auto_tasks(date(2026, 11, 11)), (None, None))
        self.assertEqual(auto_tasks(date(2027, 2, 28)), (date(2027, 2, 1), None))


class BlockTests(unittest.TestCase):
    def test_blocks_follow_labels(self):
        blocks = {b.label: (b.first, b.last) for b in find_blocks(COLUMN_A)}
        self.assertEqual(blocks["台股"], (4, 7))
        self.assertEqual(blocks["富邦奈米投"], (8, 9))
        self.assertEqual(blocks["基富通-台"], (10, 11))
        self.assertEqual(blocks["基富通-日"], (12, 14))
        self.assertEqual(blocks["渣打-美股"], (28, 30))
        self.assertEqual(blocks["台新-南非"], (34, 36))


class ReadinessTests(unittest.TestCase):
    def test_sections_and_keywords(self):
        self.assertEqual([r for r, _, _ in overview_section(OVERVIEW, "渣打-美金", "大華")], [19])
        self.assertEqual([r for r, _, _ in overview_section(OVERVIEW, "渣打-美金", None, "大華")], [20, 21])
        self.assertIsNone(overview_section(OVERVIEW, "不存在"))

    def test_fund_ready_only_with_last_trading_day(self):
        now = datetime(2026, 10, 31, 9, tzinfo=TZ)
        self.assertTrue(price_status("基富通-台", OVERVIEW, OCT, now)[0])
        self.assertTrue(price_status("基富通-日", OVERVIEW, OCT, now)[0])   # #N/A row ignored
        self.assertTrue(price_status("渣打-美股", OVERVIEW, OCT, now)[0])
        self.assertTrue(price_status("渣打-美金", OVERVIEW, OCT, now)[0])
        ready, reason, _ = price_status("渣打-基金大華", OVERVIEW, OCT, now)
        self.assertFalse(ready)
        self.assertIn("F19", reason)

    def test_missing_section_is_a_problem(self):
        ready, _, problem = price_status("台新-美金", OVERVIEW, OCT, datetime(2026, 10, 31, tzinfo=TZ))
        self.assertFalse(ready)
        self.assertIn("台新-美金", problem)

    def test_date_after_month_end_freezes_with_warning(self):
        late = [list(line) for line in OVERVIEW]
        late[18] = ["大華銀", 46327, 5.5]   # 2026/11/01
        ready, _, problem = price_status("渣打-基金大華", late, OCT, datetime(2026, 11, 2, tzinfo=TZ))
        self.assertTrue(ready)
        self.assertIn("過月底", problem)

    def test_tw_ready_after_close(self):
        self.assertFalse(price_status("台股", OVERVIEW, OCT, datetime(2026, 10, 30, 14, tzinfo=TZ))[0])
        self.assertTrue(price_status("台股", OVERVIEW, OCT, datetime(2026, 10, 30, 14, 45, tzinfo=TZ))[0])

    def test_no_price_block_always_ready(self):
        self.assertTrue(price_status("富邦奈米投", OVERVIEW, OCT, datetime(2026, 10, 30, tzinfo=TZ))[0])


class FreezeTests(unittest.TestCase):
    def test_plan_freezes_ready_blocks_and_uncle_rows(self):
        formulas = grid({
            (4, 0): 5.0, (4, 1): 6.0,                              # 台股 already values
            (10, 1): "=GA11-FY11", (11, 0): "=FX11+FZ10", (11, 1): "='基富通-台'!$K2",
            (19, 1): "='總覽'!$R$2", (20, 1): "=GA21-FY21", (21, 1): "='渣打-美金'!$M4*GA19",
            (64, 0): 8989000, (65, 0): "=Uncle!$B156", (66, 1): "=GA64-FY64",
        })
        values = grid({
            (4, 0): 5.0, (4, 1): 6.0,
            (10, 1): -375195, (11, 0): 25800000, (11, 1): 28570416.7,
            (19, 1): 32.49, (20, 1): -9131, (21, 1): 1064503,
            (64, 0): 8989000, (65, 0): 6027000, (66, 1): 0,
        })
        now = datetime(2026, 10, 31, 9, tzinfo=TZ)
        plan = plan_freeze(COLUMN_A, formulas, values, 181, OVERVIEW, OCT, now)
        written = {u["range"]: u["values"][0][0] for u in plan.updates}
        self.assertEqual(written, {"GA10": -375195, "FZ11": 25800000, "GA11": 28570416.7,
                                   "FZ65": 6027000, "GA66": 0})
        self.assertIn("台股", plan.done)
        self.assertEqual([label for label, _ in plan.waiting], ["渣打-基金大華"])
        self.assertIn("64:67 列", plan.frozen)

        forced = plan_freeze(COLUMN_A, formulas, values, 181, OVERVIEW, OCT, now, force=True)
        self.assertIn("GA21", {u["range"] for u in forced.updates})

    def test_error_values_keep_formula(self):
        formulas = grid({(11, 1): "='基富通-台'!$K2"})
        values = grid({(11, 1): "#N/A"})
        plan = plan_freeze(COLUMN_A, formulas, values, 181, OVERVIEW, OCT,
                           datetime(2026, 10, 31, tzinfo=TZ))
        self.assertEqual(plan.updates, [])
        self.assertTrue(any("GA11" in p for p in plan.problems))

    def test_still_waiting_days_after_month_end_is_reported(self):
        formulas = grid({(21, 1): "='渣打-美金'!$M4*GA19"})
        values = grid({(21, 1): 1})
        plan = plan_freeze(COLUMN_A, formulas, values, 181, OVERVIEW, OCT,
                           datetime(2026, 11, 6, tzinfo=TZ))
        self.assertTrue(any("仍未固定" in p for p in plan.problems))


class RollTests(unittest.TestCase):
    def test_overview_ledger_refs_move_to_new_month(self):
        cols = month_columns(["", "2026/10/1", "", "2026/11/1"])
        self.assertEqual(cols, {(2026, 10): 1, (2026, 11): 3})
        ledger_cols = {(2026, 10): 182, (2026, 11): 184}           # GA, GC
        formulas = [["=Jennyall!GA78"], ["=Jennyall!GA79"], ["=SUM(B2:B3)"]]
        updates = retarget(formulas, LEDGER_REF, ledger_cols, 184, 2)
        self.assertEqual([(u["range"], u["values"][0][0]) for u in updates],
                         [("B2", "=Jennyall!GC78"), ("B3", "=Jennyall!GC79")])
        self.assertEqual(retarget([["=Jennyall!GC78"]], LEDGER_REF, ledger_cols, 184, 2), [])

    def test_income_refs_keep_criteria_columns(self):
        income_cols = {(2026, 10): 33, (2026, 11): 34}             # AH, AI
        formula = ("=sumifs('每月收入'!$AH$19:$AH,'每月收入'!$J$19:$J,true,"
                   "'每月收入'!$A$19:$A,$A44)")
        updates = retarget([[formula]], INCOME_REF, income_cols, 34, 44)
        self.assertEqual(updates[0]["range"], "B44")
        self.assertEqual(updates[0]["values"][0][0],
                         "=sumifs('每月收入'!$AI$19:$AI,'每月收入'!$J$19:$J,true,"
                         "'每月收入'!$A$19:$A,$A44)")


if __name__ == "__main__":
    unittest.main()
