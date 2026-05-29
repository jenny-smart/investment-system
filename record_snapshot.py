"""
portfolio_snapshot.py - 直接從 positions 重算，與 Streamlit 邏輯一致
"""
from __future__ import annotations
import os, requests
from datetime import datetime, timezone, timedelta

try:
    import yfinance as yf
    HAS_YF = True
except Exception:
    HAS_YF = False

from supabase import create_client

SUPABASE_URL      = os.environ.get("SUPABASE_URL", "https://qrvdztqyzxlsfskdgiqp.supabase.co")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
GAS_URL = "https://script.google.com/macros/s/AKfycbx2tregTV1NlYpUkOvy9UpRu3YDMP5r9wQEQuiB7qj_Y9HGa8yON4isAUIke30XF23p/exec"

TW_NOW = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
IS_EVENING = TW_NOW.hour >= 18

def sb():
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

def fetch_fx(cur: str) -> float:
    if cur == "TWD": return 1.0
    pairs = {"USD": "USDTWD=X", "CNY": "CNYTWD=X", "JPY": "JPYTWD=X", "ZAR": "ZARTWD=X"}
    pair = pairs.get(cur)
    if not pair or not HAS_YF: return 1.0
    try:
        t = yf.Ticker(pair)
        p = getattr(t.fast_info, "last_price", None)
        return float(p) if p and float(p) > 0 else 1.0
    except Exception:
        return 1.0

def fetch_stock_price(ticker: str) -> float | None:
    if not HAS_YF or not ticker: return None
    try:
        t = yf.Ticker(ticker)
        p = getattr(t.fast_info, "last_price", None)
        if p and float(p) > 0:
            return float(p)
        hist = t.history(period="5d", auto_adjust=False)
        if not hist.empty and "Close" in hist:
            close = hist["Close"].dropna()
            if not close.empty:
                return float(close.iloc[-1])
    except Exception as e:
        print(f"  Yahoo {ticker} 失敗: {e}")
    return None

_gas_cache: dict[str, float] = {}

def fetch_gas_nav(fund_code: str) -> float | None:
    if fund_code in _gas_cache:
        return _gas_cache[fund_code]
    for code in [fund_code, fund_code.upper(), fund_code.lower()]:
        try:
            r = requests.get(GAS_URL, params={"code": code}, timeout=25,
                             headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                d = r.json()
                if d.get("ok") and d.get("nav"):
                    nav = float(d["nav"])
                    _gas_cache[fund_code] = nav
                    return nav
        except Exception:
            pass
    return None

def calc_portfolio() -> dict:
    client = sb()
    rows = client.table("positions").select("*").execute().data or []

    if not rows:
        print("⚠️ positions 沒有資料")
        return {}

    platform_val = {"台股": 0.0, "美股": 0.0, "基富通": 0.0, "渣打基金": 0.0, "台新基金": 0.0}
    total_cost = 0.0
    total_div = 0.0
    fx_cache: dict[str, float] = {}

    # 基金配息：同一 fund_code+platform+currency 只計入第一筆
    div_primary_seen: set[tuple] = set()

    for r in rows:
        platform = (r.get("platform") or "").strip()
        asset_type = (r.get("asset_type") or "").strip()
        currency = (r.get("currency") or "TWD").strip().upper()
        ticker = (r.get("ticker") or "").strip()
        fund_code = (r.get("fund_code") or "").strip()
        original_units = float(r.get("original_units") or 0)
        units = float(r.get("units") or 0)
        avg_cost = float(r.get("avg_cost") or 0)
        total_cost_input = float(r.get("total_cost_input") or 0)
        note = (r.get("note") or "")
        div_original = float(r.get("dividend_received_original_total") or 0)
        div_legacy = float(r.get("dividend_received_total") or 0)

        is_closed = any(t in note for t in ["已賣出", "已結清", "結清", "賣出"])
        market_units = units if units > 0 or is_closed else original_units
        cost_orig = total_cost_input if total_cost_input > 0 else original_units * avg_cost

        # 取即時價
        price = None
        if asset_type in ("台股", "美股"):
            name = (r.get("name") or "").strip()
            t_code = ticker or name.upper()
            price = fetch_stock_price(t_code)
        else:
            if fund_code:
                price = fetch_gas_nav(fund_code)

        if currency not in fx_cache:
            fx_cache[currency] = fetch_fx(currency)
        fx = fx_cache[currency]

        twd_cost = cost_orig * fx
        twd_value = market_units * price * fx if price is not None else 0.0

        # 累計配息（同基金只算一次）
        if asset_type == "基金" and fund_code:
            div_key = (fund_code.lower(), platform, currency)
            if div_key not in div_primary_seen:
                div_primary_seen.add(div_key)
                div_twd = div_original * fx if div_original > 0 else div_legacy
            else:
                div_twd = 0.0
        else:
            div_twd = div_original * fx if div_original > 0 else div_legacy

        total_cost += twd_cost
        total_div += div_twd

        if platform in platform_val:
            platform_val[platform] += twd_value

    total = sum(platform_val.values())
    return {
        "total_twd":           round(total, 0),
        "tw_stock":            round(platform_val["台股"], 0),
        "us_stock":            round(platform_val["美股"], 0),
        "kifutong":            round(platform_val["基富通"], 0),
        "scb":                 round(platform_val["渣打基金"], 0),
        "taishin":             round(platform_val["台新基金"], 0),
        "total_cost":          round(total_cost, 0),
        "total_pnl":           round(total - total_cost, 0),
        "cumulative_dividend": round(total_div, 0),
        "trigger":             "schedule",
        "note":                f"{'晚間' if IS_EVENING else '早間'}快照 {TW_NOW.strftime('%Y-%m-%d %H:%M')}",
    }

def sync_dividend_log():
    client = sb()
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
                "fund_code":         d.get("fund_code"),
                "fund_name":         d.get("fund_name"),
                "platform":          d.get("platform"),
                "currency":          d.get("currency"),
                "ex_date":           d.get("ex_date"),
                "pay_date":          d.get("pay_date"),
                "div_amount":        d.get("div_amount"),
                "actual_div_amount": d.get("actual_div_amount") or d.get("div_amount"),
                "units_at_ex":       d.get("units_at_ex"),
                "fx_rate":           d.get("fx_rate"),
                "twd_total":         d.get("twd_total"),
                "is_paid":           d.get("is_paid", False),
                "note":              f"從 fund_dividends 同步 {TW_NOW.strftime('%Y-%m-%d')}",
            }).execute()
            inserted += 1
        except Exception as e:
            print(f"  dividend_log insert 失敗：{e}")
    print(f"dividend_log 新增 {inserted} 筆")

def main():
    print(f"=== 投資組合快照 {TW_NOW.strftime('%Y-%m-%d %H:%M')} ({'晚間' if IS_EVENING else '早間'}) ===")
    data = calc_portfolio()
    if not data:
        print("❌ 無法計算，跳過寫入")
        return
    print(f"  總台幣市值：{data['total_twd']:,.0f}")
    print(f"  總成本：{data['total_cost']:,.0f}  累計配息：{data['cumulative_dividend']:,.0f}")
    print(f"  台股：{data['tw_stock']:,.0f}  美股：{data['us_stock']:,.0f}")
    print(f"  基富通：{data['kifutong']:,.0f}  渣打：{data['scb']:,.0f}  台新：{data['taishin']:,.0f}")
    sb().table("portfolio_snapshots").insert(data).execute()
    print("  ✅ portfolio_snapshots 已寫入")
    if IS_EVENING:
        print("  同步 dividend_log...")
        sync_dividend_log()
    print("=== 完成 ===")

if __name__ == "__main__":
    main()
