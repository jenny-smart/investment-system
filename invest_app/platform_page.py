"""各投資平台頁（台股／美股／基富通／渣打基金／台新基金）。"""
from __future__ import annotations


import pandas as pd
import streamlit as st
from invest_app.core import (
    money,
    pct,
    signed_money,
)
from invest_app.positions_admin import (
    editable_platform_table,
)


show_cols = ["sort_order", "platform", "asset_type", "name", "ticker", "fund_code", "currency",
             "total_cost_input", "original_units", "units", "市值股數", "avg_cost", "purchase_ym",
             "即時價格/淨值", "基金淨值日期", "匯率", "成本原幣", "市值原幣", "台幣成本", "台幣市值",
             "價差損益", "價差損益率", "累計配息原幣", "累計已領配息", "含息總損益", "含息總損益率", "每月配息",
             "每單位月配息估算", "月配息來源", "dividend_note", "corporate_action", "狀態"]


def render_platform_page(platform, positions, enriched, total_value, total_cost, total_pnl, total_rate, total_div) -> None:
    st.subheader(platform)
    # ── 第一排：全局KPI ──
    g1, g2, g3, g4, g5 = st.columns(5)
    g1.metric("總台幣市值", money(total_value), delta=f"{total_pnl:+,.0f} / {pct(total_rate)}")
    g2.metric("總台幣成本", money(total_cost))
    g3.metric("預估每月配息", money(total_div))
    g4.metric("投資筆數", f"{len(positions):,}")
    if g5.button("🔄 更新即時價", key=f"refresh_{platform}"):
        st.cache_data.clear(); st.rerun()
    view = enriched[enriched["platform"] == platform].copy() if not enriched.empty else pd.DataFrame()
    if view.empty:
        st.info(f"尚無 {platform} 資料")
    else:
        # ── 第二排：平台KPI ──
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("台幣市值", money(view["台幣市值"].dropna().sum()))
        m2.metric("台幣成本", money(view["台幣成本"].dropna().sum()))
        m3.metric("損益",     signed_money(view["損益"].dropna().sum()))
        m4.metric("每月配息", money(view["每月配息"].dropna().sum()))
        st.markdown("#### 即時計算結果")
        # 數值欄位直接用原始數值 + NumberColumn，靠右對齊、可排序
        num_cols = {
            "total_cost_input": st.column_config.NumberColumn("總投入成本", format="%.0f"),
            "original_units":   st.column_config.NumberColumn("成本股數",   format="%.4f"),
            "units":            st.column_config.NumberColumn("現在股數",   format="%.4f"),
            "市值股數":         st.column_config.NumberColumn("市值股數",   format="%.4f"),
            "avg_cost":         st.column_config.NumberColumn("平均成本",   format="%.4f"),
            "即時價格/淨值":    st.column_config.NumberColumn("即時價格/淨值", format="%.4f"),
            "匯率":             st.column_config.NumberColumn("匯率",       format="%.4f"),
            "成本原幣":         st.column_config.NumberColumn("成本原幣",   format="%.0f"),
            "市值原幣":         st.column_config.NumberColumn("市值原幣",   format="%.0f"),
            "台幣成本":         st.column_config.NumberColumn("台幣成本",   format="%.0f"),
            "台幣市值":         st.column_config.NumberColumn("台幣市值",   format="%.0f"),
            "價差損益":         st.column_config.NumberColumn("市值損益",   format="%.0f"),
            "累計配息原幣":     st.column_config.NumberColumn("累積配息原幣", format="%.2f"),
            "累計已領配息":     st.column_config.NumberColumn("累積配息台幣", format="%.0f"),
            "含息總損益":       st.column_config.NumberColumn("總損益",     format="%.0f"),
            "每月配息":         st.column_config.NumberColumn("月配息",     format="%.0f"),
            "每單位月配息估算": st.column_config.NumberColumn("每單位月配息", format="%.4f"),
            "價差損益率":       st.column_config.NumberColumn("市值損益率", format="%.2f%%"),
            "含息總損益率":     st.column_config.NumberColumn("總損益率",   format="%.2f%%"),
        }
        view_disp = view[show_cols].copy()
        # 把百分比欄位從小數轉成百分比數值
        for col in ["價差損益率", "含息總損益率"]:
            if col in view_disp.columns:
                view_disp[col] = view_disp[col].apply(lambda x: x * 100 if x is not None and str(x) not in ["-", "—", "nan"] else None)
        st.dataframe(
            view_disp,
            use_container_width=True,
            hide_index=True,
            height=400,
            column_config=num_cols,
        )
    editable_platform_table(platform, positions, f"editor_{platform}")
