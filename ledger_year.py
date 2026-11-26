"""新年度「YYYY細帳」自動建立（2026-11-26 Jenny）。

各程式要用「{年}細帳」時先呼叫 ensure_ledger(book, 年)；分頁不存在（或是舊格式）就從前一年度細帳建立：
1. 複製「{前一年}細帳」成「{年}細帳」（放在前一年度後面）。
2. A1＝年度；B1＝「{前一年}-12」；C1～N1 是 =$A1&"-1" 這類公式，跟著 A1 變。
3. B 欄（上年 12 月）：='{前前一年}細帳'!N{列} 改成 ='{前一年}細帳'!N{列}。
4. C～N 欄（1～12 月）清掉手打金額：
   - 數字、只有數字運算的公式（=195+70+105）→ 清空
   - 有儲存格參照的公式（=B38+C34+2000000-195）→ 只留參照的部分（=B38+C34），餘額、加總照樣算
   - 這幾欄的備註一起清掉
   O 欄以後（合計、旁邊的試算）不動。
已經有「{年}細帳」但 A 欄項目跟前一年度對不起來（例如舊範本 food／clothes…）：
改名成「{年}細帳_舊版YYYYMMDD」保留，再重新建立。
"""
from __future__ import annotations

import re
from datetime import date
from typing import Callable, List, Optional

MONTH_FIRST_COL, MONTH_LAST_COL = 3, 14   # C～N（1 起算）
MATCH_RATIO = 0.8                          # A 欄項目有八成以上跟前一年度相同才算同格式

_REF = re.compile(r"(?:'[^']+'|[A-Za-z_][\w.]*)?!?\$?[A-Z]{1,3}\$?\d+|[A-Z]{1,3}:[A-Z]{1,3}|[A-Za-z_]+\(")
_CONST_TERM = re.compile(r"^[\d.,*/()\s%]+$")


def ledger_title(year: int) -> str:
    return f"{year}細帳"


def _split_terms(body: str) -> List[str]:
    """最外層依 + - 切開（保留正負號）：'B38+C34-195' → ['B38', '+C34', '-195']。"""
    terms, depth, quote, start = [], 0, False, 0
    for i, ch in enumerate(body):
        if ch == '"':
            quote = not quote
        elif quote:
            continue
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch in "+-" and depth == 0 and i > start and body[i - 1] not in "Ee*/^(":
            terms.append(body[start:i])
            start = i
    terms.append(body[start:])
    return [t for t in terms if t.strip()]


def strip_entries(value) -> str:
    """月份格：手打金額清掉，只留有儲存格參照的公式部分。"""
    text = str(value or "").strip()
    if not text.startswith("="):
        return ""
    body = text[1:]
    if not _REF.search(body):
        return ""
    kept = [t for t in _split_terms(body) if not _CONST_TERM.match(t.lstrip("+-").strip())]
    if not kept:
        return ""
    joined = "".join(kept)
    return "=" + (joined[1:] if joined.startswith("+") else joined)


def compatible(labels: List[str], prev_labels: List[str]) -> bool:
    """A 欄項目（第 1 列是年度，不比）有八成以上跟前一年度相同。"""
    wanted = [str(x).strip() for x in prev_labels[1:] if str(x).strip()]
    if not wanted:
        return True
    have = {str(x).strip() for x in labels[1:]}
    return sum(1 for x in wanted if x in have) / len(wanted) >= MATCH_RATIO


def plan_values(prev_formulas: List[List[str]], year: int) -> List[List[str]]:
    """前一年度細帳（FORMULA）→ 新年度 A1:N 要寫的內容。"""
    old_ref, new_ref = f"'{year - 2}細帳'!", f"'{year - 1}細帳'!"
    out = []
    for r, row in enumerate(prev_formulas, start=1):
        row = list(row) + [""] * (MONTH_LAST_COL - len(row))
        new = list(row[:MONTH_LAST_COL])
        if r == 1:
            new[0] = str(year)
            new[1] = f"{year - 1}-12"
        else:
            new[1] = str(row[1]).replace(old_ref, new_ref) if str(row[1]).startswith("=") else row[1]
            for c in range(MONTH_FIRST_COL - 1, MONTH_LAST_COL):
                new[c] = strip_entries(row[c])
        out.append(new)
    return out


def ensure_ledger(book, year: int, log: Callable[[str], None] = print, today: Optional[date] = None):
    """回傳「{year}細帳」工作表；沒有（或是舊格式）就從前一年度建立。"""
    import gspread

    title = ledger_title(year)
    try:
        ws = book.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = None
    try:
        prev = book.worksheet(ledger_title(year - 1))
    except Exception as exc:  # 沒有前一年度（或讀不到）：有現成的就照用
        if ws is not None:
            return ws
        raise RuntimeError(f"找不到「{title}」，也沒有「{ledger_title(year - 1)}」可以複製") from exc
    if ws is not None:
        try:
            same = compatible(ws.col_values(1), prev.col_values(1))
        except Exception as exc:  # 檢查不了格式就照用現成的，不擋住原本的功能
            log(f"WARN 無法比對「{title}」格式，照用現有分頁：{type(exc).__name__}: {exc}")
            return ws
        if same:
            return ws
        old_title = f"{title}_舊版{(today or date.today()):%Y%m%d}"
        ws.update_title(old_title)
        log(f"「{title}」是舊格式（A 欄項目和 {ledger_title(year - 1)} 對不起來），改名為「{old_title}」保留")
    formulas = prev.get(f"A1:N{prev.row_count}", value_render_option="FORMULA")
    new = book.duplicate_sheet(prev.id, insert_sheet_index=prev.index + 1, new_sheet_name=title)
    values = plan_values(formulas, year)
    new.update(range_name=f"A1:N{len(values)}", values=values, value_input_option="USER_ENTERED")
    book.batch_update({"requests": [{"updateCells": {
        "range": {"sheetId": new.id, "startRowIndex": 1, "startColumnIndex": MONTH_FIRST_COL - 1,
                  "endColumnIndex": MONTH_LAST_COL},
        "fields": "note"}}]})
    log(f"✅ 已從「{ledger_title(year - 1)}」建立「{title}」：B 欄改接 {year - 1} 年 12 月，1～12 月手打金額與備註已清空")
    return new


def main() -> int:
    import argparse

    from bank_sync.google_auth import credentials
    from bank_sync.ledger_sync import open_book

    parser = argparse.ArgumentParser(description="建立新年度「YYYY細帳」")
    parser.add_argument("--year", type=int, default=date.today().year + 1)
    args = parser.parse_args()
    ensure_ledger(open_book(credentials()), args.year)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
