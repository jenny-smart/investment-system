from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import requests

BASE = Path(__file__).resolve().parents[1]
DATA_DIR = BASE / "data" / "stock_radar"
TW_TZ = timezone(timedelta(hours=8))
HEADERS = {"User-Agent": "investment-system/stock-radar"}

PRICE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
VALUATION_URL = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
INST_URL = "https://openapi.twse.com.tw/v1/fund/T86"


def _get_json(url: str) -> list[dict]:
    response = requests.get(url, headers=HEADERS, timeout=45)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def _num(value) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("--", "").strip()
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _pick(row: dict, *keys: str):
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _price_frame(rows: list[dict]) -> pd.DataFrame:
    out = []
    for r in rows:
        code = str(_pick(r, "Code", "證券代號") or "").strip()
        if not code.isdigit() or len(code) != 4:
            continue
        close = _num(_pick(r, "ClosingPrice", "收盤價"))
        change = _num(_pick(r, "Change", "漲跌價差"))
        volume = _num(_pick(r, "TradeVolume", "成交股數"))
        if close is None or close <= 0:
            continue
        prev = close - change if change is not None else None
        pct = (change / prev * 100) if prev and prev > 0 else None
        out.append({
            "代號": code,
            "名稱": str(_pick(r, "Name", "證券名稱") or "").strip(),
            "收盤價": close,
            "漲跌幅%": round(pct, 2) if pct is not None else None,
            "成交股數": volume,
        })
    return pd.DataFrame(out)


def _valuation_frame(rows: list[dict]) -> pd.DataFrame:
    out = []
    for r in rows:
        code = str(_pick(r, "Code", "證券代號") or "").strip()
        if not code:
            continue
        out.append({
            "代號": code,
            "本益比": _num(_pick(r, "PEratio", "本益比")),
            "殖利率%": _num(_pick(r, "DividendYield", "殖利率(%)")),
            "股價淨值比": _num(_pick(r, "PBratio", "股價淨值比")),
        })
    return pd.DataFrame(out)


def _institution_frame(rows: list[dict]) -> pd.DataFrame:
    out = []
    for r in rows:
        code = str(_pick(r, "Code", "證券代號") or "").strip()
        if not code:
            continue
        foreign = _num(_pick(r, "Foreign_Investor_BuySell", "外陸資買賣超股數(不含外資自營商)"))
        trust = _num(_pick(r, "Investment_Trust_BuySell", "投信買賣超股數"))
        dealer = _num(_pick(r, "Dealer_BuySell", "自營商買賣超股數"))
        total = _num(_pick(r, "Total", "三大法人買賣超股數"))
        out.append({
            "代號": code,
            "外資買賣超": foreign,
            "投信買賣超": trust,
            "自營商買賣超": dealer,
            "三大法人買賣超": total if total is not None else sum(v or 0 for v in (foreign, trust, dealer)),
        })
    return pd.DataFrame(out)


def _merge_optional(base: pd.DataFrame, other: pd.DataFrame) -> pd.DataFrame:
    if other.empty or "代號" not in other.columns:
        return base
    return base.merge(other, on="代號", how="left")


def _score(df: pd.DataFrame) -> pd.DataFrame:
    view = df.copy()
    for col in ["本益比", "殖利率%", "股價淨值比", "外資買賣超", "投信買賣超", "三大法人買賣超", "成交股數", "漲跌幅%"]:
        if col not in view:
            view[col] = pd.NA
    points = pd.Series(0, index=view.index, dtype="int64")
    points += ((view["本益比"] > 0) & (view["本益比"] <= 25)).fillna(False).astype(int)
    points += (view["殖利率%"] >= 2).fillna(False).astype(int)
    points += (view["外資買賣超"] > 0).fillna(False).astype(int)
    points += (view["投信買賣超"] > 0).fillna(False).astype(int)
    points += (view["三大法人買賣超"] > 0).fillna(False).astype(int)
    points += (view["成交股數"] >= 1_000_000).fillna(False).astype(int)
    points += (view["漲跌幅%"] > 0).fillna(False).astype(int)
    view["雷達分數"] = points
    reasons = []
    for _, r in view.iterrows():
        why = []
        if pd.notna(r["本益比"]) and 0 < r["本益比"] <= 25: why.append("估值")
        if pd.notna(r["殖利率%"]) and r["殖利率%"] >= 2: why.append("殖利率")
        if pd.notna(r["外資買賣超"]) and r["外資買賣超"] > 0: why.append("外資")
        if pd.notna(r["投信買賣超"]) and r["投信買賣超"] > 0: why.append("投信")
        if pd.notna(r["成交股數"]) and r["成交股數"] >= 1_000_000: why.append("量能")
        reasons.append("、".join(why) or "觀察")
    view["入選原因"] = reasons
    return view.sort_values(["雷達分數", "三大法人買賣超", "成交股數"], ascending=[False, False, False], na_position="last")


def build_daily_radar() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    price_rows = _get_json(PRICE_URL)
    price = _price_frame(price_rows)
    if price.empty:
        raise RuntimeError("TWSE price feed returned no usable listed-stock rows")

    warnings: list[str] = []
    try:
        valuation = _valuation_frame(_get_json(VALUATION_URL))
    except Exception as exc:
        valuation = pd.DataFrame()
        warnings.append(f"估值資料暫時無法取得：{exc}")
    try:
        institution = _institution_frame(_get_json(INST_URL))
    except Exception as exc:
        institution = pd.DataFrame()
        warnings.append(f"法人資料暫時無法取得：{exc}")

    merged = _merge_optional(_merge_optional(price, valuation), institution)
    ranked = _score(merged)
    selected = ranked[ranked["雷達分數"] >= 4].head(30).copy()

    now = datetime.now(TW_TZ)
    date_key = now.strftime("%Y-%m-%d")
    latest = {
        "generated_at": now.isoformat(timespec="seconds"),
        "market": "TWSE listed",
        "coverage": "上市普通股；第一版以收盤、估值、當日法人與量能為主",
        "warnings": warnings,
        "total_universe": int(len(ranked)),
        "selected_count": int(len(selected)),
        "top": json.loads(selected.fillna("").to_json(orient="records", force_ascii=False)),
    }

    ranked.to_csv(DATA_DIR / "latest.csv", index=False, encoding="utf-8-sig")
    selected.to_csv(DATA_DIR / f"{date_key}.csv", index=False, encoding="utf-8-sig")
    (DATA_DIR / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")

    history_path = DATA_DIR / "history.jsonl"
    existing = []
    if history_path.exists():
        existing = [line for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        existing = [line for line in existing if json.loads(line).get("date") != date_key]
    snapshot = {
        "date": date_key,
        "generated_at": latest["generated_at"],
        "selected_count": latest["selected_count"],
        "codes": selected["代號"].astype(str).tolist(),
    }
    existing.append(json.dumps(snapshot, ensure_ascii=False))
    history_path.write_text("\n".join(existing) + "\n", encoding="utf-8")
    return latest


if __name__ == "__main__":
    result = build_daily_radar()
    print(json.dumps(result, ensure_ascii=False, indent=2))
