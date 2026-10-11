"""Summarise one month of the 總帳 asset sheet into five categories and a net total.

The sheet rolls forward every month (a new detail/subtotal column pair is added)
and a new file may be used each year, so nothing here depends on fixed cell
addresses: the month column is found by its date in the first dated row, each category by its
first label in column A and the SUM() formula in the subtotal column that starts
on that row, and the total by following the subtotal formula just below the dates.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

DEFAULT_SPREADSHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"
DEFAULT_SHEET = "Jennyall"
RATE_SHEET = "總覽"
TAIPEI = ZoneInfo("Asia/Taipei")

# (summary name, column A label on the category's first row)
CATEGORIES = (
    ("銀行total", "零用金-淨值"),
    ("保險total", "台新保險"),
    ("懷思投資", "懷思"),
    ("uncle待還", "叔叔"),
    ("外幣total", "日幣 suica"),
)
# Money held for other people, in original currency.
DEFAULT_DEPOSITS = {"TWD": 1_500_000, "JPY": 300_000, "USD": 1400 + 960 + 960, "CNY": 5_000}
# Currency -> row label in 總覽 (rates use the 買進 column, like the sheet does).
RATE_LABELS = {"USD": "美金", "ZAR": "南非", "CNY": "人民", "JPY": "日幣"}

CELL = re.compile(r"\$?([A-Z]{1,3})\$?(\d+)")
SUM_RANGE = re.compile(r"^=\s*SUM\(\s*\$?([A-Z]{1,3})\$?(\d+)\s*:\s*\$?([A-Z]{1,3})\$?(\d+)\s*\)\s*$", re.I)
TERM = re.compile(r"([+-]?)\s*\$?([A-Z]{1,3})\$?(\d+)")


def col_index(letters):
    """'A' -> 0, 'GA' -> 182."""
    number = 0
    for char in letters.upper():
        number = number * 26 + ord(char) - 64
    return number - 1


def col_letters(index):
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def cell(grid, row, col):
    """1-based row, 0-based column; missing cells are ''."""
    if row - 1 < len(grid) and col < len(grid[row - 1]):
        return grid[row - 1][col]
    return ""


def number(value):
    if value in ("", None):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_date(value):
    text = str(value).strip()
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def parse_month(text):
    """'2026/10' or '2026-10-01' -> date(2026, 10, 1)."""
    match = re.fullmatch(r"(\d{4})[/-](\d{1,2})(?:[/-]\d{1,2})?", text.strip())
    if not match:
        raise ValueError(f"月份格式應為 YYYY/M：{text}")
    return date(int(match[1]), int(match[2]), 1)


def date_row(values):
    """First row holding month dates (row 1 in the current sheet)."""
    for row, line in enumerate(values, 1):
        if any(parse_date(v) for v in line):
            return row
    raise RuntimeError("找不到月份日期列")


def find_month_column(values, month=None, today=None):
    """Return the 0-based subtotal column whose date-row date is the requested month.

    Without a month, use the latest dated column not after today; the sheet
    carries future months forward as copies, so those are skipped.
    """
    dated = [(col, d) for col, v in enumerate(values[date_row(values) - 1])
             if (d := parse_date(v))]
    if month:
        for col, d in dated:
            if (d.year, d.month) == (month.year, month.month):
                return col
        raise RuntimeError(f"找不到 {month:%Y/%m} 的欄位")
    today = today or datetime.now(TAIPEI).date()
    past = [(d, -col) for col, d in dated if d <= today]
    if not past:
        raise RuntimeError("沒有早於今天的月份欄")
    return -max(past)[1]


def find_label_row(values, label, start=1):
    for row in range(start, len(values) + 1):
        if str(cell(values, row, 0)).strip() == label:
            return row
    raise RuntimeError(f"A 欄找不到「{label}」")


def find_category(values, formulas, sub_col, label):
    """Locate the SUM(detail start:end) subtotal that begins on `label`'s row."""
    start = find_label_row(values, label)
    for row in range(start, len(formulas) + 1):
        match = SUM_RANGE.match(str(cell(formulas, row, sub_col)))
        if match and int(match[2]) == start and match[1] == match[3]:
            detail_col, end = col_index(match[1]), int(match[4])
            items = [(str(cell(values, r, 0)).strip(), number(cell(values, r, detail_col)))
                     for r in range(start, end + 1)]
            return {
                "rows": [start, end],
                "cell": f"{col_letters(sub_col)}{row}",
                "total": number(cell(values, row, sub_col)),
                "items": items,
            }
    raise RuntimeError(f"「{label}」那列之後的 {col_letters(sub_col)} 欄找不到 =SUM({col_letters(sub_col - 1)}{start}:…) 小計")


def follow(formulas, row, col):
    """If a cell is just '=X12', return (row, col) of X12, else None."""
    match = re.fullmatch(r"=\s*\$?([A-Z]{1,3})\$?(\d+)\s*", str(cell(formulas, row, col)))
    return (int(match[2]), col_index(match[1])) if match else None


def find_total(values, formulas, sub_col):
    """Sheet net total (row under the dates) and the cells it subtracts (existing deposits)."""
    row, col = date_row(values) + 1, sub_col
    for _ in range(5):
        target = follow(formulas, row, col)
        if not target:
            break
        row, col = target
    formula = str(cell(formulas, row, col))
    minus = [(int(r), col_index(c)) for sign, c, r in TERM.findall(formula) if sign == "-"]
    return {
        "cell": f"{col_letters(col)}{row}",
        "net": number(cell(values, row, col)),
        "subtracted": [{"cell": f"{col_letters(c)}{r}", "value": number(cell(values, r, c))}
                       for r, c in minus],
    }


def read_rates(rate_values):
    """總覽 rows like ['美金', 賣出, 買進] anywhere on the sheet -> {'USD': 買進}."""
    rates = {}
    for line in rate_values:
        for i, text in enumerate(line):
            for currency, label in RATE_LABELS.items():
                if str(text).strip() == label and i + 2 < len(line) and number(line[i + 2]):
                    rates.setdefault(currency, number(line[i + 2]))
    return rates


def summarise(values, formulas, rate_values, deposits, rate_overrides=None, month=None, today=None):
    sub_col = find_month_column(values, month, today)
    rates = {"TWD": 1.0, **read_rates(rate_values), **(rate_overrides or {})}
    missing = [c for c in deposits if c not in rates]
    if missing:
        raise RuntimeError(f"缺少匯率：{', '.join(missing)}（用 --rate {missing[0]}=數字 指定）")
    categories = {name: find_category(values, formulas, sub_col, label) for name, label in CATEGORIES}
    total = find_total(values, formulas, sub_col)
    gross = total["net"] + sum(item["value"] for item in total["subtracted"])
    category_sum = sum(c["total"] for c in categories.values())
    deposit_lines = [{"currency": cur, "amount": amt, "rate": rates[cur], "twd": amt * rates[cur]}
                     for cur, amt in deposits.items()]
    deposit_twd = round(sum(line["twd"] for line in deposit_lines))
    return {
        "month": str(cell(values, date_row(values), sub_col)),
        "column": col_letters(sub_col),
        "categories": categories,
        "category_sum": category_sum,
        "other": gross - category_sum,
        "gross": gross,
        "sheet_total": total,
        "deposits": deposit_lines,
        "deposit_twd": deposit_twd,
        "net": gross - deposit_twd,
    }


def render(summary):
    fmt = "{:>16,.0f}".format
    lines = [f"月份 {summary['month']}（小計欄 {summary['column']}）", ""]
    for name, data in summary["categories"].items():
        lines.append(f"{name:<12}{fmt(data['total'])}   列 {data['rows'][0]}-{data['rows'][1]}")
        for label, value in data["items"]:
            if value:
                lines.append(f"    {label or '(無名稱)':<14}{fmt(value)}")
    lines += [
        f"{'五項小計':<12}{fmt(summary['category_sum'])}",
        f"{'其他(股票基金等)':<10}{fmt(summary['other'])}",
        f"{'資產總額(含寄放)':<10}{fmt(summary['gross'])}",
        "",
        "寄放：",
    ]
    for d in summary["deposits"]:
        lines.append(f"    {d['currency']} {d['amount']:>12,.0f} × {d['rate']:<8g}{fmt(d['twd'])}")
    lines += [
        f"{'寄放合計':<12}{fmt(summary['deposit_twd'])}",
        f"{'資產淨額':<12}{fmt(summary['net'])}",
    ]
    sheet = summary["sheet_total"]
    if round(sheet["net"]) != round(summary["net"]):
        old = ", ".join(f"{s['cell']}={s['value']:,.0f}" for s in sheet["subtracted"])
        lines.append(f"（試算表 {sheet['cell']} 為 {sheet['net']:,.0f}，扣的是 {old}）")
    return "\n".join(lines)


def spreadsheet_key(text):
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", text)
    return match[1] if match else text.strip()


def pairs(items, cast):
    result = {}
    for item in items or []:
        key, _, value = item.partition("=")
        if not value:
            raise SystemExit(f"格式應為 幣別=數字：{item}")
        result[key.strip().upper()] = cast(value.replace(",", ""))
    return result


def open_spreadsheet(key, credentials_file):
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    if credentials_file:
        credentials = Credentials.from_service_account_file(str(credentials_file), scopes=scopes)
    else:
        raw = os.environ.get("INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if not raw:
            raise RuntimeError("Missing INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON")
        credentials = Credentials.from_service_account_info(json.loads(raw), scopes=scopes)
    return gspread.authorize(credentials).open_by_key(key)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spreadsheet", default=os.environ.get("ASSET_SPREADSHEET", DEFAULT_SPREADSHEET_ID),
                        help="試算表網址或 ID（換檔時指定）")
    parser.add_argument("--sheet", default=os.environ.get("ASSET_SHEET", DEFAULT_SHEET), help="分頁名稱")
    parser.add_argument("--month", type=parse_month, help="YYYY/M，預設為今天以前最新的月份欄")
    parser.add_argument("--deposit", action="append", metavar="CUR=AMOUNT",
                        help="寄放金額，可重複；有指定就取代預設 TWD=1500000 JPY=300000 USD=3320 CNY=5000")
    parser.add_argument("--rate", action="append", metavar="CUR=RATE", help="覆寫匯率，例如 USD=32")
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument("--json", action="store_true", help="輸出 JSON")
    args = parser.parse_args(argv)

    spreadsheet = open_spreadsheet(spreadsheet_key(args.spreadsheet), args.credentials_file)
    sheet = spreadsheet.worksheet(args.sheet)
    values = sheet.get_values(value_render_option="UNFORMATTED_VALUE", date_time_render_option="FORMATTED_STRING")
    formulas = sheet.get_values(value_render_option="FORMULA")
    try:
        rate_values = spreadsheet.worksheet(RATE_SHEET).get_values()
    except Exception:
        rate_values = []
    summary = summarise(values, formulas, rate_values,
                        pairs(args.deposit, float) or dict(DEFAULT_DEPOSITS),
                        pairs(args.rate, float), args.month)
    print(json.dumps(summary, ensure_ascii=False, indent=2) if args.json else render(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
