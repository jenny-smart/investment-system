"""
record_snapshot.py
每天 08:00 / 20:00 台灣時間執行：
  - 從 latest_portfolio_values 讀取 Streamlit 已算好的市值 → 寫入 portfolio_snapshots
  - 20:00 額外同步 fund_dividends → dividend_log
"""
from __future__ import annotations
import os
from datetime import datetime, timezone, timedelta
from supabase import create_client

SUPABASE_URL      = os.environ.get("SUPABASE_URL", "https://qrvdztqyzxlsfskdgiqp.supabase.co")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

TW_NOW     = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
IS_EVENING = TW_NOW.hour >= 18


def sb():
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def calc_portfolio() -> dict:
    """從 latest_portfolio_values 讀取 Streamlit 已算好的市值"""
    client = sb()
    rows = client.table("latest_portfolio_values").select("*").eq("id", 1).execute().data or []

    if not rows:
        print("⚠️ latest_portfolio_values 沒有資料，請先在 Streamlit 頁面載入一次")
        return {}

    r = rows[0]
    total = float(r.get("total_twd") or 0)

    if total == 0:
        print("⚠️ total_twd 為 0，跳過")
        return {}

    updated_at = r.get("updated_at", "—")
    print(f"  資料來源時間：{updated_at}")

    return {
        "total_twd":           round(total, 0),
        "tw_stock":            round(float(r.get("tw_stock") or 0), 0),
        "us_stock":            round(float(r.get("us_stock") or 0), 0),
        "kifutong":            round(float(r.get("kifutong") or 0), 0),
        "scb":                 round(float(r.get("scb") or 0), 0),
        "taishin":             round(float(r.get("taishin") or 0), 0),
        "total_cost":          round(float(r.get("total_cost") or 0), 0),
        "total_pnl":           round(total - float(r.get("total_cost") or 0), 0),
        "cumulative_dividend": round(float(r.get("cumulative_dividend") or 0), 0),
        "trigger":             "schedule",
        "note":                f"{'晚間' if IS_EVENING else '早間'}快照 {TW_NOW.strftime('%Y-%m-%d %H:%M')}　資料時間：{updated_at}",
    }


def sync_dividend_log():
    """把 fund_dividends 的新記錄同步到 dividend_log"""
    client = sb()
    divs = client.table("fund_dividends").select("*").execute().data or []
    logs = client.table("dividend_log").select(
        "fund_code,ex_date,platform,currency"
    ).execute().data or []

    logged_keys = {
        (l["fund_code"], l["platform"], l["currency"], l["ex_date"])
        for l in logs
    }

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

    print(f"  dividend_log 新增 {inserted} 筆")


def main():
    print(f"=== 投資組合快照 {TW_NOW.strftime('%Y-%m-%d %H:%M')} ({'晚間' if IS_EVENING else '早間'}) ===")

    data = calc_portfolio()
    if not data:
        print("❌ 無法取得資料，跳過寫入")
        return

    print(f"  總台幣市值：{data['total_twd']:,.0f}")
    print(f"  總成本：    {data['total_cost']:,.0f}")
    print(f"  市值損益：  {data['total_pnl']:,.0f}")
    print(f"  累計配息：  {data['cumulative_dividend']:,.0f}")
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
