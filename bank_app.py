"""本機獨立開「銀行帳戶」頁（不需要 Supabase 設定）：python3 -m streamlit run bank_app.py"""
import streamlit as st

st.set_page_config(page_title="銀行帳戶與信用卡", page_icon="🏦", layout="wide")

from invest_app.ledger_pages import render_bank_detail_page, render_card_detail_page  # noqa: E402

page = st.segmented_control("功能", ["銀行明細", "信用卡"], default="銀行明細", label_visibility="collapsed") or "銀行明細"
if page == "銀行明細":
    render_bank_detail_page()
else:
    render_card_detail_page()
