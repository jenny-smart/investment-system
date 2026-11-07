"""每檔基金的累計配息原幣以總帳「總覽」N 欄（累積配息原幣）為準。

由 fund-nav 排程（每 10 分鐘）一起跑：讀總覽各分類（基富通-台、渣打-美金…）下每檔基金的 N 欄，
跟資料庫持倉的累計配息原幣比對（原幣，不受匯率影響），不一致就把資料庫改成 N 欄
（同 App 配息記錄頁「🔄 以總帳 N 欄更新資料庫」）。
N 欄是 0 或空白的不動（避免讀到空白就把資料庫清掉）；資料庫沒有這檔持倉的也不動。

  python sync_fund_dividend_totals.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import pandas as pd

SPREADSHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"  # 2025Jenny-總帳
OVERVIEW_SHEET = "總覽"


def plan(sheet_rows, positions: pd.DataFrame):
    """→ [{"分類", "基金名稱", "總帳配息原幣", "資料庫配息原幣", "_position_id"}]：要改成總帳數字的基金。"""
    from invest_app.sheet_compare import compare_fund_dividends
    df = positions.copy()
    df["累計配息原幣"] = pd.to_numeric(df.get("dividend_received_original_total"), errors="coerce").fillna(0)
    diff = compare_fund_dividends(sheet_rows, df)
    ok = diff["總帳配息原幣"].notna() & (diff["總帳配息原幣"] > 0) & diff["_position_id"].notna()
    return diff[ok].to_dict("records")


def read_overview():
    import gspread
    from google.oauth2.service_account import Credentials
    info = json.loads(os.environ["INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    sheet = gspread.authorize(creds).open_by_key(SPREADSHEET_ID).worksheet(OVERVIEW_SHEET)
    return sheet.get_values(value_render_option="UNFORMATTED_VALUE")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from invest_app.core import load_positions
    from invest_app.dividends import set_position_dividend_original_total
    from invest_app.sheet_compare import sheet_fund_dividends

    sheet_rows = sheet_fund_dividends(read_overview())
    positions = load_positions()
    positions = positions[positions["asset_type"].astype(str) == "基金"]
    todo = plan(sheet_rows, positions)
    print(f"== 基金累計配息原幣以總覽 N 欄為準：{len(todo)} 檔要改")
    done = 0
    for r in todo:
        print(f"  {r['分類']} {r['基金名稱'][:24]}：{r['資料庫配息原幣'] or 0:,.2f} → {r['總帳配息原幣']:,.2f}")
        if not args.dry_run and set_position_dividend_original_total(int(float(r["_position_id"])),
                                                                     float(r["總帳配息原幣"])):
            done += 1
    if todo and not args.dry_run:
        print(f"已寫入 {done} 檔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
