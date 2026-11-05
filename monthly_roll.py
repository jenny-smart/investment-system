"""Month-end / month-start upkeep of the 總帳 workbook.

轉值：Jennyall 該月的欄（例如 10 月 FZ、GA）把指定列的公式全部改成當下的數值，
這個月的數字就固定下來，不會再跟著之後的價格變。
  month-end  月底最後一天：第 4～36 列裡的股票（A 欄含 台股／美股／股票 的區塊）＋第 64～67 列
  fund       每月 1～7 日：第 4～36 列裡其餘的基金區塊，等總覽 G 欄每檔基金的淨值日期
             都到了上個月最後一個工作天（通常隔一個工作天才公布）才轉值；
             7 日 23:00 以後仍沒到齊就用當下的值轉值並讓執行失敗提醒
roll    月初：「總覽」裡參照 Jennyall、YYYY細帳 月份欄的公式，從上個月的欄改到本月的欄
        （同一月份區塊內相同位置；12 月→1 月時 2026細帳 換成 2027細帳）。

排程由 tool-system 主控表「排程設定」派送（job＝month-end／fund／roll，帶 scheduled_slot）；
也可用 auto 讓程式依日期自己判斷。月份欄依各分頁的日期列找，列號可用環境變數調整。
每一格「原本 → 改成」都會先印出；--dry-run 只印不寫。

  python monthly_roll.py month-end --dry-run          # 1～15 日執行＝上個月，16 日以後＝本月
  python monthly_roll.py fund --month 2026/10 --dry-run
  python monthly_roll.py freeze --month 2026/10 --only stock,fund,extra --dry-run
  python monthly_roll.py roll --month 2026/11 --dry-run
"""
from __future__ import annotations

import argparse
import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, time
import json
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

from asset_summary import DEFAULT_SPREADSHEET_ID, col_index, col_letters, date_row, spreadsheet_key

TAIPEI = ZoneInfo("Asia/Taipei")
LEDGER_SHEET = "Jennyall"
OVERVIEW_SHEET = "總覽"
DETAIL_SHEET = re.compile(r"^(\d{4})細帳$")
# auto：月底最後一天這個時間之後才做月底轉值（排程 23:50 觸發）。
FREEZE_AFTER = time(23, 45)
# auto：月初 1～7 日都會檢查換欄與基金轉值，錯過的排程也會補上。
ROLL_DAYS = range(1, 8)
# 7 日這個時間以後基金淨值還沒到齊，就用當下的值轉值並讓執行失敗提醒。
FUND_DEADLINE_DAY, FUND_DEADLINE_TIME = 7, time(23, 0)
NAV_NAME_COL, NAV_DATE_COL = 5, 6  # 總覽 F（基金名稱）、G（淨值日期）


def parse_rows(text):
    """'4:36' or '4-36' or '64:67,70' -> [4, 5, ..., 36]."""
    rows = []
    for part in re.split(r"[,，]", text):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*[:\-~]\s*(\d+)", part)
        rows.extend(range(int(m[1]), int(m[2]) + 1) if m else [int(part)])
    return rows


# Jennyall 投資區（股票＋基金）與月底直接轉值的列，2026-11 與 Jenny 確認。
INVEST_ROWS = parse_rows(os.environ.get("MONTHLY_ROLL_INVEST_ROWS", "4:36"))
MONTH_END_ROWS = parse_rows(os.environ.get("MONTHLY_ROLL_MONTH_END_ROWS", "64:67"))
# 投資區 A 欄含這些字的區塊算股票（月底轉值），其餘區塊算基金（等月底淨值）。
STOCK_LABELS = tuple(filter(None, os.environ.get("MONTHLY_ROLL_STOCK_LABELS", "台股,美股,股票").split(",")))
KIND_NAMES = {"stock": "股票", "fund": "基金", "extra": "月底列"}

# Sheet!A1, 'Sheet name'!$A$1:B2, Sheet!A:A, Sheet!A1:A
SHEET_PART = r"(?P<sheet>'(?:[^']|'')+'|[^\s'!(),;:+\-*/&=<>^\"{}]+)"
CELL_PART = r"\$?[A-Z]{1,3}(?:\$?\d+)?"
REF = re.compile(SHEET_PART + r"!(?P<a>" + CELL_PART + r")(?::(?P<b>" + CELL_PART + r"))?")
CELL_SPLIT = re.compile(r"(\$?)([A-Z]{1,3})(.*)")


# ── month headers ──────────────────────────────────────────────────────────────

def month_key(year, month):
    return year * 12 + (month - 1)


def key_label(key):
    return f"{key // 12}/{key % 12 + 1:02d}"


def parse_header_month(value, default_year=None):
    """Header cell -> month key, or None. Accepts 2026/11/1, 2026-11, 2026/11, 11月, serials."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 30000 < value < 80000:  # Sheets date serial
            d = date(1899, 12, 30).toordinal() + int(value)
            d = date.fromordinal(d)
            return month_key(d.year, d.month)
        return None
    text = str(value or "").strip()
    if not text:
        return None
    m = re.fullmatch(r"(\d{4})\s*[/\-.年]\s*(\d{1,2})(?:\s*[/\-.月]\s*(\d{1,2})?\s*日?)?\s*月?", text)
    if m and 1 <= int(m[2]) <= 12:
        return month_key(int(m[1]), int(m[2]))
    m = re.fullmatch(r"(\d{1,2})\s*月(?:份)?", text)
    if m and default_year and 1 <= int(m[1]) <= 12:
        return month_key(default_year, int(m[1]))
    return None


@dataclass
class MonthLayout:
    """Where each month's block sits on one sheet.

    anchors: month key -> the column holding that month's date.
    side: 'right' if the date sits on the last column of its block (Jennyall: detail,
    subtotal-with-date), 'left' if on the first column (a merged header).
    """
    anchors: dict
    side: str
    header_row: int = 0
    _sorted: list = field(default_factory=list, repr=False)

    def __post_init__(self):
        self._sorted = sorted((col, key) for key, col in self.anchors.items())

    def month_of(self, col):
        cols = [c for c, _ in self._sorted]
        if not cols:
            return None
        if self.side == "right":
            for i, (anchor, key) in enumerate(self._sorted):
                if col <= anchor:
                    low = cols[i - 1] if i else anchor - (cols[1] - cols[0] if len(cols) > 1 else 1)
                    return key if col > low else None
            return None
        for i in range(len(self._sorted) - 1, -1, -1):
            anchor, key = self._sorted[i]
            if col >= anchor:
                high = cols[i + 1] if i + 1 < len(cols) else anchor + (cols[-1] - cols[-2] if len(cols) > 1 else 1)
                return key if col < high else None
        return None

    def offset(self, col):
        key = self.month_of(col)
        return None if key is None else col - self.anchors[key]


def find_layout(values, side, default_year=None, max_rows=10, row=None):
    """Pick the header row with the most distinct months among the first rows
    (or use `row`, 1-based, when the sheet's date row is known)."""
    best = None
    candidates = [(row - 1, values[row - 1])] if row else list(enumerate(values[:max_rows]))
    for r, line in candidates:
        anchors = {}
        for c, v in enumerate(line):
            key = parse_header_month(v, default_year)
            if key is not None and key not in anchors:
                anchors[key] = c
        if len(anchors) >= 2 and (best is None or len(anchors) > len(best[1])):
            best = (r, anchors)
    if not best:
        return None
    return MonthLayout(anchors=best[1], side=side, header_row=best[0] + 1)


# ── formula references ─────────────────────────────────────────────────────────

def unquote(name):
    return name[1:-1].replace("''", "'") if name.startswith("'") else name


def quote(name, was_quoted):
    if was_quoted or not re.fullmatch(r"[A-Za-z_一-鿿][\w一-鿿]*", name):
        return "'" + name.replace("'", "''") + "'"
    return name


def outside_strings(formula):
    """Yield (start, end) spans of the formula that are not inside "string literals"."""
    start, inside = 0, False
    for i, ch in enumerate(formula):
        if ch == '"':
            if not inside:
                yield start, i
            else:
                start = i + 1
            inside = not inside
    if not inside:
        yield start, len(formula)


def find_refs(formula):
    """[(match, sheet name)] for cross-sheet references outside string literals."""
    found = []
    for lo, hi in outside_strings(formula):
        for m in REF.finditer(formula, lo, hi):
            found.append((m, unquote(m["sheet"])))
    return found


def ref_columns(m):
    cols = []
    for part in (m["a"], m["b"]):
        if part:
            cols.append(col_index(CELL_SPLIT.fullmatch(part)[2]))
    return cols


def shift_cell(part, new_col):
    dollar, _, rest = CELL_SPLIT.fullmatch(part).groups()
    return f"{dollar}{col_letters(new_col)}{rest}"


# ── freeze (month end) ─────────────────────────────────────────────────────────

def row_kind(label, stock_labels=STOCK_LABELS):
    """'stock' for 台股／美股／股票 blocks, otherwise 'fund'."""
    text = str(label or "")
    return "stock" if any(word in text for word in stock_labels) else "fund"


def ledger_layout(values):
    """Jennyall: dates sit in row 1 on each month's subtotal (right) column."""
    try:
        row = date_row(values)
    except RuntimeError:
        return None
    return find_layout(values, "right", row=row)


def plan_freeze(values, formulas, layout, month, kinds=("stock", "fund", "extra"),
                invest_rows=None, month_end_rows=None, sheet=LEDGER_SHEET):
    """Formulas in `month`'s columns of the chosen rows, to be replaced by their values.

    invest_rows (default 4–36) split into stock / fund blocks by the A label (a blank A
    takes the block above); month_end_rows (default 64–67) are 'extra'.
    Returns (changes, problems); a change is {"cell", "label", "kind", "formula", "value"}.
    """
    invest_rows = INVEST_ROWS if invest_rows is None else invest_rows
    month_end_rows = MONTH_END_ROWS if month_end_rows is None else month_end_rows
    if month not in layout.anchors:
        raise RuntimeError(f"{sheet} 找不到 {key_label(month)} 的月份欄")
    width = max((len(line) for line in formulas), default=0)
    cols = [c for c in range(width) if layout.month_of(c) == month]

    def cell(grid, r, c):
        return grid[r - 1][c] if r - 1 < len(grid) and c < len(grid[r - 1]) else ""

    plan = []  # (row, label, kind)
    label, kind = "", "fund"
    for r in invest_rows:
        a = str(cell(values, r, 0)).strip()
        if a:
            label, kind = a, row_kind(a)
        plan.append((r, label, kind))
    plan += [(r, str(cell(values, r, 0)).strip(), "extra") for r in month_end_rows]

    changes, problems = [], []
    for r, label, kind in plan:
        if kind not in kinds:
            continue
        for c in cols:
            f = str(cell(formulas, r, c))
            if not f.startswith("="):
                continue
            v = cell(values, r, c)
            addr = f"{col_letters(c)}{r}"
            if isinstance(v, str) and v.startswith("#"):
                problems.append(f"{addr} {f} 目前是錯誤值 {v}，保留公式未轉值")
                continue
            changes.append({"cell": addr, "label": label, "kind": kind, "formula": f, "value": v})
    return changes, problems


def last_business_day(month):
    """Last Monday–Friday of the month (holidays are covered by fund_navs_ready)."""
    year, mon = month // 12, month % 12 + 1
    d = date(year, mon, calendar.monthrange(year, mon)[1])
    while d.weekday() >= 5:
        d = date.fromordinal(d.toordinal() - 1)
    return d


def parse_nav_date(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 30000 < value < 80000:
        return date.fromordinal(date(1899, 12, 30).toordinal() + int(value))
    m = re.fullmatch(r"\s*(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})\s*", str(value or ""))
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    return None


def fund_navs_ready(overview_values, month):
    """Whether every synced fund on 總覽 (F name, G NAV date) has its month-end NAV.

    Ready = NAV date on or after the month's last business day; a date already in the
    next month also counts (that fund was closed on the last business day).
    Returns (ready, pending lines, number of funds checked).
    """
    from sync_fund_nav import IGNORED_FUNDS, match_fund, normalize_name
    target = last_business_day(month)
    pending, checked = [], 0
    for r, line in enumerate(overview_values, 1):
        name = line[NAV_NAME_COL] if len(line) > NAV_NAME_COL else ""
        if any(k in normalize_name(name) for k in IGNORED_FUNDS) or not match_fund(name):
            continue
        checked += 1
        raw = line[NAV_DATE_COL] if len(line) > NAV_DATE_COL else ""
        d = parse_nav_date(raw)
        if not d or d < target:
            pending.append(f"F{r} {name}：淨值日期 {raw or '空白'}，還沒到 {target:%Y/%m/%d}")
    return not pending and checked > 0, pending, checked


# ── roll (month start) ─────────────────────────────────────────────────────────

def family_of(name, ledger=LEDGER_SHEET):
    if name == ledger:
        return "ledger"
    return "detail" if DETAIL_SHEET.match(name) else None


def plan_roll(overview_formulas, layouts, target, shift_all=False, ledger=LEDGER_SHEET):
    """Move 總覽 references to Jennyall / YYYY細帳 month columns up to month `target`.

    layouts: sheet name -> MonthLayout (missing / None = sheet not month-based).
    Per family (Jennyall, 細帳) only references in the latest referenced month move
    (prev month -> target); --shift-all moves every month reference by the same gap.
    Returns (changes, notes, problems); a change is {"cell", "old", "new"}.
    """
    # Collect month-specific references first.
    hits = []  # (row, col, match, sheet, family, month key, offset per column)
    for r, line in enumerate(overview_formulas, 1):
        for c, f in enumerate(line):
            f = str(f)
            if not f.startswith("="):
                continue
            for m, name in find_refs(f):
                fam = family_of(name, ledger)
                layout = layouts.get(name) if fam else None
                if not layout:
                    continue
                cols = ref_columns(m)
                keys = {layout.month_of(x) for x in cols}
                if None in keys:
                    continue
                if len(keys) > 1:
                    hits.append((r, c, m, name, fam, None, None))
                    continue
                key = keys.pop()
                hits.append((r, c, m, name, fam, key, [layout.offset(x) for x in cols]))

    notes, problems, moves = [], [], {}
    for fam in ("ledger", "detail"):
        fam_hits = [h for h in hits if h[4] == fam]
        for h in fam_hits:
            if h[5] is None:
                problems.append(f"{col_letters(h[1])}{h[0]} 的 {h[2][0]} 跨了兩個月份，未處理")
        dated = [h for h in fam_hits if h[5] is not None]
        if not dated:
            continue
        latest = max(h[5] for h in dated)
        label = ledger if fam == "ledger" else "細帳"
        if latest == target:
            notes.append(f"{label}：已是 {key_label(target)}，不用換欄")
            continue
        if latest > target:
            problems.append(f"{label}：總覽已參照 {key_label(latest)}，比目標 {key_label(target)} 還新，未處理")
            continue
        gap = target - latest
        older = sorted({h[5] for h in dated if h[5] != latest})
        if older and not shift_all:
            notes.append(f"{label}：另有參照 {', '.join(key_label(k) for k in older)} 的公式維持不動"
                         "（若也該一起往後移，加 --shift-all）")
        for h in dated:
            if h[5] != latest and not shift_all:
                continue
            moves.setdefault((h[0], h[1]), []).append((h, h[5] + gap))

    changes = []
    for (r, c), items in sorted(moves.items()):
        f = str(overview_formulas[r - 1][c])
        new, ok = f, True
        for h, new_key in sorted(items, key=lambda x: -x[0][2].start()):  # right to left keeps spans valid
            m, name, offsets = h[2], h[3], h[6]
            new_name = name
            if h[4] == "detail":
                new_name = f"{new_key // 12}細帳"
            layout = layouts.get(new_name)
            if not layout or new_key not in layout.anchors:
                problems.append(f"{col_letters(c)}{r}：{new_name} 找不到 {key_label(new_key)} 的月份欄")
                ok = False
                break
            anchor = layout.anchors[new_key]
            parts = [shift_cell(m["a"], anchor + offsets[0])]
            if m["b"]:
                parts.append(shift_cell(m["b"], anchor + offsets[1]))
            sheet_txt = m["sheet"] if new_name == name else quote(new_name, m["sheet"].startswith("'"))
            new = new[:m.start()] + sheet_txt + "!" + ":".join(parts) + new[m.end():]
        if ok and new != f:
            changes.append({"cell": f"{col_letters(c)}{r}", "old": f, "new": new})
    return changes, notes, problems


# ── schedule ───────────────────────────────────────────────────────────────────

def auto_jobs(now):
    """Which jobs an `auto` run does at `now` (Asia/Taipei): [(job, month key)].

    month-end: month end night (and the 1st as a catch-up).
    fund:      1st–7th, only once the month-end NAVs are in (forced on the 7th, late).
    roll:      1st–7th; a no-op once 總覽 already points at this month.
    """
    today = now.date()
    this = month_key(today.year, today.month)
    jobs = []
    last_day = calendar.monthrange(today.year, today.month)[1]
    if today.day == last_day and now.time() >= FREEZE_AFTER:
        jobs.append(("month-end", this))
    if today.day == 1:
        jobs.append(("month-end", this - 1))  # 補做：月底那次沒跑到
    if today.day in ROLL_DAYS:
        jobs.append(("fund", this - 1))
        jobs.append(("roll", this))
    return jobs


def default_month(job, now):
    """roll → this month; freezes → last month during the 1st–15th, else this month."""
    this = month_key(now.year, now.month)
    if job == "roll":
        return this
    return this - 1 if now.day <= 15 else this


def fund_deadline(now):
    return now.day >= FUND_DEADLINE_DAY and now.day <= 15 and now.time() >= FUND_DEADLINE_TIME


def slot_time(slot):
    """scheduled_slot from the router ('20261031T2350-key') -> Taipei datetime, or None."""
    m = re.match(r"(\d{8}T\d{4})", slot or "")
    return datetime.strptime(m[1], "%Y%m%dT%H%M").replace(tzinfo=TAIPEI) if m else None


# ── Google Sheets I/O ──────────────────────────────────────────────────────────

def open_workbook(key, credentials_file=None):
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    if credentials_file:
        credentials = Credentials.from_service_account_file(str(credentials_file), scopes=scopes)
    else:
        raw = os.environ.get("INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if not raw:
            raise RuntimeError("Missing INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON")
        credentials = Credentials.from_service_account_info(json.loads(raw), scopes=scopes)
    return gspread.authorize(credentials).open_by_key(key)


def read_values(ws):
    return ws.get_values(value_render_option="UNFORMATTED_VALUE", date_time_render_option="FORMATTED_STRING")


def run_freeze(book, month, dry_run, kinds=("stock", "fund", "extra"), wait_for_nav=False, force=False):
    """wait_for_nav: only freeze fund rows once fund_navs_ready (unless force)."""
    ws = book.worksheet(LEDGER_SHEET)
    values, formulas = read_values(ws), ws.get_values(value_render_option="FORMULA")
    layout = ledger_layout(values)
    if not layout:
        raise RuntimeError(f"{LEDGER_SHEET} 找不到月份日期列")
    changes, problems = plan_freeze(values, formulas, layout, month, kinds)
    title = "、".join(KIND_NAMES[k] for k in kinds)
    print(f"== 轉值 {LEDGER_SHEET} {key_label(month)}（{title}）：{len(changes)} 格")
    if changes and wait_for_nav and "fund" in kinds:
        ready, pending, checked = fund_navs_ready(read_values(book.worksheet(OVERVIEW_SHEET)), month)
        target = last_business_day(month)
        if ready:
            print(f"  總覽 {checked} 檔基金淨值都已更新到 {target:%Y/%m/%d} 以後")
        elif force:
            problems.append(f"已過 {FUND_DEADLINE_DAY} 日 {FUND_DEADLINE_TIME:%H:%M}，仍有基金淨值沒更新到月底，"
                            "直接用目前的值轉值")
            pending_lines = pending or ["總覽 F 欄找不到要同步的基金"]
            problems.extend(pending_lines)
        else:
            print(f"  等基金淨值更新到 {target:%Y/%m/%d}，這次先不轉值：")
            for line in pending or ["總覽 F 欄找不到要同步的基金"]:
                print(f"    {line}")
            return True
    for ch in changes:
        print(f"  {ch['cell']} [{KIND_NAMES[ch['kind']]} {ch['label']}]: {ch['formula']}  ->  {ch['value']}")
    for p in problems:
        print(f"  WARN {p}")
    if changes and not dry_run:
        ws.batch_update([{"range": ch["cell"], "values": [[ch["value"]]]} for ch in changes],
                        value_input_option="RAW")
        print(f"  已寫入 {len(changes)} 格")
    elif not changes:
        print("  沒有公式要轉（可能已轉值）")
    return not problems


def run_roll(book, month, dry_run, shift_all=False):
    ov = book.worksheet(OVERVIEW_SHEET)
    formulas = ov.get_values(value_render_option="FORMULA")
    names = {r_name for line in formulas for f in line if str(f).startswith("=")
             for _, r_name in find_refs(str(f)) if family_of(r_name)}
    # The target year's 細帳 may not be referenced yet (12月 -> 1月).
    names.add(f"{month // 12}細帳")
    titles = {ws.title for ws in book.worksheets()}
    layouts = {}
    for name in sorted(names & titles):
        rows = book.worksheet(name).get("1:10", value_render_option="UNFORMATTED_VALUE",
                                        date_time_render_option="FORMATTED_STRING")
        m = DETAIL_SHEET.match(name)
        layouts[name] = (ledger_layout(rows) if name == LEDGER_SHEET
                         else find_layout(rows, "left", default_year=int(m[1]) if m else None))
        lay = layouts[name]
        print(f"  {name}: " + ("沒有月份欄" if not lay else
              f"第 {lay.header_row} 列月份 {key_label(min(lay.anchors))}～{key_label(max(lay.anchors))}"))
    changes, notes, problems = plan_roll(formulas, layouts, month, shift_all)
    print(f"== 月初換欄 {OVERVIEW_SHEET} → {key_label(month)}：{len(changes)} 格")
    for ch in changes:
        print(f"  {ch['cell']}: {ch['old']}  ->  {ch['new']}")
    for n in notes:
        print(f"  {n}")
    for p in problems:
        print(f"  WARN {p}")
    if not changes and not notes:
        problems.append("總覽沒有找到參照 Jennyall / 細帳 月份欄的公式")
        print(f"  WARN {problems[-1]}")
    if changes and not dry_run:
        ov.batch_update([{"range": ch["cell"], "values": [[ch["new"]]]} for ch in changes],
                        value_input_option="USER_ENTERED")
        print(f"  已寫入 {len(changes)} 格")
    return not problems


def parse_month_arg(text):
    m = re.fullmatch(r"(\d{4})[/-](\d{1,2})", text.strip())
    if not m or not 1 <= int(m[2]) <= 12:
        raise argparse.ArgumentTypeError(f"月份格式應為 YYYY/M：{text}")
    return month_key(int(m[1]), int(m[2]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("job", choices=["auto", "month-end", "fund", "freeze", "roll"])
    parser.add_argument("--month", type=parse_month_arg,
                        help="轉值：要轉值的月份（預設 1～15 日＝上個月，之後＝本月）；roll：要換到的月份（預設本月）")
    parser.add_argument("--only", default="stock,fund,extra",
                        help="freeze 要轉哪幾種列：stock（股票）、fund（基金）、extra（64～67 列），逗號分隔")
    parser.add_argument("--wait-nav", action="store_true",
                        help="freeze 基金列要等總覽基金淨值都更新到月底才轉值")
    parser.add_argument("--shift-all", action="store_true", help="roll 時連較舊月份的參照也一起往後移")
    parser.add_argument("--slot", default="", help="排程設定派送時段（scheduled_slot），用它當執行時間")
    parser.add_argument("--dry-run", action="store_true", help="只列出會改的格子，不寫入")
    parser.add_argument("--spreadsheet", default=os.environ.get("ASSET_SPREADSHEET", DEFAULT_SPREADSHEET_ID))
    parser.add_argument("--credentials-file", type=Path)
    args = parser.parse_args(argv)
    only = tuple(k for k in ("stock", "fund", "extra") if k in args.only.split(","))
    if not only:
        parser.error("--only 要是 stock、fund、extra 其中幾個")

    now = slot_time(args.slot) or datetime.now(TAIPEI)
    if args.job == "auto":
        jobs = auto_jobs(now)
        if not jobs:
            print(f"{now:%Y/%m/%d %H:%M} 不是月底轉值或月初換欄的時間，略過")
            return 0
    else:
        jobs = [(args.job, args.month if args.month is not None else default_month(args.job, now))]
    print(f"執行時間 {now:%Y/%m/%d %H:%M}（台北）")

    book = open_workbook(spreadsheet_key(args.spreadsheet), args.credentials_file)
    ok = True
    for job, month in jobs:  # freezes always come before roll
        try:
            if job == "month-end":
                ok &= run_freeze(book, month, args.dry_run, ("stock", "extra"))
            elif job == "fund":
                ok &= run_freeze(book, month, args.dry_run, ("fund",), wait_for_nav=True,
                                 force=fund_deadline(now))
            elif job == "freeze":
                ok &= run_freeze(book, month, args.dry_run, only, wait_for_nav=args.wait_nav)
            else:
                ok &= run_roll(book, month, args.dry_run, args.shift_all)
        except Exception as exc:
            print(f"FAILED {job} {key_label(month)}: {exc}")
            ok = False
    if args.dry_run:
        print("Dry run：沒有寫入任何格子")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
