"""把每次銀行明細／信用卡帳單的執行結果，寫進 investment-system-log 試算表的「investment-system執行Log」分頁
（跟基金、台股等排程同一張，系統欄寫「銀行明細」）。

只寫摘要：哪家、哪些帳戶、查詢期間、各抓到幾筆新交易、是否登出、錯誤訊息。**不寫金額、交易內容或完整帳號。**
用本機 google-login 的授權寫入；寫不進去只印警告，不影響抓明細。
"""
from __future__ import annotations

import socket
import sys
from datetime import date, datetime
from pathlib import Path

SUBSYSTEM = "銀行明細"


def summarize_accounts(results: list[dict]) -> str:
    parts = []
    for block in results or []:
        name = block.get("account", "")
        n = len(block.get("rows") or [])
        err = block.get("error") or block.get("note") or ""
        parts.append(f"{name}：新 {n} 筆" + (f"（{err}）" if err else ""))
    return "；".join(parts) or "沒有查到任何帳戶"


def log_run(function: str, since: date | None, target: Path | str, results: list[dict], problem: str = "",
            logged_out: str = "", message: str = "") -> None:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import gspread
        from run_log import HEADERS, LOG_SHEET_TITLE, LOG_SPREADSHEET_ID, build_row
        from .google_auth import credentials
        book = gspread.authorize(credentials()).open_by_key(LOG_SPREADSHEET_ID)
        sheet = book.worksheet(LOG_SHEET_TITLE)
        header = sheet.row_values(1) or HEADERS
        message = message or summarize_accounts(results)
        if problem:
            message = f"⚠️ {problem}｜{message}"
        if logged_out:
            message += f"｜{logged_out}"
        period = f"{since:%Y/%m/%d}～{date.today():%Y/%m/%d}" if since else f"{date.today():%Y/%m/%d}"
        row = build_row(header, {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "system": SUBSYSTEM, "function": function,
            "run_type": "本機手動", "period": period, "target": str(target).replace(str(Path.home()), "~"),
            "result": "失敗" if problem and not (results or message) else ("部分完成" if problem else "成功"),
            "message": message[:1500], "operator": f"Jenny Mac（{socket.gethostname().split('.')[0]}）",
        })
        if row is None:
            print("⚠️ 執行記錄分頁的標題認不得，沒寫入")
            return
        sheet.append_row(row, value_input_option="USER_ENTERED")
        print(f"📝 已寫入執行記錄（investment-system執行Log）：{function}")
    except (Exception, SystemExit) as exc:  # 沒有 Google 授權時 credentials() 會 SystemExit
        print(f"⚠️ 執行記錄沒寫進去（不影響明細）：{type(exc).__name__}: {exc}")
