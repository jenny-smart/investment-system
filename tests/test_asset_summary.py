import unittest
from datetime import date

from asset_summary import (col_index, col_letters, find_month_column, monthly_income_block,
                           parse_month, read_rates, sheet_other_assets, spreadsheet_key, summarise)


def build_sheet(offset=0, blank_rows=0):
    """A miniature 'Jennyall' tab: A labels, then month pairs (detail, subtotal).

    Columns B/C are 2026/9 and D/E are 2026/10; F/G is a carried-forward 2026/11.
    `offset` pushes the month columns right and `blank_rows` inserts rows on top,
    imitating the monthly roll-forward and edits in a new file.
    """
    pad = [""] * offset
    rows = [
        # label, detail, subtotal formula/value pairs per month
        ("", None, None),           # 1 dates
        ("", None, None),           # 2 totals
        ("", None, None),           # 3
        ("台股", 1000, None),        # 4 investment
        ("零用金-淨值", 170644, None),
        ("台新銀行", -15358, None),
        ("連線銀行", 4000000, None),
        ("富邦銀行", 4289, "SUM"),   # bank subtotal over rows 5-8
        ("台新保險", 0, None),
        ("保險", 6095174, None),
        ("保險", 3000000, "SUM"),
        ("日幣 suica", 824, None),
        ("渣打南非", 113456, "SUM"),
        ("懷思", 600000, None),
        ("必可", 500000, None),
        ("懷思投資", "", "SUM"),
        ("", 8989000, None),
        ("叔叔", 6027000, None),
        ("", 5182008, None),
        ("", 4300970, None),
        ("", 0, "SUM"),
        ("", 500000, None),         # unnamed extra, added to total
        ("", 2094464, None),        # deposits already subtracted by the sheet
        ("", None, "TOTAL"),
    ]
    top = [[""]] * blank_rows
    labels = [r[0] for r in rows]
    group_starts = ["零用金-淨值", "台新保險", "日幣 suica", "懷思", "叔叔"]
    starts = [labels.index(g) + 1 + blank_rows for g in group_starts]
    values, formulas = [], []
    for r in top:
        values.append(list(r))
        formulas.append(list(r))
    months = [("2026/9/1", 0.5), ("2026/10/1", 1.0), ("2026/11/1", 1.0)]
    for i, (label, detail, kind) in enumerate(rows):
        row_no = i + 1 + blank_rows
        v_line, f_line = [label] + pad, [label] + pad
        for m, (when, scale) in enumerate(months):
            d_col = col_letters(1 + offset + 2 * m)
            if i == 0:
                v_line += ["", when]
                f_line += ["", 46000 + m]
                continue
            d_val = detail * scale if isinstance(detail, (int, float)) else ""
            v_line.append(d_val)
            f_line.append(d_val)
            if kind == "SUM":
                begin = max(s for s in starts if s <= row_no)
                total = sum(values_row[1 + offset + 2 * m] or 0
                            for values_row in values[begin - 1:row_no - 1]
                            if isinstance(values_row[1 + offset + 2 * m], (int, float)))
                total += d_val or 0
                v_line.append(total)
                f_line.append(f"=SUM({d_col}{begin}:{d_col}{row_no})")
            elif kind == "TOTAL" or i == 1:
                v_line.append(None)
                f_line.append(None)
            else:
                v_line.append("")
                f_line.append("")
        values.append(v_line)
        formulas.append(f_line)
    # Fill the total row: sum of subtotals + investment + extra - deposits.
    total_row = len(values)
    for m in range(len(months)):
        d, s = 1 + offset + 2 * m, 2 + offset + 2 * m
        sub_rows = [r for r in range(len(values)) if s < len(formulas[r]) and str(formulas[r][s]).startswith("=SUM")]
        inv, extra, dep = (values[blank_rows + 3][d], values[total_row - 3][d], values[total_row - 2][d])
        net = sum(values[r][s] for r in sub_rows) + inv + extra - dep
        terms = "+".join(f"{col_letters(s)}{r + 1}" for r in sub_rows)
        values[total_row - 1][s] = net
        formulas[total_row - 1][s] = (f"={terms}+{col_letters(d)}{blank_rows + 4}"
                                      f"+{col_letters(d)}{total_row - 2}-{col_letters(d)}{total_row - 1}")
        values[blank_rows + 1][s] = net
        formulas[blank_rows + 1][s] = f"={col_letters(s)}{total_row}"
    return values, formulas


RATES = [["匯率", "賣出", "買進"], ["美金", "31.9973", "31.9614"], ["人民", "4.7638", "4.7715"],
         ["日幣", "0.2010", "0.2017"]]
DEPOSITS = {"TWD": 1_500_000, "JPY": 300_000, "USD": 3320, "CNY": 5000}


class AssetSummaryTests(unittest.TestCase):
    def check(self, summary):
        cats = summary["categories"]
        self.assertEqual(cats["銀行total"]["total"], 170644 - 15358 + 4000000 + 4289)
        self.assertEqual(cats["保險total"]["total"], 9095174)
        self.assertEqual(cats["外幣total"]["total"], 824 + 113456)
        self.assertEqual(cats["懷思投資"]["total"], 1100000)
        self.assertEqual(cats["uncle待還"]["total"], 15509978)
        self.assertEqual(summary["deposit_twd"], round(1500000 + 300000 * 0.2017 + 3320 * 31.9614 + 5000 * 4.7715))
        expected_gross = summary["category_sum"] + 1000 + 500000
        self.assertEqual(summary["gross"], expected_gross)
        self.assertEqual(summary["net"], expected_gross - summary["deposit_twd"])

    def test_picks_latest_past_month_and_sums_categories(self):
        values, formulas = build_sheet()
        summary = summarise(values, formulas, RATES, DEPOSITS, today=date(2026, 10, 11))
        self.assertEqual(summary["month"], "2026/10/1")
        self.check(summary)

    def test_rolled_columns_and_inserted_rows(self):
        values, formulas = build_sheet(offset=7, blank_rows=3)
        summary = summarise(values, formulas, RATES, DEPOSITS, today=date(2026, 10, 11))
        self.assertEqual(summary["column"], col_letters(2 + 7 + 2))
        self.check(summary)

    def test_explicit_month(self):
        values, formulas = build_sheet()
        summary = summarise(values, formulas, RATES, DEPOSITS, month=parse_month("2026/9"))
        self.assertEqual(summary["month"], "2026/9/1")
        self.assertEqual(summary["categories"]["保險total"]["total"], 9095174 / 2)

    def test_missing_rate_is_reported(self):
        values, formulas = build_sheet()
        with self.assertRaisesRegex(RuntimeError, "ZAR"):
            summarise(values, formulas, RATES, {"ZAR": 10}, today=date(2026, 10, 11))

    def test_helpers(self):
        self.assertEqual(col_index("GA"), 182)
        self.assertEqual(col_letters(182), "GA")
        self.assertEqual(read_rates(RATES), {"USD": 31.9614, "CNY": 4.7715, "JPY": 0.2017})
        self.assertEqual(spreadsheet_key("https://docs.google.com/spreadsheets/d/abc_D-1/edit#gid=1"), "abc_D-1")
        self.assertEqual(find_month_column([["", "2026/12/1", "", "2026/12/1"]], parse_month("2026/12")), 1)



def jennyall_csv():
    """Values-only grid like the CSV export: A labels, B/C = 2026/9, D/E = 2026/10."""
    rows = [
        ["", "", "2026/9/1", "", "2026/10/1"],
        ["零用金-淨值", "100", "", "170,644", ""],
        ["台新銀行", "0", "", "-15,358", ""],
        ["郵局", "0", "0", "4,421", "-220,000"],
        ["富邦銀行", "0", "100", "4,289", "163,996"],
        ["台新保險", "", "0", "", "0"],
        ["保險", "1", "1", "3,000,000", "3,000,000"],
        ["日幣 suica", "", "", "824", ""],
        ["台新美金", "", "", "156,090", "0"],
        ["渣打南非", "", "", "113,456", "270,371"],
        ["懷思", "", "", "600,000", ""],
        ["懷思投資", "", "", "", "600,000"],
        ["叔叔", "", "", "6,027,000", ""],
        ["", "", "", "0", "6,027,000"],
        ["銀行", "", "100", "4.9%", "163,996"],
        ["保險", "", "1", "", "3,000,000"],
        ["懷思投資", "", "", "", "600,000"],
        ["叔叔借款", "", "", "", "6,027,000"],
        ["外幣", "", "", "", "270,370"],
        ["", "", "", "", "-1,690,479"],
    ]
    return rows


class SheetOtherAssetsTests(unittest.TestCase):
    def test_reads_summary_block_and_details_for_current_month(self):
        other = sheet_other_assets(jennyall_csv(), today=date(2026, 10, 11))
        self.assertEqual((other["month"], other["column"]), ("2026/10/1", "E"))
        cats = other["categories"]
        self.assertEqual(cats["銀行total"]["total"], 163996)
        self.assertEqual([label for label, _ in cats["銀行total"]["items"]],
                         ["零用金-淨值", "台新銀行", "郵局", "富邦銀行"])
        self.assertEqual(cats["保險total"]["total"], 3000000)
        self.assertEqual(cats["外幣total"]["total"], 270370)
        self.assertEqual(len(cats["外幣total"]["items"]), 3)
        self.assertEqual(cats["uncle待還"]["items"], [("叔叔", 6027000)])
        self.assertEqual(other["deposits"], 1690479)
        self.assertEqual(other["other_total"], 163996 + 3000000 + 600000 + 6027000 + 270370 - 1690479)

    def test_previous_month(self):
        other = sheet_other_assets(jennyall_csv(), month=parse_month("2026/9"))
        self.assertEqual(other["categories"]["銀行total"]["total"], 100)
        self.assertEqual(other["deposits"], 0)

    def test_monthly_income_block(self):
        grid = [["加總Total", "1"], [], ["每月加總", "300", "0"], ["台幣-加總", "100", "0", "台"],
                ["利息-銀行", "200", "", "台", "508,798"], ["", "0.00"], ["股票", "9"]]
        rows = monthly_income_block(grid)
        self.assertEqual([r["項目"] for r in rows], ["每月加總", "台幣-加總", "利息-銀行"])
        self.assertEqual(rows[2]["預估"], 508798)
        self.assertIsNone(rows[1]["預估"])


if __name__ == "__main__":
    unittest.main()
