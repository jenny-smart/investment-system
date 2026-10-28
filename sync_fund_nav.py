"""Refresh fund NAV dates (G) and NAVs (H) on the 總覽 sheet by fund name (F)."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import unicodedata
import urllib.parse
from zoneinfo import ZoneInfo

SPREADSHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"
SHEET_TITLE = "總覽"
TAIPEI = ZoneInfo("Asia/Taipei")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

# (keywords that must all appear in the normalized name, MoneyDJ code, MoneyDJ pattern, 鉅亨 ID)
FUND_RULES = (
    (("富蘭克林華美新興國家", "新臺幣"), "acft94", "yp010000", "A3DaDtj"),
    (("富蘭克林華美新興國家", "人民幣"), "acft99", "yp010000", "A4OhWL3"),
    (("柏瑞新興邊境",), "acai222", "yp010000", "A2h9QYl"),
    (("貝萊德全球智慧數據",), "shzx0", "yp010001", "B090478"),
    (("安聯收益成長",), "TLZO3", "yp010001", "B200269"),
    (("大華銀新加坡房地產",), "acob36", "yp010000", "A48IfHn"),
    (("東方匯理", "南非"), "pizm9", "yp010001", "B32,253"),
    (("東方匯理", "A美元"), "pizn8", "yp010001", "B1MVJRY"),
    (("東方匯理", "U美元"), "pizo1", "yp010001", "B27DOWV"),
    (("高盛新興市場債券", "南非"), "ANZH2", "yp010001", "B33,171"),
    (("高盛新興市場債券", "美元"), "anzb6", "yp010001", "B33,131"),
)


def normalize_name(name):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(name or "")))


def match_fund(name):
    text = normalize_name(name)
    if not text:
        return None
    for keywords, code, pattern, cnyes_id in FUND_RULES:
        if all(keyword in text for keyword in keywords):
            return {"code": code, "pattern": pattern, "cnyes_id": cnyes_id}
    return None


def valid_nav(value):
    try:
        nav = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return nav if 0 < nav < 100000 else None


def parse_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) or str(value).isdigit():
        stamp = float(value)
        if stamp > 1e11:
            stamp /= 1000
        return datetime.fromtimestamp(stamp, TAIPEI).strftime("%Y/%m/%d")
    match = re.search(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", str(value))
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    return f"{year:04d}/{month:02d}/{day:02d}"


def parse_cnyes_payload(payload):
    items = ((payload or {}).get("data") or {}).get("items") or []
    for item in items:
        nav = next((valid_nav(item.get(key)) for key in ("nav", "NAV", "navPrice", "net", "unitNav")
                    if valid_nav(item.get(key))), None)
        date = next((parse_date(item.get(key)) for key in ("tradeDate", "navDate", "date", "priceDate")
                     if parse_date(item.get(key))), None)
        if nav and date:
            return {"nav": nav, "date": date}
    return None


def parse_moneydj_html(html):
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text).replace(",", "").replace("&nbsp;", " ")
    text = re.sub(r"\s+", " ", text)
    for pattern in (
        r"淨值日期\s+最新淨值.*?(20\d{2}/\d{1,2}/\d{1,2})\s+([0-9]+(?:\.[0-9]+)?)",
        r"(20\d{2}/\d{1,2}/\d{1,2})\s+([0-9]+(?:\.[0-9]+)?)",
    ):
        match = re.search(pattern, text, flags=re.S)
        if match and valid_nav(match.group(2)):
            return {"nav": valid_nav(match.group(2)), "date": parse_date(match.group(1))}
    return None


def fetch_cnyes(session, cnyes_id):
    encoded = urllib.parse.quote(cnyes_id, safe="")
    headers = {**HEADERS, "Referer": "https://fund.cnyes.com/", "Origin": "https://fund.cnyes.com"}
    for url in (
        f"https://fund.api.cnyes.com/fund/api/v1/funds/{encoded}/nav?format=table&page=1",
        f"https://fund.api.cnyes.com/fund/api/v2/funds/{encoded}/nav?format=json",
    ):
        try:
            response = session.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                quote = parse_cnyes_payload(response.json())
                if quote:
                    return quote
        except Exception as exc:  # noqa: BLE001 - try the next source
            print(f"  鉅亨錯誤 {cnyes_id}: {str(exc)[:80]}")
    return None


def fetch_moneydj(session, code, pattern):
    try:
        response = session.get(
            f"https://www.moneydj.com/funddj/ya/{pattern}.djhtm?a={code}",
            headers={**HEADERS, "Referer": "https://www.moneydj.com/"}, timeout=15,
        )
        if response.status_code == 200:
            for encoding in ("big5", "cp950", "utf-8"):
                try:
                    return parse_moneydj_html(response.content.decode(encoding))
                except UnicodeDecodeError:
                    continue
    except Exception as exc:  # noqa: BLE001
        print(f"  MoneyDJ錯誤 {code}: {str(exc)[:80]}")
    return None


def fetch_quote(session, fund):
    quote = fetch_cnyes(session, fund["cnyes_id"])
    if quote:
        return {**quote, "source": "鉅亨"}
    quote = fetch_moneydj(session, fund["code"], fund["pattern"])
    if quote:
        return {**quote, "source": "MoneyDJ"}
    return None


def plan_updates(rows, fetch):
    """rows: list of [F, G, H] starting at row 1. Returns (updates, problems)."""
    updates, problems, cache = [], [], {}
    for index, row in enumerate(rows, start=1):
        name = (row + ["", "", ""])[0]
        fund = match_fund(name)
        if not fund:
            if len(normalize_name(name)) > 8 and re.search(r"[\u4e00-\u9fff]", name):
                problems.append(f"F{index} 無對照代碼: {name}")
            continue
        if fund["code"] not in cache:
            cache[fund["code"]] = fetch(fund)
        quote = cache[fund["code"]]
        if not quote:
            problems.append(f"F{index} 抓不到淨值: {name}")
            continue
        updates.append({"row": index, "name": name, **quote})
    return updates, problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    import gspread
    import requests
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
    rows = sheet.get("F1:H200")

    session = requests.Session()
    updates, problems = plan_updates(rows, lambda fund: fetch_quote(session, fund))
    for item in updates:
        print(f"F{item['row']} {item['name']} -> {item['date']} {item['nav']} ({item['source']})")
    for problem in problems:
        print(f"WARN {problem}")
    if not updates:
        print("No NAV fetched; no cells changed")
        return 1
    if args.dry_run:
        print(f"Dry run: {len(updates)} rows would be written")
        return 1 if problems else 0
    sheet.batch_update(
        [{"range": f"G{item['row']}:H{item['row']}", "values": [[item["date"], item["nav"]]]}
         for item in updates],
        value_input_option="USER_ENTERED",
    )
    print(f"Updated {len(updates)} rows at {datetime.now(TAIPEI):%Y/%m/%d %H:%M} Asia/Taipei")
    if problems:
        # Rows did get written above; this only fails the *run* so skipped/unmatched
        # funds show up as a red X instead of silently going stale (previously this
        # returned 0 as long as >=1 fund updated, so e.g. an unconfigured fund like
        # 富蘭克林坦伯頓-科技 could sit at #N/A indefinitely with every run green).
        print(f"FAILED: {len(problems)} row(s) not synced — see WARN lines above")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
