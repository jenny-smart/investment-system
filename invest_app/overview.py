"""投資總覽：各平台群組卡片與明細表、匯率總覽。"""
from __future__ import annotations


import html
import pandas as pd
import streamlit as st
from invest_app.core import (
    two_line_metric,
    TW_STOCK_SELL_COST_RATE,
    CURRENCIES,
    _get_gas_date,
    fetch_fx,
    fmt_md,
    money,
    normalize_text,
    pct,
    signed_money,
    supabase_client,
    to_float,
    tw_now,
)


OVERVIEW_ORDER = ["台股", "美股", "基富通", "渣打基金", "台新基金"]


PLATFORM_ICONS = {"台股": "📈", "美股": "🇺🇸", "基富通": "🟧", "渣打基金": "🏦", "台新基金": "🟥"}


# 子平台群組定義（sub_label, currency_filter）
SUB_GROUPS: dict[str, list[tuple[str, str]]] = {
    "基富通":  [("基富通-台", "TWD"), ("基富通-人民幣", "CNY"), ("基富通-日", "JPY")],
    "渣打基金":[("渣打-美金",  "USD"), ("渣打-南非",    "ZAR")],
    "台新基金":[("台新-美金",  "USD"), ("台新-南非",    "ZAR")],
    "美股":    [("美股",       "USD")],
    "台股":    [("台股",       "TWD")],
}


def _merge_positions(p_rows: pd.DataFrame, asset_type: str) -> pd.DataFrame:
    """
    合併同一檔股票/基金的多筆持倉 → 一行顯示。
    - 基金：key = fund_code（空的跳過，用 name 代替）
    - 股票：key = ticker（空的用 name）
    數值加總：台幣成本/市值/損益/配息/單位數。
    取第一筆：名稱/即時價/匯率/currency 等。
    """
    if p_rows.empty:
        return pd.DataFrame()

    is_stock = asset_type in {"台股", "美股"}

    # 決定合併 key，空值用 name 補
    if is_stock:
        key_series = p_rows["ticker"].fillna("").replace("", None).combine_first(p_rows["name"])
    else:
        key_series = p_rows["fund_code"].fillna("").replace("", None).combine_first(p_rows["name"])

    p_rows = p_rows.copy()
    p_rows["_merge_key"] = key_series

    sum_cols   = ["台幣成本", "台幣市值", "賣出稅費", "扣稅後市值", "含息總損益", "累計配息原幣", "累計已領配息", "每月配息",
                  "units", "original_units", "total_cost_input", "dividend_received_total"]
    first_cols = ["name", "currency", "ticker", "fund_code", "fund_pattern",
                  "即時價格/淨值", "基金淨值日期", "匯率", "platform", "asset_type", "id"]

    merged_rows = []
    for key_val, grp in p_rows.groupby("_merge_key", dropna=False):
        row: dict = {}
        for c in first_cols:
            if c in grp.columns:
                row[c] = grp[c].iloc[0]
        for c in sum_cols:
            if c in grp.columns:
                row[c] = grp[c].fillna(0).sum()
        cost = row.get("台幣成本", 0)
        pnl  = row.get("含息總損益", 0)
        row["含息總損益率"] = pnl / cost if cost else None
        row["損益率"]       = row["含息總損益率"]
        merged_rows.append(row)

    return pd.DataFrame(merged_rows)


def render_sub_group(sub_label: str, sub_rows: pd.DataFrame) -> None:
    """
    單一子平台：藍色小標題 + 明細表（每檔一行）
    欄位固定寬度，對齊 Google Sheet 格式：
    名稱 / 日期 / 現值 / 損益 / 台幣成本 / 台幣市值 / 累積配息 / 月配息 / 配息率 / 損益率
    """
    if sub_rows.empty:
        return

    total_val  = sub_rows["台幣市值"].fillna(0).sum()
    total_pnl  = sub_rows["含息總損益"].fillna(0).sum()
    total_cost = sub_rows["台幣成本"].fillna(0).sum()
    total_div  = sub_rows["累計已領配息"].fillna(0).sum()
    total_mdiv = sub_rows["每月配息"].fillna(0).sum()
    total_rate = total_pnl / total_cost if total_cost else None
    pnl_color  = "#6ee7b7" if total_pnl >= 0 else "#fca5a5"

    sell_cost_sub = sub_rows["賣出稅費"].fillna(0).sum() if "賣出稅費" in sub_rows else 0
    nav_pnl_sub   = total_val - total_cost - sell_cost_sub if total_val and total_cost else 0
    total_pnl_sub = nav_pnl_sub + total_div
    nav_color  = "#6ee7b7" if nav_pnl_sub >= 0 else "#fca5a5"
    tot_color  = "#6ee7b7" if total_pnl_sub >= 0 else "#fca5a5"

    st.markdown(f"""
<div style="background:#f0fdf4;color:#1a2e22;padding:8px 16px;border-radius:8px;
            display:flex;flex-wrap:wrap;align-items:center;gap:14px;
            margin:6px 0 1px 20px;font-size:12px;font-weight:600;
            border:1px solid #bbf7d0;border-left:3px solid #10b981;">
  <span style="font-size:12px;font-family:sans-serif;min-width:90px;font-weight:800;color:#065f46">{sub_label}</span>
  <span style="min-width:100px;font-family:monospace">
    <span style="color:#9ca3af;font-size:10px">成本 </span>{money(total_cost)}</span>
  <span style="min-width:100px;font-family:monospace">
    <span style="color:#9ca3af;font-size:10px">市值 </span>{money(total_val)}</span>
  <span style="min-width:110px;font-family:monospace">
    <span style="color:#9ca3af;font-size:10px">市值損益 </span>
    <span style="color:{'#059669' if nav_pnl_sub>=0 else '#dc2626'};font-weight:700">{signed_money(nav_pnl_sub)}</span></span>
  <span style="min-width:90px;font-family:monospace">
    <span style="color:#9ca3af;font-size:10px">配息 </span>
    <span style="color:#0284c7">{money(total_div)}</span></span>
  <span style="min-width:110px;font-family:monospace">
    <span style="color:#9ca3af;font-size:10px">總損益 </span>
    <span style="color:{'#059669' if total_pnl_sub>=0 else '#dc2626'};font-weight:800">{signed_money(total_pnl_sub)}</span></span>
  <span style="min-width:80px;font-family:monospace">
    <span style="color:#9ca3af;font-size:10px">月配息 </span>
    <span style="color:#7c3aed">{money(total_mdiv)}</span></span>
</div>
""", unsafe_allow_html=True)

    rows_disp = []
    for _, pr in sub_rows.iterrows():
        atype     = normalize_text(pr.get("asset_type", ""))
        price_val = to_float(pr.get("即時價格/淨值"))
        cost_val  = to_float(pr.get("台幣成本")) or 0.0
        mval      = to_float(pr.get("台幣市值")) or 0.0
        pnl_val   = to_float(pr.get("含息總損益"))
        div_original = to_float(pr.get("累計配息原幣")) or 0.0
        div_val   = to_float(pr.get("累計已領配息")) or 0.0
        mdiv      = to_float(pr.get("每月配息")) or 0.0
        rate_val  = to_float(pr.get("含息總損益率"))
        ann_rate  = (mdiv * 12 / cost_val) if cost_val and mdiv else None

        # 取報價日期
        if atype in {"台股", "美股"}:
            date_str = fmt_md(tw_now())
        else:
            fc       = normalize_text(pr.get("fund_code", ""))
            date_str = normalize_text(pr.get("基金淨值日期", ""), "")
            if not date_str or date_str == "—":
                date_str = _get_gas_date(fc) if fc else "—"

        if price_val is None:
            date_str = "❌"

        # 市值損益 = 台幣市值 - 台幣成本 - 賣出稅費（台股；不含配息）
        nav_pnl = (mval - cost_val - (to_float(pr.get("賣出稅費")) or 0)) if mval and cost_val else None
        nav_pnl_rate = (nav_pnl / cost_val * 100) if nav_pnl is not None and cost_val else None
        total_pnl_val = (nav_pnl + div_val) if nav_pnl is not None else None
        total_pnl_rate = (total_pnl_val / cost_val * 100) if total_pnl_val is not None and cost_val else None

        rows_disp.append({
            "名稱":     normalize_text(pr.get("name", "")),
            "日期":     date_str,
            "現值":     round(price_val, 2)      if price_val is not None else None,
            "台幣成本": round(cost_val, 0)        if cost_val else None,
            "台幣市值": round(mval, 0)            if mval     else None,
            "賣出稅費": round(to_float(pr.get("賣出稅費")) or 0, 0) if to_float(pr.get("賣出稅費")) else None,
            "扣稅後市值": round(to_float(pr.get("扣稅後市值")) or 0, 0) if to_float(pr.get("賣出稅費")) else None,
            "市值損益": round(nav_pnl, 0)         if nav_pnl  is not None else None,
            "累積配息原幣": round(div_original, 2) if div_original else None,
            "累積配息": round(div_val, 0)         if div_val  else None,
            "總損益":   round(total_pnl_val, 0)   if total_pnl_val is not None else None,
            "市值損益率%": round(nav_pnl_rate, 2) if nav_pnl_rate is not None else None,
            "總損益率%":  round(total_pnl_rate, 2) if total_pnl_rate is not None else None,
            "月配息":   round(mdiv, 0)            if mdiv     else None,
            "配息率%":  round(ann_rate * 100, 2)  if ann_rate else None,
        })

    if rows_disp:
        df_disp = pd.DataFrame(rows_disp)
        if df_disp["賣出稅費"].isna().all():  # 只有台股有賣出稅費，其他平台不顯示這兩欄
            df_disp = df_disp.drop(columns=["賣出稅費", "扣稅後市值"])
        col_cfg = {
            "名稱":       st.column_config.TextColumn("名稱",       width="large"),
            "日期":       st.column_config.TextColumn("日期",       width="small"),
            "現值":       st.column_config.NumberColumn("現值",     width="small",  format="%.2f"),
            "台幣成本":   st.column_config.NumberColumn("台幣成本", width="medium", format="%.0f"),
            "台幣市值":   st.column_config.NumberColumn("台幣市值", width="medium", format="%.0f"),
            "賣出稅費":   st.column_config.NumberColumn("賣出稅費", width="small", format="%.0f"),
            "扣稅後市值": st.column_config.NumberColumn("扣稅後市值", width="medium", format="%.0f"),
            "市值損益":   st.column_config.NumberColumn("市值損益", width="medium", format="%.0f"),
            "累積配息原幣": st.column_config.NumberColumn("累積配息原幣", width="medium", format="%.2f"),
            "累積配息":   st.column_config.NumberColumn("累積配息", width="medium", format="%.0f"),
            "總損益":     st.column_config.NumberColumn("總損益",   width="medium", format="%.0f"),
            "市值損益率%":st.column_config.NumberColumn("市值損益率%", width="small", format="%.2f"),
            "總損益率%":  st.column_config.NumberColumn("總損益率%",  width="small", format="%.2f"),
            "月配息":     st.column_config.NumberColumn("月配息",   width="small",  format="%.0f"),
            "配息率%":    st.column_config.NumberColumn("配息率%",  width="small",  format="%.2f"),
        }
        # 台股/美股列數多，固定2列高度可上下滾動；基金類自適應
        if sub_label in {"台股", "美股"}:
            tbl_height = 42 * 2 + 44
        else:
            tbl_height = min(42 * len(df_disp) + 44, 480)
        st.dataframe(df_disp, use_container_width=True, hide_index=True,
                     height=tbl_height,
                     column_config=col_cfg)


def render_platform_group(platform: str, p_rows: pd.DataFrame) -> None:
    """主平台：深色大標題 + 子平台群組 + 未更新提示 + 手動補價"""
    if p_rows.empty:
        return

    total_val  = p_rows["台幣市值"].fillna(0).sum()
    total_pnl  = p_rows["含息總損益"].fillna(0).sum()
    total_cost = p_rows["台幣成本"].fillna(0).sum()
    total_div  = p_rows["累計已領配息"].fillna(0).sum()
    total_mdiv = p_rows["每月配息"].fillna(0).sum()
    total_rate = total_pnl / total_cost if total_cost else None
    icon       = PLATFORM_ICONS.get(platform, "💼")
    pnl_color  = "#6ee7b7" if total_pnl >= 0 else "#fca5a5"

    sell_cost_total = p_rows["賣出稅費"].fillna(0).sum() if "賣出稅費" in p_rows else 0
    nav_pnl_plt   = total_val - total_cost - sell_cost_total if total_val and total_cost else 0
    total_pnl_plt = nav_pnl_plt + total_div
    nav_color_plt = "#6ee7b7" if nav_pnl_plt >= 0 else "#fca5a5"
    tot_color_plt = "#6ee7b7" if total_pnl_plt >= 0 else "#fca5a5"
    tot_rate_plt  = total_pnl_plt / total_cost if total_cost else None
    # 台股：賣出稅費 = 總市值 × 0.4425%（手續費 0.1425% + 證交稅 0.3%）
    sell_cost_plt = total_val * TW_STOCK_SELL_COST_RATE if platform == "台股" else 0
    sell_cost_html = (f'''
  <span style="min-width:120px;font-family:monospace">
    <div style="font-size:10px;color:#6b7280;font-family:sans-serif">賣出稅費（0.4425%）</div>
    <div style="font-size:14px;font-weight:700;color:#dc2626">{money(sell_cost_plt)}</div>
  </span>
  <span style="min-width:120px;font-family:monospace">
    <div style="font-size:10px;color:#6b7280;font-family:sans-serif">扣稅後市值</div>
    <div style="font-size:14px;font-weight:700">{money(total_val - sell_cost_plt)}</div>
  </span>''' if sell_cost_plt else "")

    st.markdown(f"""
<div style="background:#fff;color:#1a2e22;padding:14px 20px;border-radius:12px;
            display:flex;flex-wrap:wrap;align-items:center;gap:18px;
            margin:24px 0 4px 0;font-size:13px;font-weight:700;
            border:1.5px solid #d1e8dc;border-left:5px solid #10b981;
            box-shadow:0 2px 10px rgba(16,185,129,.08);">
  <span style="font-size:16px;font-family:sans-serif;min-width:90px;font-weight:800;color:#10b981">{icon} {platform}</span>
  <span style="min-width:120px;font-family:monospace">
    <div style="font-size:10px;color:#6b7280;font-family:sans-serif">成本</div>
    <div style="font-size:14px;font-weight:700">{money(total_cost)}</div>
  </span>
  <span style="min-width:120px;font-family:monospace">
    <div style="font-size:10px;color:#6b7280;font-family:sans-serif">市值</div>
    <div style="font-size:14px;font-weight:700">{money(total_val)}</div>
  </span>{sell_cost_html}
  <span style="min-width:130px;font-family:monospace">
    <div style="font-size:10px;color:#6b7280;font-family:sans-serif">市值損益</div>
    <div style="font-size:14px;font-weight:700;color:{'#059669' if nav_pnl_plt>=0 else '#dc2626'}">{signed_money(nav_pnl_plt)}</div>
  </span>
  <span style="min-width:110px;font-family:monospace">
    <div style="font-size:10px;color:#6b7280;font-family:sans-serif">累積配息</div>
    <div style="font-size:14px;font-weight:700;color:#0284c7">{money(total_div)}</div>
  </span>
  <span style="min-width:140px;font-family:monospace">
    <div style="font-size:10px;color:#6b7280;font-family:sans-serif">總損益</div>
    <div style="font-size:14px;font-weight:800;color:{'#059669' if total_pnl_plt>=0 else '#dc2626'}">{signed_money(total_pnl_plt)} <span style="font-size:11px">({pct(tot_rate_plt)})</span></div>
  </span>
  <span style="min-width:90px;font-family:monospace">
    <div style="font-size:10px;color:#6b7280;font-family:sans-serif">月配息</div>
    <div style="font-size:14px;font-weight:700;color:#7c3aed">{money(total_mdiv)}</div>
  </span>
</div>
""", unsafe_allow_html=True)

    # ── 未更新持倉偵測（只看有單位數的）──
    has_pos  = p_rows[p_rows["units"].fillna(0) > 0]
    no_price = has_pos[has_pos["即時價格/淨值"].isna()].copy()
    if not no_price.empty:
        # 安全取得唯一名稱，不使用 groupby.ngroups
        unique_names = no_price["name"].dropna().unique().tolist()
        n_missing    = len(unique_names)
        names_str    = "、".join(str(n) for n in unique_names)
        st.error(f"❌ {platform}：{n_missing} 檔缺即時報價 — {names_str}")

    # ── 子平台群組 ──
    sub_defs = SUB_GROUPS.get(platform, [(platform, None)])
    for sub_label, currency_filter in sub_defs:
        if currency_filter:
            sub = p_rows[p_rows["currency"] == currency_filter].copy()
        else:
            sub = p_rows.copy()
        if sub.empty:
            continue
        atype  = normalize_text(sub["asset_type"].iloc[0])
        merged = _merge_positions(sub, atype)
        if not merged.empty:
            render_sub_group(sub_label, merged)

    # ── 手動補價（有缺報價才顯示）──
    if not no_price.empty:
        is_stock = platform in ["台股", "美股"]
        key_col  = "ticker" if is_stock else "fund_code"
        # 安全去重：先填空，再 drop_duplicates
        no_price[key_col] = no_price[key_col].fillna("")
        no_uniq  = no_price.drop_duplicates(subset=[key_col] if key_col in no_price.columns else ["name"])

        with st.expander(f"🔧 {platform}：手動補填即時價"):
            st.caption("自動抓取失敗時，手動填入現值（原幣）。儲存後按「🔄 更新即時價」重算。")
            with st.form(f"manual_price_form_{platform}"):
                manual_vals: dict[int, float] = {}
                for _, row in no_uniq.iterrows():
                    ca, cb = st.columns([3, 1])
                    code   = str(row.get("ticker") or row.get("fund_code") or "")
                    ca.markdown(f"**{row['name']}**　`{code}`　幣別：{row.get('currency','')}")
                    manual_vals[int(row["id"])] = cb.number_input(
                        "現值（原幣）", value=0.0, step=0.0001, format="%.4f",
                        key=f"mp_{platform}_{int(row['id'])}"
                    )
                if st.form_submit_button("💾 儲存"):
                    sb  = supabase_client()
                    cnt = 0
                    for rid, val in manual_vals.items():
                        if val > 0:
                            sb.table("positions").update({"avg_cost": val}).eq("id", rid).execute()
                            cnt += 1
                    if cnt:
                        st.success(f"已儲存 {cnt} 筆，請按頂端「🔄 更新即時價」重新計算。")
                        st.cache_data.clear()


def render_channel_overview_cards(enriched: pd.DataFrame, positions: pd.DataFrame) -> None:
    """總覽主函式：KPI + 匯率 + 各平台群組（美股→基富通→渣打→台新→台股）"""
    st.markdown("### 💎 所有投資管道總覽")
    if enriched.empty:
        st.info("目前沒有資料。")
        return

    # ── 頂部 5 個 KPI ──
    summary = enriched.groupby("platform", dropna=False).agg(
        台幣成本     =("台幣成本",      "sum"),
        台幣市值     =("台幣市值",      "sum"),
        含息總損益   =("含息總損益",    "sum"),
        累計已領配息 =("累計已領配息",  "sum"),
        每月配息     =("每月配息",      "sum"),
        賣出稅費     =("賣出稅費",      "sum"),
        價格缺漏     =("即時價格/淨值", lambda s: int(s.isna().sum())),
        筆數         =("id",            "count"),
    ).reset_index()
    summary["含息總損益率"] = summary.apply(
        lambda r: r["含息總損益"] / r["台幣成本"] if r["台幣成本"] else None, axis=1
    )
    summary["_order"] = summary["platform"].apply(
        lambda x: OVERVIEW_ORDER.index(x) if x in OVERVIEW_ORDER else 999
    )
    summary = summary.sort_values("_order")

    card_cols = st.columns(5)
    for i, (_, r) in enumerate(summary.iterrows()):
        p    = r["platform"]
        miss = int(r["價格缺漏"])
        warn = f" ⚠️{miss}缺" if miss else ""
        with card_cols[i % 5]:
            label = f"{PLATFORM_ICONS.get(p, '💼')} {p}{warn}"
            delta = f"{signed_money(r['含息總損益'] or 0)} / {pct(r['含息總損益率'])}"
            if r["賣出稅費"]:
                # 台股：市值一行、扣稅後市值一行（賣出稅費 0.4425%）
                two_line_metric(st, label, money(r["台幣市值"] or 0),
                                f"扣稅後 {money(r['台幣市值'] - r['賣出稅費'])}", delta)
            else:
                st.metric(label, money(r["台幣市值"] or 0), delta=delta)
            st.caption(f"成本 {money(r['台幣成本'])}｜月配 {money(r['每月配息'])}")

    # ── 匯率列 ──
    st.markdown("<br>", unsafe_allow_html=True)
    # 即時匯率：一行小字，不用大卡片（TWD 固定 1 不顯示）
    fx_parts = []
    for cur in CURRENCIES:
        if cur == "TWD":
            continue
        rate, status = fetch_fx(cur)
        warn = "" if status == "ok" else f' <span style="color:#dc2626">⚠ {html.escape(str(status))}</span>'
        fx_parts.append(f"<b>{cur}</b> {money(rate, 4)}{warn}")
    st.markdown('<div style="font-size:.85rem;color:#475569;margin:4px 0 8px">💱 即時匯率　'
                + "　·　".join(fx_parts) + "</div>", unsafe_allow_html=True)

    st.markdown("---")

    # ── 各平台群組 ──
    for platform in OVERVIEW_ORDER:
        p_rows = enriched[enriched["platform"] == platform].copy().reset_index(drop=True)
        if p_rows.empty:
            continue
        render_platform_group(platform, p_rows)


def render_fx_overview_cards() -> None:
    st.markdown("### 💱 匯率總覽")
    fx_cols = st.columns(len(CURRENCIES))
    for i, cur in enumerate(CURRENCIES):
        rate, status = fetch_fx(cur)
        with fx_cols[i]:
            st.metric(cur, money(rate, 4), delta="ok" if status == "ok" else status)


def render_investment_overview_page(enriched, positions) -> None:
    render_channel_overview_cards(enriched, positions)
    render_fx_overview_cards()
    st.markdown("### 📈 資產配置圖")
    if not enriched.empty:
        chart_summary = enriched.groupby("platform", dropna=False).agg(台幣市值=("台幣市值", "sum")).reset_index()
        chart_summary["占比"] = chart_summary["台幣市值"] / chart_summary["台幣市值"].sum() if chart_summary["台幣市值"].sum() else 0
        st.dataframe(
            chart_summary,
            use_container_width=True,
            hide_index=True,
            column_config={
                "台幣市值": st.column_config.NumberColumn("台幣市值", format="%.0f"),
                "占比": st.column_config.NumberColumn("占比", format="%.2f%%"),
            },
        )
