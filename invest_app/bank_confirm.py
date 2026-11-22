"""App 銀行明細頁的「確認與寫入細帳」：直接在 App 選 確認／略過／改記到，按一下就寫入（不用開試算表）。

只在本機（Mac）可用：要用本機的 Google 授權寫「銀行明細確認」分頁，再跑 bank-ledger --apply。
答案仍存在總帳「銀行明細確認」分頁（跟以前一樣），所以 App 和試算表填的都算數。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

CHOICE_OPTIONS = ["", "確認", "略過"]


def _book():
    from bank_sync.google_auth import credentials
    from bank_sync.ledger_sync import open_book
    if "bc_book" not in st.session_state:
        st.session_state["bc_book"] = open_book(credentials())
    return st.session_state["bc_book"]


def _load_review(force: bool = False) -> tuple[pd.DataFrame, list[str]]:
    from datetime import date
    from bank_sync.bank_ledger import REVIEW_TITLE
    if force or "bc_review" not in st.session_state:
        book = _book()
        try:
            rows = book.worksheet(REVIEW_TITLE).get_values()
        except Exception:
            rows = []
        df = pd.DataFrame(rows[1:], columns=rows[0]) if len(rows) > 1 else pd.DataFrame()
        labels = []
        try:  # 「改記到」可選的細帳列名
            col_a = book.worksheet(f"{date.today().year}細帳").col_values(1)
            labels = sorted({str(v).strip() for v in col_a[1:] if str(v).strip()})
        except Exception:
            pass
        st.session_state["bc_review"], st.session_state["bc_labels"] = df, labels
    return st.session_state["bc_review"], st.session_state["bc_labels"]


def render_confirm_panel() -> None:
    from invest_app.bank_page import is_local, start_job
    if not is_local():
        st.caption("確認與寫入細帳要用 Mac 上的授權，請在本機頁操作：http://localhost:8502")
        return
    with st.expander("✅ 確認與寫入細帳", expanded=True):
        top = st.columns([1, 1, 3])
        if top[0].button("📝 重新產生確認清單", key="bc_regen", help="依目前抓到的明細重算（同「更新銀行明細」的最後一步）"):
            start_job("銀行明細確認表", ["bank-review"])
            st.session_state.pop("bc_review", None)
        if top[1].button("🔄 重新讀取", key="bc_reload"):
            _load_review(force=True)
        try:
            df, labels = _load_review()
        except Exception as exc:
            st.warning(f"讀不到確認清單：{type(exc).__name__}: {exc}")
            return
        if df.empty:
            st.info("還沒有確認清單：按「📝 重新產生確認清單」或上方「🔄 更新銀行明細」。")
            return
        show_auto = top[2].toggle("也顯示自動（待寫入）的項目", value=False, key="bc_auto")
        view = df[df["狀態"].str.startswith("⚠️") | (show_auto & (df["狀態"] == "自動"))].copy()
        n_check = int(df["狀態"].str.startswith("⚠️").sum())
        n_auto = int((df["狀態"] == "自動").sum())
        st.markdown(f"**待確認 {n_check} 筆**（要你選）、**待寫入 {n_auto} 筆**（程式已知道記到哪，按寫入就會寫）。")
        if view.empty:
            st.success("沒有要確認的項目。")
        target_col = "改記到（另一邊列號或列名）"
        opts = [""] + labels + sorted({v for v in view[target_col] if v and v not in labels})
        edited = st.data_editor(
            view, hide_index=True, use_container_width=True, key="bc_editor",
            disabled=[c for c in view.columns if c not in ("你的確認", target_col)],
            column_order=["你的確認", target_col, "日期", "銀行帳戶", "金額", "摘要", "備註", "記到（列：金額）", "依據", "狀態"],
            column_config={
                "你的確認": st.column_config.SelectboxColumn("你的確認", options=CHOICE_OPTIONS, width="small"),
                target_col: st.column_config.SelectboxColumn("改記到（另一邊）", options=opts, width="medium",
                                                             help="另一邊要記到別列才選；留空＝照「記到」"),
                "依據": st.column_config.TextColumn(width="medium"),
            },
        ) if not view.empty else view
        b1, b2, b3, b4 = st.columns(4)
        if b1.button("☑️ 待確認全部選「確認」", key="bc_all", disabled=view.empty):
            df.loc[df["狀態"].str.startswith("⚠️") & (df["你的確認"] == ""), "你的確認"] = "確認"
            st.session_state["bc_review"] = df
            st.session_state.pop("bc_editor", None)
            st.rerun()

        def _save() -> int:
            from bank_sync.bank_ledger import save_answers
            answers = {r["代碼"]: (r["你的確認"] or "", r[target_col] or "") for _, r in edited.iterrows()}
            n = save_answers(_book(), answers)
            for code, (c, t) in answers.items():
                df.loc[df["代碼"] == code, ["你的確認", target_col]] = [c, t]
            st.session_state["bc_review"] = df
            return n

        if b2.button("💾 儲存", key="bc_save", disabled=view.empty):
            st.success(f"已儲存 {_save()} 筆的選擇。")
        if b3.button("🧪 儲存＋模擬寫入", key="bc_dry"):
            if not view.empty:
                _save()
            start_job("模擬寫入細帳", ["bank-ledger"])
        if b4.button("✍️ 儲存＋寫入細帳", key="bc_apply", type="primary"):
            st.session_state["bc_confirm"] = True
        if st.session_state.get("bc_confirm"):
            st.warning("會把「確認」和「待寫入」的項目寫進 2026細帳與 2026細帳(含信用卡)；還沒選的待確認這次不寫。"
                       "寫入前會再核對餘額，對不上會自動停止。")
            a, b = st.columns(2)
            if a.button("確定寫入", key="bc_apply_yes", type="primary"):
                st.session_state["bc_confirm"] = False
                if not view.empty:
                    _save()
                start_job("寫入細帳", ["bank-ledger", "--apply"])
                st.session_state.pop("bc_review", None)
            if b.button("取消", key="bc_apply_no"):
                st.session_state["bc_confirm"] = False
        st.caption("選擇會存回總帳「銀行明細確認」分頁，跟在試算表填一樣。執行過程顯示在上方「執行過程」。")
