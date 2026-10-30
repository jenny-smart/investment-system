"""Refresh US stock quote dates (G) and prices (H) on the 總覽 sheet by ticker (F)."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

SPREADSHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"
SHEET_TITLE = "總覽"
SECTION_HEADER = "美股"
TAIPEI = ZoneInfo("Asia/Taipei")


def normalize_ticker(value):
    text = str(value or "").strip().upper()
    return text if re.fullmatch(r"[A-Z][A-Z.\-]{0,9}", text) else None


def find_tickers(column):
    """Rows below the 美股 header in F, up to the first blank cell."""
    found, in_section = [], False
    for row, values in enumerate(column, start=1):
        text = str(values[0] if values else "").strip()
        if not in_section:
            in_section = text == SECTION_HEADER
            continue
        if not text:
            break
        ticker = normalize_ticker(text)
        if ticker:
            found.append((row, ticker))
    return found


def valid_price(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def fetch_quote(ticker):
    import yfinance as yf
    try:
        closes = yf.Ticker(ticker).history(period="5d", auto_adjust=False)["Close"].dropna()
    except Exception as exc:
        print(f"{ticker}: Yahoo unavailable ({type(exc).__name__})", file=sys.stderr)
        return None
    if closes.empty or not valid_price(closes.iloc[-1]):
        return None
    return {"price": round(float(closes.iloc[-1]), 4), "date": closes.index[-1].strftime("%Y/%m/%d")}


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
    sheet = gspread.authorize(credentials).open_by_key(SPREADSHEET_ID).worksheet(SHEET_TITLE)

    tickers = find_tickers(sheet.get("F1:F200"))
    if not tickers:
        print(f"No tickers found under {SECTION_HEADER} in F; no cells changed")
        return 1
    updates, problems = [], []
    for row, ticker in tickers:
        quote = fetch_quote(ticker)
        if quote:
            print(f"F{row} {ticker} -> {quote['date']} {quote['price']}")
            updates.append({"range": f"G{row}:H{row}", "values": [[quote["date"], quote["price"]]]})
        else:
            problems.append(f"F{row} 抓不到股價: {ticker}")
            print(f"WARN {problems[-1]}")
    if args.dry_run or not updates:
        return 1 if problems or not updates else 0
    sheet.batch_update(updates, value_input_option="USER_ENTERED")
    print(f"Updated {len(updates)} rows at {datetime.now(TAIPEI):%Y/%m/%d %H:%M} Asia/Taipei")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
