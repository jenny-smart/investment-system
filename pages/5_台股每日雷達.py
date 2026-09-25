from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

BASE = Path(__file__).resolve().parents[1]
DATA_DIR = BASE / "data" / "stock_radar"

st.set_page_config(page_title="台股每日雷達", page_icon="📡", layout="wide")
st.title("📡 台股每日雷達")
st.caption("每日收盤後自動更新。此頁提供資料整理與觀察，不代表買賣建議。")

latest_path = DATA_DIR / "latest.json"
csv_path = DATA_DIR / "latest.csv"

if not latest_path.exists() or not csv_path.exists():
    st.info("尚未產生每日雷達資料；GitHub Actions 首次執行後會自動顯示。")
    st.stop()

meta = json.loads(latest_path.read_text(encoding="utf-8"))
df = pd.read_csv(csv_path, dtype={"代號": str})
selected = df[df["雷達分數"] >= 4].head(30).copy()

c1, c2, c3, c4 = st.columns(4)
c1.metric("資料時間", meta.get("generated_at", "-").replace("T", " ")[:16])
c2.metric("上市股票", f"{meta.get('total_universe', 0):,}")
c3.metric("符合條件", f"{meta.get('selected_count', 0):,}")
c4.metric("最高雷達分數", int(df["雷達分數"].max()) if not df.empty else 0)

st.markdown("### 今日摘要")
if selected.empty:
    st.write("今天沒有股票達到第一版雷達門檻（4 分）。")
else:
    top = selected.iloc[0]
    foreign_positive = int((selected["外資買賣超"].fillna(0) > 0).sum())
    trust_positive = int((selected["投信買賣超"].fillna(0) > 0).sum())
    st.write(
        f"今日共有 **{len(selected)} 檔**進入觀察名單；"
        f"其中外資買超 **{foreign_positive} 檔**、投信買超 **{trust_positive} 檔**。"
        f"目前分數較高的資料組合為 **{top['代號']} {top['名稱']}**（{int(top['雷達分數'])} 分）。"
    )

for warning in meta.get("warnings", []):
    st.warning(warning)

st.markdown("### 今日觀察名單")
visible = ["代號", "名稱", "收盤價", "漲跌幅%", "本益比", "殖利率%", "外資買賣超", "投信買賣超", "三大法人買賣超", "成交股數", "雷達分數", "入選原因"]
st.dataframe(selected[[c for c in visible if c in selected.columns]], use_container_width=True, hide_index=True)

st.markdown("### 自訂篩選")
left, mid, right = st.columns(3)
min_score = left.slider("最低雷達分數", 0, 7, 4)
foreign_only = mid.checkbox("只看外資買超")
trust_only = right.checkbox("只看投信買超")
view = df[df["雷達分數"] >= min_score].copy()
if foreign_only:
    view = view[view["外資買賣超"].fillna(0) > 0]
if trust_only:
    view = view[view["投信買賣超"].fillna(0) > 0]
st.dataframe(view[[c for c in visible if c in view.columns]].head(100), use_container_width=True, hide_index=True)

st.markdown("### 歷史紀錄")
history_path = DATA_DIR / "history.jsonl"
if history_path.exists():
    records = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    history = pd.DataFrame(records).sort_values("date", ascending=False)
    if not history.empty:
        history["入選代號"] = history["codes"].apply(lambda x: "、".join(x[:20]))
        st.dataframe(history[["date", "selected_count", "入選代號"]], use_container_width=True, hide_index=True)

with st.expander("第一版篩選規則"):
    st.write("雷達分數由本益比、殖利率、外資、投信、三大法人、成交量與當日價格方向組成。")
    st.write("目前先涵蓋 TWSE 上市股票。營收成長、毛利率／營益率趨勢與產業族群資金流會在下一階段接入；介面已與既有投資資料分離，不改動原持倉資料。")
