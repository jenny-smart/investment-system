"""Safely refresh Taiwan stock prices and temporarily repair #N/A formulas."""
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
BACKUP_SHEET_TITLE = "_tw_price_formula_backup"
BACKUP_HEADER = [
    "version", "sheet_id", "sheet_title", "row", "code", "formula",
    "background_json", "temporary_price", "saved_at",
]
HIGHLIGHT = {"backgroundColorStyle": {"rgbColor": {"red": 1.0, "green": 0.85, "blue": 0.35}}}
PRICE_BACKGROUND = {
    "backgroundColor": {"red": 0.9882353, "green": 0.8980392, "blue": 0.8039216},
    "backgroundColorStyle": {
        "rgbColor": {"red": 0.9882353, "green": 0.8980392, "blue": 0.8039216}
    },
}
TAIPEI = ZoneInfo("Asia/Taipei")


def normalize_tw_code(value):
    text = str(value).strip().upper()
    if re.fullmatch(r"\d{4,6}\.0", text):
        text = text[:-2]
    return text if re.fullmatch(r"\d{4,6}[A-Z]?", text) else None


def normalize_fixed_code(value):
    code = normalize_tw_code(value)
    return code if code in CODES else None


def find_fixed_targets(column):
    return [(row, code) for row, values in enumerate(column, 1)
            if values and (code := normalize_fixed_code(values[0]))]


def find_na_targets(rows, formulas=None, start_row=7):
    """Return restorable #N/A targets plus unsafe row numbers."""
    targets = []
    unsafe = []
    formulas = formulas or []
    for offset, values in enumerate(rows):
        row_number = start_row + offset
        col_a = values[0] if values else ""
        col_c = values[2] if len(values) > 2 else ""
        col_j = values[9] if len(values) > 9 else ""
        if not str(col_a).strip() or str(col_j).strip().upper() != "#N/A":
            continue
        code = normalize_tw_code(col_c)
        formula = formulas[offset][0] if offset < len(formulas) and formulas[offset] else ""
        if code and str(formula).startswith("="):
            targets.append({"row": row_number, "code": code, "formula": formula})
        else:
            unsafe.append(row_number)
    return targets, unsafe


def find_legacy_0050_rows(rows, start_row=7):
    """Find 0050 rows whose J cell is still a raw value instead of a formula."""
    found = []
    for offset, values in enumerate(rows):
        code = normalize_tw_code(values[0]) if values else None
        current = values[7] if len(values) > 7 else ""
        if code == "0050" and current != "" and not str(current).startswith("="):
            found.append(offset + start_row)
    return found


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
    raise RuntimeError(f"{code}: no valid quote within seven days; original cell preserved")


def fetch_quotes(codes, today):
    quotes, errors = {}, []
    for code in dict.fromkeys(codes):
        try:
            quotes[code] = fetch_quote(code, today)
            print(code, json.dumps(quotes[code], ensure_ascii=False))
        except RuntimeError as exc:
            errors.append(str(exc))
            print(str(exc), file=sys.stderr)
    return quotes, errors


def quoted_title(title):
    return "'" + title.replace("'", "''") + "'"


def cell_range(title, row):
    return f"{quoted_title(title)}!J{row}"


def backup_header_matches(row):
    """Accept harmless whitespace/BOM differences in an existing backup header."""
    normalized = [str(value).strip().lstrip("\ufeff") for value in row]
    return normalized == BACKUP_HEADER


def backup_has_records(values):
    return any(any(str(value).strip() for value in row) for row in values[1:])


def ensure_backup_header(sheet, values):
    """Repair an empty/stale backup header without ever discarding backup records."""
    if values and backup_header_matches(values[0]):
        return
    if values and backup_has_records(values):
        raise RuntimeError(f"{BACKUP_SHEET_TITLE}: unexpected header; no cells changed")
    sheet.update([BACKUP_HEADER], "A1:I1", value_input_option="RAW")


def get_or_create_backup_sheet(spreadsheet):
    from gspread.exceptions import WorksheetNotFound
    try:
        sheet = spreadsheet.worksheet(BACKUP_SHEET_TITLE)
    except WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(BACKUP_SHEET_TITLE, rows=1000, cols=len(BACKUP_HEADER))
        sheet.hide()
    values = sheet.get_all_values()
    ensure_backup_header(sheet, values)
    return sheet


def read_backups(spreadsheet):
    from gspread.exceptions import WorksheetNotFound
    try:
        sheet = spreadsheet.worksheet(BACKUP_SHEET_TITLE)
    except WorksheetNotFound:
        return None, []
    values = sheet.get_all_values()
    if not values:
        return sheet, []
    if not backup_header_matches(values[0]):
        if backup_has_records(values):
            raise RuntimeError(f"{BACKUP_SHEET_TITLE}: unexpected header; no cells changed")
        ensure_backup_header(sheet, values)
        return sheet, []
    records = [dict(zip(BACKUP_HEADER, row + [""] * (len(BACKUP_HEADER) - len(row))))
               for row in values[1:] if any(str(value).strip() for value in row)]
    return sheet, records


def fetch_backgrounds(credentials, sheet, rows):
    """Read user-entered J-cell backgrounds for exact restoration."""
    if not rows:
        return {}
    from google.auth.transport.requests import AuthorizedSession
    ranges = [("ranges", cell_range(sheet.title, row)) for row in rows]
    params = [("includeGridData", "true"), *ranges]
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
    response = AuthorizedSession(credentials).get(url, params=params, timeout=30)
    response.raise_for_status()
    result = {}
    for returned_sheet in response.json().get("sheets", []):
        if returned_sheet.get("properties", {}).get("sheetId") != sheet.id:
            continue
        for data in returned_sheet.get("data", []):
            row_number = int(data.get("startRow", 0)) + 1
            row_data = data.get("rowData", [])
            cell = row_data[0].get("values", [{}])[0] if row_data else {}
            user_format = cell.get("userEnteredFormat", {})
            result[row_number] = {
                key: user_format[key]
                for key in ("backgroundColor", "backgroundColorStyle") if key in user_format
            }
    return {row: result.get(row, {}) for row in rows}


def update_cell_request(sheet_id, row, value, background, restore=False):
    cell = {"userEnteredValue": value, "userEnteredFormat": background}
    fields = "userEnteredValue,userEnteredFormat.backgroundColorStyle"
    if restore:
        fields += ",userEnteredFormat.backgroundColor"
    return {
        "updateCells": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": row - 1,
                "endRowIndex": row,
                "startColumnIndex": 9,
                "endColumnIndex": 10,
            },
            "rows": [{"values": [cell]}],
            "fields": fields,
        }
    }


def run_fixed(spreadsheet, sheets, today, dry_run):
    targets = {}
    for sheet_id in SHEET_IDS:
        sheet = sheets[sheet_id]
        rows = find_fixed_targets(sheet.get(f"C1:C{sheet.row_count}", value_render_option="FORMATTED_VALUE"))
        missing = set(CODES) - {code for _, code in rows}
        if missing:
            raise RuntimeError(f"{sheet.title}: missing codes {sorted(missing)}; no cells changed")
        targets[sheet_id] = rows
    quotes, errors = fetch_quotes(CODES, today)
    updates = [
        {"range": cell_range(sheets[sheet_id].title, row), "values": [[quotes[code]["price"]]]}
        for sheet_id, rows in targets.items() for row, code in rows if code in quotes
    ]
    print(json.dumps({"mode": "fixed", "dry_run": dry_run, "updates": updates}, ensure_ascii=False))
    if updates and not dry_run:
        for sheet_id, expected in targets.items():
            current = find_fixed_targets(
                sheets[sheet_id].get(
                    f"C1:C{sheets[sheet_id].row_count}", value_render_option="FORMATTED_VALUE"
                )
            )
            if current != expected:
                raise RuntimeError(f"{sheets[sheet_id].title}: rows changed during lookup; no cells changed")
        spreadsheet.values_batch_update({"valueInputOption": "RAW", "data": updates})
        actual = spreadsheet.values_batch_get(
            [item["range"] for item in updates], params={"valueRenderOption": "UNFORMATTED_VALUE"}
        ).get("valueRanges", [])
        if len(actual) != len(updates) or any(
            valid_price(cell.get("values", [[None]])[0][0]) != item["values"][0][0]
            for cell, item in zip(actual, updates)
        ):
            raise RuntimeError("Fixed-price write verification failed")
    return 1 if errors else 0


def scan_temporary_targets(sheet):
    formatted = sheet.get(
        f"A7:J{sheet.row_count}", value_render_option="FORMATTED_VALUE", maintain_size=True
    )
    formulas = sheet.get(
        f"J7:J{sheet.row_count}", value_render_option="FORMULA", maintain_size=True
    )
    return find_na_targets(formatted, formulas)


def run_temporary(spreadsheet, sheets, credentials, today, dry_run):
    _, existing = read_backups(spreadsheet)
    if existing:
        raise RuntimeError("A previous temporary update still awaits restoration; no cells changed")

    targets, unsafe_by_sheet, errors = {}, {}, []
    for sheet_id in SHEET_IDS:
        found, unsafe = scan_temporary_targets(sheets[sheet_id])
        targets[sheet_id] = found
        unsafe_by_sheet[sheet_id] = unsafe
        if unsafe:
            message = f"{sheets[sheet_id].title}: cannot safely restore rows {unsafe}; preserved"
            errors.append(message)
            print(message, file=sys.stderr)
    quotes, quote_errors = fetch_quotes(
        [target["code"] for found in targets.values() for target in found], today
    )
    errors.extend(quote_errors)
    writable = {
        sheet_id: [target for target in found if target["code"] in quotes]
        for sheet_id, found in targets.items()
    }
    preview = [
        {"range": cell_range(sheets[sheet_id].title, target["row"]),
         "code": target["code"], "price": quotes[target["code"]]["price"]}
        for sheet_id, found in writable.items() for target in found
    ]
    print(json.dumps({"mode": "temporary", "dry_run": dry_run, "updates": preview}, ensure_ascii=False))
    if dry_run or not preview:
        return 1 if errors else 0

    for sheet_id, expected in targets.items():
        current, unsafe = scan_temporary_targets(sheets[sheet_id])
        if current != expected or unsafe != unsafe_by_sheet[sheet_id]:
            raise RuntimeError(f"{sheets[sheet_id].title}: rows changed during lookup; no cells changed")

    backgrounds = {
        sheet_id: fetch_backgrounds(credentials, sheets[sheet_id], [item["row"] for item in found])
        for sheet_id, found in writable.items()
    }
    saved_at = datetime.now(TAIPEI).isoformat(timespec="seconds")
    backup_rows = []
    requests = []
    for sheet_id, found in writable.items():
        sheet = sheets[sheet_id]
        for target in found:
            price = quotes[target["code"]]["price"]
            background = backgrounds[sheet_id][target["row"]]
            backup_rows.append([
                "1", str(sheet_id), sheet.title, str(target["row"]), target["code"],
                target["formula"], json.dumps(background, ensure_ascii=False), str(price), saved_at,
            ])
            requests.append(update_cell_request(
                sheet_id, target["row"], {"numberValue": price}, HIGHLIGHT
            ))

    backup_sheet = get_or_create_backup_sheet(spreadsheet)
    backup_sheet.append_rows(backup_rows, value_input_option="RAW")
    spreadsheet.batch_update({"requests": requests})
    print(f"Temporarily repaired and highlighted {len(requests)} cells; formulas backed up")
    return 1 if errors else 0


def run_restore(spreadsheet, sheets, dry_run):
    backup_sheet, records = read_backups(spreadsheet)
    if not records:
        print(json.dumps({"mode": "restore", "dry_run": dry_run, "updates": []}))
        return 0

    parsed = []
    for record in records:
        try:
            sheet_id = int(record["sheet_id"])
            row = int(record["row"])
            price = valid_price(record["temporary_price"])
            background = json.loads(record["background_json"] or "{}")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Invalid formula backup; no cells changed") from exc
        if sheet_id not in sheets or not record["formula"].startswith("=") or not price:
            raise RuntimeError("Invalid formula backup; no cells changed")
        parsed.append({**record, "sheet_id": sheet_id, "row": row,
                       "temporary_price": price, "background": background})

    for item in parsed:
        sheet = sheets[item["sheet_id"]]
        code_values = sheet.get(f"C{item['row']}", value_render_option="FORMATTED_VALUE")
        price_values = sheet.get(f"J{item['row']}", value_render_option="UNFORMATTED_VALUE")
        code = normalize_tw_code(code_values[0][0]) if code_values and code_values[0] else None
        price = valid_price(price_values[0][0]) if price_values and price_values[0] else None
        if code != item["code"] or price != item["temporary_price"]:
            raise RuntimeError(
                f"{sheet.title}!J{item['row']}: row or temporary value changed; no cells restored"
            )

    preview = [cell_range(sheets[item["sheet_id"]].title, item["row"]) for item in parsed]
    print(json.dumps({"mode": "restore", "dry_run": dry_run, "updates": preview}, ensure_ascii=False))
    if dry_run:
        return 0

    requests = [
        update_cell_request(
            item["sheet_id"], item["row"], {"formulaValue": item["formula"]},
            item["background"], restore=True,
        )
        for item in parsed
    ]
    spreadsheet.batch_update({"requests": requests})
    ranges = [cell_range(sheets[item["sheet_id"]].title, item["row"]) for item in parsed]
    actual = spreadsheet.values_batch_get(ranges, params={"valueRenderOption": "FORMULA"}).get("valueRanges", [])
    if len(actual) != len(parsed) or any(
        cell.get("values", [[None]])[0][0] != item["formula"]
        for cell, item in zip(actual, parsed)
    ):
        raise RuntimeError("Formula restoration verification failed; backup retained")
    backup_sheet.batch_clear([f"A2:I{backup_sheet.row_count}"])
    print(f"Restored {len(requests)} formulas and original backgrounds")
    return 0


def run_repair_0050(spreadsheet, sheets, dry_run):
    """One-time repair for 0050 cells overwritten before formula backups existed."""
    targets = []
    for sheet_id in SHEET_IDS:
        sheet = sheets[sheet_id]
        rows = sheet.get(
            f"C7:J{sheet.row_count}", value_render_option="FORMULA", maintain_size=True
        )
        for row in find_legacy_0050_rows(rows):
            targets.append({"sheet_id": sheet_id, "title": sheet.title, "row": row})

    preview = [cell_range(item["title"], item["row"]) for item in targets]
    print(json.dumps({"mode": "repair-0050", "dry_run": dry_run, "updates": preview}, ensure_ascii=False))
    if dry_run or not targets:
        return 0

    requests = [
        update_cell_request(
            item["sheet_id"], item["row"],
            {"formulaValue": f'=GOOGLEFINANCE("TPE:"&C{item["row"]})'},
            PRICE_BACKGROUND, restore=True,
        )
        for item in targets
    ]
    spreadsheet.batch_update({"requests": requests})
    ranges = [cell_range(item["title"], item["row"]) for item in targets]
    actual = spreadsheet.values_batch_get(
        ranges, params={"valueRenderOption": "FORMULA"}
    ).get("valueRanges", [])
    expected = [f'=GOOGLEFINANCE("TPE:"&C{item["row"]})' for item in targets]
    if len(actual) != len(targets) or any(
        cell.get("values", [[None]])[0][0] != formula
        for cell, formula in zip(actual, expected)
    ):
        raise RuntimeError("0050 formula repair verification failed")
    print(f"Restored {len(targets)} legacy 0050 formulas and price-cell backgrounds")
    return 0


def resolve_auto_mode(now):
    if now.hour == 14:
        return "fixed"
    if now.hour in {5, 19}:
        return "temporary"
    if now.hour in {6, 20}:
        return "restore"
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument(
        "--mode", choices=("auto", "fixed", "temporary", "restore", "repair-0050"),
        default="auto",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    now = datetime.now(TAIPEI)
    mode = resolve_auto_mode(now) if args.mode == "auto" else args.mode
    if not mode:
        print(f"No scheduled action at {now:%H:%M} Asia/Taipei; skipped")
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

    if mode == "fixed":
        return run_fixed(spreadsheet, sheets, now.date(), args.dry_run)
    if mode == "temporary":
        return run_temporary(spreadsheet, sheets, credentials, now.date(), args.dry_run)
    if mode == "repair-0050":
        return run_repair_0050(spreadsheet, sheets, args.dry_run)
    return run_restore(spreadsheet, sheets, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
