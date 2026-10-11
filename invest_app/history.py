"""歷史記錄頁：portfolio_snapshots 列表與手動快照。"""
from __future__ import annotations


import pandas as pd
import streamlit as st
from invest_app.core import (
    html_table,
    money,
    supabase_client,
)
from invest_app.non_investment import (
    OTHER_SNAPSHOT_KEYS,
    _take_snapshot_now,
    write_with_optional_columns,
)


def render_history_tab(enriched: pd.DataFrame) -> None:
    """歷史記錄"""
    st.subheader("歷史記錄")

    # ── 手動記錄按鈕 ──
    col_btn, col_info = st.columns([1, 4])
    if col_btn.button("📸 立即記錄當下市值", key="manual_snapshot_btn"):
        try:
            data = _take_snapshot_now(enriched, "manual")
            if data:
                write_with_optional_columns("portfolio_snapshots", data)
                st.success(f"✅ 已記錄！總市值：{money(data['total_twd'])}")
                st.rerun()
            else:
                st.error("無法取得市值，請先更新即時價。")
        except Exception as e:
            st.error(f"記錄失敗：{e}")
    col_info.caption("排程：每天 08:00 / 20:00 自動記錄。也可以手動點按鈕立即記錄。")

    # ── 讀取資料 ──
    try:
        rows = supabase_client().table("portfolio_snapshots") \
            .select("*") \
            .order("snapshot_at", desc=True) \
            .execute().data or []
    except Exception as e:
        st.error(f"讀取失敗：{e}")
        return

    if not rows:
        st.info("還沒有記錄，點上方按鈕立即記錄一筆。")
        return

    df = pd.DataFrame(rows)
    # Supabase stores timestamptz in UTC.  Parse explicitly as UTC first so
    # timestamps are shown in Taiwan time even if the API omits the offset.
    df["snapshot_at"] = pd.to_datetime(df["snapshot_at"], utc=True).dt.tz_convert("Asia/Taipei")
    df = df.sort_values("snapshot_at", ascending=False).reset_index(drop=True)
    df["時間"] = df["snapshot_at"].dt.strftime("%m/%d %H:%M")
    columns_missing = any(key not in df for key in OTHER_SNAPSHOT_KEYS)
    for key in OTHER_SNAPSHOT_KEYS:
        if key not in df:
            df[key] = None
    df[OTHER_SNAPSHOT_KEYS] = df[OTHER_SNAPSHOT_KEYS].apply(pd.to_numeric, errors="coerce")

    if columns_missing or st.session_state.get("snapshot_columns_missing"):
        st.warning("Supabase 的 portfolio_snapshots 還沒有其他資產欄位，新快照不會存這幾欄。"
                   "請到 Supabase → SQL Editor 執行 supabase_schema.sql 裡 portfolio_snapshots / latest_portfolio_values 的 alter table。")
    st.caption("非投資資產（銀行、保險…總資產）自 2026/10/11 起記錄，之前的快照這幾欄空白。")

    # ── 明細表（愈新愈上）──
    # 欄位順序：總資產 / 非投資小計 / 投資小計，再來各項明細
    columns = {
        "時間": "時間", "grand_total": "總資產", "other_assets_total": "非投資小計", "total_twd": "投資小計",
        "bank_total": "銀行", "insurance_total": "保險", "huaisi_total": "懷思投資", "uncle_total": "uncle待還",
        "fx_cash_total": "外幣", "deposits_total": "扣除待還",
        "tw_stock": "台股", "us_stock": "美股", "kifutong": "基富通", "scb": "渣打", "taishin": "台新",
        "total_cost": "投資總成本", "total_pnl": "投資市值損益", "cumulative_dividend": "基金累計配息",
        "trigger": "觸發方式", "note": "備註",
    }
    df_show = df[list(columns)].copy()
    df_show["deposits_total"] = -df_show["deposits_total"]
    df_show = df_show.rename(columns=columns)
    number_cols = [c for c in df_show.columns if c not in {"時間", "觸發方式", "備註"}]
    st.markdown(html_table(df_show, number_cols, max_height=600), unsafe_allow_html=True)
