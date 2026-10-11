from __future__ import annotations

from datetime import timedelta
from typing import Any

import pandas as pd
import streamlit as st

from invest_app.core import (
    two_line_metric,
    APP_VERSION,
    PLATFORMS,
    enrich,
    is_delisted_tw_stock,
    load_other_assets,
    load_positions,
    money,
    pct,
    signed_money,
    tw_now,
)
from invest_app.dividends import (
    render_dividend_log_tab,
)
from invest_app.history import (
    render_history_tab,
)
from invest_app.non_investment import (
    OTHER_SNAPSHOT_KEYS,
    _take_snapshot_now,
    render_other_assets_tab,
    render_total_asset_row,
    write_with_optional_columns,
)
from invest_app.overview import (
    render_investment_overview_page,
)
from invest_app.platform_page import (
    render_platform_page,
)
from invest_app.research import (
    render_research_page,
)
from invest_app.stock_dividends import (
    render_stock_dividend_tab,
)

st.set_page_config(
    page_title="Jenny 投資系統",
    page_icon="📈",
    layout="wide"
)

# ── CSS：保留雲端工具列空間，避免標題被 Streamlit Cloud header 蓋住 ───────
st.markdown("""
<style>
.stApp { background:#f8fafc; color:#1e293b; }
.block-container { padding-top:4.75rem; max-width:1600px; }
.app-page-title {
    display: block !important;
    position: relative !important;
    z-index: 1 !important;
    margin: 0 0 0.6rem 0 !important;
    color: #1e293b !important;
    font-size: 30px !important;
    line-height: 1.25 !important;
    font-weight: 800 !important;
    letter-spacing: 0 !important;
}
@media (max-width: 640px) {
    .block-container { padding-top:5.25rem; }
    .app-page-title { font-size: 24px !important; }
}
.hero { position:relative; z-index:0; background:#fff; border:1px solid #e2e8f0; border-radius:16px; padding:16px 20px; box-shadow:0 1px 4px rgba(0,0,0,.06); }
[data-testid="stMetric"] { background:#fff !important; border:1px solid #e2e8f0 !important; border-radius:12px !important; padding:16px 18px !important; box-shadow:0 1px 4px rgba(0,0,0,.05) !important; min-width:0 !important; }
[data-testid="stMetricValue"] {
    width:100% !important;
    min-width:0 !important;
    font-size:clamp(.82rem, 1.7vw, 1.35rem) !important;
    line-height:1.25 !important;
    font-weight:700 !important;
    font-variant-numeric:tabular-nums;
    white-space:nowrap !important;
}
[data-testid="stMetricValue"] > div { overflow:visible !important; }
@media (max-width: 640px) {
    [data-testid="stMetric"] { padding:12px 10px !important; }
    [data-testid="stMetricValue"] { font-size:clamp(.78rem, 3.3vw, 1.12rem) !important; }
}
[data-testid="stDataFrame"] { background:#fff !important; border:1px solid #e2e8f0 !important; border-radius:10px !important; }
.stButton > button { background:#10b981 !important; color:#fff !important; border-radius:10px !important; border:0 !important; font-weight:600 !important; }
.stButton > button:hover { background:#059669 !important; }
.stTabs [data-baseweb="tab"] { font-size:13px !important; font-weight:500 !important; color:#64748b !important; }
.stTabs [aria-selected="true"] { color:#10b981 !important; font-weight:700 !important; border-bottom-color:#10b981 !important; }
.stAlert { border-radius:10px !important; }
/* ── Tab 質感升級 ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: #f1f5f9;
    padding: 6px 8px;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
}
.stTabs [data-baseweb="tab"] {
    height: 36px;
    padding: 0 16px;
    border-radius: 8px;
    font-size: 13px !important;
    font-weight: 500 !important;
    color: #64748b !important;
    background: transparent;
    border: none;
    white-space: nowrap;
}
.stTabs [data-baseweb="tab"]:hover {
    background: #e2e8f0 !important;
    color: #334155 !important;
}
.stTabs [aria-selected="true"] {
    background: #fff !important;
    color: #10b981 !important;
    font-weight: 700 !important;
    box-shadow: 0 1px 4px rgba(0,0,0,.1);
    border-bottom: none !important;
}
.stTabs [data-baseweb="tab-highlight"] {
    display: none;
}
.stTabs [data-baseweb="tab-border"] {
    display: none;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="app-page-title">📈 Jenny 投資即時市值系統</div>', unsafe_allow_html=True)
st.caption(f"版本：{APP_VERSION}｜Supabase 永久資料庫")

try:
    positions = load_positions()
except Exception as e:
    st.error(f"Supabase 讀取失敗：{e}"); st.stop()
enriched = enrich(positions)
_live_snap: dict[str, Any] = {}

try:
    _live_snap = _take_snapshot_now(enriched, "auto")
    # 每個連線第一次載入（含排程喚醒）、按「更新即時價」或超過 10 分鐘才寫入，
    # 不在每次點按鈕／換頁時都寫 Supabase。
    _last_write = st.session_state.get("latest_values_written_at")
    if _live_snap and (_last_write is None or tw_now() - _last_write > timedelta(minutes=10)):
        st.session_state["latest_values_written_at"] = tw_now()
        write_with_optional_columns("latest_portfolio_values", {
            "id":                  1,
            "total_twd":           _live_snap["total_twd"],
            "tw_stock":            _live_snap["tw_stock"],
            "us_stock":            _live_snap["us_stock"],
            "kifutong":            _live_snap["kifutong"],
            "scb":                 _live_snap["scb"],
            "taishin":             _live_snap["taishin"],
            "total_cost":          _live_snap["total_cost"],
            "cumulative_dividend": _live_snap["cumulative_dividend"],
            "updated_at":          tw_now().isoformat(),
            **{k: _live_snap[k] for k in OTHER_SNAPSHOT_KEYS if k in _live_snap},
        }, upsert_on="id")
except Exception as _e:
    st.warning(f"⚠️ latest_portfolio_values 更新失敗：{_e}")
total_value = enriched["台幣市值"].dropna().sum() if not enriched.empty and "台幣市值" in enriched else 0
total_cost  = enriched["台幣成本"].dropna().sum() if not enriched.empty and "台幣成本" in enriched else 0
total_pnl   = enriched["損益"].dropna().sum()     if not enriched.empty and "損益"     in enriched else 0
total_div   = enriched["每月配息"].dropna().sum()  if not enriched.empty and "每月配息" in enriched else 0
total_rate  = total_pnl / total_cost if total_cost else None
total_sell_cost = enriched["賣出稅費"].dropna().sum() if not enriched.empty and "賣出稅費" in enriched else 0
total_pnl_all = total_value - total_cost - total_sell_cost  # 損益 = 市值 − 成本 − 台股賣出稅費
total_div_received = enriched["累計已領配息"].dropna().sum() if not enriched.empty and "累計已領配息" in enriched else 0


def _received_dividends(asset_type: str) -> float:
    """某類資產（基金／台股／美股）的累計已領配息（台幣）。"""
    if enriched.empty or "累計已領配息" not in enriched:
        return 0.0
    return float(enriched.loc[enriched["asset_type"].astype(str) == asset_type, "累計已領配息"].dropna().sum())

# Hero bar（不再 sticky，標題不被蓋）
with st.container():
    st.markdown('<div class="hero">', unsafe_allow_html=True)
    # 第一排：市值、成本、損益、總配息；第二排：基金／台股配息與基金預計配息（一排 4 張，不會被截斷）
    c1, c2, c3, c4 = st.columns(4)
    # 顯示缺報價的台股名稱
    tw_missing = []
    if not enriched.empty:
        tw_no_price = enriched[
            (enriched["platform"] == "台股") &
            (enriched["units"].fillna(0) > 0) &
            (enriched["即時價格/淨值"].isna()) &
            (enriched["狀態"].astype(str) != "價格:已下市 匯率:ok")
        ]
        if not tw_no_price.empty:
            active_mask = ~tw_no_price.apply(
                lambda row: is_delisted_tw_stock(row.get("ticker", ""), row.get("name", "")),
                axis=1,
            )
            tw_no_price = tw_no_price.loc[active_mask]
            tw_missing = tw_no_price.get("name", pd.Series(dtype=str)).dropna().unique().tolist()
    if tw_missing:
        st.warning(f"⚠️ 台股缺報價：{'、'.join(tw_missing)}")
    pnl_delta = f"{total_pnl:+,.0f} / {pct(total_rate)}"
    # 投資總市值 / 扣稅後總市值（台股賣出稅費 0.4425%）
    two_line_metric(c1, "投資總市值", money(total_value),
                    f"扣稅後 {money(total_value - total_sell_cost)}" if total_sell_cost else "", pnl_delta)
    # 外部投入 = 排除配息再投入的成本
    external_cost = enriched[enriched["is_reinvest"].fillna(False) == False]["台幣成本"].dropna().sum() if not enriched.empty else 0
    c2.metric("投資總成本", money(total_cost),
              delta=f"外部投入 {money(external_cost)}" if external_cost != total_cost else None)
    c3.metric("投資市值損益", signed_money(total_pnl_all))
    c4.metric("投資總配息", money(total_div_received))
    c5, c6, c8, _spare = st.columns(4)
    c5.metric("基金配息", money(_received_dividends("基金")))
    c6.metric("台股配息", money(_received_dividends("台股")))
    c8.metric("基金預計配息", money(total_div))
    _next_month = (tw_now().replace(day=1) + timedelta(days=32)).strftime("%Y.%m")
    c8.caption(_next_month)  # 預計配息對應的月份（下個月），小字
    refresh_col = render_total_asset_row(float(total_value), load_other_assets(), float(total_sell_cost)) or st
    if refresh_col.button("🔄 更新即時價"):
        st.cache_data.clear()
        st.session_state.pop("latest_values_written_at", None)
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
PAGE_NAMES = ["投資總覽", "非投資總覽", "歷史記錄", *PLATFORMS, "股票研究", "配息記錄", "台股股利"]

# 功能列：只執行選到的那一頁（st.tabs 會每次把全部分頁都跑一遍，載入慢）。
# 選擇記在網址 ?page=，重新整理後停在同一頁。
_requested = st.query_params.get("page", PAGE_NAMES[0])

if st.session_state.get("page") not in PAGE_NAMES:
    st.session_state["page"] = _requested if _requested in PAGE_NAMES else PAGE_NAMES[0]
page = st.segmented_control("功能", PAGE_NAMES, key="page", label_visibility="collapsed") or PAGE_NAMES[0]
st.query_params["page"] = page

try:
    if page == "投資總覽":
        render_investment_overview_page(enriched, positions)

    if page == "非投資總覽":
        render_other_assets_tab(enriched)

    if page == "股票研究":
        render_research_page(enriched)

    if page in PLATFORMS:
        render_platform_page(page, positions, enriched, total_value, total_cost, total_pnl, total_rate, total_div)



    if page == "歷史記錄":
        render_history_tab(enriched)

    if page == "配息記錄":
        render_dividend_log_tab(enriched, positions)

    if page == "台股股利":
        render_stock_dividend_tab(enriched, positions)
except Exception as _page_error:
    st.error(f"「{page}」載入失敗：{_page_error}")
    st.exception(_page_error)
