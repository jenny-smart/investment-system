"""持倉維護：批次更新、修復排序、貼上清單修復、全部歸零重建、抓價測試、平台持倉編輯表。"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st
from invest_app.core import (
    ASSET_TYPES,
    CURRENCIES,
    CURRENCY_ALIAS,
    FUND_CNYES_IDS,
    FUND_PRESETS,
    INVESTMENT_ITEMS_DUPLICATE,
    PLATFORMS,
    TW_PRESETS,
    TW_STOCK_NAMES_DUPLICATE,
    US_STOCK_EXCHANGES,
    add_position,
    delete_position,
    ensure_columns,
    fetch_cnyes_fund_nav,
    fetch_fund_nav,
    fetch_fx,
    fetch_gas_fund_nav,
    fetch_google_finance_price,
    fetch_moneydj_nav,
    fetch_stock_price,
    fetch_twse_realtime_quote,
    fetch_yahoo_price,
    is_tw_stock_ticker,
    load_positions,
    mark_position_sold,
    normalize_match_name,
    normalize_number,
    normalize_payload,
    normalize_text,
    normalize_ticker,
    right_align_numbers,
    supabase_client,
    update_positions,
)


def seed_presets() -> None:
    existing = load_positions()
    if not existing.empty:
        return
    sort_order = 1
    for name in TW_STOCK_NAMES_DUPLICATE:
        add_position({"sort_order": sort_order, "platform": "台股", "asset_type": "台股",
                      "name": name, "ticker": TW_PRESETS.get(name, ""), "fund_code": "",
                      "fund_pattern": "", "currency": "TWD", "original_units": 0, "units": 0,
                      "corporate_action": "", "avg_cost": 0, "total_cost_input": 0,
                      "monthly_dividend_per_unit": 0, "purchase_ym": "", "dividend_received_total": 0,
                      "dividend_note": "", "note": f"預設台股清單：{name}"})
        sort_order += 1
    for platform, currency, asset_type, name, ticker, fund_code, fund_pattern in INVESTMENT_ITEMS_DUPLICATE:
        add_position({"sort_order": sort_order, "platform": platform, "asset_type": asset_type,
                      "name": name, "ticker": ticker, "fund_code": fund_code,
                      "fund_pattern": fund_pattern, "currency": currency, "original_units": 0,
                      "units": 0, "corporate_action": "", "avg_cost": 0, "total_cost_input": 0,
                      "monthly_dividend_per_unit": 0, "purchase_ym": "", "dividend_received_total": 0,
                      "dividend_note": "", "note": "預設投資清單"})
        sort_order += 1


def build_upload_template(positions: pd.DataFrame) -> pd.DataFrame:
    cols = ["sort_order", "platform", "name", "avg_cost", "total_cost_input", "original_units",
            "units", "monthly_dividend_per_unit", "purchase_ym", "dividend_received_original_total",
            "dividend_received_total",
            "dividend_note", "corporate_action"]
    if positions.empty:
        return pd.DataFrame(columns=cols)
    return ensure_columns(positions)[cols].sort_values(["sort_order"]).copy()


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


def apply_batch_update(upload_df: pd.DataFrame, current_positions: pd.DataFrame) -> tuple[int, int, list[str]]:
    sb = supabase_client()
    current = ensure_columns(current_positions)
    if "sort_order" not in upload_df.columns:
        raise ValueError("上傳檔案必須包含 sort_order 欄位")
    required_cols = ["sort_order", "platform", "name", "avg_cost", "total_cost_input", "original_units", "units"]
    missing = [c for c in required_cols if c not in upload_df.columns]
    if missing:
        raise ValueError("上傳檔案缺少欄位：" + ", ".join(missing))
    updated, inserted, skipped = 0, 0, []
    current_by_order = {}
    if not current.empty:
        for _, row in current.iterrows():
            so = normalize_number(row.get("sort_order", 0), 0)
            if so:
                current_by_order[so] = row
    for i, r in upload_df.iterrows():
        payload = normalize_payload(r)
        if not payload["name"]:
            skipped.append(f"第 {i + 2} 列：name 空白"); continue
        so = payload["sort_order"]
        if not so:
            skipped.append(f"第 {i + 2} 列：sort_order 空白或 0"); continue
        old_row = current_by_order.get(so)
        if old_row is not None:
            merged = normalize_payload(old_row)
            merged.update(payload)
            sb.table("positions").update(merged).eq("id", int(old_row["id"])).execute()
            updated += 1
        else:
            sb.table("positions").insert(payload).execute()
            inserted += 1
    return updated, inserted, skipped


def canonical_order_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    order = 1
    for name in TW_STOCK_NAMES_DUPLICATE:
        rows.append({"target_order": order, "platform": "台股", "asset_type": "台股", "name": name, "currency": "TWD"})
        order += 1
    for platform, currency, asset_type, name, ticker, fund_code, fund_pattern in INVESTMENT_ITEMS_DUPLICATE:
        rows.append({"target_order": order, "platform": platform, "asset_type": asset_type, "name": name, "currency": currency})
        order += 1
    return rows


def build_sort_repair_preview(current_positions: pd.DataFrame) -> pd.DataFrame:
    current = ensure_columns(current_positions).copy()
    if current.empty:
        return pd.DataFrame()
    current["_old_sort_order"] = current["sort_order"].apply(lambda x: normalize_number(x, 0))
    current["_id_sort"] = current["id"].apply(lambda x: normalize_number(x, 999999999))
    current["_matched"] = False
    current["_new_sort_order"] = None
    current["_match_note"] = ""
    current["_match_platform"] = current["platform"].astype(str).str.strip()
    current["_match_name"] = current["name"].astype(str).str.strip()
    current["_match_currency"] = current["currency"].astype(str).str.strip()
    buckets: dict[tuple, list[int]] = {}
    for idx, row in current.sort_values(["_id_sort"]).iterrows():
        key = (normalize_text(row.get("_match_platform", "")), normalize_text(row.get("_match_name", "")), normalize_text(row.get("_match_currency", "")))
        buckets.setdefault(key, []).append(idx)
    for target in canonical_order_rows():
        key = (normalize_text(target["platform"]), normalize_text(target["name"]), normalize_text(target["currency"]))
        bucket = buckets.get(key, [])
        if bucket:
            idx = bucket.pop(0)
            current.at[idx, "_new_sort_order"] = target["target_order"]
            current.at[idx, "_matched"] = True
            current.at[idx, "_match_note"] = "已依預設清單配對"
    next_order = len(canonical_order_rows()) + 1
    unmatched = current[current["_matched"] == False].sort_values(["_old_sort_order", "_id_sort"])
    for idx, row in unmatched.iterrows():
        current.at[idx, "_new_sort_order"] = next_order
        current.at[idx, "_match_note"] = "未在預設清單，排到最後"
        next_order += 1
    preview_cols = ["id", "platform", "currency", "name", "_old_sort_order", "_new_sort_order", "_match_note", "ticker", "fund_code", "units", "avg_cost", "total_cost_input"]
    return current[preview_cols].rename(columns={"_old_sort_order": "目前排序", "_new_sort_order": "修復後排序", "_match_note": "修復狀態"})


def apply_sort_repair(preview_df: pd.DataFrame) -> int:
    if preview_df.empty:
        return 0
    sb = supabase_client()
    count = 0
    for _, r in preview_df.iterrows():
        rid = r.get("id")
        new_order = r.get("修復後排序")
        if pd.isna(rid) or pd.isna(new_order):
            continue
        sb.table("positions").update({"sort_order": float(new_order)}).eq("id", int(float(rid))).execute()
        count += 1
    return count


def parse_pasted_order_text(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    order = 1
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "\t" in line:
            parts = [p.strip() for p in line.split("\t") if p.strip()]
        else:
            parts = line.split(maxsplit=2)
        if len(parts) < 3:
            continue
        raw_platform, raw_currency, name = parts[0], parts[1], parts[2]
        currency = CURRENCY_ALIAS.get(raw_currency, raw_currency)
        rows.append({"target_order": order, "raw_platform": raw_platform, "raw_currency": raw_currency, "currency": currency, "name": name.strip()})
        order += 1
    return rows


def platform_candidates_from_raw(raw_platform: str, raw_currency: str) -> list[str]:
    raw_platform = normalize_text(raw_platform)
    raw_currency = normalize_text(raw_currency)
    if raw_platform == "基富通":
        return ["基富通"]
    if raw_platform == "渣打":
        if raw_currency == "美股":
            return ["美股", "渣打"]
        return ["渣打基金", "渣打"]
    if raw_platform == "台新":
        return ["台新基金", "台新"]
    return [raw_platform]


def build_pasted_sort_repair_preview(current_positions: pd.DataFrame, pasted_text: str) -> pd.DataFrame:
    current = ensure_columns(current_positions).copy()
    targets = parse_pasted_order_text(pasted_text)
    if current.empty or not targets:
        return pd.DataFrame()
    current["_old_sort_order"] = current["sort_order"].apply(lambda x: normalize_number(x, 0))
    current["_id_sort"] = current["id"].apply(lambda x: normalize_number(x, 999999999))
    current["_matched"] = False
    current["_new_sort_order"] = None
    current["_match_note"] = ""
    buckets: dict[tuple, list[int]] = {}
    for idx, row in current.sort_values(["_id_sort"]).iterrows():
        key = (normalize_text(row.get("platform", "")), normalize_text(row.get("currency", "")), normalize_match_name(row.get("name", "")))
        buckets.setdefault(key, []).append(idx)
    for target in targets:
        name_key = normalize_match_name(target["name"])
        currency = normalize_text(target["currency"])
        candidates = platform_candidates_from_raw(target["raw_platform"], target["raw_currency"])
        matched_idx = None
        for platform in candidates:
            key = (platform, currency, name_key)
            if buckets.get(key):
                matched_idx = buckets[key].pop(0)
                break
        if matched_idx is not None:
            current.at[matched_idx, "_new_sort_order"] = target["target_order"]
            current.at[matched_idx, "_matched"] = True
            current.at[matched_idx, "_match_note"] = f"依貼上清單配對：{target['raw_platform']} / {target['raw_currency']}"
    next_order = len(targets) + 1
    unmatched = current[current["_matched"] == False].sort_values(["_old_sort_order", "_id_sort"])
    for idx, row in unmatched.iterrows():
        current.at[idx, "_new_sort_order"] = next_order
        current.at[idx, "_match_note"] = "貼上清單未配對，保留在最後"
        next_order += 1
    preview_cols = ["id", "platform", "currency", "name", "_old_sort_order", "_new_sort_order", "_match_note", "ticker", "fund_code", "units", "avg_cost", "total_cost_input"]
    return current[preview_cols].rename(columns={"_old_sort_order": "目前排序", "_new_sort_order": "修復後排序", "_match_note": "修復狀態"})


def pasted_order_repair_section(current_positions: pd.DataFrame) -> None:
    st.markdown("#### 📋 依你貼上的原始清單修復排序")
    st.warning("這裡只會更新 sort_order，不會改成本、股數、名稱、代碼。")
    if current_positions.empty:
        st.info("目前沒有資料可修復。"); return
    backup = ensure_columns(current_positions).sort_values(["sort_order", "id"], na_position="last")
    st.download_button("⬇️ 先下載完整備份 CSV", data=backup.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"), file_name="positions_backup_before_paste_order_repair.csv", mime="text/csv", key="download_backup_before_paste_order_repair")
    pasted = st.text_area("貼上你的原始三欄清單：平台、幣別/類別、名稱", height=320, key="pasted_order_text")
    targets = parse_pasted_order_text(pasted)
    if pasted:
        st.caption(f"已解析 {len(targets)} 列。")
    if not targets:
        return
    preview = build_pasted_sort_repair_preview(current_positions, pasted)
    if preview.empty:
        st.error("無法建立預覽，請確認貼上的文字至少有三欄。"); return
    st.dataframe(right_align_numbers(preview), use_container_width=True, hide_index=True, height=520)
    not_matched_count = int(preview["修復狀態"].astype(str).str.contains("未配對").sum())
    if not_matched_count:
        st.warning(f"有 {not_matched_count} 筆目前資料未在貼上清單配對，會被排到最後。")
    st.download_button("⬇️ 下載排序修復預覽 CSV", data=preview.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"), file_name="pasted_order_repair_preview.csv", mime="text/csv", key="download_pasted_order_repair_preview")
    confirm = st.checkbox("我已下載備份，確認只更新 sort_order", key="confirm_pasted_order_repair")
    if st.button("✅ 套用貼上清單排序", key="apply_pasted_order_repair", disabled=not confirm):
        n = apply_sort_repair(preview)
        st.success(f"已更新 {n} 筆 sort_order。"); st.rerun()


def sort_repair_section(current_positions: pd.DataFrame) -> None:
    st.markdown("#### 🧭 修復排序")
    st.warning("只會更新 sort_order，不會修改成本、股數、名稱、ticker、fund_code。")
    if current_positions.empty:
        st.info("目前沒有資料可修復。"); return
    backup = ensure_columns(current_positions).sort_values(["sort_order", "id"], na_position="last")
    st.download_button("⬇️ 修復前先下載完整備份 CSV", data=backup.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"), file_name="positions_backup_before_sort_repair.csv", mime="text/csv", key="download_backup_before_sort_repair")
    preview = build_sort_repair_preview(current_positions)
    st.caption("預覽：系統會依預設清單順序重排。")
    st.dataframe(right_align_numbers(preview), use_container_width=True, hide_index=True, height=520)
    csv = preview.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button("⬇️ 下載排序修復預覽 CSV", data=csv, file_name="sort_repair_preview.csv", mime="text/csv", key="download_sort_repair_preview")
    confirm = st.checkbox("我已下載備份，確認只更新 sort_order", key="confirm_sort_repair")
    if st.button("✅ 套用排序修復", key="apply_sort_repair", disabled=not confirm):
        n = apply_sort_repair(preview)
        st.success(f"已更新 {n} 筆 sort_order。"); st.rerun()


def upload_batch_section(current_positions: pd.DataFrame) -> None:
    st.markdown("#### 📤 CSV / Excel 批次更新")
    st.caption("名稱可重複，更新依據是 sort_order。")
    template = build_upload_template(current_positions)
    csv_bytes = template.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button("⬇️ 下載目前資料批次更新範例 CSV", data=csv_bytes, file_name="positions_upload_template.csv", mime="text/csv")
    uploaded = st.file_uploader("上傳 CSV / Excel", type=["csv", "xlsx", "xls"], key="batch_upload_file")
    if uploaded is not None:
        try:
            upload_df = read_uploaded_table(uploaded)
            st.dataframe(right_align_numbers(upload_df.head(50)), use_container_width=True, hide_index=True)
            if st.button("✅ 執行批次更新", key="run_batch_update"):
                updated, inserted, skipped = apply_batch_update(upload_df, current_positions)
                st.success(f"批次更新完成：更新 {updated} 筆，新增 {inserted} 筆，略過 {len(skipped)} 筆。")
                if skipped:
                    st.warning("\n".join(skipped[:20]))
                st.rerun()
        except Exception as e:
            st.error(f"上傳檔案處理失敗：{e}")


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


def price_test_section() -> None:
    st.subheader("抓價測試")
    st.caption("用這裡確認美股 ticker、基金代碼與匯率是否能抓到。")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 美股 / 台股")
        ticker = st.text_input("Ticker", value="PYPL", key="test_ticker")
        if st.button("測試股票價格", key="test_yahoo_price"):
            normalized = normalize_ticker(ticker)
            y_price, y_status = fetch_yahoo_price(normalized)
            g_price, g_status = fetch_google_finance_price(normalized, US_STOCK_EXCHANGES.get(normalized))
            tw_quote = fetch_twse_realtime_quote(normalized) if is_tw_stock_ticker(normalized) else {}
            final_price, final_status = fetch_stock_price(normalized, "台股" if is_tw_stock_ticker(normalized) else "美股")
            st.write({"ticker": normalized, "exchange": US_STOCK_EXCHANGES.get(normalized, "NASDAQ"),
                      "twse_quote": tw_quote,
                      "yahoo_price": y_price, "yahoo_status": y_status,
                      "google_price": g_price, "google_status": g_status,
                      "final_price": final_price, "final_status": final_status})
    with c2:
        st.markdown("#### 基金")
        fund_code_test = st.text_input("MoneyDJ 代號", value="acft94", key="test_fund_code")
        if st.button("測試基金淨值（所有來源）", key="test_fund_nav"):
            cnyes_id = FUND_CNYES_IDS.get(fund_code_test, "")
            pattern = FUND_PRESETS.get(fund_code_test, ("", "yp010000", "", ""))[1]
            results = {}
            nav0, st0 = fetch_gas_fund_nav(fund_code_test)
            results["GAS中繼（MoneyDJ→鉅亨）"] = {"nav": nav0, "status": st0}
            nav2, st2 = fetch_moneydj_nav(fund_code_test, pattern)
            results[f"MoneyDJ直連({pattern})"] = {"nav": nav2, "status": st2}
            if cnyes_id:
                nav1, st1 = fetch_cnyes_fund_nav(cnyes_id)
                results[f"鉅亨API直連({cnyes_id})"] = {"nav": nav1, "status": st1}
            nav_f, st_f = fetch_fund_nav(fund_code_test, pattern)
            results["✅ 最終結果"] = {"nav": nav_f, "status": st_f}
            st.write(results)
            if nav0:
                st.success(f"GAS 成功抓到：{nav0}（來源：{st0}）")
            else:
                st.warning(f"GAS 失敗：{st0}")
        st.markdown("---")
        st.markdown("**所有基金鉅亨 ID 對照：**")
        cnyes_rows = [{"MoneyDJ代號": k, "鉅亨ID": v, "名稱": FUND_PRESETS.get(k, ("?",))[0]}
                      for k, v in FUND_CNYES_IDS.items()]
        st.dataframe(pd.DataFrame(cnyes_rows), use_container_width=True, hide_index=True)
    st.markdown("#### 匯率")
    fx_rows = []
    for cur in ["USD", "ZAR", "CNY", "JPY", "TWD"]:
        rate, status = fetch_fx(cur)
        fx_rows.append({"currency": cur, "rate": rate, "status": status})
    st.dataframe(right_align_numbers(pd.DataFrame(fx_rows)), use_container_width=True, hide_index=True)


def infer_asset_from_pasted(raw_platform: str, raw_currency: str, name: str) -> dict[str, Any]:
    raw_platform = normalize_text(raw_platform)
    raw_currency = normalize_text(raw_currency)
    clean_name = normalize_text(name)
    lower_name = clean_name.lower()
    currency = CURRENCY_ALIAS.get(raw_currency, raw_currency)
    if raw_platform == "基富通":
        platform = "基富通"
    elif raw_platform == "渣打":
        platform = "美股" if raw_currency == "美股" else "渣打基金"
    elif raw_platform == "台新":
        platform = "台新基金"
    else:
        platform = raw_platform
    if raw_currency == "美股" or lower_name in {"pypl", "xyz"}:
        asset_type = "美股"; ticker = clean_name.upper(); fund_code = ""; fund_pattern = ""; currency = "USD"; name_out = clean_name.upper()
    else:
        asset_type = "基金" if platform in ["基富通", "渣打基金", "台新基金"] else "台股"
        ticker = ""; fund_code = ""; fund_pattern = ""
        if "富蘭克林華美新興國家固定收益" in clean_name and ("新臺幣" in clean_name or "新台幣" in clean_name):
            fund_code, fund_pattern = "acft94", "yp010000"
        elif "柏瑞新興邊境非投資等級債券" in clean_name:
            fund_code, fund_pattern = "acai222", "yp010000"
        elif "富蘭克林華美新興國家固定收益" in clean_name and "人民幣" in clean_name:
            fund_code, fund_pattern = "acft99", "yp010000"
        elif "貝萊德全球智慧數據股票入息" in clean_name:
            fund_code, fund_pattern = "shzx0", "yp010001"
        elif "安聯收益成長" in clean_name:
            fund_code, fund_pattern = "TLZO3", "yp010001"
        elif "大華銀新加坡房地產收益" in clean_name:
            fund_code, fund_pattern = "acob36", "yp010000"
        elif "東方匯理" in clean_name and "新興市場債券A美元" in clean_name:
            fund_code, fund_pattern = "pizn8", "yp010001"
        elif "東方匯理" in clean_name and ("新興市場債券U 美元" in clean_name or "新興市場債券Ｕ 美元" in clean_name or "新興市場債券U美元" in clean_name):
            fund_code, fund_pattern = "pizo1", "yp010001"
        elif "東方匯理" in clean_name and "南非幣" in clean_name:
            fund_code, fund_pattern = "pizm9", "yp010001"; currency = "ZAR"
        elif "高盛新興市場債券基金Y股美元" in clean_name:
            fund_code, fund_pattern = "anzb6", "yp010001"
        elif "高盛新興市場債券基金Ｙ" in clean_name and "南非幣" in clean_name:
            fund_code, fund_pattern = "ANZH2", "yp010001"; currency = "ZAR"
        name_out = clean_name
    return {"platform": platform, "asset_type": asset_type, "name": name_out, "ticker": ticker,
            "fund_code": fund_code, "fund_pattern": fund_pattern, "currency": currency,
            "original_units": 0, "units": 0, "corporate_action": "", "avg_cost": 0,
            "total_cost_input": 0, "monthly_dividend_per_unit": 0, "purchase_ym": "",
            "dividend_received_original_total": 0, "dividend_received_total": 0, "dividend_note": "",
            "note": f"依原始清單重建：{raw_platform} / {raw_currency}"}


def build_reset_seed_df_from_pasted(pasted_text: str) -> pd.DataFrame:
    targets = parse_pasted_order_text(pasted_text)
    rows = []
    for t in targets:
        row = infer_asset_from_pasted(t["raw_platform"], t["raw_currency"], t["name"])
        row["sort_order"] = t["target_order"]; row["原始平台"] = t["raw_platform"]; row["原始幣別"] = t["raw_currency"]
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    cols = ["sort_order", "原始平台", "原始幣別", "platform", "asset_type", "name", "ticker", "fund_code",
            "fund_pattern", "currency", "total_cost_input", "original_units", "units", "avg_cost",
            "monthly_dividend_per_unit", "purchase_ym", "dividend_received_original_total",
            "dividend_received_total", "dividend_note", "corporate_action", "note"]
    return pd.DataFrame(rows)[cols]


def delete_all_positions() -> int:
    current = load_positions()
    if current.empty:
        return 0
    sb = supabase_client()
    count = 0
    for _, r in current.iterrows():
        rid = r.get("id")
        if pd.isna(rid):
            continue
        sb.table("positions").delete().eq("id", int(float(rid))).execute()
        count += 1
    return count


def rebuild_positions_from_seed_df(seed_df: pd.DataFrame) -> int:
    if seed_df.empty:
        return 0
    insert_cols = ["sort_order", "platform", "asset_type", "name", "ticker", "fund_code", "fund_pattern",
                   "currency", "original_units", "units", "corporate_action", "avg_cost", "total_cost_input",
                   "monthly_dividend_per_unit", "purchase_ym", "dividend_received_original_total",
                   "dividend_received_total", "dividend_note", "note"]
    sb = supabase_client()
    count = 0
    for _, r in seed_df.iterrows():
        payload = {col: r.get(col) for col in insert_cols}
        payload = normalize_payload(payload)
        sb.table("positions").insert(payload).execute()
        count += 1
    return count


def force_zero_all_positions() -> int:
    current = load_positions()
    if current.empty:
        return 0
    sb = supabase_client()
    count = 0
    zero_payload = {"original_units": 0, "units": 0, "avg_cost": 0, "total_cost_input": 0,
                    "monthly_dividend_per_unit": 0, "dividend_received_original_total": 0,
                    "dividend_received_total": 0, "dividend_note": "", "corporate_action": ""}
    for _, r in current.iterrows():
        rid = r.get("id")
        if pd.isna(rid):
            continue
        sb.table("positions").update(zero_payload).eq("id", int(float(rid))).execute()
        count += 1
    return count


def full_reset_rebuild_section(current_positions: pd.DataFrame) -> None:
    st.markdown("#### 🧨 全部歸零並依原始清單重建")
    st.error("這會刪除 positions 全部資料，重新建立成本、股數、配息皆為 0 的乾淨清單。請務必先下載備份。")
    backup = ensure_columns(current_positions).sort_values(["sort_order", "id"], na_position="last")
    st.download_button("⬇️ 下載目前資料備份 CSV", data=backup.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"), file_name="positions_backup_before_FULL_RESET.csv", mime="text/csv", key="download_backup_before_full_reset", disabled=backup.empty)
    pasted = st.text_area("貼上你的原始三欄清單", height=360, key="full_reset_pasted_order_text")
    seed_df = build_reset_seed_df_from_pasted(pasted)
    if pasted and seed_df.empty:
        st.warning("沒有解析到資料。請確認每列至少有：平台、幣別/類別、名稱。"); return
    if not seed_df.empty:
        st.success(f"已解析 {len(seed_df)} 筆，將以這些資料重建。")
        st.dataframe(right_align_numbers(seed_df), use_container_width=True, hide_index=True, height=520)
        st.download_button("⬇️ 下載即將重建的乾淨清單 CSV", data=seed_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"), file_name="positions_clean_rebuild_preview.csv", mime="text/csv", key="download_clean_rebuild_preview")
    typed = st.text_input("若確認要全部刪除並重建，請輸入 RESET", key="full_reset_confirm_text")
    confirm_backup = st.checkbox("我已下載備份，確認要全部歸零重建", key="full_reset_confirm_backup")
    st.markdown("#### 只歸零目前資料")
    st.caption("如果你不想刪除重建，只想把現有所有成本、股數、配息歸零，可用這個。")
    zero_only_confirm = st.checkbox("我確認只把目前資料全部歸零，不刪除列", key="zero_only_confirm")
    if st.button("🧹 只歸零目前所有資料", key="zero_only_button", disabled=not zero_only_confirm):
        zeroed = force_zero_all_positions()
        st.success(f"已強制歸零 {zeroed} 筆資料。"); st.cache_data.clear(); st.rerun()
    disabled = not (typed == "RESET" and confirm_backup and not seed_df.empty)
    if st.button("🧨 刪除全部 positions 並重建", key="run_full_reset_rebuild", disabled=disabled):
        deleted = delete_all_positions()
        inserted = rebuild_positions_from_seed_df(seed_df)
        zeroed = force_zero_all_positions()
        st.success(f"完成：已刪除 {deleted} 筆，重建 {inserted} 筆，強制歸零 {zeroed} 筆。")
        st.cache_data.clear(); st.rerun()


def render_tools_page(positions) -> None:
    st.subheader("工具")
    tool_choice = st.selectbox(
        "選擇工具",
        ["批次更新", "修復排序", "貼上清單修復", "全部歸零重建", "抓價測試"],
        key="tool_menu",
    )
    if tool_choice == "批次更新":
        upload_batch_section(positions)
    elif tool_choice == "修復排序":
        sort_repair_section(positions)
    elif tool_choice == "貼上清單修復":
        pasted_order_repair_section(positions)
    elif tool_choice == "全部歸零重建":
        full_reset_rebuild_section(positions)
    elif tool_choice == "抓價測試":
        price_test_section()
