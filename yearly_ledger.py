"""Yearly roll of the 總帳: next year's YYYY細帳 and its 每月收入 month columns.

new year（每年 12 月 1 日，建立下一年）
    1. 複製「今年細帳」成「下一年細帳」（保留格式、分類、公式結構）。
       - A1 改成新年度，B1 改成今年 12/1；B 欄每列改接 ='今年細帳'!N<同列>（今年 12 月餘額）。
       - C–N（1–12 月）只留公式結構：手打的數字刪除，公式裡的數字加減項移除
         （=B43-C102+C116+130000-60000 → =B43-C102+C116；=195+70+105 → 清空）。
       - 已有同名、但不是由今年細帳產生的舊分頁，改名成「YYYY細帳-舊」保留。
    2. 每月收入：在「下一年」年度合計欄後面插入 12 個月份欄，複製今年 12 個月份欄的格式與
       公式，第 1 列填日期，細帳參照改成新年度對應月份欄，手打數字刪除；年度合計欄改成
       =SUM(新的 12 個月)（複製今年合計欄的公式）。

month columns（每月 1 日）
    Jennyall 與每月收入當月欄的「YYYY細帳」參照，改成該年細帳的當月欄（1 月 C … 12 月 N）。
"""
from __future__ import annotations

from datetime import date, timedelta
import re

from asset_summary import col_index, col_letters

DETAIL_SUFFIX = "細帳"
INCOME_SHEET = "每月收入"
LEDGER_SHEET = "Jennyall"
MONTH_COLS = (2, 13)               # 細帳 C..N = Jan..Dec (0-based columns)
LEDGER_REF_ROWS = (1, 120)         # Jennyall rows scanned for 細帳 references

LITERAL = re.compile(r"^[\s\d.+\-*/^()%]*\d[\s\d.+\-*/^()%]*$")
DETAIL_RANGE = re.compile(r"'(\d{4})細帳'!(\$?)([A-Z]{1,3})(\$?\d*):(\$?)([A-Z]{1,3})(\$?\d*)")
OPERATORS = set("+-*/^&=<>(,:")


def detail_title(year):
    return f"{year}{DETAIL_SUFFIX}"


def serial(day):
    return (day - date(1899, 12, 30)).days


def month_letter(month):
    return col_letters(MONTH_COLS[0] + month - 1)


# ---------------------------------------------------------------- formulas

def split_terms(body):
    """Split a formula body at top-level + and - (signs stay with their term)."""
    terms, start, depth, in_string = [], 0, 0, False
    for i, ch in enumerate(body):
        if ch == '"':
            in_string = not in_string
        if in_string:
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch in "+-" and depth == 0 and i > start:
            previous = body[:i].rstrip()[-1:]
            if previous and previous not in OPERATORS and not re.search(r"\d[eE]$", body[:i]):
                terms.append(body[start:i])
                start = i
    terms.append(body[start:])
    return [t for t in terms if t.strip()]


def is_literal(text):
    return bool(LITERAL.match(str(text)))


def strip_literals(value):
    """Cell for a fresh year: formulas keep only terms with references.

    Returns the new cell content: the (possibly shortened) formula, "" to clear,
    or the value unchanged (text labels).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return ""
    text = str(value)
    if not text.strip():
        return text
    if not text.startswith("="):
        return "" if is_literal(text) else text
    kept = [t for t in split_terms(text[1:]) if not is_literal(t)]
    if not kept:
        return ""
    body = "".join(kept).strip()
    if body.startswith("+") and not body.startswith("++"):
        body = body[1:].lstrip()
    return "=" + body


def plan_detail_sheet(formulas, year):
    """Cell updates turning a copy of last year's 細帳 into `year`'s.

    formulas: the copied sheet (FORMULA render) from A1. Returns {(row, col): value}
    with 1-based rows and 0-based columns.
    """
    previous = detail_title(year - 1)
    updates = {}
    first = formulas[0] if formulas else []
    if first and isinstance(first[0], (int, float)):
        updates[(1, 0)] = year
    if len(first) > 1 and isinstance(first[1], (int, float)) and not isinstance(first[1], bool):
        updates[(1, 1)] = serial(date(year - 1, 12, 1))
    for row in range(2, len(formulas) + 1):
        line = formulas[row - 1]
        if len(line) > 1 and str(line[1]).strip():
            ref = f"='{previous}'!N{row}"
            if line[1] != ref:
                updates[(row, 1)] = ref
        for col in range(MONTH_COLS[0], MONTH_COLS[1] + 1):
            if col >= len(line):
                break
            new = strip_literals(line[col])
            if new != line[col]:
                updates[(row, col)] = new
    return updates


def retarget_detail(formula, year, month):
    """Point 'YYYY細帳'!X:X ranges at `year`'s sheet and month column (A stays A)."""
    letter = month_letter(month)

    def swap(match):
        _, d1, c1, r1, d2, c2, r2 = match.groups()
        if c1 != "A":
            c1 = letter
        if c2 != "A":
            c2 = letter
        return f"'{detail_title(year)}'!{d1}{c1}{r1}:{d2}{c2}{r2}"

    return DETAIL_RANGE.sub(swap, formula)


def retarget_column(formulas, year, month, col_letter, first_row=1):
    """Updates for one column of formulas whose 細帳 references need retargeting."""
    updates = []
    for offset, line in enumerate(formulas):
        formula = line[0] if line else ""
        if not (isinstance(formula, str) and formula.startswith("=") and DETAIL_SUFFIX in formula):
            continue
        new = retarget_detail(formula, year, month)
        if new != formula:
            updates.append({"range": f"{col_letter}{first_row + offset}", "values": [[new]], "old": formula})
    return updates


# ---------------------------------------------------------------- 每月收入 layout

def income_layout(row1, year):
    """(index of `year`'s total column or None, [12 indexes of last year's months] or None,
    True if `year` already has month columns)."""
    total, previous, has_year = None, [], False
    for col, value in enumerate(row1):
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            number = int(value)
            if number == year:
                total = col
            elif 30000 < number < 80000:
                day = date(1899, 12, 30) + timedelta(days=number)
                if day.year == year:
                    has_year = True
                elif day.year == year - 1:
                    previous.append((day.month, col))
    previous.sort()
    months = [col for _, col in previous]
    if ([m for m, _ in previous] != list(range(1, 13))
            or months != list(range(months[0], months[0] + 12))):
        months = None
    return total, months, has_year


def plan_income_columns(formulas, year, first_col):
    """Fix the 12 pasted month columns. formulas: grid of those columns from row 1."""
    updates = []
    for offset in range(12):
        month = offset + 1
        letter = col_letters(first_col + offset)
        updates.append({"range": f"{letter}1", "values": [[serial(date(year, month, 1))]]})
        for row in range(2, len(formulas) + 1):
            line = formulas[row - 1]
            value = line[offset] if offset < len(line) else ""
            if isinstance(value, str) and value.startswith("=") and DETAIL_SUFFIX in value:
                new = retarget_detail(value, year, month)
            elif isinstance(value, str) and value.startswith("="):
                continue
            else:
                new = strip_literals(value)
            if new != value:
                updates.append({"range": f"{letter}{row}", "values": [[new]]})
    return updates


# ---------------------------------------------------------------- I/O

def to_updates(cells):
    return [{"range": f"{col_letters(col)}{row}", "values": [[value]]}
            for (row, col), value in sorted(cells.items())]


def create_detail_sheet(spreadsheet, year, dry_run):
    previous_title, title = detail_title(year - 1), detail_title(year)
    sheets = {ws.title: ws for ws in spreadsheet.worksheets()}
    if previous_title not in sheets:
        return [f"找不到「{previous_title}」，無法建立「{title}」"]
    source = sheets[previous_title]
    if title in sheets:
        b2 = sheets[title].get("B2", value_render_option="FORMULA")
        if b2 and b2[0] and previous_title in str(b2[0][0]):
            print(f"  「{title}」已存在（接 {previous_title}），略過")
            return []
        old = f"{title}-舊"
        while old in sheets:
            old += "-舊"
        print(f"  既有「{title}」不是由 {previous_title} 產生，改名為「{old}」保留")
        if not dry_run:
            sheets[title].update_title(old)
    if dry_run:
        formulas = source.get(value_render_option="FORMULA")
        updates = to_updates(plan_detail_sheet(formulas, year))
        print(f"  預覽：複製「{previous_title}」→「{title}」，改 {len(updates)} 格")
        for u in updates[:40]:
            print(f"    {u['range']}: {u['values'][0][0]}")
        return []
    new = spreadsheet.duplicate_sheet(source.id, insert_sheet_index=source.index + 1, new_sheet_name=title)
    formulas = new.get(value_render_option="FORMULA")
    updates = to_updates(plan_detail_sheet(formulas, year))
    if updates:
        new.batch_update(updates, value_input_option="USER_ENTERED")
    print(f"  已建立「{title}」，改 {len(updates)} 格")
    return []


def add_income_columns(spreadsheet, year, dry_run):
    sheet = spreadsheet.worksheet(INCOME_SHEET)
    row1 = sheet.row_values(1, value_render_option="UNFORMATTED_VALUE")
    total, months, has_year = income_layout(row1, year)
    if has_year:
        print(f"  {INCOME_SHEET} 已有 {year} 月份欄，略過")
        return []
    if total is None:
        return [f"{INCOME_SHEET} 第 1 列找不到年度合計欄 {year}"]
    if not months:
        return [f"{INCOME_SHEET} 第 1 列找不到連續的 {year - 1}/1–12 月份欄"]
    previous_total = months[0] - 1
    start = total + 1
    print(f"  {INCOME_SHEET}：在 {col_letters(total)}（{year} 合計）後插入 12 欄 "
          f"{col_letters(start)}–{col_letters(start + 11)}，複製 {col_letters(months[0])}–{col_letters(months[-1])}")
    if dry_run:
        return []
    rows = sheet.row_count
    grid = lambda c0, c1: {"sheetId": sheet.id, "startRowIndex": 0, "endRowIndex": rows,
                           "startColumnIndex": c0, "endColumnIndex": c1}
    spreadsheet.batch_update({"requests": [
        {"insertDimension": {"range": {"sheetId": sheet.id, "dimension": "COLUMNS",
                                       "startIndex": start, "endIndex": start + 12},
                             "inheritFromBefore": True}},
        {"copyPaste": {"source": grid(months[0], months[0] + 12), "destination": grid(start, start + 12),
                       "pasteType": "PASTE_NORMAL"}},
        {"copyPaste": {"source": grid(previous_total, previous_total + 1), "destination": grid(total, total + 1),
                       "pasteType": "PASTE_NORMAL"}},
    ]})
    formulas = sheet.get(f"{col_letters(start)}1:{col_letters(start + 11)}{rows}",
                         value_render_option="FORMULA")
    updates = plan_income_columns(formulas, year, start)
    updates.append({"range": f"{col_letters(total)}1", "values": [[year]]})
    sheet.batch_update(updates, value_input_option="USER_ENTERED")
    print(f"  已新增 {INCOME_SHEET} {year} 月份欄，改 {len(updates)} 格")
    return []


def run_new_year(spreadsheet, year, dry_run):
    print(f"== 建立 {year} 年度：{detail_title(year)}、{INCOME_SHEET} 月份欄 ==")
    problems = create_detail_sheet(spreadsheet, year, dry_run)
    if not problems:
        problems += add_income_columns(spreadsheet, year, dry_run)
    for problem in problems:
        print(f"WARN {problem}")
    return problems


def retarget_month_columns(spreadsheet, month, ledger_col, income_col, dry_run):
    """Point the month's Jennyall pair and 每月收入 column at that year's 細帳 month column."""
    updates_by_sheet = []
    if ledger_col is not None:
        sheet = spreadsheet.worksheet(LEDGER_SHEET)
        planned = []
        for col in (ledger_col - 1, ledger_col):
            letter = col_letters(col)
            formulas = sheet.get(f"{letter}{LEDGER_REF_ROWS[0]}:{letter}{LEDGER_REF_ROWS[1]}",
                                 value_render_option="FORMULA")
            planned += retarget_column(formulas, month.year, month.month, letter, LEDGER_REF_ROWS[0])
        updates_by_sheet.append((sheet, planned))
    if income_col is not None:
        sheet = spreadsheet.worksheet(INCOME_SHEET)
        letter = col_letters(income_col)
        formulas = sheet.get(f"{letter}1:{letter}{sheet.row_count}", value_render_option="FORMULA")
        updates_by_sheet.append((sheet, retarget_column(formulas, month.year, month.month, letter)))
    for sheet, planned in updates_by_sheet:
        print(f"  {sheet.title} 細帳參照 → {detail_title(month.year)}!{month_letter(month.month)}：{len(planned)} 格要改")
        for u in planned[:10]:
            print(f"    {u['range']}: {u['old']} → {u['values'][0][0]}")
        if planned and not dry_run:
            sheet.batch_update([{"range": u["range"], "values": u["values"]} for u in planned],
                               value_input_option="USER_ENTERED")
