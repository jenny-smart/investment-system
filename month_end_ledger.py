"""Month-end freeze and month-start roll for the 總帳 (2025Jenny-總帳) spreadsheet.

freeze（每月 30 日起，2 月為月底那天；持續檢查到下個月 10 日）
    Jennyall 第 2–38 列每個 A 欄基金/股票區塊，確認「總覽」裡對應的淨值／股價日期
    已是該月最後一個交易日，就把該區塊當月兩欄（例：10 月 FZ、GA）的公式換成值。
    同時把當月 64:67 列（叔叔）兩欄換成值。已經是值的格子不動，可以重複執行。

    月底最後一天起，各區塊的匯率格先固定成月底匯率。
    過了月底仍未固定（遇假日沒有最後一個平日的淨值、或排程沒跑到）時，向鉅亨／MoneyDJ
    （基金）或 Yahoo（美股）查月底那天的淨值，以「現在市值 × 月底淨值 ÷ 現在淨值」
    換算月底市值後固定，不用手動處理。

roll（每月 1 日）
    總覽 B2:B18 的 Jennyall!<欄> 換成當月小計欄（例：11 月 GA → GC），
    總覽 B40:B51 的 '每月收入'!<欄> 換成當月欄（例：11 月 AH → AI）。

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
OVERVIEW_RANGE = "F1:K200"    # name, date, NAV/price, ..., K = 台幣市值
NAV_COL, VALUE_COL = 2, 5     # offsets inside OVERVIEW_RANGE

FREEZE_START_DAY = 30         # or the last day of a shorter month
FREEZE_GRACE_DAYS = 10        # keep checking the previous month until this day
LATE_AFTER_DAYS = 5           # a block still not frozen after this day is reported
TW_CLOSE = time(14, 40)       # TWSE closes 13:30; the price sync's last run is 14:30
TW_OPEN = time(8, 30)         # the price sync starts overwriting prices here

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


def cell_date(value):
    """Sheet date: serial number (unformatted read) or 'YYYY/MM/DD' text."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return date(1899, 12, 30) + timedelta(days=int(value)) if 30000 < value < 80000 else None
    text = str(value or "").strip()
    match = re.match(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
    return date(int(match[1]), int(match[2]), int(match[3])) if match else None


def to_number(value):
    if isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


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


def backfill_updates(block, source, funds, values, first_col, month, history):
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
    rates_due = now.date() >= month_end(month)
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
                                                 history or (lambda *_: None))
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


# ---------------------------------------------------------------- price history

def parse_cnyes_history(payload):
    from sync_fund_nav import parse_date as nav_date, valid_nav
    points = []
    for item in ((payload or {}).get("data") or {}).get("items") or []:
        nav = next((valid_nav(item.get(k)) for k in ("nav", "NAV", "navPrice", "net", "unitNav")
                    if valid_nav(item.get(k))), None)
        day = next((nav_date(item.get(k)) for k in ("tradeDate", "navDate", "date", "priceDate")
                    if nav_date(item.get(k))), None)
        if nav and day:
            points.append((datetime.strptime(day, "%Y/%m/%d").date(), nav))
    return points


def parse_moneydj_history(html):
    from sync_fund_nav import valid_nav
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text).replace(",", "").replace("&nbsp;", " ")
    points = []
    for y, m, d, nav in re.findall(r"(20\d{2})/(\d{1,2})/(\d{1,2})\s+([0-9]+(?:\.[0-9]+)?)", text):
        if valid_nav(nav):
            points.append((date(int(y), int(m), int(d)), float(nav)))
    return points


class PriceHistory:
    """history(kind, name) for funds (鉅亨, then MoneyDJ) and US stocks (Yahoo)."""

    def __init__(self, month):
        self.month = month
        self.cache = {}
        self.notes = {}   # name -> ["鉅亨 5 筆 10/24–10/30", ...] for diagnostics
        self.session = None

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
        import requests
        from sync_fund_nav import HEADERS, match_fund
        import urllib.parse
        rule = match_fund(name)
        if not rule:
            return None
        self.session = self.session or requests.Session()
        end = month_end(self.month)
        points = []
        headers = {**HEADERS, "Referer": "https://fund.cnyes.com/", "Origin": "https://fund.cnyes.com"}
        encoded = urllib.parse.quote(rule["cnyes_id"], safe="")
        for page in range(1, 4):  # newest first; stop once month end is covered
            response = self.session.get(
                f"https://fund.api.cnyes.com/fund/api/v1/funds/{encoded}/nav?format=table&page={page}",
                headers=headers, timeout=15)
            if response.status_code != 200:
                self.notes.setdefault(name, []).append(f"鉅亨第 {page} 頁 HTTP {response.status_code}")
                break
            found = parse_cnyes_history(response.json())
            points += found
            if not found or min(d for d, _ in found) <= end:
                break
        self.note(name, "鉅亨", points)
        if month_end_price(points, self.month):
            return points
        history_page = rule["pattern"].replace("0100", "0110")  # yp010000 -> yp011000 (淨值走勢)
        response = self.session.get(
            f"https://www.moneydj.com/funddj/yp/{history_page}.djhtm?a={rule['code']}",
            headers={**HEADERS, "Referer": "https://www.moneydj.com/"}, timeout=15)
        found = []
        if response.status_code == 200:
            for encoding in ("big5", "cp950", "utf-8"):
                try:
                    found = parse_moneydj_history(response.content.decode(encoding))
                    break
                except UnicodeDecodeError:
                    continue
        self.note(name, f"MoneyDJ(HTTP {response.status_code})", found)
        points += found
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
        OVERVIEW_RANGE, value_render_option="UNFORMATTED_VALUE")
    plan = plan_freeze(column_a, formulas, values, first_col, overview_rows, month, now,
                       tw_closed_days(), force, PriceHistory(month))
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
        return plan.problems
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
        overview.batch_update(strip_extra(updates), value_input_option="USER_ENTERED")
        print(f"  已寫入 {len(updates)} 格")
    return problems


def show_month_end_prices(spreadsheet, month):
    """Print each 總覽 fund's month-end price from the history sources (read-only)."""
    print(f"== {month:%Y/%m} 月底淨值（只讀取） ==")
    overview_rows = spreadsheet.worksheet(OVERVIEW_SHEET).get(
        OVERVIEW_RANGE, value_render_option="UNFORMATTED_VALUE")
    history = PriceHistory(month)
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
        return 1 if show_month_end_prices(open_spreadsheet(args.credentials_file), month) else 0
    freeze_month, roll_month = auto_tasks(today)
    if args.mode == "freeze":
        freeze_month = parse_month(args.month) if args.month else (freeze_month or previous)
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
    if args.dry_run:
        return 0  # a preview only reports; WARN lines above list what a real run would flag
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
