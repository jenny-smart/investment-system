from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


# ─── Config ────────────────────────────────────────────────────────────────
BASE_DIR               = Path(__file__).resolve().parent
PROJECT_DIR            = BASE_DIR.parent
PRIMARY_SPREADSHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"
MARKET_SPREADSHEET_ID  = "17HPytZKOPR_9Od_wor-xEx9kpccJlPS2v6B0Dz6MRYc"
PRIMARY_LOCAL          = PROJECT_DIR / "inputs" / "investment-system-source.xlsx"
MARKET_LOCAL           = PROJECT_DIR / "inputs" / "market-value-source.xlsx"
SUMMARY_JSON           = PROJECT_DIR / "outputs" / "workbook_structure_summary.json"

MARKET_SHEETS = [
    "總覽", "台股", "「台股」的副本", "渣打-美股",
    "基富通-台", "基富通-人民幣", "基富通-日幣",
    "渣打-美金", "渣打-南非", "台新-美金", "台新-南非",
]

# ── Master config: 11 funds (MoneyDJ) ──────────────────────────────────────
FUND_CONFIG = [
    {"code": "acft94",  "pattern": "yp010000", "currency": "TWD", "name": "富蘭克林華美新興國家固定收益B-新臺幣"},
    {"code": "acai222", "pattern": "yp010000", "currency": "TWD", "name": "柏瑞新興邊境非投資等級債券B類型"},
    {"code": "acft99",  "pattern": "yp010000", "currency": "CNY", "name": "富蘭克林華美新興國家固定收益B-人民幣"},
    {"code": "acob36",  "pattern": "yp010000", "currency": "USD", "name": "大華銀新加坡房地產收益-美元月配"},
    {"code": "shzx0",   "pattern": "yp010001", "currency": "JPY", "name": "貝萊德全球智慧數據股票入息A6日圓"},
    {"code": "TLZO3",   "pattern": "yp010001", "currency": "JPY", "name": "安聯收益成長AMgi月收（日圓避險）"},
    {"code": "pizn8",   "pattern": "yp010001", "currency": "USD", "name": "東方匯理新興市場債券A美元（月配）"},
    {"code": "pizo1",   "pattern": "yp010001", "currency": "USD", "name": "東方匯理新興市場債券U美元（月配）"},
    {"code": "pizm9",   "pattern": "yp010001", "currency": "ZAR", "name": "東方匯理新興市場債券U南非幣（月配）"},
    {"code": "anzb6",   "pattern": "yp010001", "currency": "USD", "name": "高盛新興市場債券Y股美元"},
    {"code": "ANZH2",   "pattern": "yp010001", "currency": "ZAR", "name": "高盛新興市場債券Y（南非幣對沖）"},
]

# ── Master config: stocks ───────────────────────────────────────────────────
STOCK_CONFIG = [
    {"ticker": "PYPL",  "name": "PayPal",       "currency": "USD"},
    {"ticker": "XYZ",   "name": "XYZ",           "currency": "USD"},
]

# ── FX pairs needed ─────────────────────────────────────────────────────────
FX_PAIRS = {
    "USD": "USDTWD=X",
    "CNY": "CNYTWD=X",
    "JPY": "JPYTWD=X",
    "ZAR": "ZARTWD=X",
}

# ─── Page config ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Jenny All｜投資系統",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── CSS: pure white + mint theme ──────────────────────────────────────────
st.markdown("""
<style>
/* hide sidebar */
[data-testid="stSidebar"],
[data-testid="collapsedControl"],
section[data-testid="stSidebarNav"],
button[kind="header"] { display: none !important; }

html, body, [class*="css"] {
    font-family: "PingFang TC", "Noto Sans TC", -apple-system,
                 BlinkMacSystemFont, "Segoe UI", sans-serif !important;
}
.stApp { background: #f7faf9 !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }

/* ── Top bar ─────────────────────────────────────────────────────── */
.j-topbar {
    background: #ffffff;
    border-bottom: 1px solid #e5eae8;
    padding: 0 32px;
    height: 56px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 1px 4px rgba(0,0,0,.05);
    position: sticky; top: 0; z-index: 999;
}
.j-brand {
    font-size: 16px; font-weight: 700; color: #0f2b20;
    display: flex; align-items: center; gap: 8px;
}
.j-brand .dot { color: #10b981; font-size: 18px; }
.j-tagline { font-size: 11px; color: #a0b0a8; }

/* ── Source row ──────────────────────────────────────────────────── */
.j-source-row {
    background: #ffffff;
    border-bottom: 1px solid #e5eae8;
    padding: 8px 32px;
    display: flex; align-items: center; gap: 12px;
}

/* ── Tabs ────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: #ffffff;
    border-bottom: 2px solid #e5eae8;
    padding: 0 28px; gap: 0;
    box-shadow: 0 1px 3px rgba(0,0,0,.04);
}
.stTabs [data-baseweb="tab"] {
    color: #6b8a7a !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    padding: 13px 20px !important;
    border-bottom: 3px solid transparent !important;
    background: transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #047857 !important;
    border-bottom-color: #10b981 !important;
    font-weight: 700 !important;
}
.stTabs [data-baseweb="tab-panel"] {
    background: #f7faf9;
    padding: 28px 32px;
}

/* ── Metrics ─────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #ffffff !important;
    border: 1px solid #e5eae8 !important;
    border-radius: 12px !important;
    padding: 18px 22px !important;
    box-shadow: 0 1px 4px rgba(0,0,0,.04) !important;
}
[data-testid="stMetricLabel"] p {
    font-size: 11px !important;
    font-weight: 600 !important;
    letter-spacing: .5px !important;
    text-transform: uppercase !important;
    color: #8fa89e !important;
}
[data-testid="stMetricValue"] {
    font-size: 22px !important;
    font-weight: 700 !important;
    color: #0f2b20 !important;
}
[data-testid="stMetricDelta"] { font-size: 12px !important; }

/* ── Dataframe ───────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border: 1px solid #e5eae8 !important;
    border-radius: 12px !important;
    overflow: hidden !important;
    box-shadow: 0 1px 4px rgba(0,0,0,.04) !important;
}
.dvn-scroller { background: #ffffff !important; }

/* ── Selectbox ───────────────────────────────────────────────────── */
[data-baseweb="select"] > div {
    background: #ffffff !important;
    border-color: #e5eae8 !important;
    border-radius: 8px !important;
    color: #0f2b20 !important;
    font-size: 13px !important;
}

/* ── Radio ───────────────────────────────────────────────────────── */
[data-testid="stRadio"] fieldset { border: none !important; }
[data-testid="stRadio"] > div {
    flex-direction: row !important; flex-wrap: nowrap !important; gap: 8px !important;
}
[data-testid="stRadio"] label {
    background: #f0f5f3 !important;
    border: 1.5px solid #d5e3de !important;
    border-radius: 8px !important;
    padding: 6px 14px !important;
    font-size: 12.5px !important;
    font-weight: 500 !important;
    color: #4a7264 !important;
    cursor: pointer !important;
    white-space: nowrap !important;
}
[data-testid="stRadio"] label:has(input:checked) {
    background: #ecfdf5 !important;
    border-color: #10b981 !important;
    color: #047857 !important;
    font-weight: 600 !important;
}

/* ── Buttons ─────────────────────────────────────────────────────── */
.stButton > button {
    background: #10b981 !important; color: #fff !important;
    border: none !important; border-radius: 8px !important;
    font-weight: 600 !important; font-size: 13px !important;
    padding: 7px 18px !important;
    box-shadow: 0 2px 6px rgba(16,185,129,.25) !important;
}
.stButton > button:hover { background: #047857 !important; }

/* ── Section card ────────────────────────────────────────────────── */
.j-card {
    background: #ffffff;
    border: 1px solid #e5eae8;
    border-radius: 14px;
    padding: 22px 24px;
    margin-bottom: 18px;
    box-shadow: 0 1px 4px rgba(0,0,0,.04);
}
.j-card-title {
    font-size: 10.5px; font-weight: 700; color: #8fa89e;
    letter-spacing: .8px; text-transform: uppercase;
    margin-bottom: 14px; padding-bottom: 10px;
    border-bottom: 1px solid #f0f5f3;
}
.j-page-title { font-size: 21px; font-weight: 700; color: #0f2b20; margin-bottom: 3px; }
.j-page-sub   { font-size: 12.5px; color: #8fa89e; margin-bottom: 22px; }

/* ── Status badges ───────────────────────────────────────────────── */
.badge { display:inline-block; padding:2px 9px; border-radius:20px; font-size:11px; font-weight:600; }
.badge-ok  { background:#ecfdf5; color:#047857; }
.badge-err { background:#fef2f2; color:#dc2626; }
.badge-warn{ background:#fffbeb; color:#d97706; }

/* ── Live price table ────────────────────────────────────────────── */
.price-row { display:flex; align-items:center; justify-content:space-between;
    padding:9px 0; border-bottom:1px solid #f0f5f3; font-size:13px; }
.price-row:last-child { border-bottom:none; }
.price-name { color:#2d5a47; font-weight:500; flex:1; }
.price-val  { font-weight:700; color:#0f2b20; min-width:90px; text-align:right; }
.price-cur  { color:#8fa89e; font-size:11px; min-width:36px; text-align:right; }
.price-ok   { color:#10b981; font-size:11px; min-width:50px; text-align:right; }
.price-err  { color:#ef4444; font-size:11px; min-width:50px; text-align:right; }

/* ── Spinner ─────────────────────────────────────────────────────── */
[data-testid="stSpinner"] p { color:#10b981 !important; }
[data-testid="stAlert"] { border-radius:10px !important; font-size:13px !important; }
</style>
""", unsafe_allow_html=True)


# ─── Helpers ───────────────────────────────────────────────────────────────
def google_export_url(sid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx"

@st.cache_data(ttl=600, show_spinner=False)
def download_xlsx(sid: str) -> bytes:
    r = requests.get(google_export_url(sid), timeout=60)
    r.raise_for_status()
    if b"<!DOCTYPE" in r.content[:200]:
        raise ValueError("Google Sheet 回傳 HTML（可能需要登入或尚未公開）")
    return r.content

@st.cache_data(ttl=600, show_spinner=False)
def load_local_xlsx(path: str) -> bytes:
    return Path(path).read_bytes()

@st.cache_data(ttl=600, show_spinner=False)
def read_sheet(xlsx_bytes: bytes, sheet_name: str) -> pd.DataFrame:
    return pd.read_excel(BytesIO(xlsx_bytes), sheet_name=sheet_name,
                         header=None, engine="openpyxl")

def workbook_bytes(mode: str, which: str) -> bytes:
    if which == "primary":
        return (load_local_xlsx(str(PRIMARY_LOCAL))
                if mode == "本機快取" else download_xlsx(PRIMARY_SPREADSHEET_ID))
    return (load_local_xlsx(str(MARKET_LOCAL))
            if mode == "本機快取" else download_xlsx(MARKET_SPREADSHEET_ID))

def numeric(v: Any) -> float | None:
    try:
        return None if v is None or pd.isna(v) else float(v)
    except Exception:
        return None

def money(v: Any) -> str:
    """3-digit comma integer — per architecture spec."""
    n = numeric(v)
    return "-" if n is None else f"{n:,.0f}"

def fmt_df(df: pd.DataFrame) -> pd.DataFrame:
    """NaN / None / NaT → empty string."""
    return df.fillna("").astype(str).replace({"nan": "", "None": "", "NaT": "", "NaN": ""})

def cleaned_table(df: pd.DataFrame, max_rows: int = 120, max_cols: int = 40) -> pd.DataFrame:
    t = df.dropna(how="all").dropna(axis=1, how="all")
    t = t.iloc[:max_rows, :max_cols].copy()
    t.columns = [str(c) for c in t.columns]
    return fmt_df(t)

def row_by_label(df: pd.DataFrame, label: str) -> pd.Series | None:
    lbs = df.iloc[:, 0].astype(str).str.strip()
    m = df.loc[lbs == label]
    return None if m.empty else m.iloc[0]

def metric_from_overview(df: pd.DataFrame, label: str, col: int = 1) -> str:
    row = row_by_label(df, label)
    return money(row.iloc[col]) if row is not None and len(row) > col else "-"

def make_section_from_header(df: pd.DataFrame, sc: int, ec: int, max_rows: int = 80) -> pd.DataFrame:
    s = df.iloc[:max_rows, sc:ec].dropna(how="all").copy()
    if s.empty: return s
    hdr = s.iloc[0].fillna("")
    s = s.iloc[1:].copy()
    s.columns = [str(v).strip() or f"col_{i+1}" for i, v in enumerate(hdr)]
    return fmt_df(s.dropna(how="all"))

def monthly_income_trend(monthly_df: pd.DataFrame) -> pd.DataFrame:
    header    = monthly_df.iloc[0]
    total_row = row_by_label(monthly_df, "合計")
    if total_row is None:
        return pd.DataFrame(columns=["月份", "收入"])
    records = []
    for ci, hv in enumerate(header):
        dt  = pd.to_datetime(hv, errors="coerce")
        amt = numeric(total_row.iloc[ci])
        if pd.notna(dt) and amt is not None:
            records.append({"月份": dt, "收入": amt})
    return pd.DataFrame(records)

def ledger_long_table(ledger: pd.DataFrame) -> pd.DataFrame:
    months  = ledger.iloc[0, 1:14]
    records = []
    for ri in range(1, min(len(ledger), 160)):
        cat = ledger.iloc[ri, 0]
        if cat is None or pd.isna(cat): continue
        for offset, mv in enumerate(months, start=1):
            amt = numeric(ledger.iloc[ri, offset])
            if amt is None or amt == 0: continue
            records.append({"月份": str(mv), "項目": str(cat), "金額": amt, "來源列": ri + 1})
    return pd.DataFrame(records)

def fund_sheet_metrics(df: pd.DataFrame) -> dict[str, str]:
    row = df.iloc[1] if len(df) > 1 else pd.Series(dtype=object)
    return {
        "投資成本": money(row.iloc[9])  if len(row) > 9  else "-",
        "總市值":   money(row.iloc[10]) if len(row) > 10 else "-",
        "損益":     money(row.iloc[12]) if len(row) > 12 else "-",
        "月配息":   money(row.iloc[14]) if len(row) > 14 else "-",
    }

def load_health_summary() -> list[dict[str, Any]]:
    if not SUMMARY_JSON.exists(): return []
    return json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))


# ─── Live price fetchers ────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def fetch_fund_nav(code: str, pattern: str) -> tuple[str, str]:
    """Scrape MoneyDJ fund NAV. Returns (price_str, status)."""
    if not HAS_BS4:
        return "-", "缺少 beautifulsoup4"
    url = f"https://www.moneydj.com/funddj/ya/{pattern}.djhtm?a={code}"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        # XPath equivalent: #article form table[1] tr[2] td[2]
        table = soup.select_one("#article form table")
        if table:
            rows = table.find_all("tr")
            if len(rows) >= 2:
                cells = rows[1].find_all("td")
                if len(cells) >= 2:
                    val = cells[1].get_text(strip=True)
                    if val:
                        return val, "ok"
        return "-", "未找到淨值欄位"
    except Exception as e:
        return "-", str(e)[:40]

@st.cache_data(ttl=300, show_spinner=False)
def fetch_stock_price(ticker: str) -> tuple[str, str]:
    """Yahoo Finance stock price. Returns (price_str, status)."""
    if not HAS_YF:
        return "-", "缺少 yfinance"
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        price = getattr(info, "last_price", None)
        if price:
            return f"{price:,.4f}", "ok"
        return "-", "無資料"
    except Exception as e:
        return "-", str(e)[:40]

@st.cache_data(ttl=300, show_spinner=False)
def fetch_fx(pair: str) -> tuple[str, str]:
    """Yahoo Finance FX rate. Returns (rate_str, status)."""
    if not HAS_YF:
        return "-", "缺少 yfinance"
    try:
        t = yf.Ticker(pair)
        info = t.fast_info
        rate = getattr(info, "last_price", None)
        if rate:
            return f"{rate:,.4f}", "ok"
        return "-", "無資料"
    except Exception as e:
        return "-", str(e)[:40]


# ─── Top bar ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="j-topbar">
  <div class="j-brand"><span class="dot">◈</span> Jenny All &nbsp;|&nbsp; 投資系統</div>
  <div class="j-tagline">資料每 10 分鐘自動更新・市價每 5 分鐘自動更新</div>
</div>
""", unsafe_allow_html=True)

# ─── Source toggle + refresh ─────────────────────────────────────────────────
sc1, sc2, sc3 = st.columns([2, 1, 9])
with sc1:
    source_mode = st.radio("來源", ["Google Sheet", "本機快取"],
                           horizontal=True, label_visibility="collapsed")
with sc2:
    if st.button("🔄 重新整理"):
        st.cache_data.clear()
        st.rerun()

# ─── Load workbooks ──────────────────────────────────────────────────────────
with st.spinner("讀取試算表中…"):
    try:
        primary_bytes = workbook_bytes(source_mode, "primary")
        market_bytes  = workbook_bytes(source_mode, "market")
        load_ok = True
    except Exception as exc:
        st.error(f"❌ 讀取失敗：{exc}")
        load_ok = False

if not load_ok:
    st.stop()

# ─── Tabs ────────────────────────────────────────────────────────────────────
tabs = st.tabs(["◈ 總覽", "◷ 每月收入", "📒 2026 細帳",
                "📊 市值來源", "💹 即時市值", "🔍 資料健康"])


# ═══════════════════════════════════════════════════════════════════════════
# TAB 1 — 總覽
# ═══════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.markdown('<div class="j-page-title">總覽</div>'
                '<div class="j-page-sub">所有帳戶資產彙整</div>', unsafe_allow_html=True)
    try:
        overview = read_sheet(market_bytes, "總覽")

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("🏦 總資產",     metric_from_overview(overview, "加總Total"))
        c2.metric("📈 台股",        metric_from_overview(overview, "台股total"))
        c3.metric("🏛 銀行",        metric_from_overview(overview, "銀行total"))
        c4.metric("🛡 保險",        metric_from_overview(overview, "保險total"))
        c5.metric("👤 Uncle 待還",  metric_from_overview(overview, "uncle待還"))

        # Diagnostic — if all KPIs are "-", show first 20 labels
        kpi_vals = [metric_from_overview(overview, lbl) for lbl in
                    ["加總Total","台股total","銀行total","保險total","uncle待還"]]
        if all(v == "-" for v in kpi_vals):
            with st.expander("⚠️ KPI 全部為 — — 點此診斷 A 欄標籤", expanded=True):
                labels = overview.iloc[:20, 0].astype(str).tolist()
                st.code("\n".join(f"{i+1}: {l}" for i, l in enumerate(labels)))

        st.markdown("<br>", unsafe_allow_html=True)
        l, r = st.columns([1, 1.6])

        with l:
            st.markdown('<div class="j-card"><div class="j-card-title">彙總摘要</div>', unsafe_allow_html=True)
            summary = overview.iloc[:18, :5].copy()
            summary.columns = ["項目","現值","損益","收入/配息","合計"]
            st.dataframe(fmt_df(summary), use_container_width=True, hide_index=True, height=340)
            st.markdown('</div>', unsafe_allow_html=True)

        with r:
            st.markdown('<div class="j-card"><div class="j-card-title">投資明細</div>', unsafe_allow_html=True)
            inv = make_section_from_header(overview, 5, 18, 90)
            show_cols = [c for c in ["投資分類","日期","現值","損益","台幣成本","台幣市值",
                                      "累積配息","台幣配息","配息率","損益率"] if c in inv.columns]
            st.dataframe(inv[show_cols] if show_cols else inv,
                         use_container_width=True, hide_index=True, height=340)
            st.markdown('</div>', unsafe_allow_html=True)

    except Exception as e:
        st.warning(f"⚠️ 總覽工作表讀取錯誤：{e}")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2 — 每月收入
# ═══════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.markdown('<div class="j-page-title">每月收入</div>'
                '<div class="j-page-sub">配息・股利・利息月走勢</div>', unsafe_allow_html=True)
    try:
        monthly = read_sheet(primary_bytes, "每月收入")
        trend   = monthly_income_trend(monthly)

        if not trend.empty:
            st.markdown('<div class="j-card"><div class="j-card-title">月收入走勢</div>',
                        unsafe_allow_html=True)
            st.bar_chart(trend.set_index("月份"), height=240, color="#10b981")
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="j-card"><div class="j-card-title">每月收入明細</div>',
                    unsafe_allow_html=True)
        tbl = monthly.iloc[:22, :46].dropna(axis=1, how="all")
        tbl.columns = [str(c) for c in tbl.columns]
        st.dataframe(fmt_df(tbl), use_container_width=True, hide_index=True, height=360)
        st.markdown('</div>', unsafe_allow_html=True)

    except Exception as e:
        st.warning(f"⚠️ 每月收入工作表讀取錯誤：{e}")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 3 — 2026 細帳
# ═══════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.markdown('<div class="j-page-title">2026 細帳</div>'
                '<div class="j-page-sub">全年進出帳記錄・帳戶移轉・配息・支出</div>',
                unsafe_allow_html=True)
    try:
        ledger  = read_sheet(primary_bytes, "2026細帳")
        long_df = ledger_long_table(ledger)

        if not long_df.empty:
            # Summary metrics
            inc = long_df[long_df["金額"] > 0]["金額"].sum()
            out = long_df[long_df["金額"] < 0]["金額"].sum()
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("收入合計",  money(inc))
            m2.metric("支出合計",  money(abs(out)))
            m3.metric("淨收支",    money(inc + out))
            m4.metric("記錄筆數",  f"{len(long_df):,}")

            cats = ["全部"] + sorted(long_df["項目"].unique().tolist())
            sel  = st.selectbox("篩選項目", cats)
            view = long_df if sel == "全部" else long_df[long_df["項目"] == sel]

            st.markdown('<div class="j-card"><div class="j-card-title">細帳明細（長表）</div>',
                        unsafe_allow_html=True)
            st.dataframe(fmt_df(view), use_container_width=True, hide_index=True, height=340)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="j-card"><div class="j-card-title">原始資料（寬表）</div>',
                    unsafe_allow_html=True)
        raw = ledger.iloc[:140, :16].copy()
        raw.columns = [str(c) for c in raw.columns]
        st.dataframe(fmt_df(raw), use_container_width=True, hide_index=True, height=360)
        st.markdown('</div>', unsafe_allow_html=True)

    except Exception as e:
        st.warning(f"⚠️ 2026細帳工作表讀取錯誤：{e}")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 4 — 市值來源
# ═══════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.markdown('<div class="j-page-title">市值來源</div>'
                '<div class="j-page-sub">各平台基金・台股・外幣市值（Google Sheet 快照）</div>',
                unsafe_allow_html=True)

    sel_sheet = st.selectbox("選擇工作表", MARKET_SHEETS)
    try:
        sheet = read_sheet(market_bytes, sel_sheet)

        if sel_sheet not in {"總覽", "台股", "「台股」的副本", "渣打-美股"}:
            metrics = fund_sheet_metrics(sheet)
            mc1, mc2, mc3, mc4 = st.columns(4)
            for col, (label, val) in zip([mc1, mc2, mc3, mc4], metrics.items()):
                col.metric(label, val)

        st.markdown('<div class="j-card"><div class="j-card-title">工作表資料</div>',
                    unsafe_allow_html=True)
        st.dataframe(cleaned_table(sheet), use_container_width=True, hide_index=True, height=500)
        st.markdown('</div>', unsafe_allow_html=True)

    except Exception as e:
        st.warning(f"⚠️ 工作表 {sel_sheet} 讀取錯誤：{e}")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 5 — 即時市值  (AUTO-LOAD, no button)
# ═══════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown('<div class="j-page-title">即時市值</div>'
                '<div class="j-page-sub">自動抓取・基金 NAV via MoneyDJ・股票 via Yahoo Finance・每 5 分鐘更新</div>',
                unsafe_allow_html=True)

    # ── FX rates ──────────────────────────────────────────────────────────
    st.markdown('<div class="j-card"><div class="j-card-title">匯率（TWD 換算）</div>',
                unsafe_allow_html=True)
    fx_cols = st.columns(len(FX_PAIRS))
    fx_rates: dict[str, float] = {}
    for col, (cur, pair) in zip(fx_cols, FX_PAIRS.items()):
        with st.spinner(f"抓取 {cur}…"):
            rate_str, status = fetch_fx(pair)
        col.metric(f"1 {cur} = ? TWD", rate_str,
                   delta="✓ 即時" if status == "ok" else f"⚠ {status}")
        if status == "ok":
            try:
                fx_rates[cur] = float(rate_str.replace(",", ""))
            except Exception:
                pass
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Fund NAVs ─────────────────────────────────────────────────────────
    st.markdown('<div class="j-card"><div class="j-card-title">基金最新淨值（MoneyDJ）</div>',
                unsafe_allow_html=True)

    fund_rows = []
    progress = st.progress(0, text="抓取基金淨值…")
    for i, f in enumerate(FUND_CONFIG):
        nav_str, status = fetch_fund_nav(f["code"], f["pattern"])
        cur = f["currency"]
        twd_str = "-"
        if status == "ok" and cur in fx_rates:
            try:
                twd = float(nav_str.replace(",", "")) * fx_rates[cur]
                twd_str = f"{twd:,.4f}"
            except Exception:
                pass
        elif cur == "TWD" and status == "ok":
            twd_str = nav_str
        fund_rows.append({
            "基金名稱":   f["name"],
            "MoneyDJ代號": f["code"],
            "幣別":       cur,
            "最新淨值":   nav_str,
            "台幣換算":   twd_str,
            "狀態":       "✓" if status == "ok" else f"⚠ {status}",
        })
        progress.progress((i + 1) / len(FUND_CONFIG), text=f"抓取中… {i+1}/{len(FUND_CONFIG)}")

    progress.empty()
    fund_df = pd.DataFrame(fund_rows)
    st.dataframe(fund_df, use_container_width=True, hide_index=True, height=420)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Stock prices ──────────────────────────────────────────────────────
    st.markdown('<div class="j-card"><div class="j-card-title">股票即時價（Yahoo Finance）</div>',
                unsafe_allow_html=True)

    stock_rows = []
    for s in STOCK_CONFIG:
        price_str, status = fetch_stock_price(s["ticker"])
        stock_rows.append({
            "代號":  s["ticker"],
            "名稱":  s["name"],
            "幣別":  s["currency"],
            "即時價": price_str,
            "狀態":  "✓" if status == "ok" else f"⚠ {status}",
        })

    stock_df = pd.DataFrame(stock_rows)
    st.dataframe(stock_df, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if not HAS_YF:
        st.info("提示：安裝 `yfinance` 以啟用股票/匯率即時抓取。`pip install yfinance`")
    if not HAS_BS4:
        st.info("提示：安裝 `beautifulsoup4` 與 `lxml` 以啟用基金 NAV 抓取。")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 6 — 資料健康
# ═══════════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.markdown('<div class="j-page-title">資料健康</div>'
                '<div class="j-page-sub">工作表結構・公式統計・錯誤偵測</div>',
                unsafe_allow_html=True)

    summaries = load_health_summary()
    if not summaries:
        st.info("尚未產生 workbook_structure_summary.json，請先執行分析腳本。")
    else:
        for book in summaries:
            fname = Path(book["file"]).name
            st.markdown(f'<div class="j-card"><div class="j-card-title">{fname}</div>',
                        unsafe_allow_html=True)
            bm1, bm2, bm3 = st.columns(3)
            bm1.metric("檔案大小 MB",  book["size_mb"])
            bm2.metric("工作表數",     book["sheet_count"])
            bm3.metric("公式種類",     len(book["workbook_functions"]))

            heavy = (pd.DataFrame(book["sheets"])
                     .sort_values("formulas", ascending=False)
                     [["sheet","class","rows","cols","nonempty","formulas","literal_errors"]]
                     .head(12))
            st.dataframe(fmt_df(heavy), use_container_width=True, hide_index=True)

            funcs = pd.DataFrame(
                [{"公式": k, "次數": v} for k, v in book["workbook_functions"].items()])
            st.dataframe(fmt_df(funcs), use_container_width=True, hide_index=True)
            st.markdown('</div>', unsafe_allow_html=True)
