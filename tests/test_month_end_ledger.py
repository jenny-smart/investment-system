import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from month_end_ledger import (
    BACKFILL, INCOME_REF, LEDGER_REF, READY, WAIT, auto_tasks, find_blocks, last_weekday,
    month_columns, month_end_price, overview_section, parse_nav_log,
    plan_freeze, price_status, rate_cells, retarget,
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
    2: ["美股 "], 3: ["pypl", 46325, 57.09, "", "", 1604250], 4: ["xyz", 46325, 75.35, "", "", 3675412],
    6: ["基富通-台", "日期"], 7: ["富蘭克林華美新興國家固定收益基金B-新臺幣", 46325, 3.2, "", "", 7000000],
    8: ["柏瑞新興邊境", 46325, 4.7, "", "", 21000000],
    13: ["基富通-日"], 14: ["貝萊德", 46325, 1083, "", "", 50000],
    15: ["富蘭克林坦伯頓-穩定月收益", "#N/A", "#N/A", "", "", 0],
    16: ["安聯", 46325, 1723, "", "", 240000],
    18: ["渣打-美金"], 19: ["大華銀新加坡房地產收益基金", 46324, 5.46, "", "", 1064503],
    20: ["東方匯理A美元", 46325, 18.5, "", "", 598314], 21: ["東方匯理A美元", 46325, 18.5, "", "", 0],
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

    def test_overview_income_range_includes_rows_40_to_43(self):
        from month_end_ledger import OVERVIEW_INCOME_CELLS
        self.assertEqual(OVERVIEW_INCOME_CELLS, "B40:B51")


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
        self.assertEqual([f.row for f in overview_section(OVERVIEW, "渣打-美金", "大華")], [19])
        self.assertEqual([f.row for f in overview_section(OVERVIEW, "渣打-美金", None, "大華")], [20, 21])
        self.assertEqual([f.row for f in overview_section(OVERVIEW, "基富通-日")], [14, 16])  # #N/A skipped
        self.assertIsNone(overview_section(OVERVIEW, "不存在"))

    def test_fund_ready_only_with_last_trading_day(self):
        now = datetime(2026, 10, 31, 9, tzinfo=TZ)
        self.assertEqual(price_status("基富通-台", OVERVIEW, OCT, now)[0], READY)
        self.assertEqual(price_status("基富通-日", OVERVIEW, OCT, now)[0], READY)   # #N/A row ignored
        self.assertEqual(price_status("渣打-美股", OVERVIEW, OCT, now)[0], READY)
        self.assertEqual(price_status("渣打-美金", OVERVIEW, OCT, now)[0], READY)
        state, reason, _, _ = price_status("渣打-基金大華", OVERVIEW, OCT, now)
        self.assertEqual(state, WAIT)
        self.assertIn("F19", reason)

    def test_missing_section_is_a_problem(self):
        state, _, problem, _ = price_status("台新-美金", OVERVIEW, OCT, datetime(2026, 10, 31, tzinfo=TZ))
        self.assertEqual(state, WAIT)
        self.assertIn("台新-美金", problem)

    def test_after_month_end_unfinished_blocks_need_backfill(self):
        late = [list(line) for line in OVERVIEW]
        late[18] = ["大華銀", 46327, 5.5]   # 2026/11/01
        self.assertEqual(price_status("渣打-基金大華", late, OCT, datetime(2026, 11, 2, tzinfo=TZ))[0], BACKFILL)
        # Holiday: NAV stuck on 10/29 is also looked up once the month is over.
        self.assertEqual(price_status("渣打-基金大華", OVERVIEW, OCT, datetime(2026, 11, 1, tzinfo=TZ))[0], BACKFILL)

    def test_tw_ready_after_close_until_next_open(self):
        at = lambda *a: price_status("台股", OVERVIEW, OCT, datetime(*a, tzinfo=TZ))
        self.assertEqual(at(2026, 10, 30, 14)[0], WAIT)
        self.assertEqual(at(2026, 10, 30, 14, 45)[0], READY)
        self.assertEqual(at(2026, 11, 2, 8, 20)[0], READY)            # Monday before the open
        state, _, problem, _ = at(2026, 11, 2, 9)
        self.assertEqual(state, WAIT)
        self.assertIn("手動", problem)

    def test_no_price_block_always_ready(self):
        self.assertEqual(price_status("富邦奈米投", OVERVIEW, OCT, datetime(2026, 10, 30, tzinfo=TZ))[0], READY)


class HistoryTests(unittest.TestCase):
    def test_month_end_price_needs_a_later_price(self):
        history = [(date(2026, 10, 28), 5.4), (date(2026, 10, 29), 5.46)]
        self.assertIsNone(month_end_price(history, OCT))
        history.append((date(2026, 11, 2), 5.5))                      # 10/30 was a holiday
        self.assertEqual(month_end_price(history, OCT), (date(2026, 10, 29), 5.46))
        self.assertIsNone(month_end_price([(date(2026, 11, 2), 5.5)], OCT))

    def test_nav_log(self):
        rows = [["2026/10/29", "大華銀", "5.46", "MoneyDJ", "2026/10/30 08:00"],
                ["2026/11/02", "大華銀 ", 5.5],
                ["2026/10/29", "大華銀", "5.46"],          # duplicate
                ["bad", "大華銀", "1"], ["2026/10/30", "", "1"]]
        self.assertEqual(parse_nav_log(rows),
                         {"大華銀": [(date(2026, 10, 29), 5.46), (date(2026, 11, 2), 5.5)]})


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
        # 10/31 is the month's last day, so 大華's rate is frozen while its NAV waits.
        self.assertEqual(written, {"GA10": -375195, "FZ11": 25800000, "GA11": 28570416.7,
                                   "GA19": 32.49, "FZ65": 6027000, "GA66": 0})
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


class BackfillTests(unittest.TestCase):
    NOW = datetime(2026, 11, 3, 22, tzinfo=TZ)

    def history(self, prices):
        return lambda kind, name: prices.get(name)

    def test_fund_value_scaled_to_month_end_nav_then_frozen(self):
        formulas = grid({(19, 1): "='總覽'!$R$2", (20, 1): "=GA21-FY21",
                         (21, 0): "=60000*27", (21, 1): "='渣打-美金'!$M4*GA19"})
        values = grid({(19, 1): 32.49, (20, 1): 100, (21, 0): 1620000, (21, 1): 1064503})
        overview = [list(line) for line in OVERVIEW]
        overview[18] = ["大華銀新加坡房地產收益基金", 46328, 5.6, "", "", 1064503]   # now 11/02
        prices = {"大華銀新加坡房地產收益基金": [(date(2026, 11, 2), 5.6), (date(2026, 10, 30), 5.46)]}
        plan = plan_freeze(COLUMN_A, formulas, values, 181, overview, OCT, self.NOW,
                           history=self.history(prices))
        self.assertEqual(len(plan.backfill), 1)
        block, scaled, note = plan.backfill[0]
        self.assertEqual(block.label, "渣打-基金大華")
        self.assertEqual(scaled[0]["range"], "GA21")
        self.assertAlmostEqual(scaled[0]["values"][0][0], 1064503 * 5.46 / 5.6)
        self.assertIn("10/30", note)
        self.assertNotIn("GA21", {u["range"] for u in plan.updates})
        self.assertTrue(any("匯率" in p for p in plan.problems))     # rate never frozen at month end

    def test_implausible_month_end_nav_is_rejected(self):
        formulas = grid({(21, 1): "='渣打-美金'!$M4*GA19"})
        values = grid({(21, 1): 1064503})
        overview = [list(line) for line in OVERVIEW]
        overview[18] = ["大華銀新加坡房地產收益基金", 46328, 18.51, "", "", 1064503]
        prices = {"大華銀新加坡房地產收益基金": [(date(2026, 11, 2), 18.51), (date(2026, 9, 30), 7.94),
                                          (date(2026, 10, 30), 7.94)]}
        plan = plan_freeze(COLUMN_A, formulas, values, 181, overview, OCT, self.NOW,
                           history=self.history(prices))
        self.assertEqual(plan.backfill, [])
        self.assertTrue(any("相差超過" in r for _, r in plan.waiting))

    def test_multi_fund_block_uses_value_weights(self):
        formulas = grid({(11, 1): "='基富通-台'!$K2"})
        values = grid({(11, 1): 28000000})
        overview = [list(line) for line in OVERVIEW]
        overview[6][1] = overview[7][1] = 46328
        prices = {overview[6][0]: [(date(2026, 11, 2), 3.2), (date(2026, 10, 30), 3.0)],
                  overview[7][0]: [(date(2026, 11, 2), 4.7), (date(2026, 10, 30), 4.7)]}
        plan = plan_freeze(COLUMN_A, formulas, values, 181, overview, OCT, self.NOW,
                           history=self.history(prices))
        ratio = (7000000 * 3.0 / 3.2 + 21000000) / 28000000
        self.assertAlmostEqual(plan.backfill[0][1][0]["values"][0][0], 28000000 * ratio)

    def test_us_stocks_scale_each_ticker_cell(self):
        formulas = grid({(29, 0): "=sum('渣打-美股'!$K4:$K6)", (30, 0): "='渣打-美股'!$K7",
                         (30, 1): "=SUM(FZ29:FZ30)"})
        values = grid({(29, 0): 1604250, (30, 0): 3675412, (30, 1): 5279662})
        overview = [list(line) for line in OVERVIEW]
        overview[2][1] = overview[3][1] = 46328
        prices = {"pypl": [(date(2026, 11, 2), 57.09), (date(2026, 10, 30), 60.0)],
                  "xyz": [(date(2026, 11, 2), 75.35), (date(2026, 10, 30), 70.0)]}
        plan = plan_freeze(COLUMN_A, formulas, values, 181, overview, OCT, self.NOW,
                           history=self.history(prices))
        scaled = {u["range"]: u["values"][0][0] for u in plan.backfill[0][1]}
        self.assertAlmostEqual(scaled["FZ29"], 1604250 * 60.0 / 57.09)
        self.assertAlmostEqual(scaled["FZ30"], 3675412 * 70.0 / 75.35)

    def test_unknown_history_waits_and_freezes_rates_only(self):
        formulas = grid({(19, 1): "='總覽'!$R$2", (21, 1): "='渣打-美金'!$M4*GA19",
                         (22, 1): "=GA19", (24, 1): "='渣打-美金'!$M2*GA22"})
        values = grid({(19, 1): 32.49, (21, 1): 1, (22, 1): 32.49, (24, 1): 2})
        plan = plan_freeze(COLUMN_A, formulas, values, 181, OVERVIEW, OCT,
                           datetime(2026, 10, 31, 22, tzinfo=TZ))
        # 渣打-美金 (10/30 NAV) is frozen whole; 大華 only gets its rate frozen.
        self.assertEqual({u["range"] for u in plan.updates}, {"GA19", "GA22", "GA24"})
        self.assertIn("渣打-基金大華 匯率", plan.frozen)
        self.assertEqual(rate_cells(formulas, 181, (22, 24)), {(22, 1)})

        later = plan_freeze(COLUMN_A, formulas, values, 181, OVERVIEW, OCT,
                            datetime(2026, 11, 2, tzinfo=TZ), history=lambda *_: None)
        self.assertEqual(later.backfill, [])
        self.assertTrue(any("查不到歷史淨值" in r for _, r in later.waiting))

    def test_rates_wait_for_the_last_day(self):
        formulas = grid({(19, 1): "='總覽'!$R$2", (21, 1): "='渣打-美金'!$M4*GA19"})
        values = grid({(19, 1): 32.49, (21, 1): 1})
        plan = plan_freeze(COLUMN_A, formulas, values, 181, OVERVIEW, OCT,
                           datetime(2026, 10, 30, 22, tzinfo=TZ))
        self.assertEqual(plan.updates, [])


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
