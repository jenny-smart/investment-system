"""App「銀行明細」「信用卡」頁：讀總帳的「銀行明細」「信用卡明細」分頁（由本機 python3 -m bank_sync publish 寫入）。

每筆都有「記到細帳（列：正負金額）」「依據」「狀態」。雲端、本機都能看；
在本機開 App 時，「銀行明細」頁下方另有抓明細／確認／寫入細帳的操作（不用密碼）。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

MAIN_GOOGLE_SHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"  # 2025Jenny-總帳（同 invest_app.core）


def gviz_values(sheet_id: str, sheet: str, cell_range: str) -> list[list]:
    """讀分頁儲存格實際值（同 invest_app.core.gviz_values；這裡不 import core，本機獨立頁不用裝 supabase）。"""
    import json
    import requests
    params = {"tqx": "out:json", "range": cell_range, "headers": "1", "sheet": sheet}
    response = requests.get(f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq", params=params, timeout=15)
    response.raise_for_status()
    text = response.text
    payload = json.loads(text[text.index("(") + 1:text.rindex(")")])
    if payload.get("status") == "error":
        raise RuntimeError(str(payload.get("errors"))[:200])
    table = payload.get("table") or {}
    rows = [[(c or {}).get("label", "") for c in table.get("cols", [])]]
    for r in table.get("rows", []):
        rows.append([(cell or {}).get("v") if cell else "" for cell in (r.get("c") or [])])
    return [["" if v is None else v for v in row] for row in rows]

STATE_ORDER = ["待確認", "待寫入", "已寫入細帳", "細帳已有", "略過"]


@st.cache_data(ttl=120, show_spinner=False)
def _load(sheet: str) -> pd.DataFrame:
    rows = gviz_values(MAIN_GOOGLE_SHEET_ID, sheet, "A1:L8000")
    if not rows or len(rows) < 2:
        return pd.DataFrame()
    head = [str(h) for h in rows[0]]
    return pd.DataFrame(rows[1:], columns=head)


def _amount_col(df: pd.DataFrame) -> str:
    return next((c for c in df.columns if c.startswith("金額")), "")


def _signed_money(v) -> str:
    try:
        x = float(str(v).replace(",", ""))
    except ValueError:
        return str(v)
    text = f"{x:+,.2f}".rstrip("0").rstrip(".")
    return text


def render_bank_detail_page() -> None:
    st.subheader("銀行明細")
    try:
        df = _load("銀行明細")
    except Exception as exc:
        st.warning(f"讀不到總帳「銀行明細」分頁：{exc}")
        df = pd.DataFrame()
    if df.empty:
        st.info("還沒有資料。請在 Mac 執行一次：`python3 -m bank_sync publish`（會把已下載的銀行明細整理進總帳）。")
    else:
        amt = _amount_col(df)
        df["月份"] = df["日期"].astype(str).str[:2] + "月"
        c1, c2, c3, c4 = st.columns([2, 1, 2, 2])
        banks = c1.multiselect("銀行", sorted(df["銀行"].unique()), key="bd_bank")
        months = ["全部"] + sorted(df["月份"].unique(), reverse=True)
        month = c2.selectbox("月份", months, key="bd_month")
        states = c3.multiselect("狀態", [s for s in STATE_ORDER if s in set(df["狀態"])], key="bd_state")
        keyword = c4.text_input("搜尋（摘要／備註／其他）", key="bd_kw")
        view = df
        if banks:
            view = view[view["銀行"].isin(banks)]
        if month != "全部":
            view = view[view["月份"] == month]
        if states:
            view = view[view["狀態"].isin(states)]
        if keyword:
            cols_ = [c for c in ("摘要", "備註", "銀行（細帳）", "其他", "依據") if c in view.columns]
            mask = view[cols_].astype(str).apply(
                lambda col: col.str.contains(keyword, case=False, regex=False)).any(axis=1)
            view = view[mask]
        counts = view["狀態"].value_counts()
        cols = st.columns(len(STATE_ORDER))
        for col, name in zip(cols, STATE_ORDER):
            col.metric(name, int(counts.get(name, 0)))
        show = view.drop(columns=["月份"]).copy()
        for c in ("收入", "支出", "餘額"):
            if c in show.columns:
                show[c] = pd.to_numeric(show[c].astype(str).str.replace(",", ""), errors="coerce")
        if amt:
            show[amt] = show[amt].map(_signed_money)
        st.dataframe(show, hide_index=True, use_container_width=True, height=560,
                     column_config={"其他": st.column_config.TextColumn(width="large"),
                                    "收入": st.column_config.NumberColumn(format="%,.2f"),
                                    "支出": st.column_config.NumberColumn(format="%,.2f"),
                                    "餘額": st.column_config.NumberColumn(format="%,.2f"),
                                    "依據": st.column_config.TextColumn(width="medium")})
        st.caption("「銀行（細帳）」「其他」：記到細帳哪一列、加多少（＋／−）；空白的銀行欄＝公式會自動帶入（例 116 加進建北）。"
                   "「待確認」請到總帳「銀行明細確認」分頁處理。資料每 2 分鐘重新讀一次。")
    _local_tools()


def render_card_detail_page() -> None:
    st.subheader("信用卡明細")
    try:
        df = _load("信用卡明細")
    except Exception as exc:
        st.warning(f"讀不到總帳「信用卡明細」分頁：{exc}")
        return
    if df.empty:
        st.info("還沒有資料。請在 Mac 執行一次：`python3 -m bank_sync publish`。")
        return
    amt = _amount_col(df)
    c1, c2, c3, c4 = st.columns([2, 1, 2, 2])
    cards = c1.multiselect("卡別", sorted(df["卡別"].unique()), key="cd_card")
    months = ["全部"] + sorted(df["帳單月份"].astype(str).unique(), reverse=True)
    month = c2.selectbox("帳單月份", months, key="cd_month")
    cats = c3.multiselect("零用金分類", sorted(df["零用金分類"].unique()), key="cd_cat")
    keyword = c4.text_input("搜尋店名", key="cd_kw")
    view = df
    if cards:
        view = view[view["卡別"].isin(cards)]
    if month != "全部":
        view = view[view["帳單月份"].astype(str) == month]
    if cats:
        view = view[view["零用金分類"].isin(cats)]
    if keyword:
        view = view[view["店名"].astype(str).str.contains(keyword, case=False, regex=False)]
    total = pd.to_numeric(view[amt].astype(str).str.replace(",", ""), errors="coerce").sum() if amt else 0
    a, b, c = st.columns(3)
    a.metric("筆數", len(view))
    b.metric("金額合計", f"{total:,.0f}")
    c.metric("待分類", int((view["狀態"] == "待分類").sum()))
    show = view.copy()
    if amt:
        show[amt] = show[amt].map(_signed_money)
    st.dataframe(show, hide_index=True, use_container_width=True, height=560,
                 column_config={"記到細帳（列：正負金額）": st.column_config.TextColumn(width="large")})
    st.caption("金額：消費為＋、退款為−；記到「2026細帳(含信用卡)」下方信用卡區的分類列，原本 2026細帳的信用卡列只加備註。")


def _local_tools() -> None:
    from invest_app.bank_page import is_local
    st.divider()
    if not is_local():
        st.link_button("🏦 開啟本機操作（抓明細、確認、寫入細帳）", "http://localhost:8502")
        st.caption("抓銀行明細要用你 Mac 上的帳密和 Chrome，只能在本機操作；上面的明細是讀總帳，雲端也看得到。")
        return
    with st.expander("本機操作：抓明細、確認表、寫入細帳、全年核對", expanded=False):
        from invest_app.bank_page import render_bank_tools
        render_bank_tools()
