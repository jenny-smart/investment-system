from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import json
import pandas as pd
import requests
import streamlit as st

# ─── Config ───────────────────────────────────────────────────────────────
PRIMARY_SPREADSHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"
MARKET_SPREADSHEET_ID  = "17HPytZKOPR_9Od_wor-xEx9kpccJlPS2v6B0Dz6MRYc"
BASE_DIR    = Path(__file__).resolve().parent
PRIMARY_LOCAL = BASE_DIR / "inputs" / "investment-system-source.xlsx"
MARKET_LOCAL  = BASE_DIR / "inputs" / "market-value-source.xlsx"
SUMMARY_JSON  = BASE_DIR / "outputs" / "workbook_structure_summary.json"

MARKET_SHEETS = [
    "總覽", "台股", "「台股」的副本", "渣打-美股",
    "基富通-台", "基富通-人民幣", "基富通-日幣",
    "渣打-美金", "渣打-南非", "台新-美金", "台新-南非",
]

st.set_page_config(
    page_title="Jenny All｜投資系統",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── CSS ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* hide sidebar toggle & sidebar entirely */
[data-testid="stSidebar"]          { display: none !important; }
[data-testid="collapsedControl"]   { display: none !important; }
section[data-testid="stSidebarNav"]{ display: none !important; }
button[kind="header"]              { display: none !important; }

/* base */
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.stApp { background: #0d0f12; color: #e8eaf0; }
.block-container { padding: 0 !important; max-width: 100% !important; }

/* ── top nav bar ─────────────────────────────────────────────────────── */
.jenny-topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #141720;
    border-bottom: 1px solid #2a2f45;
    padding: 0 28px;
    height: 52px;
    position: sticky; top: 0; z-index: 999;
}
.jenny-topbar .logo {
    font-size: 16px; font-weight: 700; color: #e8eaf0;
    display: flex; align-items: center; gap: 8px;
}
.jenny-topbar .logo span { color: #22d48a; }
.jenny-topbar .sync {
    font-size: 11px; color: #5a6280;
}

/* ── tabs ────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: #141720;
    border-bottom: 1px solid #2a2f45;
    padding: 0 28px;
    gap: 0;
}
.stTabs [data-baseweb="tab"] {
    color: #9098b8 !important;
    font-size: 13px;
    padding: 12px 18px;
    border-bottom: 2px solid transparent !important;
    background: transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #22d48a !important;
    border-bottom-color: #22d48a !important;
    font-weight: 600 !important;
}
.stTabs [data-baseweb="tab-panel"] {
    background: #0d0f12;
    padding: 24px 28px;
}

/* ── metrics ─────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #1c2030;
    border: 1px solid #2a2f45;
    border-radius: 10px;
    padding: 14px 18px !important;
}
[data-testid="stMetricLabel"] {
    font-size: 10px !important;
    letter-spacing: .6px;
    text-transform: uppercase;
    color: #5a6280 !important;
}
[data-testid="stMetricValue"] {
    font-size: 22px !important;
    font-weight: 700 !important;
    color: #e8eaf0 !important;
}

/* ── dataframe ───────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border: 1px solid #2a2f45 !important;
    border-radius: 10px !important;
    overflow: hidden;
}
.dvn-scroller { background: #141720 !important; }

/* ── selectbox ───────────────────────────────────────────────────────── */
[data-baseweb="select"] > div {
    background: #1c2030 !important;
    border-color: #2a2f45 !important;
    color: #e8eaf0 !important;
    border-radius: 8px !important;
}

/* ── source radio ────────────────────────────────────────────────────── */
[data-testid="stRadio"] > div {
    display: flex; flex-direction: row; gap: 10px;
}
[data-testid="stRadio"] label {
    background: #1c2030;
    border: 1px solid #2a2f45;
    border-radius: 8px;
    padding: 5px 14px;
    font-size: 12px;
    color: #9098b8 !important;
    cursor: pointer;
}
[data-testid="stRadio"] label:has(input:checked) {
    border-color: #22d48a;
    color: #22d48a !important;
}

/* ── section card ────────────────────────────────────────────────────── */
.j-card {
    background: #141720;
    border: 1px solid #2a2f45;
    border-radius: 12px;
    padding: 20px 22px;
    margin-bottom: 16px;
}
.j-card-title {
    font-size: 10px; color: #5a6280;
    letter-spacing: .8px; text-transform: uppercase;
    margin-bottom: 14px; padding-bottom: 8px;
    border-bottom: 1px solid #2a2f45;
    display: flex; align-items: center; justify-content: space-between;
}
.j-page-title   { font-size: 22px; font-weight: 700; color: #e8eaf0; margin-bottom: 2px; }
.j-page-sub     { font-size: 12px; color: #5a6280; margin-bottom: 18px; }
.j-pos          { color: #22d48a; }
.j-neg          { color: #f05a6e; }
.j-muted        { color: #9098b8; }

/* ── tag badges ──────────────────────────────────────────────────────── */
.tag { display:inline-block; padding:2px 8px; border-radius:20px; font-size:10px; font-weight:600; }
.tg  { background:rgba(34,212,138,.12); color:#22d48a; }
.tr  { background:rgba(240,90,110,.12); color:#f05a6e; }
.to  { background:rgba(240,183,77,.12); color:#f0b74d; }
.tb  { background:rgba(77,142,245,.12); color:#4d8ef5; }

/* ── bar chart fix ───────────────────────────────────────────────────── */
[data-testid="stVegaLiteChart"] { border-radius: 10px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# ─── Helpers ──────────────────────────────────────────────────────────────
def google_export_url(sid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx"

@st.cache_data(ttl=600, show_spinner=False)
def download_xlsx(sid: str) -> bytes:
    r = requests.get(google_export_url(sid), timeout=60)
    r.raise_for_status()
    return r.content

@st.cache_data(ttl=600, show_spinner=False)
def load_local(path: str) -> bytes:
    return Path(path).read_bytes()

@st.cache_data(ttl=600, show_spinner=False)
def read_sheet(xlsx: bytes, sheet: str) -> pd.DataFrame:
    return pd.read_excel(BytesIO(xlsx), sheet_name=sheet, header=None, engine="openpyxl")

def wb(mode: str, which: str) -> bytes:
    if which == "primary":
        return load_local(str(PRIMARY_LOCAL)) if mode == "本機快取" else download_xlsx(PRIMARY_SPREADSHEET_ID)
    return load_local(str(MARKET_LOCAL)) if mode == "本機快取" else download_xlsx(MARKET_SPREADSHEET_ID)

def num(v: Any) -> float | None:
    try:
        return None if v is None or pd.isna(v) else float(v)
    except Exception:
        return None

def money(v: Any) -> str:
    n = num(v)
    if n is None: return "—"
    abs_n = abs(n)
    if abs_n >= 1e8: return f"{n/1e8:,.2f} 億"
    if abs_n >= 1e4: return f"{n/1e4:,.1f} 萬"
    return f"{n:,.0f}"

def pct(v: Any) -> str:
    n = num(v)
    return "—" if n is None else f"{n:.2%}"

def cleaned(df: pd.DataFrame, rows=120, cols=40) -> pd.DataFrame:
    t = df.dropna(how="all").dropna(axis=1, how="all")
    t = t.iloc[:rows, :cols].copy()
    t.columns = [str(c) for c in t.columns]
    return t

def row_label(df: pd.DataFrame, label: str) -> pd.Series | None:
    lbs = df.iloc[:, 0].astype(str).str.strip()
    m = df.loc[lbs == label]
    return None if m.empty else m.iloc[0]

def metric_ov(df: pd.DataFrame, label: str, col: int = 1) -> str:
    row = row_label(df, label)
    return money(row.iloc[col]) if row is not None and len(row) > col else "—"

def section_from_header(df: pd.DataFrame, sc: int, ec: int, rows=80) -> pd.DataFrame:
    s = df.iloc[:rows, sc:ec].dropna(how="all").copy()
    if s.empty: return s
    hdr = s.iloc[0].fillna("")
    s = s.iloc[1:].copy()
    s.columns = [str(v).strip() or f"col_{i+1}" for i, v in enumerate(hdr)]
    return s.dropna(how="all")

# ─── Top bar ──────────────────────────────────────────────────────────────
st.markdown("""
<div class="jenny-topbar">
  <div class="logo"><span>◈</span> Jenny All｜投資系統</div>
  <div class="sync">資料每 10 分鐘自動更新</div>
</div>
""", unsafe_allow_html=True)

# ─── Source toggle (inline, no sidebar) ──────────────────────────────────
with st.container():
    st.markdown('<div style="padding:12px 28px 0">', unsafe_allow_html=True)
    col_src, col_refresh, _ = st.columns([2, 1, 8])
    with col_src:
        source_mode = st.radio("資料來源", ["Google Sheet", "本機快取"], horizontal=True, label_visibility="collapsed")
    with col_refresh:
        if st.button("🔄 重新整理"):
            st.cache_data.clear()
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# ─── Load data ────────────────────────────────────────────────────────────
with st.spinner("讀取試算表中…"):
    try:
        pri = wb(source_mode, "primary")
        mkt = wb(source_mode, "market")
        load_ok = True
    except Exception as e:
        st.error(f"❌ 讀取失敗：{e}")
        load_ok = False

if not load_ok:
    st.stop()

# ─── Tabs ─────────────────────────────────────────────────────────────────
tabs = st.tabs(["◈ 總覽", "◷ 每月收入", "📒 2026 細帳", "📊 市值來源", "🔍 資料健康"])

# ══════════════════════════════════════════════════════════════════════════
# TAB 1 — 總覽
# ══════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.markdown('<div class="j-page-title">總覽</div><div class="j-page-sub">所有帳戶資產彙整</div>', unsafe_allow_html=True)
    try:
        ov = read_sheet(mkt, "總覽")

        # ── KPI row ──
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("🏦 總資產",     metric_ov(ov, "加總Total"))
        c2.metric("📈 台股",        metric_ov(ov, "台股total"))
        c3.metric("🏛 銀行",        metric_ov(ov, "銀行total"))
        c4.metric("🛡 保險",        metric_ov(ov, "保險total"))
        c5.metric("👤 Uncle 待還",  metric_ov(ov, "uncle待還"))

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Two-column layout ──
        left, right = st.columns([1, 1.5])
        with left:
            st.markdown('<div class="j-card"><div class="j-card-title">彙總摘要</div>', unsafe_allow_html=True)
            summary = ov.iloc[:18, :5].copy()
            summary.columns = ["項目", "現值", "損益", "收入/配息", "合計"]
            st.dataframe(summary, use_container_width=True, hide_index=True, height=320)
            st.markdown('</div>', unsafe_allow_html=True)

        with right:
            st.markdown('<div class="j-card"><div class="j-card-title">投資明細</div>', unsafe_allow_html=True)
            inv = section_from_header(ov, 5, 18, 90)
            show = [c for c in ["投資分類","日期","現值","損益","台幣成本","台幣市值","累積配息","台幣配息","配息率","損益率"] if c in inv.columns]
            st.dataframe(inv[show] if show else inv, use_container_width=True, hide_index=True, height=320)
            st.markdown('</div>', unsafe_allow_html=True)

    except Exception as e:
        st.warning(f"總覽工作表讀取錯誤：{e}")

# ══════════════════════════════════════════════════════════════════════════
# TAB 2 — 每月收入
# ══════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.markdown('<div class="j-page-title">每月收入</div><div class="j-page-sub">配息・股利・利息月走勢</div>', unsafe_allow_html=True)
    try:
        monthly = read_sheet(pri, "每月收入")

        # build trend
        hdr       = monthly.iloc[0]
        total_row = row_label(monthly, "合計")
        records   = []
        if total_row is not None:
            for ci, hv in enumerate(hdr):
                dt  = pd.to_datetime(hv, errors="coerce")
                amt = num(total_row.iloc[ci])
                if pd.notna(dt) and amt is not None:
                    records.append({"月份": dt, "收入": amt})

        if records:
            trend = pd.DataFrame(records).set_index("月份")
            st.markdown('<div class="j-card"><div class="j-card-title">月收入走勢</div>', unsafe_allow_html=True)
            st.bar_chart(trend, height=220, color="#22d48a")
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="j-card"><div class="j-card-title">明細資料</div>', unsafe_allow_html=True)
        tbl = monthly.iloc[:22, :46].dropna(axis=1, how="all")
        tbl.columns = [str(c) for c in tbl.columns]
        st.dataframe(tbl, use_container_width=True, hide_index=True, height=340)
        st.markdown('</div>', unsafe_allow_html=True)

    except Exception as e:
        st.warning(f"每月收入工作表讀取錯誤：{e}")

# ══════════════════════════════════════════════════════════════════════════
# TAB 3 — 2026 細帳
# ══════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.markdown('<div class="j-page-title">2026 細帳</div><div class="j-page-sub">全年進出帳記錄・帳戶移轉・配息・支出</div>', unsafe_allow_html=True)
    try:
        ledger = read_sheet(pri, "2026細帳")

        # pivot to long
        months = ledger.iloc[0, 1:14]
        rows_data = []
        for ri in range(1, min(len(ledger), 160)):
            cat = ledger.iloc[ri, 0]
            if cat is None or pd.isna(cat): continue
            for offset, mv in enumerate(months, start=1):
                amt = num(ledger.iloc[ri, offset])
                if amt is None or amt == 0: continue
                rows_data.append({"月份": str(mv), "項目": str(cat), "金額": amt})

        if rows_data:
            long = pd.DataFrame(rows_data)
            col_f, col_sum = st.columns([3, 1])
            with col_f:
                cats = ["全部"] + sorted(long["項目"].unique().tolist())
                sel  = st.selectbox("篩選項目", cats, label_visibility="collapsed")
            view = long if sel == "全部" else long[long["項目"] == sel]

            # summary metrics
            total_in  = long[long["金額"] > 0]["金額"].sum()
            total_out = long[long["金額"] < 0]["金額"].sum()
            m1, m2, m3 = st.columns(3)
            m1.metric("收入合計",   money(total_in))
            m2.metric("支出合計",   money(abs(total_out)))
            m3.metric("淨收支",     money(total_in + total_out))

            st.markdown('<div class="j-card"><div class="j-card-title">篩選結果</div>', unsafe_allow_html=True)
            st.dataframe(view, use_container_width=True, hide_index=True, height=320)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="j-card"><div class="j-card-title">原始資料（寬表）</div>', unsafe_allow_html=True)
        raw = ledger.iloc[:140, :16].copy()
        raw.columns = [str(c) for c in raw.columns]
        st.dataframe(raw, use_container_width=True, hide_index=True, height=340)
        st.markdown('</div>', unsafe_allow_html=True)

    except Exception as e:
        st.warning(f"2026細帳工作表讀取錯誤：{e}")

# ══════════════════════════════════════════════════════════════════════════
# TAB 4 — 市值來源
# ══════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.markdown('<div class="j-page-title">市值來源</div><div class="j-page-sub">各平台基金・台股・外幣市值</div>', unsafe_allow_html=True)

    sel_sheet = st.selectbox("選擇工作表", MARKET_SHEETS)
    try:
        sheet_df = read_sheet(mkt, sel_sheet)

        if sel_sheet not in {"總覽", "台股", "「台股」的副本", "渣打-美股"}:
            r = sheet_df.iloc[1] if len(sheet_df) > 1 else pd.Series(dtype=object)
            def mval(col):
                return money(r.iloc[col]) if len(r) > col else "—"
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("投資成本", mval(9))
            mc2.metric("總市值",   mval(10))
            mc3.metric("損益",     mval(12))
            mc4.metric("月配息",   mval(14))

        st.markdown('<div class="j-card"><div class="j-card-title">工作表資料</div>', unsafe_allow_html=True)
        tbl = cleaned(sheet_df)
        st.dataframe(tbl, use_container_width=True, hide_index=True, height=480)
        st.markdown('</div>', unsafe_allow_html=True)

    except Exception as e:
        st.warning(f"工作表 {sel_sheet} 讀取錯誤：{e}")

# ══════════════════════════════════════════════════════════════════════════
# TAB 5 — 資料健康
# ══════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown('<div class="j-page-title">資料健康</div><div class="j-page-sub">工作表結構・公式統計・錯誤偵測</div>', unsafe_allow_html=True)

    if not SUMMARY_JSON.exists():
        st.info("尚未產生 workbook_structure_summary.json，請先執行分析腳本。")
    else:
        try:
            summaries = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
            for book in summaries:
                fname = Path(book["file"]).name
                st.markdown(f'<div class="j-card"><div class="j-card-title">{fname}</div>', unsafe_allow_html=True)
                bm1, bm2, bm3 = st.columns(3)
                bm1.metric("檔案大小 MB", book["size_mb"])
                bm2.metric("工作表數",    book["sheet_count"])
                bm3.metric("公式種類",    len(book["workbook_functions"]))

                heavy = (pd.DataFrame(book["sheets"])
                         .sort_values("formulas", ascending=False)
                         [["sheet","class","rows","cols","nonempty","formulas","literal_errors"]]
                         .head(12))
                st.dataframe(heavy, use_container_width=True, hide_index=True)

                funcs = pd.DataFrame([{"公式": k, "次數": v} for k, v in book["workbook_functions"].items()])
                st.dataframe(funcs, use_container_width=True, hide_index=True)
                st.markdown('</div>', unsafe_allow_html=True)
        except Exception as e:
            st.error(f"讀取健康報告失敗：{e}")
