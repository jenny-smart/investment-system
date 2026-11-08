"""Month-end freeze and month-start roll for the 總帳 (2025Jenny-總帳) spreadsheet.

freeze（每月 30 日起，2 月為月底那天；持續檢查到下個月 10 日）
    Jennyall 第 2–38 列每個 A 欄基金/股票區塊，確認「總覽」裡對應的淨值／股價日期
    已是該月最後一個交易日，就把該區塊當月兩欄（例：10 月 FZ、GA）的公式換成值。
    同時把當月 64:67 列（叔叔）兩欄換成值。已經是值的格子不動，可以重複執行。

    月底最後一天起，各區塊的匯率格先固定成月底匯率。
    過了月底仍未固定（遇假日沒有最後一個平日的淨值、或排程沒跑到）時，從淨值紀錄
    （基金，由基金淨值排程記錄）或 Yahoo（美股）查月底那天的淨值，以「現在市值 × 月底淨值 ÷ 現在淨值」
    換算月底市值後固定，不用手動處理。

roll（每月 1–10 日，已是本月欄就不改；1 日沒跑到會補上）
    總覽 B2:B18 的 Jennyall!<欄> 換成當月小計欄（例：11 月 GA → GC），
    總覽 B40:B51 的 '每月收入'!<欄> 換成當月欄（例：11 月 AH → AI）。
    Jennyall 當月兩欄第 40–57 列的 'YYYY細帳'!<欄> 換成細帳的當月欄
    （例：12 月 '2026細帳'!$M:$M → $N:$N；1 月換成 '2027細帳'!$C:$C）。

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
OVERVIEW_INCOME_CELLS = "B40:B51"
DETAIL_ROWS = (40, 57)        # Jennyall rows that sum the year's 細帳 by month
OVERVIEW_RANGE = "F1:K200"    # name, date, NAV/price, ..., K = 台幣市值
NAV_COL, VALUE_COL = 2, 5     # offsets inside OVERVIEW_RANGE

FREEZE_START_DAY = 30         # or the last day of a shorter month
FREEZE_GRACE_DAYS = 10        # keep checking the previous month until this day
NAV_BUSINESS_DAYS = 2         # 上個月基金月底淨值只在新月份前 2 個工作天讀取；之後沒取得就記入日曆
LATE_AFTER_DAYS = 5           # a block still not frozen after this day is reported
TW_CLOSE = time(14, 40)       # TWSE closes 13:30; the price sync's last run is 14:30
TW_OPEN = time(8, 30)         # the price sync starts overwriting prices here
RATE_FREEZE_TIME = time(16, 0)  # FX cells of open blocks freeze from this time on the month's last day
REPORT_HOUR = 8               # problems that persist across runs fail (and email) only in this hour

# Each block ends on its A-label row and starts right after the previous block,
# except 台股, whose label sits on the first row with three more rows below it.
ROWS_BELOW_LABEL = {"台股": 3}

TW_STOCK = "tw"
NO_PRICE = "none"
FUND, US_STOCK = "fund", "us"


@dataclass(frozen=True)
class Source:
    """Where a block's month-end price lives in 總覽 and which cells hold its market value.

    targets: {ticker or None: (row offset from the label row, 0 = detail / 1 = subtotal column)}.
    None means the block's value, scaled by the value-weighted NAV ratio of all
    its funds; a ticker scales that cell by that ticker's own price ratio.
    """
    section: str
    include: str | None = None
    exclude: str | None = None
    kind: str = FUND
    targets: tuple = ((None, (0, 1)),)


# Jennyall A label -> source. Unlisted labels use their own name as the 總覽 section.
SOURCES = {
    "台股": TW_STOCK,
    "富邦奈米投": NO_PRICE,
    "渣打-基金大華": Source("渣打-美金", include="大華"),
    "渣打-美金": Source("渣打-美金", exclude="大華"),
    # 渣打-美股: pypl value on the row above the label, xyz on the label row (detail column);
    # the subtotal is =SUM() of the two and follows.
    "渣打-美股": Source("美股", kind=US_STOCK, targets=(("PYPL", (-1, 0)), ("XYZ", (0, 0)))),
}

RATE_REF = re.compile(r"(?:'總覽'|總覽)!\$?R\$?\d+")
SAME_COL_REF = re.compile(r"^=\s*\$?([A-Z]{1,3})\$?(\d+)\s*$")


@dataclass
class Block:
    label: str
    first: int
    last: int


@dataclass
class Fund:
    row: int
    name: str
    date: date
    nav: float
    value: float


@dataclass
class Plan:
    updates: list = field(default_factory=list)   # [{"range": "FZ4", "values": [[v]]}]
    frozen: list = field(default_factory=list)    # labels frozen in this run
    done: list = field(default_factory=list)      # labels already values
    waiting: list = field(default_factory=list)   # (label, reason)
    backfill: list = field(default_factory=list)  # (Block, [updates], description)
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


def first_weekday(month, closed=()):
    day = month.replace(day=1)
    while day.weekday() >= 5 or day in closed:
        day += timedelta(days=1)
    return day


def cell_date(value, strict=False):
    """Sheet date: serial number (unformatted read) or 'YYYY/MM/DD' text."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return date(1899, 12, 30) + timedelta(days=int(value)) if 30000 < value < 80000 else None
    text = str(value or "").strip()
    match = re.match(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
    if not match:
        return None
    try:
        return date(int(match[1]), int(match[2]), int(match[3]))
    except ValueError:   # 例如 2026/11/31：不是有效日期
        if strict:
            raise
        print(f"WARN「{text}」不是有效日期，略過")
        return None


def to_number(value):
    if isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def nth_business_day(month_start, n, closed=()):
    """該月第 n 個工作天（跳過週末、休市日）。"""
    day, count = month_start, 0
    while True:
        if day.weekday() < 5 and day not in closed:
            count += 1
            if count == n:
                return day
        day += timedelta(days=1)


def auto_tasks(today, closed=()):
    """(要固定的月份或 None, 總覽要切換到的月份或 None, 要檢查是否漏固定、記日曆的月份或 None)。

    上個月：只在本月前 NAV_BUSINESS_DAYS 個工作天讀月底淨值固定；過了就不再重試，改檢查並記日曆。"""
    this_month = today.replace(day=1)
    start = min(FREEZE_START_DAY, month_end(today).day)
    freeze = alert = None
    if today.day >= start:
        freeze = this_month
    elif today.day <= FREEZE_GRACE_DAYS:
        if today <= nth_business_day(this_month, NAV_BUSINESS_DAYS, closed):
            freeze = add_months(this_month, -1)
        else:
            alert = add_months(this_month, -1)
    # 1–10 日每次都檢查：已是本月欄就不會改，1 日沒跑到（例如排程停擺）之後也會補上
    roll = this_month if today.day <= FREEZE_GRACE_DAYS else None
    return freeze, roll, alert


def month_end_price(history, month):
    """history: [(date, price)]. Returns (date, price) of the last price on or
    before month end, or None until the source has a price after month end
    (only then is the month's last price certainly published)."""
    end = month_end(month)
    if not any(d > end for d, _ in history):
        return None
    inside = [(d, p) for d, p in history if d <= end and d.year == end.year and d.month == end.month]
    return max(inside) if inside else None


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


def label_row(block):
    return block.last - ROWS_BELOW_LABEL.get(block.label, 0)


def is_formula(value):
    return isinstance(value, str) and value.startswith("=")


def grid_cell(grid, row, col):
    line = grid[row - 1] if 0 < row <= len(grid) else []
    return line[col] if col < len(line) else ""


def freeze_updates(formulas, values, first_col, rows, only=None):
    """Cell updates replacing formulas with their values for rows (first, last).

    formulas / values: grids read from row 1 starting at first_col; `only`
    optionally limits to (row, col) cells. Returns (updates, error_cells);
    cells showing an error keep their formula.
    """
    updates, errors = [], []
    for row in range(rows[0], rows[1] + 1):
        for c in range(2):
            formula = grid_cell(formulas, row, c)
            if not is_formula(formula) or only is not None and (row, c) not in only:
                continue
            value = grid_cell(values, row, c)
            address = f"{col_letters(first_col + c)}{row}"
            if isinstance(value, str) and value.startswith("#"):
                errors.append(f"{address} {value}")
                continue
            updates.append({"range": address, "values": [[value]]})
    return updates, errors


def rate_cells(formulas, first_col, rows):
    """(row, col) cells holding an FX rate: =總覽!R… or a plain reference to one."""
    found = set()
    for _ in range(2):  # second pass catches =GA19 pointing at a rate cell
        for row in range(rows[0], rows[1] + 1):
            for c in range(2):
                formula = str(grid_cell(formulas, row, c))
                if RATE_REF.search(formula):
                    found.add((row, c))
                    continue
                match = SAME_COL_REF.match(formula)
                if not match:
                    continue
                ref = (int(match[2]), col_index(match[1]) - first_col)
                if 0 <= ref[1] < 2 and (ref in found or RATE_REF.search(str(grid_cell(formulas, *ref)))):
                    found.add((row, c))
    return found


# ---------------------------------------------------------------- readiness

def overview_section(rows, header, include=None, exclude=None):
    """rows: 總覽 F:K from row 1. Fund rows under `header` until a blank F.

    Returns [Fund] for rows with a date (others, e.g. #N/A, are skipped), or
    None when the header is missing.
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
        line = list(rows[index - 1]) + [""] * 6
        name = str(line[0]).strip()
        if not name:
            break
        if include and include not in name or exclude and exclude in name:
            continue
        day = cell_date(line[1])
        if day:
            funds.append(Fund(index, name, day, to_number(line[NAV_COL]) or 0.0,
                              to_number(line[VALUE_COL]) or 0.0))
    return funds


READY, WAIT, BACKFILL = "ready", "wait", "backfill"


def price_status(label, overview_rows, month, now, tw_closed=()):
    """(state, reason, problem, funds) for one Jennyall block."""
    source = SOURCES.get(label, Source(label))
    if source == NO_PRICE:
        return READY, "無市價，隨月份固定", None, []
    if source == TW_STOCK:
        last_day = last_weekday(month, tw_closed)
        if now < datetime.combine(last_day, TW_CLOSE, TAIPEI):
            return WAIT, f"等 {last_day:%m/%d} 收盤", None, []
        next_open = datetime.combine(first_weekday(add_months(month, 1), tw_closed), TW_OPEN, TAIPEI)
        if now >= next_open:
            return WAIT, "", f"{label}：已過下個月第一個交易日開盤，股價不是月底收盤，請手動固定", []
        return READY, f"台股 {last_day:%m/%d} 已收盤", None, []

    funds = overview_section(overview_rows, source.section, source.include, source.exclude)
    if funds is None:
        return WAIT, "", f"{label}：總覽 F 欄找不到「{source.section}」", []
    if not funds:
        return WAIT, "", f"{label}：總覽「{source.section}」下沒有日期", []
    expected, end = last_weekday(month), month_end(month)
    if all(expected <= f.date <= end for f in funds):
        return READY, f"日期 {expected:%m/%d}", None, funds
    if now.date() > end:
        return BACKFILL, "查月底淨值", None, funds
    behind = [f"F{f.row} {f.date:%m/%d}" for f in funds if f.date < expected]
    return WAIT, f"等 {expected:%m/%d} 淨值（{', '.join(behind)}）", None, funds


def backfill_updates(block, source, funds, values, first_col, month, history, formulas=None):
    """Scale the block's market-value cells to month-end prices.

    history(kind, name) -> [(date, price)] or None. Returns (updates, note, reason)
    where reason explains why nothing could be done yet (updates is then None).
    """
    month_end_navs, notes = {}, []
    for fund in funds:
        found = history(source.kind, fund.name)
        if found is None:
            return None, "", f"F{fund.row} {fund.name} 查不到歷史淨值"
        point = month_end_price(found, month)
        if point is None:
            return None, "", f"F{fund.row} 月底淨值尚未確定"
        if not fund.nav:
            return None, "", f"F{fund.row} 總覽沒有現在淨值"
        if abs(point[1] / fund.nav - 1) > MAX_NAV_MOVE:
            return None, "", (f"F{fund.row} 月底淨值 {point[1]:g} 與現在 {fund.nav:g} 相差超過 "
                              f"{MAX_NAV_MOVE:.0%}，不換算")
        month_end_navs[fund.row] = point
        notes.append(f"F{fund.row} {point[0]:%m/%d} {point[1]:g}（現在 {fund.date:%m/%d} {fund.nav:g}）")

    base_row = label_row(block)
    updates = []
    for ticker, (offset, col) in source.targets:
        if ticker is None:
            weight = sum(f.value for f in funds)
            ratio = (sum(f.value * month_end_navs[f.row][1] / f.nav for f in funds) / weight
                     if weight else 1.0)
        else:
            matched = [f for f in funds if f.name.strip().upper() == ticker]
            if not matched:
                return None, "", f"總覽「{source.section}」找不到 {ticker}"
            ratio = month_end_navs[matched[0].row][1] / matched[0].nav
        row = base_row + offset
        if formulas is not None and not is_formula(grid_cell(formulas, row, col)):
            # Already scaled by an earlier (or concurrent) run: never scale twice.
            return None, "", f"{col_letters(first_col + col)}{row} 已換算，等待固定"
        current = to_number(grid_cell(values, row, col))
        if current is None:
            return None, "", f"{col_letters(first_col + col)}{row} 不是數字"
        updates.append({"range": f"{col_letters(first_col + col)}{row}",
                        "values": [[current * ratio]], "old": current, "ratio": ratio})
    return updates, "；".join(notes), None


# ---------------------------------------------------------------- plans

def plan_freeze(column_a, formulas, values, first_col, overview_rows, month, now,
                tw_closed=(), force=False, history=None):
    """formulas / values: Jennyall grids for the month's two columns, from row 1.

    history(kind, name) -> [(date, price)] or None, used for blocks still open
    after month end. Blocks to backfill land in plan.backfill: write those cells
    first, re-read, then freeze the whole block.
    """
    plan = Plan()
    after_month = now.date() > month_end(month)
    rates_due = now >= datetime.combine(month_end(month), RATE_FREEZE_TIME, TAIPEI)
    for block in find_blocks(column_a):
        rows = (block.first, block.last)
        updates, errors = freeze_updates(formulas, values, first_col, rows)
        plan.problems += [f"{block.label}：{e} 是錯誤值，保留公式" for e in errors]
        if not updates:
            if not errors:
                plan.done.append(block.label)
            continue
        state, reason, problem, funds = price_status(block.label, overview_rows, month, now, tw_closed)
        if problem:
            plan.problems.append(problem)
        if state == BACKFILL and not force:
            source = SOURCES.get(block.label, Source(block.label))
            scaled, note, why = backfill_updates(block, source, funds, values, first_col, month,
                                                 history or (lambda *_: None), formulas)
            if scaled is None:
                state, reason = WAIT, why
            else:
                plan.backfill.append((block, scaled, note))
                if rate_cells(formulas, first_col, rows):
                    plan.problems.append(f"{block.label}：匯率格到月底後才固定，可能不是月底匯率")
                continue
        if state == READY or force:
            plan.updates += updates
            plan.frozen.append(block.label)
            continue
        plan.waiting.append((block.label, reason))
        if rates_due:
            rates, _ = freeze_updates(formulas, values, first_col, rows,
                                      only=rate_cells(formulas, first_col, rows))
            if rates:
                plan.updates += rates
                plan.frozen.append(f"{block.label} 匯率")
                if after_month:
                    plan.problems.append(f"{block.label}：月底之後才固定匯率，可能不是月底匯率")
    uncle, errors = freeze_updates(formulas, values, first_col, UNCLE_ROWS)
    plan.problems += [f"{UNCLE_ROWS[0]}:{UNCLE_ROWS[1]} 列：{e} 是錯誤值，保留公式" for e in errors]
    if uncle:
        plan.updates += uncle
        plan.frozen.append(f"{UNCLE_ROWS[0]}:{UNCLE_ROWS[1]} 列")
    if plan.waiting and now.date() > add_months(month, 1) + timedelta(days=LATE_AFTER_DAYS - 1):
        plan.problems.append("已過月底多日仍未固定：" + "、".join(
            f"{label}（{reason}）" if reason else label for label, reason in plan.waiting))
    return plan


def month_columns(row1):
    """{(year, month): 0-based column} for dated cells in a header row."""
    found = {}
    for col, value in enumerate(row1):
        try:
            d = parse_date(value) or cell_date(value, strict=True)
        except ValueError:
            print(f"WARN 第 1 列 {col_letters(col)} 欄「{value}」不是有效日期，略過這欄")
            continue
        if d and (d.year, d.month) not in found:
            found[(d.year, d.month)] = col
    return found


# '2026細帳'!$M:$M, '2026細帳'!M5, '2026細帳'!$M$2:$M — sheet year, then each side of the range
DETAIL_REF = re.compile(r"'(\d{4})細帳'!(\$?)([A-Z]{1,3})(\$?\d*)(?::(\$?)([A-Z]{1,3})(\$?\d*))?")
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


def detail_first_col(formulas_by_month, before=None):
    """細帳's January column (0-based), learned from Jennyall's earlier month columns.

    formulas_by_month: {(year, month): [formula, ...]} for the 40–57 rows of each month.
    Every month's first 細帳 reference is that month's column, so column − (month − 1)
    is January's; the most common answer wins. Months from `before` on are ignored
    (they may still be copies of the previous month).
    """
    votes = {}
    for (year, mon), formulas in formulas_by_month.items():
        if before and (year, mon) >= before:
            continue
        for formula in formulas:
            match = DETAIL_REF.search(str(formula)) if is_formula(formula) else None
            if match:
                jan = col_index(match.group(3)) - (mon - 1)
                if jan >= 0:
                    votes[jan] = votes.get(jan, 0) + 1
    return max(votes, key=votes.get) if votes else None


def retarget_detail(formulas, month, first_col, detail_cols, col_letter, first_row, sheet_cols=None):
    """Point 'YYYY細帳' month-column references in one Jennyall column at `month`.

    detail_cols: 0-based 細帳 columns that are month columns (Jan..Dec); others ($A
    criteria) stay. sheet_cols: optional {(year, month): col} read from the target
    year's 細帳 row 1, preferred over first_col + month − 1.
    """
    target = (sheet_cols or {}).get((month.year, month.month), first_col + month.month - 1)
    new_sheet = f"'{month.year}細帳'"
    new_letters = col_letters(target)
    updates = []

    def swap(match):
        # Every 細帳 reference moves to the month's year sheet; only month columns change
        # letters, so the criteria range ($A) follows to the new sheet unchanged.
        _year, d1, c1, r1, d2, c2, r2 = match.groups()
        text = f"{new_sheet}!{d1}{new_letters if col_index(c1) in detail_cols else c1}{r1}"
        if c2:
            text += f":{d2}{new_letters if col_index(c2) in detail_cols else c2}{r2}"
        return text

    for offset, line in enumerate(formulas):
        formula = str(line[0]) if line else ""
        if not is_formula(formula):
            continue
        changed = DETAIL_REF.sub(swap, formula)
        if changed != formula:
            updates.append({"range": f"{col_letter}{first_row + offset}", "values": [[changed]], "old": formula})
    return updates


def roll_detail_refs(spreadsheet, month, ledger_cols, dry_run):
    """Jennyall's month columns, rows 40–57: 'YYYY細帳' refs → the month's 細帳 column."""
    key = (month.year, month.month)
    ledger = spreadsheet.worksheet(LEDGER_SHEET)
    first, last = DETAIL_ROWS
    if key not in ledger_cols:
        return [f"{LEDGER_SHEET} 第 1 列找不到 {month:%Y/%m}"], 0
    subtotal = ledger_cols[key]
    cols = [subtotal - 1, subtotal]  # detail, subtotal
    # Earlier months teach which 細帳 column is January (one read for every month).
    grid = ledger.get(f"A{first}:{col_letters(max(ledger_cols.values()))}{last}", value_render_option="FORMULA")
    history = {k: [grid_cell(grid, r, c) for r in range(1, len(grid) + 1) for c in (col - 1, col)]
               for k, col in ledger_cols.items() if col >= 1}
    sheet_name = f"{month.year}細帳"
    titles = {ws.title for ws in spreadsheet.worksheets()}
    if sheet_name not in titles:
        return [f"找不到「{sheet_name}」分頁，{LEDGER_SHEET} 第 {first}–{last} 列沒有換細帳欄"], 0
    sheet_cols = {k: c for k, c in month_columns(spreadsheet.worksheet(sheet_name).row_values(1)).items()
                  if k[0] == month.year}
    first_col = detail_first_col(history, before=key)
    if len(sheet_cols) >= 12:
        detail_cols = set(sheet_cols.values())
        first_col = sheet_cols[(month.year, 1)]
    elif first_col is not None:
        detail_cols = set(range(first_col, first_col + 12))
        sheet_cols = {}
    else:
        return [f"判斷不出細帳每個月在哪一欄（細帳第 1 列沒有月份日期、Jennyall 之前的月份也沒有細帳公式）"], 0
    updates = []
    for col in cols:
        formulas = [[grid_cell(grid, r, col)] for r in range(1, last - first + 2)]
        updates += retarget_detail(formulas, month, first_col, detail_cols, col_letters(col), first, sheet_cols)
    target = sheet_cols.get(key, first_col + month.month - 1)
    print(f"  {LEDGER_SHEET} {col_letters(cols[0])}{first}:{col_letters(cols[1])}{last} → "
          f"{sheet_name} {col_letters(target)} 欄：{len(updates)} 格要改")
    for u in updates:
        print(f"    {u['range']}: {u['old']} → {u['values'][0][0]}")
    if updates and not dry_run:
        ledger.batch_update(strip_extra(updates), value_input_option="USER_ENTERED")
        print(f"  已寫入 {len(updates)} 格")
        return [], len(updates)
    return [], 0


# ---------------------------------------------------------------- price history

NAV_LOG_TITLE = "淨值紀錄"   # written by sync_fund_nav.py: 淨值日期, 基金名稱, 淨值, 來源, 記錄時間
MAX_NAV_MOVE = 0.3            # a month-end NAV more than 30% from the current one is rejected


def parse_nav_log(rows):
    """{fund name: [(date, nav)]} from the 淨值紀錄 sheet rows (header skipped)."""
    history = {}
    for row in rows:
        if len(row) < 3:
            continue
        day, nav = cell_date(row[0]), to_number(row[2])
        name = str(row[1]).strip()
        if day and nav and name:
            history.setdefault(name, set()).add((day, nav))
    return {name: sorted(points) for name, points in history.items()}


class PriceHistory:
    """history(kind, name): funds from the 淨值紀錄 sheet, US stocks from Yahoo.

    MoneyDJ only serves a fund's latest NAV (鉅亨 returns nothing from GitHub
    Actions), so the fund NAV sync logs every NAV date it sees and this reads
    that log.
    """

    def __init__(self, month, spreadsheet=None):
        self.month = month
        self.spreadsheet = spreadsheet
        self.cache = {}
        self.notes = {}   # name -> ["淨值紀錄 3 筆 10/29–11/02", ...] for diagnostics
        self.nav_log = None

    def note(self, name, source, points):
        days = sorted(d for d, _ in points)
        span = f"{days[0]:%m/%d}–{days[-1]:%m/%d}" if days else "無資料"
        self.notes.setdefault(name, []).append(f"{source} {len(points)} 筆 {span}")

    def __call__(self, kind, name):
        key = (kind, name)
        if key not in self.cache:
            try:
                self.cache[key] = self.fund(name) if kind == FUND else self.us(name)
            except Exception as exc:  # noqa: BLE001 - reported as "not found"
                print(f"  歷史價格錯誤 {name}: {type(exc).__name__} {str(exc)[:80]}")
                self.cache[key] = None
        return self.cache[key]

    def fund(self, name):
        if self.nav_log is None:
            import gspread
            try:
                rows = self.spreadsheet.worksheet(NAV_LOG_TITLE).get("A2:C") if self.spreadsheet else []
            except gspread.WorksheetNotFound:
                rows = []
            self.nav_log = parse_nav_log(rows)
        points = self.nav_log.get(str(name).strip(), [])
        self.note(name, NAV_LOG_TITLE, points)
        return points or None

    def us(self, ticker):
        import yfinance as yf
        start = month_end(self.month) - timedelta(days=10)
        closes = yf.Ticker(ticker.strip().upper()).history(
            start=start.isoformat(), end=(datetime.now(TAIPEI).date() + timedelta(days=1)).isoformat(),
            auto_adjust=False)["Close"].dropna()
        points = [(index.date(), float(price)) for index, price in closes.items()]
        self.note(ticker, "Yahoo", points)
        return points or None


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


def strip_extra(updates):
    return [{"range": u["range"], "values": u["values"]} for u in updates]


def run_freeze(spreadsheet, month, now, dry_run, force, plan_only=False):
    ledger = spreadsheet.worksheet(LEDGER_SHEET)
    sub_col = find_month_column([ledger.row_values(1)], month)
    first_col = sub_col - 1
    span = f"{col_letters(first_col)}1:{col_letters(sub_col)}{UNCLE_ROWS[1]}"
    print(f"== 固定 {month:%Y/%m}：Jennyall {col_letters(first_col)}/{col_letters(sub_col)} 欄 ==")
    column_a = ledger.get(f"A1:A{BLOCK_ROWS[1]}")
    formulas = ledger.get(span, value_render_option="FORMULA")
    values = ledger.get(span, value_render_option="UNFORMATTED_VALUE")
    overview_rows = spreadsheet.worksheet(OVERVIEW_SHEET).get(
        OVERVIEW_RANGE, value_render_option="UNFORMATTED_VALUE")
    plan = plan_freeze(column_a, formulas, values, first_col, overview_rows, month, now,
                       tw_closed_days(), force, PriceHistory(month, spreadsheet))
    if plan_only:
        return plan
    for label in plan.done:
        print(f"  已是值：{label}")
    for label, reason in plan.waiting:
        print(f"  等待中：{label} {reason}")
    for label in plan.frozen:
        print(f"  固定：{label}")
    for block, scaled, note in plan.backfill:
        cells = "、".join(f"{u['range']} {u['old']:,.0f} → {u['values'][0][0]:,.0f}" for u in scaled)
        print(f"  月底淨值回填：{block.label} {cells}（{note}）")
    for problem in plan.problems:
        print(f"WARN {problem}")

    written = 0
    if dry_run:
        count = len(plan.updates) + sum(len(s) for _, s, _ in plan.backfill)
        if count:
            print(f"  預覽：會寫入 {count} 格以上")
        return plan.problems, 0
    updates = list(plan.updates)
    if plan.backfill:
        ledger.batch_update(strip_extra([u for _, s, _ in plan.backfill for u in s]),
                            value_input_option="RAW")
        # Re-read so the block's other formulas (difference rows) use the month-end value.
        formulas = ledger.get(span, value_render_option="FORMULA")
        values = ledger.get(span, value_render_option="UNFORMATTED_VALUE")
        for block, _, _ in plan.backfill:
            rest, errors = freeze_updates(formulas, values, first_col, (block.first, block.last))
            updates += rest
            plan.problems += [f"{block.label}：{e} 是錯誤值，保留公式" for e in errors]
            print(f"  固定：{block.label}（月底淨值）")
    if updates:
        ledger.batch_update(strip_extra(updates), value_input_option="RAW")
        written = len(updates)
    print(f"  已寫入 {written} 格")
    return plan.problems, written


def run_missing_alert(spreadsheet, month, now, dry_run):
    """前 2 個工作天過後：上個月還沒固定的區塊（多半是基金月底淨值沒取得）記入 Google 日曆，一個月一次。"""
    import calendar_note
    print(f"== {month:%Y/%m} 月底固定檢查（已過本月第 {NAV_BUSINESS_DAYS} 個工作天，不再讀淨值） ==")
    plan = run_freeze(spreadsheet, month, now, True, False, plan_only=True)
    missing = [label for label, _ in plan.waiting] + [block.label for block, _, _ in plan.backfill]
    if not missing:
        print("  都已固定")
        return []
    detail = "\n".join(f"・{label}：{reason}" for label, reason in plan.waiting)
    detail += "".join(f"\n・{block.label}：可回填月底淨值（{note}）" for block, _, note in plan.backfill)
    print(f"  還沒固定：{'、'.join(missing)}")
    if dry_run:
        return []
    result = calendar_note.add_once(
        key=f"month-end-nav-{month:%Y-%m}", day=now.date(),
        summary=f"{month:%Y/%m} 月底淨值未取得｜{'、'.join(missing)}",
        description=(f"本月前 {NAV_BUSINESS_DAYS} 個工作天內沒有取得 {month:%Y/%m} 月底淨值，"
                     f"Jennyall {month:%Y/%m} 欄這些區塊還是公式，請手動固定：\n{detail}"))
    print(f"  日曆：{'已加入' if result == 'added' else '已記過' if result == 'exists' else 'WARN 寫入失敗 ' + result}")
    return []


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
    written = 0
    if updates and not dry_run:
        overview.batch_update(strip_extra(updates), value_input_option="USER_ENTERED")
        print(f"  已寫入 {len(updates)} 格")
        written = len(updates)
    detail_problems, detail_written = roll_detail_refs(spreadsheet, month, ledger_cols, dry_run)
    problems += detail_problems
    for problem in problems:
        print(f"WARN {problem}")
    return problems, written + detail_written


def show_month_end_prices(spreadsheet, month):
    """Print each 總覽 fund's month-end price from the history sources (read-only)."""
    print(f"== {month:%Y/%m} 月底淨值（只讀取） ==")
    overview_rows = spreadsheet.worksheet(OVERVIEW_SHEET).get(
        OVERVIEW_RANGE, value_render_option="UNFORMATTED_VALUE")
    history = PriceHistory(month, spreadsheet)
    problems, seen = [], set()
    labels = list(SOURCES) + ["基富通-台", "基富通-日", "基富通-人民幣", "渣打-南非", "台新-美金", "台新-南非"]
    for label in labels:
        source = SOURCES.get(label, Source(label))
        if not isinstance(source, Source):
            continue
        for fund in overview_section(overview_rows, source.section, source.include, source.exclude) or []:
            if fund.row in seen:
                continue
            seen.add(fund.row)
            found = history(source.kind, fund.name)
            point = month_end_price(found or [], month)
            sources = "；".join(history.notes.get(fund.name, [])) or "沒有對照代碼"
            if point:
                print(f"  F{fund.row} {fund.name}: {point[0]:%Y/%m/%d} {point[1]:g}（{sources}）")
            else:
                problems.append(f"F{fund.row} {fund.name}: 查不到 {month:%Y/%m} 月底淨值（{sources}）")
                print(f"WARN {problems[-1]}")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument("--mode", choices=("auto", "freeze", "roll", "prices"), default="auto",
                        help="auto 依日期決定；freeze／roll 立即執行；prices 只列出月底淨值")
    parser.add_argument("--month", help="月份 YYYY/M（預設：freeze 目前檢查中的月份或上個月，roll 本月，prices 已確定的最近月份：6 日起上個月，之前上上個月）")
    parser.add_argument("--force", action="store_true", help="freeze 時不檢查日期，全部用現值固定")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    now = datetime.now(TAIPEI)
    today = now.date()
    previous = add_months(today.replace(day=1), -1)
    if args.mode == "prices":
        # Default to a month whose month-end price is surely final (a price after it exists).
        settled = previous if today.day > LATE_AFTER_DAYS else add_months(previous, -1)
        month = parse_month(args.month) if args.month else settled
        show_month_end_prices(open_spreadsheet(args.credentials_file), month)
        return 0  # diagnostic only; the fund NAV log fills up as the NAV sync runs
    closed = tw_closed_days() if today.day <= FREEZE_GRACE_DAYS else set()
    freeze_month, roll_month, alert_month = auto_tasks(today, closed)
    if args.mode == "freeze":
        freeze_month = parse_month(args.month) if args.month else (freeze_month or alert_month or previous)
        roll_month = alert_month = None
    elif args.mode == "roll":
        roll_month = parse_month(args.month) if args.month else today.replace(day=1)
        freeze_month = alert_month = None
    if not freeze_month and not roll_month and not alert_month:
        print(f"{today:%Y/%m/%d}：不在月底檢查期間（{FREEZE_START_DAY} 日起到下月 {FREEZE_GRACE_DAYS} 日），略過")
        return 0

    spreadsheet = open_spreadsheet(args.credentials_file)
    problems, written = [], 0
    if roll_month:
        found, count = run_roll(spreadsheet, roll_month, args.dry_run)
        problems, written = problems + found, written + count
    if freeze_month:
        found, count = run_freeze(spreadsheet, freeze_month, now, args.dry_run, args.force)
        problems, written = problems + found, written + count
    if alert_month:
        run_missing_alert(spreadsheet, alert_month, now, args.dry_run)
    return exit_code(problems, written, now, args.mode, args.dry_run)


def exit_code(problems, written, now, mode, dry_run):
    """1 marks the run failed (GitHub emails). The schedule runs every 30 minutes,
    so in auto mode a problem fails the run only when this run wrote something or
    in REPORT_HOUR; otherwise a lasting problem would email every half hour."""
    if dry_run or not problems:
        return 0  # a preview only reports; WARN lines above list what a real run would flag
    if mode != "auto" or written or now.hour == REPORT_HOUR:
        return 1
    print(f"（問題只記在紀錄裡；每天 {REPORT_HOUR}:00 那次或有寫入時才標示失敗並寄信）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
