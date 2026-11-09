"""把 App 已確認入帳的基金配息，同步到股票總帳「配息月份」分頁的勾選。

App 配息記錄頁按「💾 套用確認狀態」只寫進 Supabase；這支由 fund-nav 排程（每 10 分鐘）一起跑：
讀 fund_dividends、dividend_log 裡 is_paid 的記錄，依發放日期的月份、基金對到「配息月份」的格子，
列＝配息月份（發放日的前一個月：11 月發放的勾 2026/10）。
從 SYNC_FROM（2026/10）起到「上個月」：有已確認記錄就勾 TRUE，取消確認就改回 FALSE；
更早的月份不動，本月和之後的月份也不動（本月領的是上個月的配息，本月的格子永遠不會由排程勾）。
沒有發放日的記錄：用同一檔基金過去「除息日→發放日」的天數推算發放日；推不出來就不勾、那一欄不動並提醒。

分頁格式：第 1 列平台（基富通-台、渣打-美金…）、第 2 列基金名稱、第 3 列配息日，A 欄 YYYY/MM。
基金對欄：幣別相同、級別（A／U／Y）相同的欄裡，名稱最像的那一欄（東方匯理＝鋒裕匯理），平台相同加分；
對不到就略過並提醒。

  python sync_dividend_months.py --dry-run
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import difflib
import json
import os
import re
import sys
import unicodedata
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
SPREADSHEET_ID = "17HPytZKOPR_9Od_wor-xEx9kpccJlPS2v6B0Dz6MRYc"
SHEET_GID = 2033264385  # 配息月份
SYNC_FROM = (2026, 10)  # 9 月以前是手動勾的，資料庫不一定每格都有記錄，不動
LABEL_ROW, NAME_ROW, FIRST_MONTH_ROW = 1, 2, 4
SECTION_CURRENCY = {"台": "TWD", "人民幣": "CNY", "日": "JPY", "美金": "USD", "南非": "ZAR"}
PLATFORM_PREFIX = {"基富通": "基富通", "渣打基金": "渣打", "渣打": "渣打", "台新基金": "台新", "台新": "台新"}
NAME_ALIASES = (("東方匯理", "鋒裕匯理"), ("證劵", "證券"))
MIN_SCORE = 0.35


def norm_name(name):
    text = unicodedata.normalize("NFKC", str(name or "")).lower()
    for old, new in NAME_ALIASES:
        text = text.replace(old, new)
    return re.sub(r"[\s()（）\-—_]", "", text)


def share_class(name):
    """債券 A／U／Y 等級別字母（'...債券u美元' → 'u'）；沒有就 ''。"""
    m = re.search(r"債券(?:基金)?([a-z])(?![a-z])", norm_name(name))
    return m.group(1) if m else ""


def section_of(label):
    """'渣打-美金' → ('渣打', 'USD')；認不得回傳 None。"""
    platform, _, cur = str(label or "").strip().partition("-")
    currency = SECTION_CURRENCY.get(cur.strip())
    return (platform.strip(), currency) if platform and currency else None


def sheet_columns(grid):
    """[(0-based col, platform prefix, currency, fund name)] from rows 1–2."""
    labels = grid[LABEL_ROW - 1] if len(grid) >= LABEL_ROW else []
    names = grid[NAME_ROW - 1] if len(grid) >= NAME_ROW else []
    cols = []
    for c, label in enumerate(labels):
        sec = section_of(label)
        if sec:
            cols.append((c, sec[0], sec[1], names[c] if c < len(names) else ""))
    return cols


def match_column(columns, platform, currency, fund_name):
    """Best column for a record, or None. Same currency only; same platform +0.3."""
    want = norm_name(fund_name)
    prefix = PLATFORM_PREFIX.get(str(platform or "").strip(), str(platform or "").strip()[:2])
    scored = []
    want_class = share_class(fund_name)
    for col, plat, cur, name in columns:
        if cur != str(currency or "").upper():
            continue
        have_class = share_class(name)
        if want_class and have_class and want_class != have_class:
            continue  # 東方匯理 A美元 vs U美元：級別不同就不是同一檔
        score = difflib.SequenceMatcher(None, want, norm_name(name)).ratio()
        scored.append((score + (0.3 if plat == prefix else 0), score, col))
    if not scored:
        return None
    scored.sort(reverse=True)
    best_total, best_score, col = scored[0]
    if best_score < MIN_SCORE or (len(scored) > 1 and best_total - scored[1][0] < 0.05):
        return None
    return col


def month_rows(grid):
    """{(year, month): 1-based row} from column A (YYYY/MM)."""
    rows = {}
    for r in range(FIRST_MONTH_ROW, len(grid) + 1):
        line = grid[r - 1]
        month = cell_month(line[0] if line else "")
        if month:
            rows[month] = r
    return rows


def cell_month(value):
    """A 欄的月份：文字 2026/09、2026-09-01，或日期格的序號（UNFORMATTED_VALUE 讀出來是 46266 這種數字）。"""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 20000 < value < 80000:
        d = date(1899, 12, 30) + timedelta(days=int(value))
        return (d.year, d.month)
    m = re.match(r"\s*(\d{4})\s*[/\-.]\s*(\d{1,2})", str(value or ""))
    return (int(m[1]), int(m[2])) if m else None


def _year_month(text):
    m = re.match(r"(\d{4})[/\-.](\d{1,2})", str(text or ""))
    return (int(m[1]), int(m[2])) if m else None


def _date(text):
    m = re.match(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", str(text or ""))
    try:
        return date(int(m[1]), int(m[2]), int(m[3])) if m else None
    except ValueError:
        return None


def _previous(year, month):
    return (year - 1, 12) if month == 1 else (year, month - 1)


def fund_key(record):
    return (norm_name(record.get("fund_name")), str(record.get("currency") or "").upper())


def pay_lags(records):
    """{基金: 除息日→發放日天數}，取這檔基金所有同時有兩個日期的記錄的中位數。"""
    lags = {}
    for rec in records:
        ex, pay = _date(rec.get("ex_date")), _date(rec.get("pay_date"))
        if ex and pay and 0 <= (pay - ex).days <= 45:
            lags.setdefault(fund_key(rec), []).append((pay - ex).days)
    return {k: sorted(v)[len(v) // 2] for k, v in lags.items()}


def dividend_month(record, lags=None):
    """配息月份＝發放日的前一個月（11/10 發的是 10 月的配息 → 勾 2026/10）。
    沒有發放日：除息日＋這檔基金過去的發放天數推算發放日；沒有依據就回傳 None（不勾）。"""
    paid = _year_month(record.get("pay_date"))
    if paid:
        return _previous(*paid)
    ex = _date(record.get("ex_date"))
    lag = (lags or {}).get(fund_key(record))
    if ex is None or lag is None:
        return None
    pay = ex + timedelta(days=lag)
    return _previous(pay.year, pay.month)


pay_month = dividend_month  # 舊名稱


def is_true(value):
    return str(value).strip().upper() in {"TRUE", "1", "Y", "YES", "V", "✓"}


def plan(grid, records, today):
    """Returns (updates [{"cell", "value", "old", "why"}], problems)."""
    columns = sheet_columns(grid)
    rows = month_rows(grid)
    last = _previous(today.year, today.month)  # 最多勾到上個月
    lags = pay_lags(records)
    want, problems, frozen = {}, [], set()
    for rec in records:
        if not rec.get("is_paid"):
            continue
        month = dividend_month(rec, lags)
        if month is None:
            ex = _year_month(rec.get("ex_date"))
            if ex and ex >= SYNC_FROM:
                col = match_column(columns, rec.get("platform"), rec.get("currency"), rec.get("fund_name"))
                if col is not None:
                    frozen.add(col)  # 不知道是哪個月，這一欄先都不動
                problems.append(f"{rec.get('platform')} {rec.get('fund_name')} 除息 {rec.get('ex_date')}："
                                "已確認但沒有發放日、也推算不出來，配息月份不勾")
            continue
        if month < SYNC_FROM or month > last:
            continue
        col = match_column(columns, rec.get("platform"), rec.get("currency"), rec.get("fund_name"))
        if col is None:
            problems.append(f"{rec.get('platform')} {rec.get('fund_name')}（{rec.get('currency')}）"
                            "對不到配息月份的欄，略過")
            continue
        if month not in rows:
            problems.append(f"配息月份 A 欄沒有 {month[0]}/{month[1]:02d}")
            continue
        want.setdefault((rows[month], col), []).append(str(rec.get("fund_name") or ""))
    updates = []
    for month, r in sorted(rows.items()):
        if month < SYNC_FROM or month > last:
            continue
        for col, _plat, _cur, name in columns:
            if col in frozen:
                continue
            line = grid[r - 1]
            current = line[col] if col < len(line) else ""
            paid = (r, col) in want
            if paid != is_true(current):
                updates.append({"cell": f"{col_letter(col)}{r}", "value": paid, "old": current,
                                "why": f"{month[0]}/{month[1]:02d} {name[:16]}：" +
                                       ("已確認入帳" if paid else "沒有已確認的配息記錄")})
    return updates, problems


def col_letter(index):
    s, n = "", index + 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def load_records():
    from supabase import create_client
    client = create_client(os.environ.get("SUPABASE_URL", "https://qrvdztqyzxlsfskdgiqp.supabase.co"),
                           os.environ["SUPABASE_ANON_KEY"])
    rows = []
    for table in ("fund_dividends", "dividend_log"):
        data = client.table(table).select("fund_code,fund_name,platform,currency,ex_date,pay_date,is_paid").execute()
        rows += data.data or []
    return rows


def open_sheet():
    import gspread
    from google.oauth2.service_account import Credentials
    info = json.loads(os.environ["INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_key(SPREADSHEET_ID).get_worksheet_by_id(SHEET_GID)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    sheet = open_sheet()
    grid = sheet.get_values(value_render_option="UNFORMATTED_VALUE")
    updates, problems = plan(grid, load_records(), datetime.now(TAIPEI).date())
    print(f"== 配息月份同步：{len(updates)} 格要改")
    for u in updates:
        print(f"  {u['cell']}: {u['old']} → {u['value']}（{u['why']}）")
    for p in problems:
        print(f"WARN {p}")
    if updates and not args.dry_run:
        sheet.batch_update([{"range": u["cell"], "values": [[u["value"]]]} for u in updates],
                           value_input_option="USER_ENTERED")
        print(f"已寫入 {len(updates)} 格")
    return 0


if __name__ == "__main__":
    sys.exit(main())
