"""持倉維護：批次更新、修復排序、貼上清單修復、全部歸零重建、抓價測試、平台持倉編輯表。"""
from __future__ import annotations


import pandas as pd
import streamlit as st
from invest_app.core import (
    ASSET_TYPES,
    CURRENCIES,
    PLATFORMS,
    add_position,
    delete_position,
    ensure_columns,
    mark_position_sold,
    update_positions,
)


def read_uploaded_table(uploaded_file) -> pd.DataFrame:
    filename = uploaded_file.name.lower()
    if filename.endswith(".csv"):
        try:
            return pd.read_csv(uploaded_file, encoding="utf-8-sig")
        except UnicodeDecodeError:
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file, encoding="big5")
    if filename.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)
    raise ValueError("只支援 CSV / Excel 檔案")


def editable_platform_table(platform_name: str, current_positions: pd.DataFrame, editor_key: str) -> None:
    st.markdown("#### ✏️ 編輯 / 新增")
    st.caption("新增列請拉到表格最下方直接輸入；按儲存後會寫入 Supabase。")
    cols = ["sort_order", "id", "platform", "asset_type", "name", "ticker", "fund_code", "fund_pattern",
            "currency", "original_units", "units", "corporate_action", "avg_cost", "total_cost_input",
            "monthly_dividend_per_unit", "purchase_ym", "dividend_received_original_total",
            "dividend_received_total", "dividend_note", "note", "is_reinvest"]
    current_positions = ensure_columns(current_positions)
    if current_positions.empty:
        base = pd.DataFrame(columns=cols)
    else:
        base = current_positions[current_positions["platform"] == platform_name][cols].sort_values(["sort_order", "id"], na_position="last").copy()
    next_sort = 1
    if not current_positions.empty:
        next_sort = int(current_positions["sort_order"].fillna(0).max()) + 1
    blank = {"sort_order": next_sort, "id": None, "platform": platform_name,
             "asset_type": "基金" if platform_name in ["基富通", "渣打基金", "台新基金"] else platform_name,
             "name": "", "ticker": "", "fund_code": "",
             "fund_pattern": "yp010001" if platform_name in ["基富通", "渣打基金", "台新基金"] else "",
             "currency": "TWD" if platform_name in ["台股", "基富通"] else "USD",
             "original_units": 0.0, "units": 0.0, "corporate_action": "", "avg_cost": 0.0,
             "total_cost_input": 0.0, "monthly_dividend_per_unit": 0.0, "purchase_ym": "",
             "dividend_received_original_total": 0.0, "dividend_received_total": 0.0,
             "dividend_note": "", "note": "", "is_reinvest": False}
    base = pd.concat([base, pd.DataFrame([blank])], ignore_index=True)
    edited = st.data_editor(
        base, use_container_width=True, hide_index=True, height=360, num_rows="dynamic",
        column_order=["sort_order", "platform", "asset_type", "name", "ticker", "fund_code", "fund_pattern",
                      "currency", "original_units", "units", "avg_cost", "total_cost_input", "purchase_ym",
                      "dividend_received_original_total", "dividend_received_total",
                      "monthly_dividend_per_unit", "dividend_note", "corporate_action", "note", "is_reinvest"],
        column_config={
            "sort_order": st.column_config.NumberColumn("排序", step=1),
            "platform": st.column_config.SelectboxColumn("平台", options=PLATFORMS, required=True),
            "asset_type": st.column_config.SelectboxColumn("類型", options=ASSET_TYPES, required=True),
            "currency": st.column_config.SelectboxColumn("幣別", options=CURRENCIES, required=True),
            "dividend_received_original_total": st.column_config.NumberColumn("累計配息原幣", format="localized"),
            "dividend_received_total": st.column_config.NumberColumn("累計配息台幣舊欄", format="localized"),
            "is_reinvest": st.column_config.CheckboxColumn("配息再投入"),
        }, key=editor_key,
    )
    c1, c2, c3, c4 = st.columns([1, 1.4, 1.4, 1.4])
    if c1.button("💾 儲存此頁變更", key=f"save_{editor_key}"):
        update_positions(edited); st.success("已儲存"); st.rerun()
    platform_rows = current_positions[current_positions["platform"] == platform_name].copy()
    if not platform_rows.empty:
        platform_rows["選項"] = platform_rows["sort_order"].astype(str) + "｜" + platform_rows["name"].astype(str) + "｜" + platform_rows["ticker"].fillna("").astype(str) + platform_rows["fund_code"].fillna("").astype(str) + "｜ID " + platform_rows["id"].astype(str)
        options = [""] + platform_rows["選項"].tolist()
    else:
        options = [""]
    copy_choice = c2.selectbox("複製股票/基金名稱", options, key=f"copy_name_{editor_key}")
    if c2.button("📋 複製選取品項", key=f"copybtn_{editor_key}") and copy_choice:
        row = platform_rows[platform_rows["選項"] == copy_choice]
        if row.empty:
            st.error("找不到此品項")
        else:
            r = row.iloc[0].to_dict(); r.pop("id", None); r.pop("選項", None); r["sort_order"] = next_sort
            add_position(r); st.success("已複製"); st.rerun()
    sold_choice = c3.selectbox("賣出 / 結清品項", options, key=f"sold_name_{editor_key}")
    if c3.button("✅ 標記賣出 / 結清", key=f"soldbtn_{editor_key}") and sold_choice:
        row = platform_rows[platform_rows["選項"] == sold_choice]
        if row.empty:
            st.error("找不到此品項")
        else:
            mark_position_sold(int(row.iloc[0]["id"])); st.success(f"已標記賣出 / 結清：{row.iloc[0]['name']}"); st.rerun()
    delete_choice = c4.selectbox("刪除股票/基金名稱", options, key=f"delete_name_{editor_key}")
    if c4.button("🗑️ 刪除選取品項", key=f"deletebtn_{editor_key}") and delete_choice:
        row = platform_rows[platform_rows["選項"] == delete_choice]
        if row.empty:
            st.error("找不到此品項")
        else:
            delete_position(int(row.iloc[0]["id"])); st.success(f"已刪除：{row.iloc[0]['name']}"); st.rerun()


