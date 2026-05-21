"""
portfolio_snapshot.py
每天 08:00 / 20:00 台灣時間執行：
  - 計算各平台即時市值 → 寫入 portfolio_snapshots
  - 20:00 額外同步 fund_dividends → dividend_log
"""
from __future__ import annotations
import os, sys, json, requests
from datetime import datetime, timezone, timedelta
from typing import Any

try:
    import yfinance as yf
    HAS_YF = True
except Exception:
    HAS_YF = False

from supabase import create_client

# ── 設定 ──────────────────────────────────────────────────────────────────
SUPABASE_URL      = os.environ.get("SUPABASE_URL", "https://qrvdztqyzxlsfskdgiqp.supabase.co")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
GAS_V3 = "https://script.google.com/macros/s/AKfycbwS8AUn4M4Qx9qHxcRkNv2GqTTKAIYgXmNRoYsOKFNfSv9yLFz1sEu5EKY2Tqvnf_Ok/exec"

TW_NOW = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
IS_EVENING = TW_NOW.hour >= 18   # 20:00 觸發的那次

FUND_PRESETS = {
    "acft94": "TWD", "acai222": "TWD", "acft99": "CNY",
    "shzx0": "JPY",  "TLZO3": "JPY",
    "acob36": "USD", "pizn8": "USD",  "pizo1": "USD",
    "pizm9": "ZAR",  "anzb6": "USD",  "ANZH2": "ZAR",
}

def sb():
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

def fetch_fx(cur: str) -> float:
    if cur == "TWD": return 1.0
    pairs = {"USD":"USDTWD=X","CNY":"CNYTWD=X","JPY":"JPYTWD=X","ZAR":"ZARTWD=X"}
    pair = pairs.get(cur)
    if not pair or not HAS_YF: return 1.0
    try:
        t = yf.Ticker(pair)
        p = getattr(t.fast_info, "last_price", None)
        return float(p) if p else 1.0
    except Exception:
        return 1.0

def fetch_yahoo(ticker: str) -> float | None:
    if not HAS_YF or not ticker: return None
    for attempt in range(2):
        try:
            t = yf.Ticker(ticker)
            p = getattr(t.fast_info, "last_price", None)
            if p is None or float(p) <= 0:
                hist = t.history(period="5d", auto_adjust=False)
                if not hist.empty and "Close" in hist:
                    close = hist["Close"].dropna()
                    if not close.empty:
                        p = close.iloc[-1]
            if p and float(p) > 0:
                return float(p)
        except Exception as e:
            print(f"  Yahoo {ticker} attempt {attempt+1} 失敗: {e}")
    return None

def fetch_gas(fund_code: str) -> dict:
    try:
        r = requests.get(GAS_V3, params={"code": fund_code},
                         timeout=25, headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code == 200:
            d = r.json()
            if d.get("ok"):
                return d
    except Exception:
        pass
    return {}

def calc_portfolio() -> dict:
    """從 Supabase positions 計算各平台市值"""
    client = sb()
    rows = client.table("positions").select("*").execute().data or []

    # 預先抓匯率
    fx_cache: dict[str, float] = {"TWD": 1.0}
    for cur in ["USD", "CNY", "JPY", "ZAR"]:
        fx_cache[cur] = fetch_fx(cur)

    # 預先抓基金淨值（GAS）
    nav_cache: dict[str, float] = {}
    for fc in FUND_PRESETS:
        d = fetch_gas(fc)
        if d.get("nav"):
            nav_cache[fc] = float(d["nav"])

    platform_val: dict[str, float] = {
        "台股": 0, "美股": 0, "基富通": 0, "渣打基金": 0, "台新基金": 0
    }
    total_cost = 0.0

    for r in rows:
        platform = (r.get("platform") or "").strip()
        currency = (r.get("currency") or "TWD").strip().upper()
        units    = float(r.get("units") or 0)
        orig_u   = float(r.get("original_units") or 0)
        avg_cost = float(r.get("avg_cost") or 0)
        total_ci = float(r.get("total_cost_input") or 0)
        note     = (r.get("note") or "")
        asset    = (r.get("asset_type") or "").strip()

        if "已賣出" in note or "已結清" in note:
            continue

        mkt_units = units if units > 0 else orig_u
        fx = fx_cache.get(currency, 1.0)
        cost = (total_ci if total_ci > 0 else orig_u * avg_cost) * fx
        total_cost += cost

        price = None
        if asset in {"台股", "美股"}:
            ticker = (r.get("ticker") or "").strip()
            price = fetch_yahoo(ticker) if ticker else None
        elif asset == "基金":
            fc = (r.get("fund_code") or "").strip()
            price = nav_cache.get(fc)

        if price is None or mkt_units <= 0:
            continue

        val = mkt_units * price * fx
        if platform in platform_val:
            platform_val[platform] += val

    total = sum(platform_val.values())
    total_pnl = total - total_cost

    return {
        "total_twd": round(total, 0),
        "tw_stock":  round(platform_val["台股"], 0),
        "us_stock":  round(platform_val["美股"], 0),
        "kifutong":  round(platform_val["基富通"], 0),
        "scb":       round(platform_val["渣打基金"], 0),
        "taishin":   round(platform_val["台新基金"], 0),
        "total_cost": round(total_cost, 0),
        "total_pnl":  round(total_pnl, 0),
        "note": f"{'晚間' if IS_EVENING else '早間'}快照 {TW_NOW.strftime('%Y-%m-%d %H:%M')}",
        "trigger": "schedule",
    }

def sync_dividend_log():
    """把 fund_dividends 的新記錄同步到 dividend_log"""
    client = sb()
    # 取 fund_dividends 裡還沒有進 dividend_log 的記錄
    divs = client.table("fund_dividends").select("*").execute().data or []
    logs = client.table("dividend_log").select("fund_code,ex_date,platform,currency").execute().data or []
    logged_keys = {(l["fund_code"], l["platform"], l["currency"], l["ex_date"]) for l in logs}

    inserted = 0
    for d in divs:
        key = (d.get("fund_code"), d.get("platform"), d.get("currency"), d.get("ex_date"))
        if key in logged_keys:
            continue
        try:
            client.table("dividend_log").insert({
                "fund_code":    d.get("fund_code"),
                "fund_name":    d.get("fund_name"),
                "platform":     d.get("platform"),
                "currency":     d.get("currency"),
                "ex_date":      d.get("ex_date"),
                "pay_date":     d.get("pay_date"),
                "div_amount":   d.get("div_amount"),
                "actual_div_amount": d.get("actual_div_amount") or d.get("div_amount"),
                "units_at_ex":  d.get("units_at_ex"),
                "fx_rate":      d.get("fx_rate"),
                "twd_total":    d.get("twd_total"),
                "is_paid":      d.get("is_paid", False),
                "note":         f"從 fund_dividends 同步 {TW_NOW.strftime('%Y-%m-%d')}",
            }).execute()
            inserted += 1
        except Exception as e:
            print(f"  dividend_log insert 失敗：{e}")

    print(f"dividend_log 新增 {inserted} 筆")

def main():
    print(f"=== 投資組合快照 {TW_NOW.strftime('%Y-%m-%d %H:%M')} ({'晚間' if IS_EVENING else '早間'}) ===")

    # 1. 計算市值並寫入快照
    data = calc_portfolio()
    print(f"  總台幣市值：{data['total_twd']:,.0f}")
    print(f"  台股：{data['tw_stock']:,.0f}  美股：{data['us_stock']:,.0f}")
    print(f"  基富通：{data['kifutong']:,.0f}  渣打：{data['scb']:,.0f}  台新：{data['taishin']:,.0f}")

    client = sb()
    client.table("portfolio_snapshots").insert(data).execute()
    print("  ✅ portfolio_snapshots 已寫入")

    # 2. 晚間額外同步配息記錄
    if IS_EVENING:
        print("  同步 dividend_log...")
        sync_dividend_log()

    print("=== 完成 ===")

if __name__ == "__main__":
    main()
