"""
Jenny All｜投資系統 — 清新版本
================================
- 純白底 + 薄荷綠強調色，中文小字也看得清楚
- 強化資料來源切換：Google Sheet / 本機快取 / 手動上傳 xlsx
- 讀不到資料時會給出具體診斷（缺哪個工作表、Google Sheet 是否回傳 HTML、找到哪些列標籤）
- 同一檔案即可上線 Streamlit Community Cloud，本機執行也支援
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st

# yfinance is optional — we import lazily so the app still loads if it's missing
try:
    import yfinance as yf
    _YF_OK = True
except Exception:
    yf = None  # type: ignore[assignment]
    _YF_OK = False

try:
    from bs4 import BeautifulSoup
    _BS4_OK = True
except Exception:
    BeautifulSoup = None  # type: ignore[assignment]
    _BS4_OK = False

# ─── Config ──────────────────────────────────────────────────────────────
PRIMARY_SPREADSHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"
MARKET_SPREADSHEET_ID = "17HPytZKOPR_9Od_wor-xEx9kpccJlPS2v6B0Dz6MRYc"
BASE_DIR = Path(__file__).resolve().parent
PRIMARY_LOCAL = BASE_DIR / "inputs" / "investment-system-source.xlsx"
MARKET_LOCAL = BASE_DIR / "inputs" / "market-value-source.xlsx"
SUMMARY_JSON = BASE_DIR / "outputs" / "workbook_structure_summary.json"

MARKET_SHEETS = [
    "總覽", "台股", "「台股」的副本", "渣打-美股",
    "基富通-台", "基富通-人民幣", "基富通-日幣",
    "渣打-美金", "渣打-南非", "台新-美金", "台新-南非",
]

# ─── Holdings Master Config ──────────────────────────────────────────────
# 維護方式：直接編輯下面四個區塊；要新增/移除部位就改這裡
# 1. TW_NAME_TO_CODE — 中文名稱 → 證交所代碼
# 2. TW_HOLDINGS — 台股部位清單（重複代表多筆部位，不去重）
# 3. US_HOLDINGS — 美股部位清單
# 4. FUND_HOLDINGS — 基金部位清單

TW_NAME_TO_CODE: dict[str, str] = {
    "儒鴻": "1476",
    "大魯閣": "1432",
    "中砂": "1560",
    "中鴻": "2014",
    "凱美": "5317",
    "華碩": "2357",
    "日勝生": "2547",
    "晶華": "2707",
    "中壽": "2823",            # ⚠️ 2023 與凱基金合併，可能查無資料
    "凱基金": "2883",
    "凱基金乙特": "2883E",       # ⚠️ 特別股；yfinance 不一定支援，需確認
    "聯陽": "3014",
    "景碩": "3189",
    "緯創": "3231",
    "東隆興": "4401",
    "和碩": "4938",
    "松翰": "5471",
    "智冠": "5478",
    "久元": "6261",
    "台塑化": "6505",
    "上銀": "2049",
    "元大高股息": "0056",
    "元大台灣50": "0050",
    "泰碩": "3338",
    "尼得科超眾": "6230",
    "立積": "4968",
    "鈺齊-KY": "9802",
    "東陽": "1319",
    "華邦電": "2344",
    "元大金": "2885",
    "鴻海": "2317",
    "長榮": "2603",
    "長華*": "8070",            # * 是除息註記，代碼仍是 8070
    "群創": "3481",
    "集盛": "1455",
    "華新": "1605",
    "第一銅": "2009",
    "大聯大": "3702",
    "富邦特選高股息30": "00900",
    "群益台灣精選高息": "00919",
    "富邦全球投等債": "00746B",   # 債券 ETF，B 是代碼一部分
    "群益半導體收益": "00927",
    "華泰": "2329",
    "圓剛": "2417",
    "楠梓電": "2316",
    "富邦台50": "006208",
    "南亞科": "2408",
    "欣興": "3037",
    "京元電子": "2449",
    "國巨": "2327",
}

# 台股部位清單（保留重複；順序如 Jenny 提供）
TW_HOLDINGS: list[str] = [
    "儒鴻", "儒鴻", "大魯閣", "中砂", "中砂", "中鴻", "凱美", "華碩",
    "日勝生", "日勝生", "晶華", "晶華", "中壽", "中壽", "凱基金", "凱基金乙特",
    "聯陽", "景碩", "景碩", "景碩",
    "緯創", "緯創", "緯創", "緯創", "緯創", "緯創", "緯創",
    "東隆興", "東隆興", "和碩", "松翰", "松翰", "智冠",
    "久元", "久元", "久元", "台塑化", "台塑化", "上銀",
    "元大高股息", "元大台灣50", "泰碩", "尼得科超眾", "立積", "立積",
    "鈺齊-KY", "東陽", "東陽", "東陽", "東陽",
    "中砂", "中砂", "中砂", "中砂", "中砂", "中砂", "中砂", "中砂",
    "華邦電", "華邦電",
    "元大金", "元大金", "元大金", "元大金", "元大金", "元大金", "元大金", "元大金",
    "鴻海", "長榮", "長華*", "群創", "集盛", "華新", "第一銅", "大聯大",
    "富邦特選高股息30", "富邦特選高股息30",
    "群益台灣精選高息", "群益台灣精選高息",
    "富邦全球投等債", "群益半導體收益",
    "華泰", "圓剛", "圓剛", "中鴻",
    "楠梓電", "富邦台50", "南亞科", "欣興", "京元電子", "國巨",
]

# 美股部位（代號, 名稱）
US_HOLDINGS: list[tuple[str, str]] = [
    ("PYPL", "PayPal Holdings"),
    ("XYZ", "Block Inc"),
]

# 基金部位（MoneyDJ 代號, URL pattern, 計價幣別, 中文名稱）
FUND_HOLDINGS: list[tuple[str, str, str, str]] = [
    ("acft94", "yp010000", "TWD", "富蘭克林華美新興國家固定收益基金B-新臺幣"),
    ("acai222", "yp010000", "TWD", "柏瑞新興邊境非投資等級債券-B類型"),
    ("acft99", "yp010000", "CNY", "富蘭克林華美新興國家固定收益-人民幣B"),
    ("acob36", "yp010000", "USD", "大華銀新加坡房地產收益-美元月配(後收)"),
    ("shzx0", "yp010001", "JPY", "貝萊德全球智慧數據股票入息Hedged A6日圓"),
    ("TLZO3", "yp010001", "JPY", "安聯收益成長基金AMgi(日圓避險)"),
    ("pizn8", "yp010001", "USD", "東方匯理新興市場債券A美元(穩定月配息)"),
    ("pizo1", "yp010001", "USD", "東方匯理新興市場債券U美元(穩定月配息)"),
    ("pizm9", "yp010001", "ZAR", "東方匯理新興市場債券U南非幣(穩定月配息)"),
    ("anzb6", "yp010001", "USD", "高盛新興市場債券基金Y股美元"),
    ("ANZH2", "yp010001", "ZAR", "高盛新興市場債券基金Y(南非幣對沖)"),
]

# Theme palette — 清新薄荷綠
INK = "#1f2937"          # 主文字
INK_SOFT = "#4b5563"     # 次要文字
MUTED = "#9ca3af"        # 灰色說明
BORDER = "#e5e7eb"       # 卡片邊線
SURFACE = "#ffffff"      # 卡片底色
PAGE = "#f7faf9"         # 頁面底色（極淺薄荷）
MINT = "#10b981"         # 主強調（薄荷綠）
MINT_SOFT = "#ecfdf5"    # 淺薄荷
MINT_INK = "#047857"     # 深薄荷（文字用）
ROSE = "#ef4444"         # 負值
ROSE_SOFT = "#fef2f2"
AMBER = "#f59e0b"
SKY = "#0ea5e9"

st.set_page_config(
    page_title="Jenny All｜投資系統",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── CSS ─────────────────────────────────────────────────────────────────
st.markdown(
    f"""
<style>
/* hide sidebar — keep top bar only */
[data-testid="stSidebar"], [data-testid="collapsedControl"],
section[data-testid="stSidebarNav"], button[kind="header"] {{
    display: none !important;
}}

/* base */
html, body, [class*="css"] {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                 "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif;
}}
.stApp {{ background: {PAGE}; color: {INK}; }}
.block-container {{ padding: 0 !important; max-width: 100% !important; }}

/* ── top nav ────────────────────────────────────────────────────────── */
.jenny-topbar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: {SURFACE};
    border-bottom: 1px solid {BORDER};
    padding: 0 28px;
    height: 56px;
    position: sticky; top: 0; z-index: 999;
}}
.jenny-topbar .logo {{
    font-size: 15px; font-weight: 700; color: {INK};
    display: flex; align-items: center; gap: 8px;
}}
.jenny-topbar .logo .dot {{
    width: 10px; height: 10px; border-radius: 50%;
    background: {MINT};
    box-shadow: 0 0 0 4px {MINT_SOFT};
    display: inline-block;
}}
.jenny-topbar .meta {{
    font-size: 12px; color: {MUTED};
}}

/* ── controls strip ─────────────────────────────────────────────────── */
.jenny-controls {{ padding: 14px 28px 0; }}

/* ── tabs ───────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {{
    background: {SURFACE};
    border-bottom: 1px solid {BORDER};
    padding: 0 28px;
    gap: 4px;
}}
.stTabs [data-baseweb="tab"] {{
    color: {INK_SOFT} !important;
    font-size: 14px;
    padding: 14px 16px;
    border-bottom: 2px solid transparent !important;
    background: transparent !important;
    font-weight: 500;
}}
.stTabs [data-baseweb="tab"]:hover {{ color: {MINT_INK} !important; }}
.stTabs [aria-selected="true"] {{
    color: {MINT_INK} !important;
    border-bottom-color: {MINT} !important;
    font-weight: 600 !important;
}}
.stTabs [data-baseweb="tab-panel"] {{
    background: {PAGE};
    padding: 22px 28px 40px;
}}

/* ── metric cards ───────────────────────────────────────────────────── */
[data-testid="stMetric"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 14px 18px !important;
    box-shadow: 0 1px 2px rgba(16,24,40,.04);
}}
[data-testid="stMetricLabel"] {{
    font-size: 12px !important;
    color: {MUTED} !important;
    font-weight: 500;
    letter-spacing: 0;
    text-transform: none;
}}
[data-testid="stMetricLabel"] p {{
    font-size: 12px !important;
    color: {MUTED} !important;
}}
[data-testid="stMetricValue"] {{
    font-size: 22px !important;
    font-weight: 700 !important;
    color: {INK} !important;
    line-height: 1.3;
}}
[data-testid="stMetricDelta"] {{ font-size: 12px !important; }}

/* ── dataframe ──────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {{
    border: 1px solid {BORDER} !important;
    border-radius: 10px !important;
    overflow: hidden;
    background: {SURFACE};
}}

/* ── radio (source selector) ────────────────────────────────────────── */
[data-testid="stRadio"] > div {{
    display: flex; flex-direction: row; gap: 8px; flex-wrap: wrap;
}}
[data-testid="stRadio"] label {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 13px;
    color: {INK_SOFT} !important;
    cursor: pointer;
    transition: all .15s ease;
}}
[data-testid="stRadio"] label:hover {{
    border-color: {MINT};
    color: {MINT_INK} !important;
}}
[data-testid="stRadio"] label:has(input:checked) {{
    background: {MINT_SOFT};
    border-color: {MINT};
    color: {MINT_INK} !important;
    font-weight: 600;
}}
[data-testid="stRadio"] label > div:first-child {{ display: none; }}

/* ── selectbox / file uploader ──────────────────────────────────────── */
[data-baseweb="select"] > div {{
    background: {SURFACE} !important;
    border-color: {BORDER} !important;
    color: {INK} !important;
    border-radius: 8px !important;
    font-size: 14px;
}}
[data-testid="stFileUploader"] section {{
    background: {SURFACE};
    border: 1px dashed {BORDER};
    border-radius: 10px;
}}

/* ── primary button ─────────────────────────────────────────────────── */
.stButton > button {{
    background: {MINT_SOFT};
    color: {MINT_INK};
    border: 1px solid {MINT};
    border-radius: 8px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 600;
    transition: all .15s ease;
}}
.stButton > button:hover {{
    background: {MINT};
    color: white;
}}

/* ── card ───────────────────────────────────────────────────────────── */
.j-card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 18px 22px;
    margin-bottom: 16px;
    box-shadow: 0 1px 2px rgba(16,24,40,.04);
}}
.j-card-title {{
    font-size: 13px; color: {INK};
    font-weight: 600;
    margin-bottom: 12px; padding-bottom: 10px;
    border-bottom: 1px solid {BORDER};
    display: flex; align-items: center; justify-content: space-between;
}}
.j-card-title .hint {{
    font-size: 11px; color: {MUTED}; font-weight: 400;
}}

/* ── page heading ───────────────────────────────────────────────────── */
.j-page-title {{
    font-size: 22px; font-weight: 700; color: {INK};
    margin: 4px 0 2px;
    display: flex; align-items: center; gap: 10px;
}}
.j-page-sub {{
    font-size: 13px; color: {INK_SOFT}; margin-bottom: 18px;
}}

/* ── status pill ────────────────────────────────────────────────────── */
.pill {{
    display:inline-block; padding:3px 10px; border-radius:999px;
    font-size:11px; font-weight:600; letter-spacing:.2px;
}}
.pill-ok   {{ background:{MINT_SOFT}; color:{MINT_INK}; }}
.pill-warn {{ background:#fff7ed; color:#c2410c; }}
.pill-err  {{ background:{ROSE_SOFT}; color:{ROSE}; }}
.pill-info {{ background:#eff6ff; color:#1d4ed8; }}

/* ── colored numbers ────────────────────────────────────────────────── */
.j-pos {{ color: {MINT_INK}; font-weight: 600; }}
.j-neg {{ color: {ROSE}; font-weight: 600; }}
.j-muted {{ color: {MUTED}; }}

/* ── info / warn / error banners (Streamlit) ───────────────────────── */
[data-testid="stAlert"] {{
    border-radius: 10px;
    border: 1px solid {BORDER};
}}

/* chart container */
[data-testid="stVegaLiteChart"], [data-testid="stChart"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px;
}}
</style>
""",
    unsafe_allow_html=True,
)

# ─── Helpers ─────────────────────────────────────────────────────────────
def google_export_url(sid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx"


@st.cache_data(ttl=600, show_spinner=False)
def download_xlsx(sid: str) -> bytes:
    """Download xlsx export, raising informative errors if Google returns HTML."""
    url = google_export_url(sid)
    r = requests.get(url, timeout=60, allow_redirects=True)
    r.raise_for_status()
    ct = r.headers.get("content-type", "")
    body = r.content
    # Detect HTML login / permission page disguised as 200
    if "text/html" in ct or body[:6].lower().startswith(b"<!doct") or body[:5].lower().startswith(b"<html"):
        raise RuntimeError(
            f"Google Sheet 沒回傳 xlsx，而是 HTML（content-type={ct or 'n/a'}）。"
            f"請打開 https://docs.google.com/spreadsheets/d/{sid}/edit，"
            f"確認分享設定為「知道連結的任何人可檢視」。"
        )
    if not body[:2] == b"PK":  # xlsx is a zip starting with PK
        raise RuntimeError(
            f"回傳內容不是 xlsx 檔（開頭非 PK）。content-type={ct}, 長度={len(body)}。"
        )
    return body


@st.cache_data(ttl=600, show_spinner=False)
def load_local(path: str) -> bytes:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"本機快取檔不存在：{path}")
    return p.read_bytes()


def load_uploaded(uploaded) -> bytes:
    return uploaded.getvalue()


@st.cache_data(ttl=600, show_spinner=False)
def list_sheets(xlsx: bytes) -> list[str]:
    return pd.ExcelFile(BytesIO(xlsx), engine="openpyxl").sheet_names


@st.cache_data(ttl=600, show_spinner=False)
def read_sheet(xlsx: bytes, sheet: str) -> pd.DataFrame:
    return pd.read_excel(BytesIO(xlsx), sheet_name=sheet, header=None, engine="openpyxl")


def find_sheet(xlsx: bytes, target: str) -> str | None:
    """Find the actual sheet name matching `target` (exact, then fuzzy)."""
    names = list_sheets(xlsx)
    if target in names:
        return target
    norm_t = target.replace(" ", "").replace("　", "").lower()
    for n in names:
        if n.replace(" ", "").replace("　", "").lower() == norm_t:
            return n
    # contains
    for n in names:
        if target in n or n in target:
            return n
    return None


def num(v: Any) -> float | None:
    try:
        return None if v is None or pd.isna(v) else float(v)
    except Exception:
        return None


def money(v: Any) -> str:
    """All money values: rounded integer with 3-digit comma separators."""
    n = num(v)
    if n is None:
        return "—"
    return f"{int(round(n)):,}"


def pct(v: Any) -> str:
    n = num(v)
    return "—" if n is None else f"{n:.2%}"


def fmt_df(df: pd.DataFrame) -> pd.DataFrame:
    """Display formatter:
    - Numeric cells → rounded integer with 3-digit comma separators
    - Empty / None / NaN / NaT → empty string (空格保持空格)
    - Strings that *look* like 'nan' / 'none' → empty string
    """
    def cell(v: Any) -> Any:
        if isinstance(v, bool):
            return v
        # Anything pandas considers missing → blank
        try:
            if pd.isna(v):
                return ""
        except (TypeError, ValueError):
            pass
        if isinstance(v, (int, float)):
            return f"{int(round(v)):,}"
        s = str(v).strip()
        if s.lower() in ("nan", "none", "nat", "<na>", "null"):
            return ""
        return s
    try:
        return df.map(cell)  # pandas ≥ 2.1
    except AttributeError:
        return df.applymap(cell)


def cleaned(df: pd.DataFrame, rows: int = 120, cols: int = 40) -> pd.DataFrame:
    t = df.dropna(how="all").dropna(axis=1, how="all")
    t = t.iloc[:rows, :cols].copy()
    t.columns = [str(c) for c in t.columns]
    return t


def row_label(df: pd.DataFrame, label: str) -> pd.Series | None:
    """Find a row whose first column matches `label` (exact, then fuzzy contains)."""
    lbs = df.iloc[:, 0].astype(str).str.strip()
    m = df.loc[lbs == label]
    if not m.empty:
        return m.iloc[0]
    # Try contains
    m2 = df.loc[lbs.str.contains(label, na=False, regex=False)]
    return None if m2.empty else m2.iloc[0]


def metric_ov(df: pd.DataFrame, label: str, col: int = 1) -> str:
    row = row_label(df, label)
    return money(row.iloc[col]) if row is not None and len(row) > col else "—"


def section_from_header(df: pd.DataFrame, sc: int, ec: int, rows: int = 80) -> pd.DataFrame:
    s = df.iloc[:rows, sc:ec].dropna(how="all").copy()
    if s.empty:
        return s
    hdr = s.iloc[0].fillna("")
    s = s.iloc[1:].copy()
    s.columns = [str(v).strip() or f"col_{i+1}" for i, v in enumerate(hdr)]
    return s.dropna(how="all")


# ─── Market price fetchers (stocks / funds / FX) ─────────────────────────
TW_STOCK_RE = re.compile(r"^\d{4,6}$")  # 台股代碼通常 4~6 碼純數字


def normalize_tw_ticker(symbol: str) -> str:
    """`2330` → `2330.TW`； `0050` → `0050.TW`；其他原樣保留。"""
    s = symbol.strip().upper()
    if "." in s:
        return s
    if TW_STOCK_RE.match(s):
        return f"{s}.TW"  # 主要市場；上櫃則需手動 .TWO
    return s


@st.cache_data(ttl=300, show_spinner=False)
def fetch_stock_quotes(symbols: list[str]) -> pd.DataFrame:
    """批次抓股票最新收盤價。回傳 DataFrame：代碼/即時價/幣別/資料時間/狀態。"""
    if not _YF_OK:
        return pd.DataFrame(
            [{"代碼": s, "即時價": None, "幣別": "", "資料時間": "", "狀態": "未安裝 yfinance"} for s in symbols]
        )
    rows = []
    normed = [normalize_tw_ticker(s) for s in symbols]
    try:
        data = yf.download(
            " ".join(normed),
            period="5d",
            interval="1d",
            group_by="ticker",
            progress=False,
            threads=True,
        )
    except Exception as e:
        return pd.DataFrame([{"代碼": s, "即時價": None, "幣別": "", "資料時間": "", "狀態": f"下載失敗: {e}"} for s in normed])

    for original, norm in zip(symbols, normed):
        price = None
        ts = ""
        ccy = ""
        status = "ok"
        try:
            if len(normed) == 1:
                col = data["Close"] if "Close" in data.columns else None
            else:
                col = data[(norm, "Close")] if (norm, "Close") in data.columns else None
            if col is not None and not col.dropna().empty:
                last = col.dropna()
                price = float(last.iloc[-1])
                ts = str(last.index[-1].date())
            else:
                status = "查無資料"
            if norm.endswith(".TW") or norm.endswith(".TWO"):
                ccy = "TWD"
            elif norm.endswith("=X"):
                ccy = norm[:3]
            else:
                ccy = "USD"
        except Exception as e:
            status = f"err: {e}"
        rows.append(
            {"代碼": original, "yfinance": norm, "即時價": price, "幣別": ccy, "資料時間": ts, "狀態": status}
        )
    return pd.DataFrame(rows)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_fx_rates(currencies: list[str], base: str = "TWD") -> pd.DataFrame:
    """抓主要外幣 → TWD 的匯率（例 USDTWD=X）。"""
    if not _YF_OK:
        return pd.DataFrame(
            [{"幣別": c, "匯率": None, "資料時間": "", "狀態": "未安裝 yfinance"} for c in currencies]
        )
    symbols = [f"{c.upper()}{base}=X" for c in currencies]
    try:
        data = yf.download(
            " ".join(symbols), period="5d", interval="1d",
            group_by="ticker", progress=False, threads=True,
        )
    except Exception as e:
        return pd.DataFrame([{"幣別": c, "匯率": None, "資料時間": "", "狀態": f"下載失敗: {e}"} for c in currencies])

    rows = []
    for c, sym in zip(currencies, symbols):
        rate = None
        ts = ""
        status = "ok"
        try:
            if len(symbols) == 1:
                col = data["Close"] if "Close" in data.columns else None
            else:
                col = data[(sym, "Close")] if (sym, "Close") in data.columns else None
            if col is not None and not col.dropna().empty:
                last = col.dropna()
                rate = float(last.iloc[-1])
                ts = str(last.index[-1].date())
            else:
                status = "查無資料"
        except Exception as e:
            status = f"err: {e}"
        rows.append({"幣別": f"{c.upper()}/{base}", "匯率": rate, "資料時間": ts, "狀態": status})
    return pd.DataFrame(rows)


@st.cache_data(ttl=600, show_spinner=False)
def fetch_fund_nav_moneydj(fund_code: str, url_pattern: str = "yp010000") -> dict[str, Any]:
    """從 MoneyDJ 抓單檔基金最新淨值。

    fund_code:    MoneyDJ 上的基金代號（網址 ?a= 後面那串）
    url_pattern:  "yp010000"（國內基金）或 "yp010001"（境外基金）

    解析邏輯對齊 Jenny 原本 Sheet 的公式：
        importXML(B, "//*[@id='article']/form/table[1]/tbody/tr[2]/td[2]")
    """
    if not _BS4_OK:
        return {"nav": None, "date": "", "name": "", "status": "未安裝 beautifulsoup4"}
    url = f"https://www.moneydj.com/funddj/ya/{url_pattern}.djhtm?a={fund_code}"
    try:
        r = requests.get(url, timeout=30, headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
            ),
            "Accept-Language": "zh-TW,zh;q=0.9",
        })
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "big5"
        soup = BeautifulSoup(r.text, "lxml")

        nav = None
        date = ""
        name = ""

        title = soup.find("title")
        if title:
            name = title.get_text(strip=True).split("-")[0].strip()

        # 對應 XPath: //*[@id='article']/form/table[1]/tbody/tr[2]/td[2]
        article = soup.find(id="article")
        if article:
            form = article.find("form")
            container = form if form else article
            table = container.find("table")  # 第一個 table
            if table:
                # 找 tbody（有些頁面省略 tbody，BS4 會自動補上）
                tbody = table.find("tbody") or table
                rows_tr = tbody.find_all("tr", recursive=False) or tbody.find_all("tr")
                if len(rows_tr) >= 2:
                    cells = rows_tr[1].find_all("td")
                    if len(cells) >= 2:
                        nav_text = cells[1].get_text(strip=True).replace(",", "")
                        try:
                            nav = float(nav_text)
                        except ValueError:
                            nav = None
                        # 第一個 cell 通常是日期
                        date_text = cells[0].get_text(strip=True)
                        if re.search(r"\d{4}/\d{1,2}/\d{1,2}", date_text):
                            date = date_text

        # 備援：頁面整段文字 regex 找「最新淨值」
        if nav is None:
            text = soup.get_text(" ", strip=True)
            m = re.search(r"最新淨值[\s:：]*([0-9]+(?:\.[0-9]+)?)", text)
            if m:
                nav = float(m.group(1))
            m2 = re.search(r"資料日期[\s:：]*([0-9]{4}/[0-9]{1,2}/[0-9]{1,2})", text)
            if m2 and not date:
                date = m2.group(1)

        if nav is None:
            return {"nav": None, "date": date, "name": name, "status": "未找到淨值（MoneyDJ 結構可能調整）"}
        return {"nav": nav, "date": date, "name": name, "status": "ok"}

    except requests.exceptions.RequestException as e:
        return {"nav": None, "date": "", "name": "", "status": f"連線失敗：{e}"}
    except Exception as e:
        return {"nav": None, "date": "", "name": "", "status": f"解析失敗：{e}"}


def fetch_fund_navs_master() -> pd.DataFrame:
    """依 FUND_HOLDINGS 一次抓全部基金淨值。"""
    rows = []
    for code, url_pattern, ccy, name in FUND_HOLDINGS:
        info = fetch_fund_nav_moneydj(code, url_pattern)
        rows.append({
            "基金名稱": name,
            "代號": code,
            "幣別": ccy,
            "最新淨值": info.get("nav"),
            "資料日期": info.get("date") or "—",
            "狀態": info.get("status", ""),
            "MoneyDJ URL": f"https://www.moneydj.com/funddj/ya/{url_pattern}.djhtm?a={code}",
        })
    return pd.DataFrame(rows)


def fetch_tw_holdings_quotes() -> pd.DataFrame:
    """依 TW_HOLDINGS 抓所有台股即時價（保留重複列）。
    內部會去重後批次呼叫 yfinance，再展開回原始順序。
    """
    # 去重對應到 code
    unique_codes = []
    seen = set()
    for name in TW_HOLDINGS:
        code = TW_NAME_TO_CODE.get(name)
        if code and code not in seen:
            unique_codes.append(code)
            seen.add(code)

    quote_by_code: dict[str, dict[str, Any]] = {}
    if _YF_OK and unique_codes:
        symbols = " ".join(f"{c}.TW" for c in unique_codes)
        try:
            data = yf.download(
                symbols, period="5d", interval="1d",
                group_by="ticker", progress=False, threads=True,
            )
            for code in unique_codes:
                sym = f"{code}.TW"
                price = None
                ts = ""
                try:
                    if len(unique_codes) == 1:
                        col = data["Close"] if "Close" in data.columns else None
                    else:
                        col = data[(sym, "Close")] if (sym, "Close") in data.columns else None
                    if col is not None and not col.dropna().empty:
                        last = col.dropna()
                        price = float(last.iloc[-1])
                        ts = str(last.index[-1].date())
                except Exception:
                    pass
                quote_by_code[code] = {"price": price, "date": ts}
        except Exception as e:
            for code in unique_codes:
                quote_by_code[code] = {"price": None, "date": "", "err": str(e)}

    # 展開回 92 筆
    rows = []
    for idx, name in enumerate(TW_HOLDINGS, start=1):
        code = TW_NAME_TO_CODE.get(name, "")
        q = quote_by_code.get(code, {})
        price = q.get("price")
        status = "ok" if price is not None else ("查無代碼" if not code else "查無資料")
        if not _YF_OK:
            status = "未安裝 yfinance"
        rows.append({
            "#": idx,
            "名稱": name,
            "代號": code,
            "即時價": price,
            "幣別": "TWD",
            "資料日期": q.get("date", "") or "—",
            "狀態": status,
        })
    return pd.DataFrame(rows)


def fetch_us_holdings_quotes() -> pd.DataFrame:
    """依 US_HOLDINGS 抓所有美股即時價。"""
    if not US_HOLDINGS:
        return pd.DataFrame()
    symbols = [s for s, _ in US_HOLDINGS]
    quotes = fetch_stock_quotes(symbols)
    name_map = dict(US_HOLDINGS)
    rows = []
    for _, q in quotes.iterrows():
        rows.append({
            "名稱": name_map.get(q["代碼"], ""),
            "代號": q["代碼"],
            "即時價": q["即時價"],
            "幣別": q["幣別"] or "USD",
            "資料日期": q["資料時間"] or "—",
            "狀態": q["狀態"],
        })
    return pd.DataFrame(rows)


# ─── Editable Holdings Helpers ────────────────────────────────────────────
# 為「即時行情」分頁的可編輯持倉介面：初始 DataFrame、平台選項、
# 任意代碼批次抓價、FX 工具、市值與損益計算

PLATFORM_OPTIONS: list[str] = ["基富通-台幣", "基富通-外幣", "渣打", "台新"]


def _platform_default_for_fund(ccy: str) -> str:
    """基金平台預設值：TWD → 基富通-台幣，其他 → 基富通-外幣。
    這只是初始猜測，user 可在表格內改成「渣打」或「台新」。
    """
    return "基富通-台幣" if (ccy or "").upper() == "TWD" else "基富通-外幣"


def initial_tw_editable() -> pd.DataFrame:
    rows = []
    for name in TW_HOLDINGS:
        rows.append({
            "名稱": name,
            "代號": TW_NAME_TO_CODE.get(name, ""),
            "單位數": 0,
            "購買成本(TWD)": 0,
        })
    return pd.DataFrame(rows)


def initial_us_editable() -> pd.DataFrame:
    rows = []
    for code, name in US_HOLDINGS:
        rows.append({
            "名稱": name,
            "代號": code,
            "單位數": 0,
            "購買成本(USD)": 0.0,
        })
    return pd.DataFrame(rows)


def initial_fund_editable() -> pd.DataFrame:
    rows = []
    for code, url_pattern, ccy, name in FUND_HOLDINGS:
        rows.append({
            "基金名稱": name,
            "代號": code,
            "URL Pattern": url_pattern,
            "計價幣別": ccy,
            "平台": _platform_default_for_fund(ccy),
            "單位數": 0.0,
            "購買成本(原幣)": 0.0,
        })
    return pd.DataFrame(rows)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_tw_prices_by_codes(codes_tuple: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    """根據任意 TW 代碼批次抓最新收盤價。回傳 {code: {price, date}}。
    tuple 入參是為了讓 st.cache_data 可以 hash。
    """
    out: dict[str, dict[str, Any]] = {}
    codes = [c for c in codes_tuple if c]
    if not codes or not _YF_OK:
        return out
    try:
        data = yf.download(
            " ".join(f"{c}.TW" for c in codes),
            period="5d", interval="1d", group_by="ticker",
            progress=False, threads=True,
        )
    except Exception:
        return out
    for code in codes:
        sym = f"{code}.TW"
        try:
            if len(codes) == 1:
                col = data["Close"] if "Close" in data.columns else None
            else:
                col = data[(sym, "Close")] if (sym, "Close") in data.columns else None
            if col is not None and not col.dropna().empty:
                last = col.dropna()
                out[code] = {"price": float(last.iloc[-1]), "date": str(last.index[-1].date())}
        except Exception:
            pass
    return out


@st.cache_data(ttl=300, show_spinner=False)
def fetch_us_prices_by_codes(codes_tuple: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    """根據任意美股代碼批次抓最新收盤價。"""
    out: dict[str, dict[str, Any]] = {}
    codes = [c for c in codes_tuple if c]
    if not codes or not _YF_OK:
        return out
    try:
        data = yf.download(
            " ".join(codes),
            period="5d", interval="1d", group_by="ticker",
            progress=False, threads=True,
        )
    except Exception:
        return out
    for code in codes:
        try:
            if len(codes) == 1:
                col = data["Close"] if "Close" in data.columns else None
            else:
                col = data[(code, "Close")] if (code, "Close") in data.columns else None
            if col is not None and not col.dropna().empty:
                last = col.dropna()
                out[code] = {"price": float(last.iloc[-1]), "date": str(last.index[-1].date())}
        except Exception:
            pass
    return out


def fx_df_to_dict(fx_df: pd.DataFrame) -> dict[str, float]:
    """把 fetch_fx_rates 回傳的 DataFrame 轉成 {'USD': 30.5, ...}。TWD 自己 1.0。"""
    out: dict[str, float] = {"TWD": 1.0}
    if fx_df is None or fx_df.empty:
        return out
    for _, r in fx_df.iterrows():
        ccy_label = str(r.get("幣別", ""))
        rate = r.get("匯率")
        if "/" in ccy_label and pd.notna(rate):
            base = ccy_label.split("/")[0].strip()
            try:
                out[base] = float(rate)
            except (TypeError, ValueError):
                continue
    return out


def to_twd(amount: float | None, ccy: str, fx: dict[str, float]) -> float | None:
    """把原幣金額換算成 TWD。找不到匯率回傳 None。"""
    if amount is None or pd.isna(amount):
        return None
    ccy = (ccy or "").upper().strip()
    if not ccy:
        return None
    rate = fx.get(ccy)
    if rate is None:
        return None
    try:
        return float(amount) * float(rate)
    except (TypeError, ValueError):
        return None


def get_sheet_safely(xlsx: bytes, target: str) -> tuple[pd.DataFrame | None, str | None, str | None]:
    """Return (df, actual_sheet_name, error_message). One of df / error will be set."""
    try:
        actual = find_sheet(xlsx, target)
        if actual is None:
            available = ", ".join(list_sheets(xlsx)[:20])
            return None, None, f"找不到工作表「{target}」。可用的工作表：{available}…"
        return read_sheet(xlsx, actual), actual, None
    except Exception as e:
        return None, None, f"讀取「{target}」失敗：{e}"


# ─── Top bar ─────────────────────────────────────────────────────────────
st.markdown(
    """
<div class="jenny-topbar">
    <div class="logo"><span class="dot"></span> Jenny All｜投資系統</div>
    <div class="meta">資料每 10 分鐘自動快取・薄荷清新版</div>
</div>
""",
    unsafe_allow_html=True,
)

# ─── Source toggle ───────────────────────────────────────────────────────
st.markdown('<div class="jenny-controls">', unsafe_allow_html=True)
col_src, col_refresh, col_status = st.columns([3, 1, 6])
with col_src:
    source_mode = st.radio(
        "資料來源",
        ["Google Sheet", "本機快取", "上傳檔案"],
        horizontal=True,
        label_visibility="collapsed",
    )
with col_refresh:
    if st.button("🔄 重新整理"):
        st.cache_data.clear()
        st.rerun()

uploaded_primary = None
uploaded_market = None
if source_mode == "上傳檔案":
    up1, up2 = st.columns(2)
    with up1:
        uploaded_primary = st.file_uploader(
            "主帳本 xlsx（含 每月收入 / 2026細帳）", type=["xlsx"], key="up_primary"
        )
    with up2:
        uploaded_market = st.file_uploader(
            "市值來源 xlsx（含 總覽 / 各平台）", type=["xlsx"], key="up_market"
        )
st.markdown("</div>", unsafe_allow_html=True)


# ─── Load data ───────────────────────────────────────────────────────────
def load_workbook(which: str) -> tuple[bytes | None, str | None]:
    """Return (bytes, error). which ∈ {'primary','market'}."""
    try:
        if source_mode == "Google Sheet":
            sid = PRIMARY_SPREADSHEET_ID if which == "primary" else MARKET_SPREADSHEET_ID
            return download_xlsx(sid), None
        if source_mode == "本機快取":
            path = PRIMARY_LOCAL if which == "primary" else MARKET_LOCAL
            return load_local(str(path)), None
        # 上傳檔案
        up = uploaded_primary if which == "primary" else uploaded_market
        if up is None:
            return None, "請先上傳檔案"
        return load_uploaded(up), None
    except Exception as e:
        return None, str(e)


with st.spinner("讀取試算表中…"):
    pri, pri_err = load_workbook("primary")
    mkt, mkt_err = load_workbook("market")

# Status pills
status_bits = []
if pri_err:
    status_bits.append(f'<span class="pill pill-err">主帳本：{pri_err[:60]}</span>')
elif pri is not None:
    status_bits.append(
        f'<span class="pill pill-ok">主帳本 OK · {len(list_sheets(pri))} 個工作表</span>'
    )
if mkt_err:
    status_bits.append(f'<span class="pill pill-err">市值來源：{mkt_err[:60]}</span>')
elif mkt is not None:
    status_bits.append(
        f'<span class="pill pill-ok">市值來源 OK · {len(list_sheets(mkt))} 個工作表</span>'
    )

st.markdown(
    f'<div style="padding:10px 28px 0; display:flex; gap:8px; flex-wrap:wrap;">{" ".join(status_bits)}</div>',
    unsafe_allow_html=True,
)

if pri is None and mkt is None:
    st.markdown('<div style="padding: 20px 28px">', unsafe_allow_html=True)
    st.error("兩份試算表都讀不到。請檢查上方的錯誤訊息，或切換「資料來源」試試看。")
    if source_mode == "Google Sheet":
        st.info(
            "**Google Sheet 讀不到時最常見的原因**：\n\n"
            "1. 分享設定不是「知道連結的任何人可檢視」\n"
            "2. 試算表 ID 換了（請對照程式碼開頭的 `PRIMARY_SPREADSHEET_ID` / `MARKET_SPREADSHEET_ID`）\n"
            "3. Streamlit Cloud 暫時連不上 Google\n\n"
            "建議先用「上傳檔案」直接拖兩個 xlsx 上來看資料是否正常。"
        )
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# ─── Tabs ────────────────────────────────────────────────────────────────
tabs = st.tabs(["總覽", "每月收入", "2026 細帳", "市值來源", "即時行情", "資料健康"])

# ══════════════════════════════════════════════════════════════════════════
# TAB 1 — 總覽
# ══════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.markdown('<div class="j-page-title">🏠 總覽</div>', unsafe_allow_html=True)
    st.markdown('<div class="j-page-sub">所有帳戶資產彙整</div>', unsafe_allow_html=True)

    if mkt is None:
        st.warning(f"市值來源讀不到：{mkt_err}")
    else:
        ov, ov_name, ov_err = get_sheet_safely(mkt, "總覽")
        if ov_err:
            st.warning(ov_err)
        else:
            # KPI row
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("總資產", metric_ov(ov, "加總Total"))
            c2.metric("台股", metric_ov(ov, "台股total"))
            c3.metric("銀行", metric_ov(ov, "銀行total"))
            c4.metric("保險", metric_ov(ov, "保險total"))
            c5.metric("Uncle 待還", metric_ov(ov, "uncle待還"))

            # If every KPI is "—", show a diagnostic
            if all(
                metric_ov(ov, lbl) == "—"
                for lbl in ["加總Total", "台股total", "銀行total", "保險total", "uncle待還"]
            ):
                with st.expander("⚠️ KPI 全部顯示 — 點開看診斷"):
                    st.write("找到的工作表 A 欄前 20 列：")
                    st.dataframe(
                        fmt_df(ov.iloc[:20, :2].rename(columns={0: "A欄標籤", 1: "B欄值"})),
                        hide_index=True,
                        use_container_width=True,
                    )
                    st.caption(
                        "如果 A 欄標籤跟程式碼裡的 `加總Total / 台股total / 銀行total / 保險total / uncle待還` 不一致，"
                        "請改名其中之一就會對上。"
                    )

            st.markdown("<br>", unsafe_allow_html=True)

            left, right = st.columns([1, 1.5])
            with left:
                st.markdown(
                    '<div class="j-card"><div class="j-card-title">彙總摘要 <span class="hint">前 18 列</span></div>',
                    unsafe_allow_html=True,
                )
                summary = ov.iloc[:18, :5].copy()
                summary.columns = ["項目", "現值", "損益", "收入/配息", "合計"]
                st.dataframe(fmt_df(summary), use_container_width=True, hide_index=True, height=320)
                st.markdown("</div>", unsafe_allow_html=True)

            with right:
                st.markdown(
                    '<div class="j-card"><div class="j-card-title">投資明細 <span class="hint">F–R 欄</span></div>',
                    unsafe_allow_html=True,
                )
                inv = section_from_header(ov, 5, 18, 90)
                show = [
                    c
                    for c in [
                        "投資分類", "日期", "現值", "損益",
                        "台幣成本", "台幣市值", "累積配息", "台幣配息",
                        "配息率", "損益率",
                    ]
                    if c in inv.columns
                ]
                st.dataframe(
                    fmt_df(inv[show] if show else inv),
                    use_container_width=True,
                    hide_index=True,
                    height=320,
                )
                st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
# TAB 2 — 每月收入
# ══════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.markdown('<div class="j-page-title">💰 每月收入</div>', unsafe_allow_html=True)
    st.markdown('<div class="j-page-sub">配息・股利・利息月走勢</div>', unsafe_allow_html=True)

    if pri is None:
        st.warning(f"主帳本讀不到：{pri_err}")
    else:
        monthly, m_name, m_err = get_sheet_safely(pri, "每月收入")
        if m_err:
            st.warning(m_err)
        else:
            hdr = monthly.iloc[0]
            total_row = row_label(monthly, "合計")
            records = []
            if total_row is not None:
                for ci, hv in enumerate(hdr):
                    dt = pd.to_datetime(hv, errors="coerce")
                    amt = num(total_row.iloc[ci])
                    if pd.notna(dt) and amt is not None:
                        records.append({"月份": dt, "收入": amt})

            if records:
                trend = pd.DataFrame(records).set_index("月份")
                st.markdown(
                    '<div class="j-card"><div class="j-card-title">月收入走勢 '
                    f'<span class="hint">{len(records)} 個月</span></div>',
                    unsafe_allow_html=True,
                )
                st.bar_chart(trend, height=240, color=MINT)
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("找不到「合計」這列、或合計列裡沒有可解析的數字。請檢查工作表結構。")

            st.markdown(
                '<div class="j-card"><div class="j-card-title">明細資料 '
                '<span class="hint">前 22 列 × 46 欄</span></div>',
                unsafe_allow_html=True,
            )
            tbl = monthly.iloc[:22, :46].dropna(axis=1, how="all")
            tbl.columns = [str(c) for c in tbl.columns]
            st.dataframe(fmt_df(tbl), use_container_width=True, hide_index=True, height=340)
            st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
# TAB 3 — 2026 細帳
# ══════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.markdown('<div class="j-page-title">📒 2026 細帳</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="j-page-sub">全年進出帳記錄・帳戶移轉・配息・支出</div>',
        unsafe_allow_html=True,
    )

    if pri is None:
        st.warning(f"主帳本讀不到：{pri_err}")
    else:
        ledger, l_name, l_err = get_sheet_safely(pri, "2026細帳")
        if l_err:
            st.warning(l_err)
        else:
            months = ledger.iloc[0, 1:14]
            rows_data = []
            for ri in range(1, min(len(ledger), 160)):
                cat = ledger.iloc[ri, 0]
                if cat is None or pd.isna(cat):
                    continue
                for offset, mv in enumerate(months, start=1):
                    amt = num(ledger.iloc[ri, offset])
                    if amt is None or amt == 0:
                        continue
                    rows_data.append({"月份": str(mv), "項目": str(cat), "金額": amt})

            if rows_data:
                long = pd.DataFrame(rows_data)

                # summary metrics
                total_in = long[long["金額"] > 0]["金額"].sum()
                total_out = long[long["金額"] < 0]["金額"].sum()
                m1, m2, m3 = st.columns(3)
                m1.metric("收入合計", money(total_in))
                m2.metric("支出合計", money(abs(total_out)))
                m3.metric("淨收支", money(total_in + total_out))

                col_f, _ = st.columns([3, 9])
                with col_f:
                    cats = ["全部"] + sorted(long["項目"].unique().tolist())
                    sel = st.selectbox("篩選項目", cats, label_visibility="collapsed")
                view = long if sel == "全部" else long[long["項目"] == sel]

                st.markdown(
                    '<div class="j-card"><div class="j-card-title">篩選結果 '
                    f'<span class="hint">{len(view)} 筆</span></div>',
                    unsafe_allow_html=True,
                )
                st.dataframe(fmt_df(view), use_container_width=True, hide_index=True, height=320)
                st.markdown("</div>", unsafe_allow_html=True)

                with st.expander("查看原始寬表（前 140 列）"):
                    raw = ledger.iloc[:140, :16].copy()
                    raw.columns = [str(c) for c in raw.columns]
                    st.dataframe(fmt_df(raw), use_container_width=True, hide_index=True, height=340)
            else:
                st.info("這份工作表的格子全是空的或全為 0，沒有可顯示的明細。")

# ══════════════════════════════════════════════════════════════════════════
# TAB 4 — 市值來源
# ══════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.markdown('<div class="j-page-title">📊 市值來源</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="j-page-sub">各平台基金・台股・外幣市值</div>',
        unsafe_allow_html=True,
    )

    if mkt is None:
        st.warning(f"市值來源讀不到：{mkt_err}")
    else:
        all_sheets = list_sheets(mkt)
        default_list = [s for s in MARKET_SHEETS if s in all_sheets] or all_sheets
        sel_sheet = st.selectbox("選擇工作表", default_list)

        sheet_df, actual_name, err = get_sheet_safely(mkt, sel_sheet)
        if err:
            st.warning(err)
        else:
            if sel_sheet not in {"總覽", "台股", "「台股」的副本", "渣打-美股"}:
                r = sheet_df.iloc[1] if len(sheet_df) > 1 else pd.Series(dtype=object)

                def mval(col: int) -> str:
                    return money(r.iloc[col]) if len(r) > col else "—"

                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("投資成本", mval(9))
                mc2.metric("總市值", mval(10))
                mc3.metric("損益", mval(12))
                mc4.metric("月配息", mval(14))

            st.markdown(
                '<div class="j-card"><div class="j-card-title">工作表資料 '
                f'<span class="hint">{actual_name or sel_sheet}</span></div>',
                unsafe_allow_html=True,
            )
            tbl = cleaned(sheet_df)
            st.dataframe(fmt_df(tbl), use_container_width=True, hide_index=True, height=480)
            st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
# TAB 5 — 即時行情（股票 + 基金 + 匯率）
# ══════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown('<div class="j-page-title">📡 即時行情・市值計算機</div>', unsafe_allow_html=True)
    badge_yf = "" if _YF_OK else '<span class="pill pill-warn">缺 yfinance 套件</span>'
    badge_bs = "" if _BS4_OK else '<span class="pill pill-warn">缺 beautifulsoup4 套件</span>'
    st.markdown(
        '<div class="j-page-sub">'
        '填入「單位數」與「購買成本」，下方表格也可以新增列數加碼。'
        '系統會自動抓即時價＋匯率，把全部部位換算成台幣，並按 6 大平台彙總損益。 '
        f'{badge_yf} {badge_bs}'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Session state 初始化（首次進入分頁） ─────────────────────────
    if "tw_editable" not in st.session_state:
        st.session_state.tw_editable = initial_tw_editable()
    if "us_editable" not in st.session_state:
        st.session_state.us_editable = initial_us_editable()
    if "fund_editable" not in st.session_state:
        st.session_state.fund_editable = initial_fund_editable()

    # ── 預留頂部摘要與匯率位置（最後再填） ────────────────────────────
    summary_placeholder = st.empty()
    fx_placeholder = st.empty()

    # ── 重置按鈕 ────────────────────────────────────────────────────────
    rc1, rc2, _ = st.columns([1, 1, 8])
    with rc1:
        if st.button("↺ 重設台股表", help="清掉所有 單位數 / 成本 編輯，回到 92 檔預設清單"):
            st.session_state.tw_editable = initial_tw_editable()
            st.rerun()
    with rc2:
        if st.button("↺ 重設基金表", help="清掉基金平台 / 單位數 / 成本 編輯"):
            st.session_state.fund_editable = initial_fund_editable()
            st.rerun()

    # ══════════════════════════════════════════════════════════════════
    # 台股表
    # ══════════════════════════════════════════════════════════════════
    st.markdown(
        '<div class="j-card"><div class="j-card-title">📈 台股持倉 '
        '<span class="hint">可直接編輯「單位數」「購買成本(TWD)」；表格下緣有 + 新增列</span></div>',
        unsafe_allow_html=True,
    )
    tw_edited = st.data_editor(
        st.session_state.tw_editable,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="tw_data_editor",
        column_config={
            "名稱": st.column_config.TextColumn("名稱", width="medium"),
            "代號": st.column_config.TextColumn("代號", width="small", help="證交所 4 碼，例 2330"),
            "單位數": st.column_config.NumberColumn("單位數（股）", min_value=0, step=1000, format="%d"),
            "購買成本(TWD)": st.column_config.NumberColumn("購買成本(TWD)", min_value=0, step=1000, format="%d"),
        },
        height=360,
    )
    st.session_state.tw_editable = tw_edited
    st.markdown("</div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════
    # 美股表
    # ══════════════════════════════════════════════════════════════════
    st.markdown(
        '<div class="j-card"><div class="j-card-title">🇺🇸 美股持倉 '
        '<span class="hint">購買成本以 USD 計，下方會自動換算成 TWD</span></div>',
        unsafe_allow_html=True,
    )
    us_edited = st.data_editor(
        st.session_state.us_editable,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="us_data_editor",
        column_config={
            "名稱": st.column_config.TextColumn("名稱", width="medium"),
            "代號": st.column_config.TextColumn("代號（Ticker）", width="small"),
            "單位數": st.column_config.NumberColumn("單位數（股）", min_value=0, step=1, format="%d"),
            "購買成本(USD)": st.column_config.NumberColumn("購買成本(USD)", min_value=0, step=100.0, format="%.2f"),
        },
    )
    st.session_state.us_editable = us_edited
    st.markdown("</div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════
    # 基金表（含平台選擇）
    # ══════════════════════════════════════════════════════════════════
    st.markdown(
        '<div class="j-card"><div class="j-card-title">💰 基金持倉 '
        '<span class="hint">「平台」可下拉選擇（基富通-台幣 / 基富通-外幣 / 渣打 / 台新）'
        '；成本以基金計價幣別為單位</span></div>',
        unsafe_allow_html=True,
    )
    fund_edited = st.data_editor(
        st.session_state.fund_editable,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="fund_data_editor",
        column_config={
            "基金名稱": st.column_config.TextColumn("基金名稱", width="large"),
            "代號": st.column_config.TextColumn("MoneyDJ 代號", width="small"),
            "URL Pattern": st.column_config.SelectboxColumn(
                "URL", help="yp010000=國內基金 / yp010001=境外基金",
                options=["yp010000", "yp010001"], width="small",
            ),
            "計價幣別": st.column_config.SelectboxColumn(
                "幣別", options=["TWD", "USD", "CNY", "JPY", "ZAR", "EUR", "HKD"], width="small",
            ),
            "平台": st.column_config.SelectboxColumn(
                "平台", options=PLATFORM_OPTIONS, required=True, width="small",
            ),
            "單位數": st.column_config.NumberColumn("單位數", min_value=0, step=100.0, format="%.4f"),
            "購買成本(原幣)": st.column_config.NumberColumn("購買成本(原幣)", min_value=0, step=100.0, format="%.2f"),
        },
        height=420,
    )
    st.session_state.fund_editable = fund_edited
    st.markdown("</div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════
    # 抓資料：價格 + FX
    # ══════════════════════════════════════════════════════════════════
    # 從 session_state 收集所有需要的代碼
    tw_codes = tuple(sorted({
        str(c).strip() for c in tw_edited["代號"].dropna().tolist() if str(c).strip()
    }))
    us_codes = tuple(sorted({
        str(c).strip().upper() for c in us_edited["代號"].dropna().tolist() if str(c).strip()
    }))

    with st.spinner("抓取即時報價與匯率中…"):
        try:
            tw_price_map = fetch_tw_prices_by_codes(tw_codes)
        except Exception as e:
            tw_price_map = {}
            st.warning(f"台股報價抓取失敗：{type(e).__name__}: {e}")
        try:
            us_price_map = fetch_us_prices_by_codes(us_codes)
        except Exception as e:
            us_price_map = {}
            st.warning(f"美股報價抓取失敗：{type(e).__name__}: {e}")
        try:
            fund_master_df = fetch_fund_navs_master()
            fund_nav_map = {row["代號"]: {"nav": row["最新淨值"], "date": row["資料日期"]}
                            for _, row in fund_master_df.iterrows()}
        except Exception as e:
            fund_nav_map = {}
            st.warning(f"基金淨值抓取失敗：{type(e).__name__}: {e}")
        # 收集所有出現過的幣別
        ccy_set = {"USD", "CNY", "JPY", "ZAR"}
        for c in fund_edited.get("計價幣別", []):
            cs = str(c).strip().upper()
            if cs and cs != "TWD":
                ccy_set.add(cs)
        try:
            fx_df = fetch_fx_rates(sorted(ccy_set))
        except Exception as e:
            fx_df = pd.DataFrame()
            st.warning(f"匯率抓取失敗：{type(e).__name__}: {e}")
    fx_dict = fx_df_to_dict(fx_df)

    # ══════════════════════════════════════════════════════════════════
    # 加上即時價與市值欄位（呈現用）
    # ══════════════════════════════════════════════════════════════════

    def _enrich_tw(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["即時價"] = out["代號"].map(lambda c: tw_price_map.get(str(c).strip(), {}).get("price"))
        out["資料日期"] = out["代號"].map(lambda c: tw_price_map.get(str(c).strip(), {}).get("date", "") or "")
        out["市值(TWD)"] = out.apply(
            lambda r: (r["單位數"] * r["即時價"]) if pd.notna(r["即時價"]) and pd.notna(r["單位數"]) else None,
            axis=1,
        )
        out["損益(TWD)"] = out.apply(
            lambda r: (r["市值(TWD)"] - r["購買成本(TWD)"])
            if pd.notna(r["市值(TWD)"]) and pd.notna(r["購買成本(TWD)"]) and r["購買成本(TWD)"] else None,
            axis=1,
        )
        return out

    def _enrich_us(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        usd_rate = fx_dict.get("USD")
        out["即時價(USD)"] = out["代號"].map(lambda c: us_price_map.get(str(c).strip().upper(), {}).get("price"))
        out["資料日期"] = out["代號"].map(lambda c: us_price_map.get(str(c).strip().upper(), {}).get("date", "") or "")
        out["市值(USD)"] = out.apply(
            lambda r: (r["單位數"] * r["即時價(USD)"]) if pd.notna(r["即時價(USD)"]) and pd.notna(r["單位數"]) else None,
            axis=1,
        )
        out["市值(TWD)"] = out["市值(USD)"].apply(lambda v: v * usd_rate if (v is not None and usd_rate) else None)
        cost_twd = out["購買成本(USD)"].apply(lambda v: v * usd_rate if (v and usd_rate) else None)
        out["損益(TWD)"] = [
            (mv - c) if (mv is not None and c is not None) else None
            for mv, c in zip(out["市值(TWD)"], cost_twd)
        ]
        return out

    def _enrich_fund(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["最新淨值"] = out["代號"].map(lambda c: fund_nav_map.get(str(c).strip(), {}).get("nav"))
        out["資料日期"] = out["代號"].map(lambda c: fund_nav_map.get(str(c).strip(), {}).get("date", "") or "")
        out["市值(原幣)"] = out.apply(
            lambda r: (r["單位數"] * r["最新淨值"]) if pd.notna(r["最新淨值"]) and pd.notna(r["單位數"]) else None,
            axis=1,
        )
        out["市值(TWD)"] = out.apply(
            lambda r: to_twd(r["市值(原幣)"], r["計價幣別"], fx_dict),
            axis=1,
        )
        cost_twd = out.apply(lambda r: to_twd(r["購買成本(原幣)"], r["計價幣別"], fx_dict), axis=1)
        out["損益(TWD)"] = [
            (mv - c) if (mv is not None and c is not None and c) else None
            for mv, c in zip(out["市值(TWD)"], cost_twd)
        ]
        # 攜帶換算後成本以供彙總
        out["__cost_twd"] = cost_twd
        return out

    tw_full = _enrich_tw(tw_edited)
    us_full = _enrich_us(us_edited)
    fund_full = _enrich_fund(fund_edited)

    # ══════════════════════════════════════════════════════════════════
    # 平台彙總
    # ══════════════════════════════════════════════════════════════════
    def _sum(s):
        return float(pd.to_numeric(s, errors="coerce").sum(skipna=True))

    usd_rate = fx_dict.get("USD")

    bucket_rows = []

    # 台股
    bucket_rows.append({
        "平台": "台股",
        "市值(TWD)": _sum(tw_full["市值(TWD)"]),
        "成本(TWD)": _sum(tw_full["購買成本(TWD)"]),
    })
    # 美股
    us_cost_twd = (
        pd.to_numeric(us_full["購買成本(USD)"], errors="coerce").fillna(0) * (usd_rate or 0)
    )
    bucket_rows.append({
        "平台": "美股",
        "市值(TWD)": _sum(us_full["市值(TWD)"]),
        "成本(TWD)": float(us_cost_twd.sum()),
    })
    # 基金 4 桶
    for plat in PLATFORM_OPTIONS:
        sub = fund_full[fund_full["平台"] == plat]
        bucket_rows.append({
            "平台": (
                "基富通台幣" if plat == "基富通-台幣"
                else "基富通外幣" if plat == "基富通-外幣"
                else "渣打基金" if plat == "渣打"
                else "台新基金"
            ),
            "市值(TWD)": _sum(sub["市值(TWD)"]) if not sub.empty else 0.0,
            "成本(TWD)": _sum(sub["__cost_twd"]) if not sub.empty else 0.0,
        })

    bucket_df = pd.DataFrame(bucket_rows)
    bucket_df["損益(TWD)"] = bucket_df["市值(TWD)"] - bucket_df["成本(TWD)"]
    bucket_df["損益%"] = bucket_df.apply(
        lambda r: (r["損益(TWD)"] / r["成本(TWD)"] * 100) if r["成本(TWD)"] else None,
        axis=1,
    )

    total_mv = float(bucket_df["市值(TWD)"].sum())
    total_cost = float(bucket_df["成本(TWD)"].sum())
    total_pl = total_mv - total_cost
    total_pct = (total_pl / total_cost * 100) if total_cost else None

    # ══════════════════════════════════════════════════════════════════
    # 填入頂部摘要 + 匯率
    # ══════════════════════════════════════════════════════════════════
    with summary_placeholder.container():
        st.markdown(
            '<div class="j-card"><div class="j-card-title">📊 投資總覽（換算 TWD）</div>',
            unsafe_allow_html=True,
        )
        # 大 KPI
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("總市值(TWD)", f"{int(round(total_mv)):,}")
        k2.metric("總成本(TWD)", f"{int(round(total_cost)):,}")
        k3.metric("總損益(TWD)", f"{int(round(total_pl)):,}",
                  delta=f"{total_pct:+.2f}%" if total_pct is not None else None)
        k4.metric("最後更新", datetime.now().strftime("%Y-%m-%d %H:%M"))

        # 平台明細
        disp = bucket_df.copy()
        disp["市值(TWD)"] = disp["市值(TWD)"].apply(lambda v: int(round(v)) if pd.notna(v) else 0)
        disp["成本(TWD)"] = disp["成本(TWD)"].apply(lambda v: int(round(v)) if pd.notna(v) else 0)
        disp["損益(TWD)"] = disp["損益(TWD)"].apply(lambda v: int(round(v)) if pd.notna(v) else 0)
        disp["損益%"] = disp["損益%"].apply(lambda v: f"{v:+.2f}%" if pd.notna(v) else "")
        st.dataframe(fmt_df(disp), use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with fx_placeholder.container():
        st.markdown(
            '<div class="j-card"><div class="j-card-title">💱 即時匯率（→ TWD）'
            '<span class="hint">下方所有市值都用這張表換算</span></div>',
            unsafe_allow_html=True,
        )
        if not fx_df.empty:
            disp_fx = fx_df.copy()
            if "匯率" in disp_fx.columns:
                disp_fx["匯率"] = disp_fx["匯率"].apply(lambda v: f"{v:,.4f}" if pd.notna(v) else "")
            st.dataframe(fmt_df(disp_fx), use_container_width=True, hide_index=True)
        else:
            st.info("目前沒有匯率資料。")
        st.markdown("</div>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════
    # 詳細市值表（展開檢視）
    # ══════════════════════════════════════════════════════════════════
    with st.expander("🔍 看詳細市值表（每筆部位）"):
        st.markdown("**台股**")
        tw_cols = ["名稱", "代號", "單位數", "即時價", "資料日期",
                   "市值(TWD)", "購買成本(TWD)", "損益(TWD)"]
        st.dataframe(
            fmt_df(tw_full[[c for c in tw_cols if c in tw_full.columns]]),
            use_container_width=True, hide_index=True,
        )

        st.markdown("**美股**")
        us_cols = ["名稱", "代號", "單位數", "即時價(USD)", "資料日期",
                   "市值(USD)", "市值(TWD)", "購買成本(USD)", "損益(TWD)"]
        st.dataframe(
            fmt_df(us_full[[c for c in us_cols if c in us_full.columns]]),
            use_container_width=True, hide_index=True,
        )

        st.markdown("**基金**")
        fund_cols = ["基金名稱", "代號", "平台", "計價幣別", "單位數", "最新淨值",
                     "資料日期", "市值(原幣)", "市值(TWD)", "購買成本(原幣)", "損益(TWD)"]
        st.dataframe(
            fmt_df(fund_full[[c for c in fund_cols if c in fund_full.columns]]),
            use_container_width=True, hide_index=True,
        )


# ══════════════════════════════════════════════════════════════════════════
# TAB 6 — 資料健康
# ══════════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.markdown('<div class="j-page-title">🔍 資料健康</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="j-page-sub">工作表結構・公式統計・錯誤偵測</div>',
        unsafe_allow_html=True,
    )

    # Live health: count NaN / errors in each loaded workbook
    def workbook_health(xlsx: bytes, name: str) -> pd.DataFrame:
        rows = []
        for sh in list_sheets(xlsx):
            try:
                df = read_sheet(xlsx, sh)
                nonempty = int(df.notna().sum().sum())
                errors = int(
                    df.astype(str)
                    .apply(lambda s: s.str.contains(r"#REF!|#N/A|#DIV/0!|#VALUE!|#NAME\?", na=False))
                    .sum()
                    .sum()
                )
                rows.append(
                    {
                        "workbook": name,
                        "sheet": sh,
                        "rows": int(df.shape[0]),
                        "cols": int(df.shape[1]),
                        "nonempty_cells": nonempty,
                        "error_cells": errors,
                    }
                )
            except Exception as e:
                rows.append(
                    {
                        "workbook": name,
                        "sheet": sh,
                        "rows": 0,
                        "cols": 0,
                        "nonempty_cells": 0,
                        "error_cells": -1,
                    }
                )
        return pd.DataFrame(rows)

    health_frames = []
    if pri is not None:
        health_frames.append(workbook_health(pri, "主帳本"))
    if mkt is not None:
        health_frames.append(workbook_health(mkt, "市值來源"))

    if health_frames:
        all_health = pd.concat(health_frames, ignore_index=True)
        err_total = int(all_health["error_cells"].clip(lower=0).sum())
        sh_total = len(all_health)
        h1, h2, h3 = st.columns(3)
        h1.metric("工作表總數", f"{sh_total:,}")
        h2.metric("非空儲存格", f"{int(all_health['nonempty_cells'].sum()):,}")
        h3.metric("錯誤儲存格", f"{err_total:,}")

        st.markdown(
            '<div class="j-card"><div class="j-card-title">工作表健康總覽</div>',
            unsafe_allow_html=True,
        )
        st.dataframe(
            fmt_df(all_health.sort_values(["workbook", "error_cells"], ascending=[True, False])),
            use_container_width=True,
            hide_index=True,
            height=420,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    # Also support the cached JSON summary from the analysis script
    if SUMMARY_JSON.exists():
        try:
            summaries = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
            for book in summaries:
                fname = Path(book["file"]).name
                st.markdown(
                    f'<div class="j-card"><div class="j-card-title">{fname} '
                    '<span class="hint">workbook_structure_summary.json</span></div>',
                    unsafe_allow_html=True,
                )
                bm1, bm2, bm3 = st.columns(3)
                bm1.metric("檔案大小 MB", book.get("size_mb", "—"))
                bm2.metric("工作表數", book.get("sheet_count", "—"))
                bm3.metric("公式種類", len(book.get("workbook_functions", {})))

                if "sheets" in book:
                    heavy = (
                        pd.DataFrame(book["sheets"])
                        .sort_values("formulas", ascending=False)[
                            ["sheet", "class", "rows", "cols", "nonempty", "formulas", "literal_errors"]
                        ]
                        .head(12)
                    )
                    st.dataframe(fmt_df(heavy), use_container_width=True, hide_index=True)

                if book.get("workbook_functions"):
                    funcs = pd.DataFrame(
                        [{"公式": k, "次數": v} for k, v in book["workbook_functions"].items()]
                    )
                    st.dataframe(fmt_df(funcs), use_container_width=True, hide_index=True)
                st.markdown("</div>", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"讀取 workbook_structure_summary.json 失敗：{e}")
    else:
        st.caption(
            "💡 若要看完整公式統計，可在本機跑分析腳本產出 `outputs/workbook_structure_summary.json`，"
            "此頁會自動顯示。"
        )
