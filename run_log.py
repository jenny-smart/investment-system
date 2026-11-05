"""把排程執行結果寫進「更新記錄」試算表（每個 workflow 最後一步呼叫，永遠不讓執行失敗）。

位置：試算表 1oCblr-zksaLsmK10i20PLMeDZtzk22N8QyyMuivwPOw 的 gid 613651036 分頁
（可用環境變數 INVESTMENT_LOG_SPREADSHEET_ID、INVESTMENT_LOG_SHEET_GID 改）。
服務帳號（INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON）要是這個試算表的編輯者。

欄位依分頁第 1 列標題對應（執行時間、系統、功能、執行方式、期別/日期、目標位置、結果、訊息…，
常見同義字也認得）；第 1 列空白時寫入各系統統一的執行 Log 標題。都對不上就不寫，只印警告。

寫哪些：
- 有寫入資料的成功執行（輸出裡有 Updated／已寫入）、或加 --always 的功能 → 成功
- 失敗或取消 → 失敗／已取消；同一功能當天最後一筆已是同樣的錯誤就不重複寫
- 時段外略過、資料沒變、App 喚醒成功 → 不寫

  python run_log.py --function 台股價格 --target "台股 J 欄" --status success --output run.out
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
SYSTEM = "investment-system"
LOG_SPREADSHEET_ID = os.environ.get("INVESTMENT_LOG_SPREADSHEET_ID", "1oCblr-zksaLsmK10i20PLMeDZtzk22N8QyyMuivwPOw")
LOG_SHEET_GID = int(os.environ.get("INVESTMENT_LOG_SHEET_GID", "613651036"))
# 與 tool-system／orders-system 等系統的執行 Log 相同欄位
HEADERS = ["執行時間", "系統", "功能", "執行方式", "區域", "期別/日期", "目標位置", "來源檔案", "結果", "訊息", "執行者"]
ALIASES = {
    "time": ("執行時間", "時間", "更新時間", "記錄時間", "日期時間"),
    "system": ("系統", "系統名稱"),
    "function": ("功能", "功能名稱", "項目", "工作", "排程"),
    "run_type": ("執行方式", "觸發方式", "方式"),
    "period": ("期別/日期", "期別", "資料日期", "日期"),
    "target": ("目標位置", "目標", "工作表", "位置"),
    "result": ("結果", "狀態"),
    "message": ("訊息", "說明", "內容", "更新內容", "備註"),
    "operator": ("執行者",),
    "link": ("連結", "執行紀錄", "Run"),
}
# 有寫入的訊號（「已寫入 0 格」不算）
WRITE_MARKERS = re.compile(r"^\s*(Updated [1-9]|已寫入 *[1-9]|✅)", re.M)
KEEP_LINES = re.compile(r"^\s*(Updated |已寫入 *[1-9]|✅|WARN|⚠️|FAILED|ERROR|❌|\S*Error\b|固定：|月底淨值回填|.*格要改)",
                        re.M)
MESSAGE_LIMIT = 1500


def norm(text):
    return re.sub(r"[\s／/]", "", str(text or "")).lower()


def column_map(header):
    """field -> 0-based column, matched by header text."""
    names = [norm(h) for h in header]
    found = {}
    for field, aliases in ALIASES.items():
        for alias in aliases:
            if norm(alias) in names:
                found[field] = names.index(norm(alias))
                break
    return found


def result_of(status):
    return {"success": "成功", "failure": "失敗", "cancelled": "已取消"}.get(status, status or "失敗")


def summarize(output):
    """Key lines of the run output (writes, warnings, errors); else its last 3 lines."""
    picked = [line.strip() for line in output.splitlines() if KEEP_LINES.match(line)]
    if not picked:
        picked = [line.strip() for line in output.splitlines() if line.strip()][-3:]
    return "；".join(dict.fromkeys(picked))[:MESSAGE_LIMIT]  # keep order, drop repeats


def should_log(status, output, always=False):
    if status != "success":
        return True
    return always or bool(WRITE_MARKERS.search(output))


def build_row(header, fields):
    cols = column_map(header)
    # 一定要有時間、功能、結果三欄才算執行記錄分頁（避免寫進股票明細之類的資料分頁）
    if not {"time", "function", "result"} <= set(cols):
        return None
    row = [""] * len(header)
    for field, col in cols.items():
        row[col] = fields.get(field, "")
    if "link" not in cols and fields.get("link") and "message" in cols:
        row[cols["message"]] = f"{row[cols['message']]}｜{fields['link']}".strip("｜")
    return row


def is_repeat(header, recent, fields):
    """Same function failed with the same message already today (avoid a row every 10 minutes)."""
    cols = column_map(header)
    if fields["result"] == "成功" or not {"function", "result", "message", "time"} <= set(cols):
        return False
    for row in reversed(recent):
        row = list(row) + [""] * len(header)
        if row[cols["function"]] != fields["function"]:
            continue
        same_day = str(row[cols["time"]])[:10] == fields["time"][:10]
        same = row[cols["result"]] == fields["result"] and \
            str(row[cols["message"]]).split("｜")[0] == fields["message"]
        return same_day and same
    return False


def open_log_sheet():
    import gspread
    from google.oauth2.service_account import Credentials
    raw = os.environ.get("INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        raise RuntimeError("Missing INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON")
    credentials = Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    book = gspread.authorize(credentials).open_by_key(LOG_SPREADSHEET_ID)
    return book.get_worksheet_by_id(LOG_SHEET_GID)


def write(fields, sheet=None):
    sheet = sheet or open_log_sheet()
    header = sheet.row_values(1)
    if not any(str(h).strip() for h in header):
        sheet.update([HEADERS], "A1")
        header = HEADERS
    row = build_row(header, fields)
    if row is None:
        print(f"WARN 更新記錄分頁第 1 列沒有認得的欄位（{header}），未寫入")
        return False
    if fields["result"] != "成功":
        last = max(len(sheet.col_values(1)), 1)
        recent = sheet.get_values(f"{max(2, last - 200)}:{last}") if last > 1 else []
        if is_repeat(header, [r for r in recent if any(r)], fields):
            print("同樣的錯誤今天已記錄過，略過")
            return False
    sheet.append_row(row, value_input_option="RAW", table_range="A1")
    print(f"已寫入更新記錄：{fields['function']} {fields['result']}")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--function", required=True, help="功能名稱，例如 台股價格")
    parser.add_argument("--target", default="", help="目標位置，例如 總帳 總覽 G/H")
    parser.add_argument("--status", default="success", help="GitHub job.status：success／failure／cancelled")
    parser.add_argument("--output", type=Path, help="這次執行的輸出（tee 下來的檔案）")
    parser.add_argument("--period", default="", help="期別/日期，預設今天")
    parser.add_argument("--always", action="store_true", help="成功也一定寫（每天一兩次的功能）")
    parser.add_argument("--dry-run", action="store_true", help="這次是預覽")
    args = parser.parse_args(argv)
    try:
        output = args.output.read_text(encoding="utf-8", errors="replace") if args.output and args.output.exists() else ""
        if not should_log(args.status, output, args.always):
            print("沒有寫入資料、也沒有失敗，不寫更新記錄")
            return 0
        now = datetime.now(TAIPEI)
        slot = os.environ.get("SCHEDULED_SLOT", "")
        run_type = "排程" if slot else "手動／App"
        if args.dry_run:
            run_type += "（預覽）"
        server, repo, run_id = (os.environ.get(k, "") for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
        fields = {
            "time": f"{now:%Y-%m-%d %H:%M:%S}", "system": SYSTEM, "function": args.function,
            "run_type": run_type, "period": args.period or f"{now:%Y-%m-%d}", "target": args.target,
            "result": result_of(args.status), "message": summarize(output), "operator": "GitHub Actions",
            "link": f"{server}/{repo}/actions/runs/{run_id}" if run_id else "",
        }
        write(fields)
    except Exception as exc:  # noqa: BLE001 - logging must never fail the run
        print(f"WARN 更新記錄寫入失敗：{type(exc).__name__} {str(exc)[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
