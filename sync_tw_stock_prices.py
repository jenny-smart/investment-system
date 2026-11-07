"""Refresh Taiwan stock prices in column J every 10 minutes, 08:30-14:30 on trading days."""
from __future__ import annotations

import argparse
from datetime import datetime, time, timedelta
import json
import math
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

SPREADSHEET_ID = "17HPytZKOPR_9Od_wor-xEx9kpccJlPS2v6B0Dz6MRYc"
SHEET_IDS = (0, 1591931043)
START_ROW = 7
TIMESTAMP_CELL = "A2"
# tool-system 排程設定 dispatches every 10 minutes 08:30-14:30 on weekdays; only
# 08:30-14:30 on TWSE trading days runs. The end allows up to 9 minutes of
# runner delay for the 14:30 trigger.
WINDOW_START = time(8, 30)
WINDOW_END = time(14, 40)
# 收盤後（13:35 起）J 欄改用證交所／櫃買中心公布的正式收盤價；抓不到才退回即時報價
CLOSE_AFTER = time(13, 35)
MIS_BATCH = 20
TAIPEI = ZoneInfo("Asia/Taipei")


def normalize_tw_code(value):
    text = str(value).strip().upper()
    if re.fullmatch(r"\d{4,6}\.0", text):
        text = text[:-2]
    return text if re.fullmatch(r"\d{4,6}[A-Z]?", text) else None


def plan_rows(column, start_row=START_ROW):
    """Split non-empty C cells into priced rows, duplicate rows and skipped rows.

    The first row of each code gets the live price; later rows with the same
    code reference that first J cell instead of looking the price up again.
    """
    first, prices, duplicates, skipped = {}, [], [], []
    for offset, values in enumerate(column):
        raw = values[0] if values else ""
        if not str(raw).strip():
            continue
        row = start_row + offset
        code = normalize_tw_code(raw)
        if not code:
            skipped.append(row)
        elif code in first:
            duplicates.append((row, f"=J{first[code]}"))
        else:
            first[code] = row
            prices.append((row, code))
    return prices, duplicates, skipped


def in_update_window(now):
    return now.weekday() < 5 and WINDOW_START <= now.time() < WINDOW_END


def parse_holidays(items):
    """Market-closed dates from the TWSE holiday schedule (ROC or AD dates).

    The schedule also lists first/last trading days around long holidays;
    those are trading days and are excluded.
    """
    closed = set()
    for item in items or []:
        text = f"{item.get('Name', '')}{item.get('Description', '')}"
        if "開始交易" in text or "最後交易" in text:
            continue
        digits = re.sub(r"\D", "", str(item.get("Date", "")))
        if len(digits) == 7:
            digits = f"{int(digits[:3]) + 1911}{digits[3:]}"
        try:
            closed.add(datetime.strptime(digits, "%Y%m%d").date())
        except ValueError:
            continue
    return closed


def is_market_holiday(today):
    """True when TWSE lists today as closed; unknown (lookup failed) counts as open."""
    import requests
    try:
        response = requests.get(
            "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=20,
        )
        response.raise_for_status()
        return today in parse_holidays(response.json())
    except Exception as exc:
        print(f"TWSE holiday schedule unavailable ({type(exc).__name__}); assuming open")
        return False


def valid_price(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def recent_date(date_text, today):
    try:
        day = datetime.strptime(date_text, "%Y%m%d").date()
        return today - timedelta(days=7) <= day <= today
    except (ValueError, TypeError):
        return False


def fetch_mis_quotes(codes, today):
    import requests
    quotes = {}
    for start in range(0, len(codes), MIS_BATCH):
        chunk = codes[start:start + MIS_BATCH]
        try:
            response = requests.get(
                "https://mis.twse.com.tw/stock/api/getStockInfo.jsp",
                params={
                    "ex_ch": "|".join(f"tse_{code}.tw|otc_{code}.tw" for code in chunk),
                    "json": "1", "delay": "0",
                },
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://mis.twse.com.tw/stock/fibest.jsp"},
                timeout=25,
            )
            response.raise_for_status()
            for item in response.json().get("msgArray", []):
                code = item.get("c")
                price = valid_price(item.get("z"))
                if code in chunk and code not in quotes and price and recent_date(item.get("d"), today):
                    quotes[code] = {"price": price, "date": item["d"], "source": "TWSE MIS"}
        except Exception as exc:
            print(f"MIS unavailable for {chunk} ({type(exc).__name__})")
    return quotes


def fetch_yahoo_quote(code, today):
    import yfinance as yf
    suffixes = (".TW", ".TWO") if code == "00927" else (".TWO", ".TW")
    for suffix in suffixes:
        try:
            history = yf.Ticker(code + suffix).history(period="1mo", auto_adjust=False)
            closes = history["Close"].dropna()
            if closes.empty:
                continue
            price = valid_price(closes.iloc[-1])
            quote_date = closes.index[-1].strftime("%Y%m%d")
            if price and recent_date(quote_date, today):
                return {"price": price, "date": quote_date, "source": "Yahoo " + code + suffix}
        except Exception as exc:
            print(f"{code + suffix}: Yahoo unavailable ({type(exc).__name__})")
    raise RuntimeError(f"{code}: no valid quote within seven days; original cell preserved")


def _number_text(value):
    text = str(value or "").replace(",", "").strip()
    return valid_price(text) if re.fullmatch(r"\d+(\.\d+)?", text) else None


def _roc_or_ad(text):
    """'1151106'、'115/11/06'、'20261106'、'2026/11/06' → 'YYYYMMDD'；認不得回 ''。"""
    digits = re.sub(r"\D", "", str(text or ""))
    if len(digits) == 7:
        return f"{int(digits[:3]) + 1911}{digits[3:]}"
    return digits if len(digits) == 8 else ""


def _tables(payload):
    """[(fields, rows)]：新格式 tables[]，舊格式 fieldsN/dataN、aaData。"""
    out = []
    for table in payload.get("tables") or []:
        out.append((table.get("fields") or [], table.get("data") or []))
    for k, v in payload.items():
        if k.startswith("fields") and isinstance(v, list):
            out.append((v, payload.get("data" + k[len("fields"):]) or []))
    if payload.get("aaData"):
        out.append((["代號", "名稱", "收盤"], payload["aaData"]))
    return out


def parse_close_table(payload, day):
    """證交所 MI_INDEX／櫃買 每日收盤行情 JSON → {code: price}；日期不是 day（YYYYMMDD）就回空。"""
    when = _roc_or_ad(payload.get("date") or payload.get("reportDate") or "")
    if when and when != day:
        return {}
    closes = {}
    for fields, rows in _tables(payload):
        names = [str(f).strip() for f in fields]
        code_col = next((i for i, f in enumerate(names) if f in ("證券代號", "代號")), None)
        close_col = next((i for i, f in enumerate(names) if f.startswith("收盤") and "價差" not in f), None)
        if code_col is None or close_col is None:
            continue
        for row in rows:
            if len(row) > max(code_col, close_col):
                code = normalize_tw_code(row[code_col])
                price = _number_text(row[close_col])
                if code and price:
                    closes.setdefault(code, price)
    return closes


def fetch_official_closes(day):
    """{code: {"price", "date", "source"}}：day（YYYYMMDD）證交所＋櫃買中心正式收盤價。"""
    import requests
    headers = {"User-Agent": "Mozilla/5.0"}
    ad = f"{day[:4]}/{day[4:6]}/{day[6:]}"
    roc = f"{int(day[:4]) - 1911}/{day[4:6]}/{day[6:]}"
    sources = (
        ("TWSE 收盤", "https://www.twse.com.tw/exchangeReport/MI_INDEX",
         {"response": "json", "date": day, "type": "ALLBUT0999"}),
        ("TPEx 收盤", "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc",
         {"date": ad, "type": "EW", "response": "json"}),
        ("TPEx 收盤", "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php",
         {"l": "zh-tw", "d": roc, "o": "json"}),
    )
    quotes = {}
    for name, url, params in sources:
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            found = parse_close_table(response.json(), day)
            for code, price in found.items():
                quotes.setdefault(code, {"price": price, "date": day, "source": name})
            print(f"{name}: {len(found)} 檔收盤價（{url.split('/')[2]}）")
        except Exception as exc:
            print(f"{name} unavailable ({type(exc).__name__}: {str(exc)[:80]})")
    return quotes


def fetch_closing_quotes(codes, day, fallback):
    """收盤後：正式收盤價優先；沒有的代碼用 fallback（即時報價）或略過。"""
    official = fetch_official_closes(day)
    wanted = list(dict.fromkeys(codes))
    quotes = {c: official[c] for c in wanted if c in official}
    missing = [c for c in wanted if c not in quotes]
    errors = []
    if missing and fallback:
        more, errors = fetch_quotes(missing, datetime.strptime(day, "%Y%m%d").date())
        quotes.update(more)
    elif missing:
        errors = [f"{c}: {day} 沒有正式收盤價，J 欄不變" for c in missing]
        for e in errors:
            print(e, file=sys.stderr)
    for code in wanted:
        if code in quotes and quotes[code].get("source", "").endswith("收盤"):
            print(code, json.dumps(quotes[code], ensure_ascii=False))
    return quotes, errors


def fetch_quotes(codes, today):
    codes = list(dict.fromkeys(codes))
    quotes, errors = fetch_mis_quotes(codes, today), []
    for code in codes:
        if code not in quotes:
            try:
                quotes[code] = fetch_yahoo_quote(code, today)
            except RuntimeError as exc:
                errors.append(str(exc))
                print(str(exc), file=sys.stderr)
                continue
        print(code, json.dumps(quotes[code], ensure_ascii=False))
    return quotes, errors


def quoted_title(title):
    return "'" + title.replace("'", "''") + "'"


def read_codes(sheet):
    return sheet.get(
        f"C{START_ROW}:C{sheet.row_count}", value_render_option="FORMATTED_VALUE", maintain_size=True
    )


def run_update(spreadsheet, sheets, now, dry_run, close_date=None):
    plans, columns = {}, {}
    for sheet_id in SHEET_IDS:
        sheet = sheets[sheet_id]
        columns[sheet_id] = read_codes(sheet)
        plans[sheet_id] = plan_rows(columns[sheet_id])
        if plans[sheet_id][2]:
            print(f"{sheet.title}: rows {plans[sheet_id][2]} are not Taiwan codes; J unchanged")

    codes = [code for prices, _, _ in plans.values() for _, code in prices]
    if close_date:   # 指定日期：只用那天的正式收盤價，沒有的不改
        quotes, errors = fetch_closing_quotes(codes, close_date, fallback=False)
    elif now.time() >= CLOSE_AFTER:
        quotes, errors = fetch_closing_quotes(codes, f"{now:%Y%m%d}", fallback=True)
    else:
        quotes, errors = fetch_quotes(codes, now.date())
    updates = []
    for sheet_id, (prices, duplicates, _) in plans.items():
        title = quoted_title(sheets[sheet_id].title)
        updates += [{"range": f"{title}!J{row}", "values": [[quotes[code]["price"]]]}
                    for row, code in prices if code in quotes]
        updates += [{"range": f"{title}!J{row}", "values": [[formula]]}
                    for row, formula in duplicates]
    stamp = now.strftime("%Y/%m/%d %H:%M")
    print(json.dumps({"dry_run": dry_run, "updated_at": stamp, "updates": updates}, ensure_ascii=False))
    if dry_run:
        return 1 if errors else 0

    for sheet_id, expected in columns.items():
        if read_codes(sheets[sheet_id]) != expected:
            raise RuntimeError(f"{sheets[sheet_id].title}: C column changed during lookup; no cells changed")
    if updates:
        spreadsheet.values_batch_update({"valueInputOption": "USER_ENTERED", "data": updates})
    spreadsheet.values_batch_update({
        "valueInputOption": "RAW",
        "data": [{"range": f"{quoted_title(sheets[sheet_id].title)}!{TIMESTAMP_CELL}", "values": [[stamp]]}
                 for sheet_id in SHEET_IDS],
    })
    print(f"Updated {len(updates)} J cells; {TIMESTAMP_CELL} set to {stamp}")
    return 1 if errors else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument(
        "--mode", choices=("auto", "update"), default="auto",
        help="auto only runs 08:30-14:30 Asia/Taipei on trading days; update always runs",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--close-date", help="YYYYMMDD：用這天的正式收盤價更新 J 欄（補正用，視為 update 模式）")
    args = parser.parse_args()
    if args.close_date:
        args.close_date = _roc_or_ad(args.close_date)
        args.mode = "update"

    now = datetime.now(TAIPEI)
    if args.mode == "auto" and not in_update_window(now):
        print(f"{now:%a %H:%M} Asia/Taipei is outside weekday 08:30-14:30; skipped")
        return 0
    if args.mode == "auto" and is_market_holiday(now.date()):
        print(f"{now:%Y/%m/%d} is a TWSE market holiday; skipped")
        return 0

    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    if args.credentials_file:
        credentials = Credentials.from_service_account_file(str(args.credentials_file), scopes=scopes)
    else:
        raw = os.environ.get("INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if not raw:
            raise RuntimeError("Missing INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON secret")
        credentials = Credentials.from_service_account_info(json.loads(raw), scopes=scopes)
    spreadsheet = gspread.authorize(credentials).open_by_key(SPREADSHEET_ID)
    sheets = {sheet.id: sheet for sheet in spreadsheet.worksheets()}
    missing_sheets = set(SHEET_IDS) - set(sheets)
    if missing_sheets:
        raise RuntimeError(f"Missing sheet IDs {sorted(missing_sheets)}; no cells changed")
    return run_update(spreadsheet, sheets, now, args.dry_run, args.close_date)


if __name__ == "__main__":
    sys.exit(main())
