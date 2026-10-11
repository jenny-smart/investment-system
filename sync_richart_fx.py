"""把 Richart 賣外幣匯率寫進總帳「總覽」R 欄（Q 欄為 美金／南非／人民／日幣 的第一組）。"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from richart_fx import fetch_richart_rates

SPREADSHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"  # 2025Jenny-總帳
OVERVIEW_SHEET_ID = 1120619093  # 總覽
SHEET_LABELS = {"美金": "USD", "南非": "ZAR", "人民": "CNY", "日幣": "JPY"}


def find_rate_rows(q_column: list[list[str]]) -> dict[str, int]:
    """Q 欄每個幣別第一次出現的列號（1 起算）。"""
    rows: dict[str, int] = {}
    for row, values in enumerate(q_column, 1):
        code = SHEET_LABELS.get(str(values[0]).strip()) if values else None
        if code and code not in rows:
            rows[code] = row
    return rows


def build_updates(title: str, rows: dict[str, int], rates: dict[str, float]) -> list[dict]:
    quoted = "'" + title.replace("'", "''") + "'"
    return [{"range": f"{quoted}!R{row}", "values": [[rates[code]]]}
            for code, row in sorted(rows.items(), key=lambda item: item[1]) if code in rates]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    rates = fetch_richart_rates()
    print("Richart", json.dumps(rates, ensure_ascii=False))
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
    sheet = next(s for s in spreadsheet.worksheets() if s.id == OVERVIEW_SHEET_ID)
    rows = find_rate_rows(sheet.get(f"Q1:Q{min(sheet.row_count, 80)}"))
    missing = set(SHEET_LABELS.values()) - set(rows)
    if missing:
        raise RuntimeError(f"總覽 Q 欄找不到 {sorted(missing)}；未寫入")
    updates = build_updates(sheet.title, rows, rates)
    print(json.dumps({"dry_run": args.dry_run, "updates": updates}, ensure_ascii=False))
    if updates and not args.dry_run:
        spreadsheet.values_batch_update({"valueInputOption": "RAW", "data": updates})
        print(f"Updated {len(updates)} R cells")
    return 0 if len(updates) == len(SHEET_LABELS) else 1


if __name__ == "__main__":
    sys.exit(main())
