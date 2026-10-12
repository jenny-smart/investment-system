"""Update requested Taiwan securities and repair #N/A prices in Google Sheets."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import math
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

SPREADSHEET_ID = "17HPytZKOPR_9Od_wor-xEx9kpccJlPS2v6B0Dz6MRYc"
SHEET_IDS = (0, 1591931043)
CODES = ("4401", "6261", "00740B", "00927", "6244", "5314", "5478")
TAIPEI = ZoneInfo("Asia/Taipei")


def normalize_code(value):
    text = str(value).strip().upper()
    if re.fullmatch(r"\d{4}\.0", text):
        text = text[:-2]
    return text if text in CODES else None


def normalize_tw_code(value):
    """Accept common Taiwan stock/ETF codes without limiting them to CODES."""
    text = str(value).strip().upper()
    if re.fullmatch(r"\d{4,6}\.0", text):
        text = text[:-2]
    return text if re.fullmatch(r"\d{4,6}[A-Z]?", text) else None


def find_targets(column):
    return [(row, code) for row, values in enumerate(column, 1)
            if values and (code := normalize_code(values[0]))]


def find_na_targets(rows, start_row=7):
    """Find rows where A is nonblank and J is #N/A, using C as the ticker."""
    targets = []
    unresolved = []
    for row_number, values in enumerate(rows, start_row):
        col_a = values[0] if values else ""
        col_c = values[2] if len(values) > 2 else ""
        col_j = values[9] if len(values) > 9 else ""
        if str(col_a).strip() and str(col_j).strip().upper() == "#N/A":
            code = normalize_tw_code(col_c)
            if code:
                targets.append((row_number, code))
            else:
                unresolved.append(row_number)
    return targets, unresolved


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


def fetch_quote(code, today):
    import requests
    # Probe listed and OTC markets; do not mistake a bid or yesterday's close
    # for the latest trade when MIS reports z='-'.
    try:
        response = requests.get(
            "https://mis.twse.com.tw/stock/api/getStockInfo.jsp",
            params={"ex_ch": f"tse_{code}.tw|otc_{code}.tw", "json": "1", "delay": "0"},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://mis.twse.com.tw/stock/fibest.jsp"},
            timeout=25,
        )
        response.raise_for_status()
        for item in response.json().get("msgArray", []):
            price = valid_price(item.get("z"))
            if item.get("c") == code and price and recent_date(item.get("d"), today):
                return {"price": price, "date": item["d"], "source": "TWSE MIS"}
    except Exception as exc:
        print(f"{code}: MIS unavailable ({type(exc).__name__})")

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
    raise RuntimeError(f"{code}: no valid quote within seven days; original cells preserved")


def build_updates(title, targets, quotes):
    quoted_title = "'" + title.replace("'", "''") + "'"
    return [{"range": f"{quoted_title}!J{row}", "values": [[quotes[code]["price"]]]}
            for row, code in targets if code in quotes]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
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
    targets = {}
    unresolved_by_sheet = {}
    # All tabs must contain every code in CODES before any writes are attempted.
    for sheet_id in SHEET_IDS:
        sheet = sheets[sheet_id]
        rows = find_targets(sheet.get(f"C1:C{sheet.row_count}", value_render_option="FORMATTED_VALUE"))
        missing = set(CODES) - {code for _, code in rows}
        if missing:
            raise RuntimeError(f"{sheet.title}: missing codes {sorted(missing)}; no cells changed")
        na_rows, unresolved = find_na_targets(
            sheet.get(f"A7:J{sheet.row_count}", value_render_option="FORMATTED_VALUE")
        )
        unresolved_by_sheet[sheet_id] = unresolved
        # The fixed list is always refreshed; #N/A rows are added dynamically.
        targets[sheet_id] = list(dict.fromkeys(rows + na_rows))
    quotes, errors = {}, []
    for sheet_id, unresolved in unresolved_by_sheet.items():
        if unresolved:
            message = (
                f"{sheets[sheet_id].title}: A is nonblank and J is #N/A, but C has no "
                f"valid ticker at rows {unresolved}; those cells are preserved"
            )
            errors.append(message)
            print(message, file=sys.stderr)
    today = datetime.now(TAIPEI).date()
    requested_codes = list(dict.fromkeys(
        list(CODES) + [code for rows in targets.values() for _, code in rows]
    ))
    for code in requested_codes:
        try:
            quotes[code] = fetch_quote(code, today)
            print(code, json.dumps(quotes[code], ensure_ascii=False))
        except RuntimeError as exc:
            errors.append(str(exc))
            print(str(exc), file=sys.stderr)
    updates = []
    for sheet_id, rows in targets.items():
        sheet = sheets[sheet_id]
        # Recheck identities after network price queries in case rows moved.
        fixed = find_targets(sheet.get(f"C1:C{sheet.row_count}", value_render_option="FORMATTED_VALUE"))
        na_rows, unresolved = find_na_targets(
            sheet.get(f"A7:J{sheet.row_count}", value_render_option="FORMATTED_VALUE")
        )
        current = list(dict.fromkeys(fixed + na_rows))
        if current != rows or unresolved != unresolved_by_sheet[sheet_id]:
            raise RuntimeError(f"{sheet.title}: rows changed during lookup; no cells changed")
        updates.extend(build_updates(sheet.title, rows, quotes))
    print(json.dumps({"dry_run": args.dry_run, "updates": updates}, ensure_ascii=False))
    if updates and not args.dry_run:
        spreadsheet.values_batch_update({"valueInputOption": "RAW", "data": updates})
        result = spreadsheet.values_batch_get([item["range"] for item in updates])
        actual = result.get("valueRanges", [])
        if len(actual) != len(updates) or any(
            valid_price(cell.get("values", [[None]])[0][0]) != item["values"][0][0]
            for cell, item in zip(actual, updates)
        ):
            raise RuntimeError("Write readback verification failed")
        print(f"Verified {len(updates)} J cells across both tabs")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
