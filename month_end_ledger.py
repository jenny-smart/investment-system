"""Month-end freeze and month-start roll for the 總帳 (2025Jenny-總帳) spreadsheet.

freeze（每月 30 日起，2 月為月底那天；持續檢查到下個月 10 日）
    Jennyall 第 2–38 列每個 A 欄基金/股票區塊，確認「總覽」裡對應的淨值／股價日期
    已是該月最後一個交易日，就把該區塊當月兩欄（例：10 月 FZ、GA）的公式換成值。
    同時把當月 64:67 列（叔叔）兩欄換成值。已經是值的格子不動，可以重複執行。

roll（每月 1 日）
    總覽 B2:B18 的 Jennyall!<欄> 換成當月小計欄（例：11 月 GA → GC），
    總覽 B44:B51 的 '每月收入'!<欄> 換成當月欄（例：11 月 AH → AI）。

月份欄位都依第 1 列的日期尋找，不寫死欄位字母；區塊依 A 欄名稱尋找，中間插列也能抓到。
"""
from __future__ import annotations

import argparse
import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import json
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

from asset_summary import col_index, col_letters, find_month_column, parse_date, parse_month

SPREADSHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"  # 2025Jenny-總帳
LEDGER_SHEET = "Jennyall"
OVERVIEW_SHEET = "總覽"
INCOME_SHEET = "每月收入"
TAIPEI = ZoneInfo("Asia/Taipei")

BLOCK_ROWS = (2, 38)          # Jennyall rows holding the fund/stock blocks
UNCLE_ROWS = (64, 67)         # frozen together with the month
OVERVIEW_LEDGER_CELLS = "B2:B18"
OVERVIEW_INCOME_CELLS = "B44:B51"

FREEZE_START_DAY = 30         # or the last day of a shorter month
FREEZE_GRACE_DAYS = 10        # keep checking the previous month until this day
LATE_AFTER_DAYS = 5           # a block still not frozen after this day is reported
TW_CLOSE = time(14, 40)       # TWSE closes 13:30; the price sync's last run is 14:30

# Each block ends on its A-label row and starts right after the previous block,
# except 台股, whose label sits on the first row with three more rows below it.
ROWS_BELOW_LABEL = {"台股": 3}

TW_STOCK = "tw"
NO_PRICE = "none"
# Jennyall A label -> where its month-end price date lives.
#   TW_STOCK: Taiwan stocks (ready after the last TWSE trading day's close)
#   NO_PRICE: no market price; frozen with the month
#   (section, include, exclude): 總覽 F-column section header and an optional
#   keyword the fund name must / must not contain. Unlisted labels use their own
#   name as the section.
SOURCES = {
    "台股": TW_STOCK,
    "富邦奈米投": NO_PRICE,
    "渣打-基金大華": ("渣打-美金", "大華", None),
    "渣打-美金": ("渣打-美金", None, "大華"),
    "渣打-美股": ("美股", None, None),
}


@dataclass
class Block:
    label: str
    first: int
    last: int


@dataclass
class Plan:
    updates: list = field(default_factory=list)   # [{"range": "FZ4", "values": [[v]]}]
    frozen: list = field(default_factory=list)    # labels frozen in this run
    done: list = field(default_factory=list)      # labels already values
    waiting: list = field(default_factory=list)   # (label, reason)
    problems: list = field(default_factory=list)


# ---------------------------------------------------------------- dates

def month_end(month):
    return date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])


def add_months(month, delta):
    index = month.year * 12 + month.month - 1 + delta
    return date(index // 12, index % 12 + 1, 1)


def last_weekday(month, closed=()):
    day = month_end(month)
    while day.weekday() >= 5 or day in closed:
        day -= timedelta(days=1)
    return day


def cell_date(value):
    """Sheet date: serial number (unformatted read) or 'YYYY/MM/DD' text."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return date(1899, 12, 30) + timedelta(days=int(value)) if 30000 < value < 80000 else None
    text = str(value or "").strip()
    match = re.match(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
    return date(int(match[1]), int(match[2]), int(match[3])) if match else None


def auto_tasks(today):
    """(month to freeze or None, month to roll the overview to or None)."""
    this_month = today.replace(day=1)
    start = min(FREEZE_START_DAY, month_end(today).day)
    if today.day >= start:
        freeze = this_month
    elif today.day <= FREEZE_GRACE_DAYS:
        freeze = add_months(this_month, -1)
    else:
        freeze = None
    roll = this_month if today.day == 1 else None
    return freeze, roll


# ---------------------------------------------------------------- Jennyall blocks

def find_blocks(column_a, rows=BLOCK_ROWS):
    """column_a: Jennyall column A from row 1. Returns blocks inside `rows`."""
    first_row, last_row = rows
    labels = []
    for row in range(first_row, last_row + 1):
        text = str(column_a[row - 1][0] if row - 1 < len(column_a) and column_a[row - 1] else "").strip()
        if text:
            labels.append((row, text))
    blocks, previous_end = [], None
    for row, label in labels:
        start = row if previous_end is None else previous_end + 1
        end = min(row + ROWS_BELOW_LABEL.get(label, 0), last_row)
        blocks.append(Block(label, start, end))
        previous_end = end
    return blocks


def is_formula(value):
    return isinstance(value, str) and value.startswith("=")


def freeze_updates(formulas, values, first_row, first_col, rows):
    """Cell updates replacing formulas with their values for rows (first, last).

    formulas / values: grids read from (first_row, first_col); returns
    (updates, error_cells). Cells showing an error keep their formula.
    """
    updates, errors = [], []
    for row in range(rows[0], rows[1] + 1):
        r = row - first_row
        f_line = formulas[r] if r < len(formulas) else []
        v_line = values[r] if r < len(values) else []
        for c, formula in enumerate(f_line):
            if not is_formula(formula):
                continue
            value = v_line[c] if c < len(v_line) else ""
            address = f"{col_letters(first_col + c)}{row}"
            if isinstance(value, str) and value.startswith("#"):
                errors.append(f"{address} {value}")
                continue
            updates.append({"range": address, "values": [[value]]})
    return updates, errors


# ---------------------------------------------------------------- readiness

def overview_section(rows, header, include=None, exclude=None):
    """rows: 總覽 [F, G, H] from row 1. Fund rows under `header` until a blank F.

    Returns [(row, name, date or None)], or None when the header is missing.
    """
    start = None
    for index, line in enumerate(rows, start=1):
        if str((line or [""])[0]).strip() == header:
            start = index
            break
    if start is None:
        return None
    funds = []
    for index in range(start + 1, len(rows) + 1):
        line = list(rows[index - 1]) + ["", ""]
        name = str(line[0]).strip()
        if not name:
            break
        if include and include not in name or exclude and exclude in name:
            continue
        funds.append((index, name, cell_date(line[1])))
    return funds


def price_status(label, overview_rows, month, now, tw_closed=()):
    """(ready, reason, problem) for one Jennyall block."""
    source = SOURCES.get(label, (label, None, None))
    if source == NO_PRICE:
        return True, "無市價，隨月份固定", None
    if source == TW_STOCK:
        last_day = last_weekday(month, tw_closed)
        close = datetime.combine(last_day, TW_CLOSE, TAIPEI)
        if now >= close:
            return True, f"台股 {last_day:%m/%d} 已收盤", None
        return False, f"等 {last_day:%m/%d} 收盤", None

    header, include, exclude = source
    funds = overview_section(overview_rows, header, include, exclude)
    if funds is None:
        return False, "", f"{label}：總覽 F 欄找不到「{header}」"
    dated = [(row, name, d) for row, name, d in funds if d]
    if not dated:
        return False, "", f"{label}：總覽「{header}」下沒有日期"
    expected = last_weekday(month)
    behind = [f"F{row} {d:%m/%d}" for row, _, d in dated if d < expected]
    if behind:
        return False, f"等 {expected:%m/%d} 淨值（{', '.join(behind)}）", None
    late = [f"F{row} {d:%m/%d}" for row, _, d in dated if d > month_end(month)]
    if late:
        return True, "", f"{label}：日期已過月底才固定，可能不是月底市值（{', '.join(late)}）"
    return True, f"日期 {expected:%m/%d}", None


# ---------------------------------------------------------------- plans

def plan_freeze(column_a, formulas, values, first_col, overview_rows, month, now,
                tw_closed=(), force=False):
    """formulas / values: Jennyall grids for the month's two columns, from row 1."""
    plan = Plan()
    for block in find_blocks(column_a):
        updates, errors = freeze_updates(formulas, values, 1, first_col, (block.first, block.last))
        plan.problems += [f"{block.label}：{e} 是錯誤值，保留公式" for e in errors]
        if not updates:
            if not errors:
                plan.done.append(block.label)
            continue
        ready, reason, problem = price_status(block.label, overview_rows, month, now, tw_closed)
        if problem:
            plan.problems.append(problem)
        if ready or force:
            plan.updates += updates
            plan.frozen.append(block.label)
        else:
            plan.waiting.append((block.label, reason))
    uncle, errors = freeze_updates(formulas, values, 1, first_col, UNCLE_ROWS)
    plan.problems += [f"{UNCLE_ROWS[0]}:{UNCLE_ROWS[1]} 列：{e} 是錯誤值，保留公式" for e in errors]
    if uncle:
        plan.updates += uncle
        plan.frozen.append(f"{UNCLE_ROWS[0]}:{UNCLE_ROWS[1]} 列")
    if plan.waiting and now.date() > add_months(month, 1) + timedelta(days=LATE_AFTER_DAYS - 1):
        plan.problems.append("已過月底多日仍未固定：" + "、".join(label for label, _ in plan.waiting))
    return plan


def month_columns(row1):
    """{(year, month): 0-based column} for dated cells in a header row."""
    found = {}
    for col, value in enumerate(row1):
        d = parse_date(value) or cell_date(value)
        if d and (d.year, d.month) not in found:
            found[(d.year, d.month)] = col
    return found


LEDGER_REF = re.compile(r"((?:'Jennyall'|Jennyall)!\$?)([A-Z]{1,3})(\$?\d+)")
INCOME_REF = re.compile(r"('每月收入'!\$?)([A-Z]{1,3})(\$?\d+:\$?)([A-Z]{1,3})\b")


def retarget(formulas, pattern, month_cols, new_col, first_row, column="B"):
    """Point every month-column reference in `formulas` at `new_col`.

    Only columns that are month columns (dated in the source sheet's row 1) are
    changed, so the criteria ranges ($J, $A) stay as they are.
    """
    dated = set(month_cols.values())
    new_letters = col_letters(new_col)
    updates = []

    def swap(match):
        groups = list(match.groups())
        if col_index(groups[1]) not in dated:
            return match.group(0)
        groups[1] = new_letters
        if len(groups) == 4 and col_index(groups[3]) in dated:
            groups[3] = new_letters
        return "".join(groups)

    for offset, line in enumerate(formulas):
        formula = str(line[0]) if line else ""
        if not is_formula(formula):
            continue
        changed = pattern.sub(swap, formula)
        if changed != formula:
            updates.append({"range": f"{column}{first_row + offset}", "values": [[changed]],
                            "old": formula})
    return updates


# ---------------------------------------------------------------- I/O

def open_spreadsheet(credentials_file):
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    if credentials_file:
        credentials = Credentials.from_service_account_file(str(credentials_file), scopes=scopes)
    else:
        raw = os.environ.get("INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if not raw:
            raise RuntimeError("Missing INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON secret")
        credentials = Credentials.from_service_account_info(json.loads(raw), scopes=scopes)
    return gspread.authorize(credentials).open_by_key(SPREADSHEET_ID)


def tw_closed_days():
    import requests
    from sync_tw_stock_prices import parse_holidays
    try:
        response = requests.get(
            "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=20,
        )
        response.raise_for_status()
        return parse_holidays(response.json())
    except Exception as exc:  # noqa: BLE001 - weekends still count
        print(f"TWSE holiday schedule unavailable ({type(exc).__name__}); weekdays assumed open")
        return set()


def run_freeze(spreadsheet, month, now, dry_run, force):
    ledger = spreadsheet.worksheet(LEDGER_SHEET)
    sub_col = find_month_column([ledger.row_values(1)], month)
    first_col = sub_col - 1
    span = f"{col_letters(first_col)}1:{col_letters(sub_col)}{UNCLE_ROWS[1]}"
    print(f"== 固定 {month:%Y/%m}：Jennyall {col_letters(first_col)}/{col_letters(sub_col)} 欄 ==")
    column_a = ledger.get(f"A1:A{BLOCK_ROWS[1]}")
    formulas = ledger.get(span, value_render_option="FORMULA")
    values = ledger.get(span, value_render_option="UNFORMATTED_VALUE")
    overview_rows = spreadsheet.worksheet(OVERVIEW_SHEET).get(
        "F1:H200", value_render_option="UNFORMATTED_VALUE")
    plan = plan_freeze(column_a, formulas, values, first_col, overview_rows, month, now,
                       tw_closed_days(), force)
    for label in plan.done:
        print(f"  已是值：{label}")
    for label, reason in plan.waiting:
        print(f"  等待中：{label} {reason}")
    for label in plan.frozen:
        print(f"  固定：{label}")
    for problem in plan.problems:
        print(f"WARN {problem}")
    if plan.updates and not dry_run:
        ledger.batch_update([{"range": u["range"], "values": u["values"]} for u in plan.updates],
                            value_input_option="RAW")
        print(f"  已寫入 {len(plan.updates)} 格")
    elif plan.updates:
        print(f"  預覽：會寫入 {len(plan.updates)} 格")
    return plan.problems


def run_roll(spreadsheet, month, dry_run):
    print(f"== 總覽切換到 {month:%Y/%m} ==")
    ledger_cols = month_columns(spreadsheet.worksheet(LEDGER_SHEET).row_values(1))
    income_cols = month_columns(spreadsheet.worksheet(INCOME_SHEET).row_values(1))
    problems = []
    key = (month.year, month.month)
    overview = spreadsheet.worksheet(OVERVIEW_SHEET)
    updates = []
    for cells, pattern, cols, name in (
        (OVERVIEW_LEDGER_CELLS, LEDGER_REF, ledger_cols, LEDGER_SHEET),
        (OVERVIEW_INCOME_CELLS, INCOME_REF, income_cols, INCOME_SHEET),
    ):
        if key not in cols:
            problems.append(f"{name} 第 1 列找不到 {month:%Y/%m}")
            continue
        first_row = int(re.search(r"\d+", cells).group(0))
        formulas = overview.get(cells, value_render_option="FORMULA")
        planned = retarget(formulas, pattern, cols, cols[key], first_row)
        print(f"  {cells} → {name} {col_letters(cols[key])} 欄：{len(planned)} 格要改")
        for u in planned:
            print(f"    {u['range']}: {u['old']} → {u['values'][0][0]}")
        updates += planned
    for problem in problems:
        print(f"WARN {problem}")
    if updates and not dry_run:
        overview.batch_update([{"range": u["range"], "values": u["values"]} for u in updates],
                              value_input_option="USER_ENTERED")
        print(f"  已寫入 {len(updates)} 格")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument("--mode", choices=("auto", "freeze", "roll"), default="auto",
                        help="auto 依日期決定；freeze／roll 立即執行指定的那一項")
    parser.add_argument("--month", help="freeze／roll 的月份 YYYY/M（預設：freeze 上個月底前後自動判斷，roll 本月）")
    parser.add_argument("--force", action="store_true", help="freeze 時不檢查日期，全部固定")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    now = datetime.now(TAIPEI)
    today = now.date()
    freeze_month, roll_month = auto_tasks(today)
    if args.mode == "freeze":
        freeze_month = parse_month(args.month) if args.month else (freeze_month or add_months(today.replace(day=1), -1))
        roll_month = None
    elif args.mode == "roll":
        roll_month = parse_month(args.month) if args.month else today.replace(day=1)
        freeze_month = None
    if not freeze_month and not roll_month:
        print(f"{today:%Y/%m/%d}：不在月底檢查期間（{FREEZE_START_DAY} 日起到下月 {FREEZE_GRACE_DAYS} 日），略過")
        return 0

    spreadsheet = open_spreadsheet(args.credentials_file)
    problems = []
    if roll_month:
        problems += run_roll(spreadsheet, roll_month, args.dry_run)
    if freeze_month:
        problems += run_freeze(spreadsheet, freeze_month, now, args.dry_run, args.force)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
