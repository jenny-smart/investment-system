"""台指期夜盤每日整理（早上 07:00 由 tool-system 排程設定派送 night-futures.yml）。

資料來源
- 期交所「期貨每日交易行情下載」（futDataDown，臺股期貨 TX，近 4 週）：
  日盤（一般）與夜盤（盤後）的開高低收、成交量。
  夜盤的「交易日期」是期交所的歸屬日：例如 11/9 15:00～11/10 05:00 的夜盤記在 11/10。
  所以「夜盤 N」對應的日盤是 N 之前最近一個有日盤資料的交易日。
- 期交所「三大法人－區分各期貨契約－夜盤」（futContractsDateAh）：外資臺股期貨多空淨額。
- Yahoo Finance（yfinance）：美股四大指數、費半、台積電 ADR、USD/TWD、加權指數、台積電。
- Google News RSS：台股／台指期／美股 近一天新聞標題。

成交量：每個時段把 TX 各到期月份（不含價差單）的成交量加總。
夜盤量佔比 = 夜盤成交量 ÷（日盤成交量 ＋ 夜盤成交量）。

輸出
- data/night_futures/latest.json：頁籤顯示用（最新一筆夜盤＋國際盤＋開盤預估＋新聞）
- data/night_futures/history.csv：每晚一列（日盤量、夜盤量、佔比、外資夜盤淨額…）

  python -m night_futures.pipeline              # 抓資料並寫檔
  python -m night_futures.pipeline --wait 20    # 夜盤還沒公布就每 5 分鐘重抓，最多等 20 分鐘
  python -m night_futures.pipeline --dry-run    # 只印結果不寫檔
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests

BASE = Path(__file__).resolve().parents[1]
DATA_DIR = BASE / "data" / "night_futures"
LATEST_PATH = DATA_DIR / "latest.json"
HISTORY_PATH = DATA_DIR / "history.csv"
TW_TZ = timezone(timedelta(hours=8))
HEADERS = {"User-Agent": "Mozilla/5.0 (investment-system night-futures)"}

FUT_DOWNLOAD_URL = "https://www.taifex.com.tw/cht/3/futDataDown"
FUT_OPENAPI_URL = "https://openapi.taifex.com.tw/v1/DailyMarketReportFut"
FOREIGN_NIGHT_URL = "https://www.taifex.com.tw/cht/3/futContractsDateAh"
NEWS_RSS_URL = "https://news.google.com/rss/search"

DAY = "一般"
NIGHT = "盤後"

GLOBAL_SYMBOLS = [
    ("道瓊", "^DJI"),
    ("標普500", "^GSPC"),
    ("那斯達克", "^IXIC"),
    ("費城半導體", "^SOX"),
    ("台積電ADR", "TSM"),
    ("美元/台幣", "TWD=X"),
    ("加權指數", "^TWII"),
    ("台積電", "2330.TW"),
]
TSM_ADR_RATIO = 5  # 1 股 ADR = 5 股台積電普通股

HISTORY_COLUMNS = [
    "夜盤日期", "日盤日期", "契約月份", "夜盤開盤", "夜盤最高", "夜盤最低", "夜盤收盤",
    "日盤收盤", "夜盤漲跌點", "夜盤漲跌幅", "日盤成交量", "夜盤成交量", "夜盤量佔比",
    "外資夜盤多空淨額口數", "外資夜盤多空淨額千元",
]


# ── 小工具 ──────────────────────────────────────────────────────────────

def tw_now() -> datetime:
    return datetime.now(timezone.utc).astimezone(TW_TZ)


def num(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("▲", "").replace("▼", "").replace("%", "").strip()
    if text in {"", "-", "--", "—"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def norm_date(value: Any) -> str:
    """2026/11/10、20261110、2026-11-10 → 2026-11-10。"""
    text = str(value or "").strip()
    digits = re.sub(r"\D", "", text)
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"
    return text


def is_outright_month(month: str) -> bool:
    """一般月份契約（202611）；週契約（202611W2）與價差單（202611/202612）不算。"""
    return bool(re.fullmatch(r"\d{6}", str(month or "").strip()))


def is_single_contract(month: str) -> bool:
    """單式契約（含週契約），排除價差單。成交量加總用。"""
    return "/" not in str(month or "") and bool(str(month or "").strip())


# ── 期交所：日盤 / 夜盤行情 ────────────────────────────────────────────

def _find_col(header: list[str], *keywords: str) -> int | None:
    for i, h in enumerate(header):
        h = h.strip()
        if all(k in h for k in keywords):
            return i
    return None


def parse_fut_csv(text: str) -> list[dict[str, Any]]:
    """解析 futDataDown 的 CSV（第一列為標題）。只留 TX。"""
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return []
    header = [h.strip() for h in rows[0]]
    idx = {
        "date": _find_col(header, "交易日期"),
        "contract": _find_col(header, "契約"),
        "month": _find_col(header, "到期月份"),
        "open": _find_col(header, "開盤"),
        "high": _find_col(header, "最高"),
        "low": _find_col(header, "最低"),
        "close": _find_col(header, "收盤"),
        "change": _find_col(header, "漲跌價"),
        "volume": _find_col(header, "成交量"),
        "oi": _find_col(header, "未沖銷"),
        "session": _find_col(header, "交易時段"),
    }
    if idx["date"] is None or idx["month"] is None or idx["volume"] is None or idx["session"] is None:
        raise ValueError(f"期交所 CSV 欄位不符：{header}")

    def cell(r: list[str], key: str) -> str:
        i = idx[key]
        return r[i].strip() if i is not None and i < len(r) else ""

    out = []
    for r in rows[1:]:
        contract = cell(r, "contract")
        if contract and contract != "TX":
            continue
        out.append({
            "date": norm_date(cell(r, "date")),
            "month": cell(r, "month"),
            "open": num(cell(r, "open")),
            "high": num(cell(r, "high")),
            "low": num(cell(r, "low")),
            "close": num(cell(r, "close")),
            "change": num(cell(r, "change")),
            "volume": num(cell(r, "volume")) or 0.0,
            "oi": num(cell(r, "oi")),
            "session": cell(r, "session"),
        })
    return out


def parse_openapi_rows(payload: list[dict]) -> list[dict[str, Any]]:
    """期交所 OpenAPI DailyMarketReportFut（只有最近一個交易日）。"""
    out = []
    for r in payload or []:
        if str(r.get("Contract", "")).strip() != "TX":
            continue
        month = str(r.get("ContractMonth(Week)", r.get("ContractMonth", ""))).strip()
        out.append({
            "date": norm_date(r.get("Date")),
            "month": month,
            "open": num(r.get("Open")),
            "high": num(r.get("High")),
            "low": num(r.get("Low")),
            "close": num(r.get("Last")),
            "change": num(r.get("Change")),
            "volume": num(r.get("Volume")) or 0.0,
            "oi": num(r.get("OpenInterest")),
            "session": str(r.get("TradingSession", "")).strip(),
        })
    return out


def fetch_tx_rows(today: datetime, days: int = 28) -> list[dict[str, Any]]:
    start = (today - timedelta(days=days)).strftime("%Y/%m/%d")
    end = today.strftime("%Y/%m/%d")
    errors = []
    try:
        resp = requests.post(
            FUT_DOWNLOAD_URL,
            data={"down_type": "1", "commodity_id": "TX", "commodity_id2": "",
                  "queryStartDate": start, "queryEndDate": end},
            headers=HEADERS, timeout=60,
        )
        resp.raise_for_status()
        text = resp.content.decode("cp950", errors="replace")
        rows = parse_fut_csv(text)
        if rows:
            return rows
        errors.append("futDataDown 沒有資料")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"futDataDown：{exc}")
    try:
        resp = requests.get(FUT_OPENAPI_URL, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        rows = parse_openapi_rows(resp.json())
        if rows:
            print("WARN 改用期交所 OpenAPI（只有最近一個交易日）：" + "；".join(errors))
            return rows
        errors.append("OpenAPI 沒有資料")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"OpenAPI：{exc}")
    raise RuntimeError("抓不到期交所臺股期貨行情：" + "；".join(errors))


def _near_month(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [r for r in rows if is_outright_month(r["month"]) and r["close"] is not None and r["volume"] > 0]
    return min(candidates, key=lambda r: r["month"]) if candidates else None


def summarize_sessions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """每個夜盤一列，配上前一個日盤。舊到新排序。"""
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        by_key.setdefault((r["session"], r["date"]), []).append(r)
    day_dates = sorted(d for s, d in by_key if s == DAY)
    night_dates = sorted(d for s, d in by_key if s == NIGHT)
    out = []
    for nd in night_dates:
        prior_days = [d for d in day_dates if d < nd]
        if not prior_days:
            continue
        dd = prior_days[-1]
        night_rows, day_rows = by_key[(NIGHT, nd)], by_key[(DAY, dd)]
        near = _near_month(night_rows)
        if near is None:
            continue
        day_same = next((r for r in day_rows if r["month"] == near["month"] and r["close"] is not None), None)
        day_near = day_same or _near_month(day_rows)
        night_vol = sum(r["volume"] for r in night_rows if is_single_contract(r["month"]))
        day_vol = sum(r["volume"] for r in day_rows if is_single_contract(r["month"]))
        total = day_vol + night_vol
        day_close = day_near["close"] if day_near else None
        chg = near["close"] - day_close if day_close else None
        out.append({
            "夜盤日期": nd,
            "日盤日期": dd,
            "契約月份": near["month"],
            "夜盤開盤": near["open"],
            "夜盤最高": near["high"],
            "夜盤最低": near["low"],
            "夜盤收盤": near["close"],
            "日盤收盤": day_close,
            "夜盤漲跌點": chg,
            "夜盤漲跌幅": (chg / day_close) if chg is not None and day_close else None,
            "日盤成交量": int(day_vol),
            "夜盤成交量": int(night_vol),
            "夜盤量佔比": (night_vol / total) if total else None,
            "夜盤未平倉": near["oi"],
        })
    return out


# ── 期交所：外資夜盤多空淨額 ──────────────────────────────────────────

def parse_foreign_night(html: str, product: str = "臺股期貨") -> dict[str, float] | None:
    """從 futContractsDateAh 頁面取出某商品「外資」列：多方口數/金額、空方口數/金額、淨額口數/金額。"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    current = ""
    for tr in soup.find_all("tr"):
        cells = [re.sub(r"\s+", "", c.get_text()) for c in tr.find_all(["td", "th"])]
        if not cells:
            continue
        for c in cells:
            if c.endswith("期貨") and not re.search(r"\d", c):
                current = c
        if current == product and "外資" in cells:
            nums = [num(c) for c in cells[cells.index("外資") + 1:]]
            nums = [n for n in nums if n is not None]
            if len(nums) >= 6:
                long_lots, long_amt, short_lots, short_amt, net_lots, net_amt = nums[:6]
                return {"多方口數": long_lots, "多方千元": long_amt, "空方口數": short_lots,
                        "空方千元": short_amt, "淨額口數": net_lots, "淨額千元": net_amt}
    return None


def fetch_foreign_night(night_date: str) -> dict[str, float] | None:
    query_date = night_date.replace("-", "/")
    resp = requests.post(
        FOREIGN_NIGHT_URL,
        data={"queryType": "1", "goDay": "", "doQuery": "1", "dateaddcnt": "",
              "queryDate": query_date, "commodityId": ""},
        headers=HEADERS, timeout=60,
    )
    resp.raise_for_status()
    resp.encoding = resp.encoding or "utf-8"
    return parse_foreign_night(resp.text)


# ── 國際盤 ────────────────────────────────────────────────────────────

def fetch_global() -> list[dict[str, Any]]:
    import yfinance as yf

    out = []
    for name, symbol in GLOBAL_SYMBOLS:
        item: dict[str, Any] = {"名稱": name, "代號": symbol, "收盤": None, "漲跌": None, "漲跌幅": None, "日期": ""}
        try:
            hist = yf.Ticker(symbol).history(period="10d", interval="1d", auto_adjust=False)
            close = hist["Close"].dropna() if hist is not None and not hist.empty else []
            if len(close) >= 2:
                last, prev = float(close.iloc[-1]), float(close.iloc[-2])
                item.update({"收盤": last, "漲跌": last - prev, "漲跌幅": (last - prev) / prev if prev else None,
                             "日期": close.index[-1].strftime("%Y-%m-%d")})
        except Exception as exc:  # noqa: BLE001
            print(f"WARN {name}（{symbol}）抓不到：{exc}")
        out.append(item)
    return out


# ── 開盤預估 ─────────────────────────────────────────────────────────

def estimate_open(night: dict[str, Any], global_quotes: list[dict[str, Any]],
                  foreign: dict[str, float] | None) -> dict[str, Any]:
    q = {g["代號"]: g for g in global_quotes}
    twii = (q.get("^TWII") or {}).get("收盤")
    pct_change = night.get("夜盤漲跌幅")
    est_open = twii * (1 + pct_change) if twii and pct_change is not None else None
    signals = []
    if pct_change is not None:
        signals.append(f"夜盤收 {night['夜盤收盤']:,.0f}，較日盤收盤 {night['夜盤漲跌點']:+,.0f} 點（{pct_change:+.2%}）")
    sox = (q.get("^SOX") or {}).get("漲跌幅")
    if sox is not None:
        signals.append(f"費半 {sox:+.2%}")
    tsm, fx, tw2330 = (q.get("TSM") or {}).get("收盤"), (q.get("TWD=X") or {}).get("收盤"), (q.get("2330.TW") or {}).get("收盤")
    adr_premium = None
    if tsm and fx and tw2330:
        adr_premium = tsm * fx / TSM_ADR_RATIO / tw2330 - 1
        tsm_chg = (q.get("TSM") or {}).get("漲跌幅")
        signals.append(f"台積電 ADR {tsm_chg:+.2%}，折合台股溢價 {adr_premium:+.1%}" if tsm_chg is not None
                       else f"台積電 ADR 折合台股溢價 {adr_premium:+.1%}")
    if foreign and foreign.get("淨額口數") is not None:
        side = "偏多" if foreign["淨額口數"] > 0 else "偏空" if foreign["淨額口數"] < 0 else "持平"
        signals.append(f"外資夜盤多空淨額 {foreign['淨額口數']:+,.0f} 口（{side}）")
    if pct_change is None:
        direction = "無法判斷"
    elif pct_change >= 0.003:
        direction = "開高"
    elif pct_change <= -0.003:
        direction = "開低"
    else:
        direction = "平盤附近"
    return {
        "方向": direction,
        "預估漲跌幅": pct_change,
        "加權指數前收": twii,
        "預估開盤": est_open,
        "台積電ADR溢價": adr_premium,
        "依據": signals,
        "說明": "預估開盤＝加權指數前收 ×（1＋夜盤近月較日盤收盤漲跌幅），只供參考。",
    }


# ── 四種劇本（夜盤漲跌 × 外資多空淨額，夜盤量佔比確認可信度）────────────

SCENARIOS = {
    1: {"名稱": "劇本一", "條件": "夜盤上漲＋外資偏多", "解讀": ["開高", "續揚機率高"]},
    2: {"名稱": "劇本二", "條件": "夜盤上漲＋外資偏空", "解讀": ["先漲", "小心開高走低"]},
    3: {"名稱": "劇本三", "條件": "夜盤下跌＋外資偏空", "解讀": ["開低", "續跌機率高"]},
    4: {"名稱": "劇本四", "條件": "夜盤下跌＋外資偏多", "解讀": ["先跌", "開低反彈"]},
}


def pick_scenario(night_change: float | None, foreign_net: float | None,
                  ratio: float | None, ratio_history: list[float]) -> dict[str, Any]:
    """夜盤漲跌決定方向、外資多空淨額判斷外資站哪邊、夜盤量佔比（對近 20 晚平均）確認可不可信。"""
    avg = sum(ratio_history[-20:]) / len(ratio_history[-20:]) if ratio_history else None
    if ratio is None or avg is None:
        confidence = "無法判斷"
    elif ratio >= avg:
        confidence = "可信度高"
    else:
        confidence = "可信度低"
    out: dict[str, Any] = {"編號": None, "夜盤量佔比": ratio, "近20晚平均佔比": avg, "可信度": confidence}
    if night_change is None or foreign_net is None or night_change == 0 or foreign_net == 0:
        out["說明"] = "夜盤平盤或外資淨額為 0／尚未公布，無法歸類劇本"
        return out
    up, long_ = night_change > 0, foreign_net > 0
    n = 1 if up and long_ else 2 if up else 4 if long_ else 3
    out.update({"編號": n, **SCENARIOS[n]})
    out["說明"] = (f"{SCENARIOS[n]['條件']} → {'、'.join(SCENARIOS[n]['解讀'])}；"
                  f"夜盤量佔比 {ratio:.1%}（近 20 晚平均 {avg:.1%}），{confidence}"
                  if ratio is not None and avg is not None else f"{SCENARIOS[n]['條件']} → {'、'.join(SCENARIOS[n]['解讀'])}")
    return out


# ── 新聞 ─────────────────────────────────────────────────────────────

def parse_news_rss(xml_text: str, limit: int = 8) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        source = (item.findtext("source") or "").strip()
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3].strip()
        pub = item.findtext("pubDate") or ""
        try:
            pub = parsedate_to_datetime(pub).astimezone(TW_TZ).strftime("%m/%d %H:%M")
        except Exception:  # noqa: BLE001
            pass
        out.append({"標題": title, "來源": source, "時間": pub, "連結": (item.findtext("link") or "").strip()})
        if len(out) >= limit:
            break
    return out


def fetch_news() -> list[dict[str, str]]:
    resp = requests.get(
        NEWS_RSS_URL,
        params={"q": "(台股 OR 台指期 OR 美股 OR 費半) when:1d", "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"},
        headers=HEADERS, timeout=30,
    )
    resp.raise_for_status()
    return parse_news_rss(resp.text)


# ── 歷史與輸出 ───────────────────────────────────────────────────────

def load_history() -> dict[str, dict[str, Any]]:
    if not HISTORY_PATH.exists():
        return {}
    with HISTORY_PATH.open(encoding="utf-8-sig") as f:
        return {r["夜盤日期"]: dict(r) for r in csv.DictReader(f) if r.get("夜盤日期")}


def merge_history(existing: dict[str, dict[str, Any]], nights: list[dict[str, Any]],
                  foreign_by_date: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    merged = dict(existing)
    for n in nights:
        row = {k: n.get(k) for k in HISTORY_COLUMNS if k in n}
        old = merged.get(n["夜盤日期"], {})
        f = foreign_by_date.get(n["夜盤日期"])
        row["外資夜盤多空淨額口數"] = f["淨額口數"] if f else old.get("外資夜盤多空淨額口數", "")
        row["外資夜盤多空淨額千元"] = f["淨額千元"] if f else old.get("外資夜盤多空淨額千元", "")
        merged[n["夜盤日期"]] = row
    return [merged[k] for k in sorted(merged)]


def write_history(rows: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in HISTORY_COLUMNS})


def previous_night_date() -> str:
    if not LATEST_PATH.exists():
        return ""
    try:
        return json.loads(LATEST_PATH.read_text(encoding="utf-8")).get("夜盤", {}).get("夜盤日期", "")
    except Exception:  # noqa: BLE001
        return ""


def build(wait_minutes: int = 0, dry_run: bool = False) -> dict[str, Any]:
    now = tw_now()
    prev = previous_night_date()
    deadline = time.monotonic() + wait_minutes * 60
    while True:
        nights = summarize_sessions(fetch_tx_rows(now))
        if not nights:
            raise RuntimeError("期交所資料裡沒有可配對的日盤／夜盤")
        latest = nights[-1]
        if latest["夜盤日期"] > prev or time.monotonic() >= deadline:
            break
        print(f"夜盤資料還是 {latest['夜盤日期']}（尚未公布新的一晚），5 分鐘後重抓…")
        time.sleep(300)
    is_new = latest["夜盤日期"] > prev
    if not is_new:
        print(f"WARN 夜盤資料沒有新的一晚（最新 {latest['夜盤日期']}）；國際盤與新聞照常更新")

    existing = load_history()
    foreign_by_date: dict[str, dict[str, float]] = {}
    missing = [n["夜盤日期"] for n in nights
               if n["夜盤日期"] == latest["夜盤日期"] or not existing.get(n["夜盤日期"], {}).get("外資夜盤多空淨額口數")]
    for d in missing[-10:]:  # 第一次執行時回補最近 10 晚
        try:
            f = fetch_foreign_night(d)
            if f:
                foreign_by_date[d] = f
            else:
                print(f"WARN {d} 外資夜盤資料解析不到")
        except Exception as exc:  # noqa: BLE001
            print(f"WARN {d} 外資夜盤抓不到：{exc}")
    foreign = foreign_by_date.get(latest["夜盤日期"])

    global_quotes = fetch_global()
    try:
        news = fetch_news()
    except Exception as exc:  # noqa: BLE001
        print(f"WARN 新聞抓不到：{exc}")
        news = []

    history = merge_history(existing, nights, foreign_by_date)
    prior_ratios = [float(r["夜盤量佔比"]) for r in history
                    if r["夜盤日期"] < latest["夜盤日期"] and num(r.get("夜盤量佔比")) is not None]
    result = {
        "更新時間": now.strftime("%Y-%m-%d %H:%M"),
        "夜盤": latest,
        "外資夜盤": foreign,
        "劇本": pick_scenario(latest.get("夜盤漲跌點"), (foreign or {}).get("淨額口數"),
                            latest.get("夜盤量佔比"), prior_ratios),
        "國際盤": global_quotes,
        "開盤預估": estimate_open(latest, global_quotes, foreign),
        "新聞": news,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    if not dry_run:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        LATEST_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        write_history(history)
        print(f"已寫入 {LATEST_PATH.relative_to(BASE)}、{HISTORY_PATH.relative_to(BASE)}"
              f"（夜盤 {latest['夜盤日期']}，{len(history)} 晚）")
        if is_new:
            print(f"Updated 1 夜盤 {latest['夜盤日期']}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--wait", type=int, default=0, help="夜盤還沒公布時最多等幾分鐘（每 5 分鐘重抓）")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    build(wait_minutes=args.wait, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
