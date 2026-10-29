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
# cron-job.org fires every 10 minutes from 08:00 to 14:50 on weekdays; only
# 08:30-14:30 on TWSE trading days runs. The end allows up to 9 minutes of
# runner delay for the 14:30 trigger.
WINDOW_START = time(8, 30)
WINDOW_END = time(14, 40)
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


def run_update(spreadsheet, sheets, now, dry_run):
    plans, columns = {}, {}
    for sheet_id in SHEET_IDS:
        sheet = sheets[sheet_id]
        columns[sheet_id] = read_codes(sheet)
        plans[sheet_id] = plan_rows(columns[sheet_id])
        if plans[sheet_id][2]:
            print(f"{sheet.title}: rows {plans[sheet_id][2]} are not Taiwan codes; J unchanged")

    quotes, errors = fetch_quotes(
        [code for prices, _, _ in plans.values() for _, code in prices], now.date()
    )
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
    args = parser.parse_args()

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
    return run_update(spreadsheet, sheets, now, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
