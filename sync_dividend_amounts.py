"""總覽 O 欄「配息金額」跟最近一次已入帳配息不同時：把 O 欄改成實際金額，並在 Google 日曆加一則提醒。

由 fund-nav 排程（每 10 分鐘）一起跑：
1. 讀總覽各分類（基富通-台、渣打-美金…）下每檔基金的 O 欄（原幣）。
2. 讀 App 配息記錄（fund_dividends、dividend_log）已確認入帳、發放日在本月或上月的，每檔取最新一筆的原幣金額。
3. 差超過 0.2%（至少 1）→ O 欄改成實際金額，日曆加一則全天事件「配息金額變動」。
   同名多列（分批買進）的基金不自動改，只提醒。

日曆：用服務帳號寫入 CALENDAR_ID（預設 jennytsai26888@gmail.com）的日曆；
要先在 Google 日曆設定把這個日曆共用給服務帳號（「變更活動」權限），並在 GCP 啟用 Google Calendar API。
寫不進日曆只印警告，不影響 O 欄更新。

  python sync_dividend_amounts.py --dry-run
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import difflib
import json
import os
import re
import sys
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
SPREADSHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"  # 2025Jenny-總帳
OVERVIEW_SHEET = "總覽"
NAME_HEADER, AMOUNT_HEADER = "投資分類", "配息金額"
CALENDAR_ID = os.environ.get("DIVIDEND_CALENDAR_ID", "jennytsai26888@gmail.com")
SECTIONS = {  # 同 invest_app.sheet_compare.SHEET_FUND_SECTIONS
    "基富通-台": ("基富通", "TWD"), "基富通-人民幣": ("基富通", "CNY"), "基富通-日": ("基富通", "JPY"),
    "渣打-美金": ("渣打基金", "USD"), "渣打-南非": ("渣打基金", "ZAR"),
    "台新-南非": ("台新基金", "ZAR"), "台新-美金": ("台新基金", "USD"),
}


def key(name):
    import unicodedata
    return "".join(unicodedata.normalize("NFKC", str(name or "")).lower().split())


def number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return float(str(value or "").replace(",", "").strip())
    except ValueError:
        return 0.0


def col_letter(index):
    s, n = "", index + 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def sheet_funds(grid):
    """[{row (1-based), col (0-based O 欄), section, platform, currency, name, amount}]"""
    header = next((i for i, r in enumerate(grid) if NAME_HEADER in r and AMOUNT_HEADER in r), None)
    if header is None:
        raise RuntimeError(f"總覽找不到「{NAME_HEADER}」「{AMOUNT_HEADER}」標題")
    name_col, amount_col = grid[header].index(NAME_HEADER), grid[header].index(AMOUNT_HEADER)
    out, section = [], None
    for i in range(header + 1, len(grid)):
        row = grid[i]
        name = str(row[name_col]).strip() if name_col < len(row) else ""
        if not name or re.fullmatch(r"[\d.,\-]+", name):
            section = None
            continue
        if name in SECTIONS:
            section = name
            continue
        if section:
            out.append({"row": i + 1, "col": amount_col, "section": section, "platform": SECTIONS[section][0],
                        "currency": SECTIONS[section][1], "name": name,
                        "amount": number(row[amount_col]) if amount_col < len(row) else 0.0})
    return out


def paid_amount(rec):
    """已入帳配息的原幣金額（同 App：單位數 × 每單位實際配息；沒有就 台幣 ÷ 匯率）。"""
    if str(rec.get("is_paid")).lower() not in {"true", "1"}:
        return 0.0
    units, per = number(rec.get("units_at_ex")), number(rec.get("actual_div_amount")) or number(rec.get("div_amount"))
    amount = units * per if units > 0 and per > 0 else 0.0
    if amount <= 0 and number(rec.get("twd_total")) > 0 and number(rec.get("fx_rate")) > 0:
        amount = number(rec.get("twd_total")) / number(rec.get("fx_rate"))
    return amount


def parse_day(text):
    m = re.match(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", str(text or ""))
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


def latest_paid(records, today):
    """{(platform, currency, 名稱 key): (pay_date, amount, 名稱)}：本月、上月已入帳的最新一筆。"""
    first_last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    out = {}
    for rec in records:
        amount = paid_amount(rec)
        day = parse_day(rec.get("pay_date")) or parse_day(rec.get("ex_date"))
        if amount <= 0 or not day or not (first_last_month <= day <= today):
            continue
        k = (str(rec.get("platform") or "").strip(), str(rec.get("currency") or "").upper(), key(rec.get("fund_name")))
        if k not in out or day > out[k][0]:
            out[k] = (day, amount, str(rec.get("fund_name") or ""))
    return out


def plan(funds, records, today):
    """→ (updates [{row, col, cell, name, currency, old, new, pay_date}], warnings)"""
    paid = latest_paid(records, today)
    by_section = {}
    for f in funds:
        by_section.setdefault((f["platform"], f["currency"]), []).append(f)
    updates, warnings = [], []
    for (platform, currency, rkey), (day, amount, rname) in paid.items():
        rows = by_section.get((platform, currency), [])
        names = {key(f["name"]) for f in rows}
        target = rkey if rkey in names else next(iter(difflib.get_close_matches(rkey, list(names), n=1, cutoff=0.6)), None)
        if target is None:
            continue
        matches = [f for f in rows if key(f["name"]) == target]
        f = matches[0]
        if abs(amount - f["amount"]) <= max(1.0, abs(f["amount"]) * 0.002):
            continue
        if len(matches) > 1:
            warnings.append(f"{f['section']} {f['name'][:20]} 有 {len(matches)} 列（分批），O 欄請手動改成 {amount:,.2f}")
            continue
        updates.append({"row": f["row"], "col": f["col"], "cell": f"{col_letter(f['col'])}{f['row']}",
                        "name": f["name"], "section": f["section"], "currency": currency,
                        "old": f["amount"], "new": round(amount, 2), "pay_date": day})
    return updates, warnings


def credentials(scopes):
    from google.oauth2.service_account import Credentials
    return Credentials.from_service_account_info(json.loads(os.environ["INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON"]),
                                                 scopes=scopes)


def add_calendar_event(update, today):
    from google.auth.transport.requests import AuthorizedSession
    session = AuthorizedSession(credentials(["https://www.googleapis.com/auth/calendar.events"]))
    body = {
        "summary": f"配息金額變動｜{update['name'][:20]} {update['old']:,.2f} → {update['new']:,.2f} {update['currency']}",
        "description": (f"{update['section']} {update['name']}\n"
                        f"{update['pay_date']:%Y/%m/%d} 入帳 {update['new']:,.2f} {update['currency']}，"
                        f"總覽 O 欄原本 {update['old']:,.2f}，已自動改為實際金額（{update['cell']}）。"),
        "start": {"date": today.isoformat()}, "end": {"date": (today + timedelta(days=1)).isoformat()},
    }
    resp = session.post(f"https://www.googleapis.com/calendar/v3/calendars/{CALENDAR_ID}/events", json=body, timeout=20)
    if resp.status_code >= 300:
        raise RuntimeError(f"{resp.status_code} {resp.text[:200]}")


def load_records():
    from supabase import create_client
    client = create_client(os.environ.get("SUPABASE_URL", "https://qrvdztqyzxlsfskdgiqp.supabase.co"),
                           os.environ["SUPABASE_ANON_KEY"])
    rows = []
    for table in ("fund_dividends", "dividend_log"):
        rows += client.table(table).select("*").execute().data or []
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    import gspread
    sheet = gspread.authorize(credentials(["https://www.googleapis.com/auth/spreadsheets"])) \
        .open_by_key(SPREADSHEET_ID).worksheet(OVERVIEW_SHEET)
    try:
        funds = sheet_funds(sheet.get_values(value_render_option="UNFORMATTED_VALUE"))
    except RuntimeError as exc:
        print(f"WARN {exc}；略過配息金額檢查")
        return 0
    today = datetime.now(TAIPEI).date()
    updates, warnings = plan(funds, load_records(), today)
    print(f"== 總覽 O 欄配息金額：{len(updates)} 檔跟實際入帳不同")
    for u in updates:
        print(f"  {u['cell']} {u['section']} {u['name'][:20]}：{u['old']:,.2f} → {u['new']:,.2f}（{u['pay_date']:%m/%d} 入帳）")
    for w in warnings:
        print(f"WARN {w}")
    if not updates or args.dry_run:
        return 0
    sheet.batch_update([{"range": u["cell"], "values": [[u["new"]]]} for u in updates], value_input_option="RAW")
    print(f"已寫入 {len(updates)} 格")
    for u in updates:
        try:
            add_calendar_event(u, today)
            print(f"  ✅ 日曆已加：{u['name'][:20]}")
        except Exception as exc:  # noqa: BLE001
            print(f"WARN 日曆寫入失敗（{CALENDAR_ID} 要共用給服務帳號、並啟用 Calendar API）：{str(exc)[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
