"""歷史記錄頁：portfolio_snapshots 列表與手動快照。"""
from __future__ import annotations


import pandas as pd
import streamlit as st
from invest_app.core import (
    money,
    supabase_client,
)
from invest_app.non_investment import (
    OTHER_SNAPSHOT_KEYS,
    _take_snapshot_now,
    write_with_optional_columns,
)


def render_history_tab(enriched: pd.DataFrame) -> None:
    """📊 歷史記錄"""
    st.subheader("📊 歷史記錄")

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
                   "請到 Supabase → SQL Editor 執行頁面上方「資料庫欄位提醒」裡 portfolio_snapshots / latest_portfolio_values 那幾行 SQL。")
    st.caption("非投資資產（銀行、保險…總資產）自 2026/10/11 起記錄，之前的快照這幾欄空白。")

    # ── 明細表（愈新愈上）──
    other_labels = {"bank_total": "銀行", "insurance_total": "保險", "huaisi_total": "懷思投資",
                    "uncle_total": "uncle待還", "fx_cash_total": "外幣", "deposits_total": "扣除待還",
                    "other_assets_total": "其他資產小計", "grand_total": "總資產"}
    df_show = df[[
        "時間", "total_twd", "tw_stock", "us_stock",
        "kifutong", "scb", "taishin", *other_labels,
        "total_cost", "total_pnl", "cumulative_dividend", "trigger", "note"
    ]].copy()
    df_show["deposits_total"] = -df_show["deposits_total"]
    df_show.columns = [
        "時間", "總市值", "台股", "美股",
        "基富通", "渣打", "台新", *other_labels.values(),
        "總成本", "市值損益", "累計配息", "觸發方式", "備註"
    ]
    col_cfg = {
        "時間":     st.column_config.TextColumn("時間",       width="small"),
        "總市值":   st.column_config.NumberColumn("總市值",   format="%.0f", width="medium"),
        "台股":     st.column_config.NumberColumn("台股",     format="%.0f", width="medium"),
        "美股":     st.column_config.NumberColumn("美股",     format="%.0f", width="medium"),
        "基富通":   st.column_config.NumberColumn("基富通",   format="%.0f", width="medium"),
        "渣打":     st.column_config.NumberColumn("渣打",     format="%.0f", width="medium"),
        "台新":     st.column_config.NumberColumn("台新",     format="%.0f", width="medium"),
        **{label: st.column_config.NumberColumn(label, format="%.0f", width="medium")
           for label in other_labels.values()},
        "總成本":   st.column_config.NumberColumn("總成本",   format="%.0f", width="medium"),
        "市值損益": st.column_config.NumberColumn("市值損益", format="%.0f", width="medium"),
        "累計配息": st.column_config.NumberColumn("累計配息", format="%.0f", width="medium"),
        "觸發方式": st.column_config.TextColumn("觸發方式",   width="small"),
        "備註":     st.column_config.TextColumn("備註",       width="medium"),
    }
    number_cols = [c for c, cfg in col_cfg.items() if c not in {"時間", "觸發方式", "備註"}]
    # 數字欄用 Styler 格式化：沒有資料的格子顯示空白，不顯示 None。
    col_cfg = {c: (st.column_config.Column(c, width="medium") if c in number_cols else cfg)
               for c, cfg in col_cfg.items()}
    st.dataframe(
        df_show.style.format("{:,.0f}", subset=number_cols, na_rep=""),
        use_container_width=True, hide_index=True,
        height=min(42 * len(df_show) + 44, 600),
        column_config=col_cfg
    )
