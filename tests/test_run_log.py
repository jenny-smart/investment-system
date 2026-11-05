import unittest

from run_log import HEADERS, build_row, column_map, is_repeat, should_log, summarize, write


def fields(**kw):
    base = {"time": "2026-11-06 09:30:05", "system": "investment-system", "function": "基金淨值／匯率",
            "run_type": "排程", "period": "2026-11-06", "target": "總覽 G/H、R", "result": "成功",
            "message": "Updated 3 rows", "operator": "GitHub Actions", "link": "https://github.com/x/runs/1"}
    base.update(kw)
    return base


class FakeSheet:
    def __init__(self, header, rows=()):
        self.data = [list(header)] + [list(r) for r in rows]
        self.row_count = 1000
        self.appended = []

    def row_values(self, n):
        return self.data[n - 1] if n <= len(self.data) else []

    def update(self, values, cell):
        self.data[0] = list(values[0])

    def col_values(self, n):
        return [r[n - 1] if len(r) >= n else "" for r in self.data]

    def get_values(self, rng):
        start, end = (int(x) for x in rng.split(":"))
        return self.data[start - 1:end]

    def append_row(self, row, **kw):
        self.appended.append(row)
        self.data.append(row)


class RunLogTests(unittest.TestCase):
    def test_should_log(self):
        self.assertTrue(should_log("success", "F3 x -> 1\nUpdated 3 rows at 09:30"))
        self.assertTrue(should_log("success", "  已寫入 4 格"))
        self.assertFalse(should_log("success", "  等待中：基富通-台 淨值日期 10/29\n  已寫入 0 格"))
        self.assertFalse(should_log("success", "Updated 0 J cells"))
        self.assertTrue(should_log("success", "  ✅ portfolio_snapshots 已寫入"))
        self.assertFalse(should_log("success", "Mon 16:00 Asia/Taipei is outside weekday 08:30-14:30; skipped"))
        self.assertFalse(should_log("success", "All 9 NAVs unchanged; no cells changed"))
        self.assertTrue(should_log("success", "nothing", always=True))
        self.assertTrue(should_log("failure", ""))
        self.assertTrue(should_log("cancelled", ""))

    def test_summarize_keeps_key_lines(self):
        out = "F3 a -> 1\nWARN F9 抓不到淨值: X\nUpdated 2 rows at x\nWARN F9 抓不到淨值: X\n"
        self.assertEqual(summarize(out), "WARN F9 抓不到淨值: X；Updated 2 rows at x")
        ledger = "  已是值：台股\n  固定：基富通-台\n  B2:B18 → Jennyall GC 欄：17 格要改\n  已寫入 21 格\n"
        self.assertEqual(summarize(ledger), "固定：基富通-台；B2:B18 → Jennyall GC 欄：17 格要改；已寫入 21 格")
        self.assertEqual(summarize("a\nb\nc\nd\n"), "b；c；d")

    def test_column_map_aliases_any_order(self):
        cols = column_map(["時間", "功能", "狀態", "說明", "連結"])
        self.assertEqual(cols, {"time": 0, "function": 1, "result": 2, "message": 3, "link": 4})
        self.assertEqual(column_map(["A", "B"]), {})

    def test_build_row_follows_existing_header(self):
        row = build_row(["功能", "時間", "結果", "訊息"], fields())
        self.assertEqual(row, ["基金淨值／匯率", "2026-11-06 09:30:05", "成功",
                               "Updated 3 rows｜https://github.com/x/runs/1"])
        self.assertIsNone(build_row(["x", "y"], fields()))
        stock_sheet = ["部位ID", "資料日期", "本人/媽媽", "券商", "市場", "股票代碼", "股票名稱", "幣別"]
        self.assertIsNone(build_row(stock_sheet, fields()))

    def test_empty_sheet_gets_standard_headers(self):
        sheet = FakeSheet([])
        self.assertTrue(write(fields(), sheet))
        self.assertEqual(sheet.data[0], HEADERS)
        self.assertEqual(sheet.appended[0][2], "基金淨值／匯率")

    def test_same_failure_logged_once_per_day(self):
        fail = fields(result="失敗", message="WARN F9 抓不到淨值: X")
        sheet = FakeSheet(HEADERS)
        self.assertTrue(write(fail, sheet))
        self.assertFalse(write(dict(fail, time="2026-11-06 09:40:05"), sheet))
        self.assertTrue(write(dict(fail, time="2026-11-07 00:00:05"), sheet))            # next day
        self.assertTrue(write(dict(fail, time="2026-11-07 00:10:05", message="other"), sheet))
        ok = sheet.data[-1]
        self.assertFalse(is_repeat(HEADERS, [ok], fields()))                             # successes always


if __name__ == "__main__":
    unittest.main()
