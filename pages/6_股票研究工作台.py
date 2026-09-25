from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

BASE = Path(__file__).resolve().parents[1]
DATA_DIR = BASE / "data" / "stock_radar"

st.set_page_config(page_title="股票研究工作台", page_icon="🔎", layout="wide")
st.title("🔎 股票研究工作台")
st.caption("把 7 組研究提示整合成同一流程；數值由資料/程式計算，AI 僅負責解讀。")

tabs = st.tabs(["研究方向", "技術分析", "新聞影響", "策略回測", "投資組合健檢", "交易紀錄", "每日計畫"])

with tabs[0]:
    st.subheader("研究方向")
    st.write("從每日雷達延伸研究：估值、法人、量能與後續基本面資料集中在這裡。")
    latest = DATA_DIR / "latest.csv"
    if latest.exists():
        df = pd.read_csv(latest, dtype={"代號": str})
        cols = [c for c in ["代號","名稱","收盤價","本益比","殖利率%","雷達分數","入選原因"] if c in df.columns]
        st.dataframe(df.sort_values("雷達分數", ascending=False)[cols].head(30), use_container_width=True, hide_index=True)
    else:
        st.info("先執行台股每日雷達產生資料。")

with tabs[1]:
    st.subheader("技術分析")
    st.write("MA5／10／20／60、RSI14、MACD 由程式計算；下一階段接入個股歷史 OHLCV 後直接顯示日／週線。")

with tabs[2]:
    st.subheader("新聞影響")
    st.write("預留新聞來源、發布日期、短期／中長期影響欄位。未取得來源時不生成新聞結論。")

with tabs[3]:
    st.subheader("策略回測")
    st.write("回測使用真實歷史價格，不讓 AI 模擬勝率或最大回撤。第一個共用策略為 MA5/MA20 黃金交叉。")

with tabs[4]:
    st.subheader("投資組合健檢")
    st.write("將沿用既有持倉資料，只讀分析集中度與風險，不修改任何原始持倉。")

with tabs[5]:
    st.subheader("交易紀錄")
    st.write("分析既有成交紀錄的重複行為；原始交易資料維持不變。")

with tabs[6]:
    st.subheader("每日計畫")
    st.write("盤前準備 → 開盤觀察 → 盤中調整 → 收盤檢討。後續由每日雷達、技術、新聞與持股資料自動彙整。")

st.divider()
st.caption("研究工具，不代替個人投資決策；缺資料時明確顯示缺項，不猜測數字。")
