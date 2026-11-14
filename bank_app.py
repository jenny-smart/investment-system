"""本機獨立開「銀行帳戶」頁（不需要 Supabase 設定）：python3 -m streamlit run bank_app.py"""
import streamlit as st

st.set_page_config(page_title="銀行帳戶與信用卡", page_icon="🏦", layout="wide")

from invest_app.bank_page import render_bank_page  # noqa: E402

render_bank_page()
