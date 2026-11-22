"""App「銀行明細」「信用卡」頁：讀總帳的「銀行明細」「信用卡明細」分頁（由本機 python3 -m bank_sync publish 寫入）。

每筆都有「記到細帳（列：正負金額）」「依據」「狀態」。雲端、本機都能看；
在本機開 App 時，「銀行明細」頁下方另有抓明細／確認／寫入細帳的操作（不用密碼）。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

MAIN_GOOGLE_SHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"  # 2025Jenny-總帳（同 invest_app.core）


BANK_DISPLAY_ORDER = ("台新", "富邦", "渣打", "將來", "LINE Bank", "元大", "郵局")


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


def _fetch_csv(sheet: str) -> pd.DataFrame:
    """用 CSV 匯出讀（gviz 會猜欄位型態，混合欄位的少數值會變空白）。"""
    import io
    import requests
    response = requests.get(f"https://docs.google.com/spreadsheets/d/{MAIN_GOOGLE_SHEET_ID}/gviz/tq",
                            params={"tqx": "out:csv", "sheet": sheet, "headers": "1"}, timeout=30)
    response.raise_for_status()
    if "<html" in response.text[:200].lower():
        raise RuntimeError("Google Sheet 讀取失敗（權限？）")
    return pd.read_csv(io.StringIO(response.text), dtype=str, keep_default_na=False)


# 明細只在 publish／更新後才會變：快取 10 分鐘；本機按「更新」完成或按「重新讀取」會立即清掉。
@st.cache_data(ttl=600, show_spinner="讀取總帳…")
def _load_many(sheets: tuple) -> dict:
    """一次平行讀多個分頁（明細＋核對），比一頁一頁讀快。讀不到的分頁回傳錯誤訊息字串。"""
    from concurrent.futures import ThreadPoolExecutor

    def one(name):
        try:
            return _fetch_csv(name)
        except Exception as exc:
            return f"{type(exc).__name__}: {exc}"
    with ThreadPoolExecutor(max_workers=len(sheets)) as pool:
        return dict(zip(sheets, pool.map(one, sheets)))


def _load(sheet: str, group: tuple = ()) -> pd.DataFrame:
    got = _load_many(group or (sheet,)).get(sheet)
    if isinstance(got, str):
        raise RuntimeError(got)
    return got


_load.clear = _load_many.clear  # 舊程式呼叫 _load.clear()


def _amount_col(df: pd.DataFrame) -> str:
    return next((c for c in df.columns if c.startswith("金額")), "")


def _signed_money(v) -> str:
    try:
        x = float(str(v).replace(",", ""))
    except ValueError:
        return str(v)
    text = f"{x:+,.2f}".rstrip("0").rstrip(".")
    return text


BANK_SHEETS = ("銀行明細", "銀行餘額核對")
CARD_SHEETS = ("信用卡明細", "信用卡核對")


def _check_alert(sheet: str, what: str, group: tuple = ()) -> None:
    """讀「銀行餘額核對」／「信用卡核對」分頁，有不相符就顯示警示。"""
    try:
        df = _load(sheet, group)
    except Exception:
        return
    if df.empty or "結果" not in df.columns:
        return
    when = df[df.iloc[:, 0].astype(str) == "更新時間"]
    stamp = str(when.iloc[0, 1]) if not when.empty and when.shape[1] > 1 else ""
    bad = df[df["結果"].astype(str).str.startswith("⚠️")]
    if bad.empty:
        st.success(f"✓ 細帳與{what}相符" + (f"（{stamp} 核對）" if stamp else ""))
        return
    st.error(f"⚠️ 細帳與{what}有 {len(bad)} 項不相符" + (f"（{stamp} 核對）" if stamp else "") + "，請檢查：")
    st.dataframe(bad, hide_index=True, use_container_width=True)


def _update_panel(kind: str) -> None:
    """頁面上方的「更新」：本機才能抓（要用 Mac 上的帳密與 Chrome）；雲端顯示開本機頁的按鈕。"""
    from invest_app.bank_page import FETCH_BANKS, is_local, job_panel, start_job
    if not is_local():
        st.link_button("🔄 到本機更新" + ("銀行明細" if kind == "bank" else "信用卡"), "http://localhost:8502")
        return
    if kind == "bank":
        c1, c2 = st.columns([4, 1])
        picked = c1.multiselect("要更新的銀行", list(FETCH_BANKS), default=list(FETCH_BANKS),
                                format_func=FETCH_BANKS.get, key="upd_banks")
        c2.write("")
        if c2.button("🔄 更新銀行明細", key="upd_bank_go", type="primary", disabled=not picked):
            start_job("更新銀行明細：" + "、".join(FETCH_BANKS[k] for k in picked),
                      ["refresh-bank", *[a for k in picked for a in ("--bank", k)]])
    else:
        if st.button("🔄 更新信用卡", key="upd_card_go", type="primary",
                     help="下載新帳單（下載過的不重抓）→ 比對細帳（不寫入）→ 更新明細"):
            start_job("更新信用卡", ["refresh-cards"])
    job = st.session_state.get("bank_job")
    if job and job.get("args", [""])[0] in ("refresh-bank", "refresh-cards", "bank-review", "bank-ledger"):
        with st.expander("執行過程", expanded=job["proc"].poll() is None):
            job_panel(prefix="top_")


def _reload_button(key: str) -> None:
    if st.button("🔄 重新讀取", key=key):
        _load.clear()
        st.rerun()


def render_bank_detail_page() -> None:
    st.subheader("銀行明細")
    _update_panel("bank")
    _check_alert("銀行餘額核對", "銀行餘額", BANK_SHEETS)
    from invest_app.bank_confirm import render_confirm_panel
    render_confirm_panel()
    _reload_button("bd_reload")
    try:
        df = _load("銀行明細", BANK_SHEETS)
    except Exception as exc:
        st.warning(f"讀不到總帳「銀行明細」分頁：{type(exc).__name__}: {exc}")
        df = pd.DataFrame()
    if df.empty:
        st.info("還沒有資料。請在 Mac 執行一次：`python3 -m bank_sync publish`（會把已下載的銀行明細整理進總帳）。")
    else:
        amt = _amount_col(df)
        df["月份"] = df["日期"].astype(str).str[:2] + "月"
        c1, c1b, c2, c3, c4 = st.columns([2, 2, 1, 2, 2])
        banks = c1.multiselect("銀行", sorted(df["銀行"].unique()), key="bd_bank")
        pool = df[df["銀行"].isin(banks)] if banks else df
        accounts = c1b.multiselect("帳戶", sorted(pool["帳戶"].unique()) if "帳戶" in df.columns else [], key="bd_acct")
        months = ["全部"] + sorted(df["月份"].unique(), reverse=True)
        month = c2.selectbox("月份", months, key="bd_month")
        states = c3.multiselect("狀態", [s for s in STATE_ORDER if s in set(df["狀態"])], key="bd_state")
        keyword = c4.text_input("搜尋（摘要／備註／其他）", key="bd_kw")
        view = df
        if banks:
            view = view[view["銀行"].isin(banks)]
        if accounts:
            view = view[view["帳戶"].isin(accounts)]
        if month != "全部":
            view = view[view["月份"] == month]
        if states:
            view = view[view["狀態"].isin(states)]
        if keyword:
            cols_ = [c for c in ("摘要", "備註", "銀行（細帳）", "其他", "依據") if c in view.columns]
            mask = view[cols_].astype(str).apply(
                lambda col: col.str.contains(keyword, case=False, regex=False)).any(axis=1)
            view = view[mask]
        order = {b: i for i, b in enumerate(BANK_DISPLAY_ORDER)}  # 依銀行、帳戶排（同帳戶維持新的在上）
        view = view.assign(_o=view["銀行"].map(lambda b: order.get(b, len(order)))) \
            .sort_values(["_o"] + (["帳戶"] if "帳戶" in view.columns else []), kind="stable").drop(columns="_o")
        counts = view["狀態"].value_counts()
        cols = st.columns(len(STATE_ORDER))
        for col, name in zip(cols, STATE_ORDER):
            col.metric(name, int(counts.get(name, 0)))
        show = view.drop(columns=["月份"]).copy()
        for c in ("收入", "支出", "餘額"):  # 數字加千分位，空白就留空白（不要顯示 None）
            if c in show.columns:
                nums = pd.to_numeric(show[c].astype(str).str.replace(",", ""), errors="coerce")
                show[c] = nums.map(lambda x: "" if pd.isna(x) else f"{x:,.2f}".rstrip("0").rstrip("."))
        if amt:
            show[amt] = show[amt].map(_signed_money)
        cfg = {"其他": st.column_config.TextColumn(width="large"), "依據": st.column_config.TextColumn(width="medium")}
        split = st.toggle("依帳戶分開顯示", value=True, key="bd_split") and "帳戶" in show.columns
        if not split:
            st.dataframe(show, hide_index=True, use_container_width=True, height=560, column_config=cfg)
        else:  # 每個帳戶一張表：標題列出筆數、待確認、最新餘額（資料已依銀行→帳戶→新到舊排）
            for (bank, acct), part in show.groupby(["銀行", "帳戶"], sort=False):
                bal = next((v for v in part["餘額"] if str(v).strip()), "") if "餘額" in part.columns else ""
                n_check = int((part["狀態"] == "待確認").sum()) if "狀態" in part.columns else 0
                title = f"{bank}｜{acct}　{len(part)} 筆" + (f"　⚠️ 待確認 {n_check}" if n_check else "") + \
                    (f"　最新餘額 {bal}" if bal else "")
                with st.expander(title, expanded=len(part) <= 30 or n_check > 0):
                    st.dataframe(part.drop(columns=["銀行", "帳戶"]), hide_index=True, use_container_width=True,
                                 height=min(38 + 35 * len(part), 460), column_config=cfg)
        st.caption("「銀行（細帳）」「其他」：記到細帳哪一列、加多少（＋／−）；空白的銀行欄＝公式會自動帶入（例 116 加進建北）。"
                   "「待確認」在上方「✅ 確認與寫入細帳」處理。資料快取 10 分鐘；剛更新完要看最新請按「重新讀取」。")
    _local_tools()


def render_card_detail_page() -> None:
    st.subheader("信用卡明細")
    _update_panel("card")
    _check_alert("信用卡核對", "信用卡帳單", CARD_SHEETS)
    _reload_button("cd_reload")
    try:
        df = _load("信用卡明細", CARD_SHEETS)
    except Exception as exc:
        st.warning(f"讀不到總帳「信用卡明細」分頁：{type(exc).__name__}: {exc}")
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
