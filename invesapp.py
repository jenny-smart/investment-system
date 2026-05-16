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


# =============================================================================
# CONFIG
# =============================================================================
APP_VERSION = "2026-05-16-v6-realsheet"

PRIMARY_SPREADSHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"
MARKET_SPREADSHEET_ID  = "17HPytZKOPR_9Od_wor-xEx9kpccJlPS2v6B0Dz6MRYc"

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
PRIMARY_LOCAL   = PROJECT_DIR / "inputs" / "investment-system-source.xlsx"
MARKET_LOCAL    = PROJECT_DIR / "inputs" / "market-value-source.xlsx"
SUMMARY_JSON    = PROJECT_DIR / "outputs" / "workbook_structure_summary.json"
LOCAL_RECORDS_DIR = PROJECT_DIR / "data"

# 你 Sheet 裡的工作表名稱
MARKET_SHEETS = [
    "總覽", "台股", "「台股」的副本", "渣打-美股",
    "基富通-台", "基富通-人民幣", "基富通-日幣",
    "渣打-美金", "渣打-南非", "台新-美金", "台新-南非",
]

# 平台 → 工作表對應
DETAIL_GROUPS = {
    "台股":   ["台股", "「台股」的副本"],
    "基富通": ["基富通-台", "基富通-人民幣", "基富通-日幣"],
    "渣打美股": ["渣打-美股"],
    "渣打基金": ["渣打-美金", "渣打-南非"],
    "台新基金": ["台新-美金", "台新-南非"],
    "其他投資": [],
}

# 你 Sheet 欄位（從截圖確認）：F=投資分類 G=日期 H=現值 I=損益 J=台幣成本 K=台幣市值 L=累積配息 M=台幣配息 N=配息率
# 欄索引（0-based，F=5, G=6, H=7, I=8, J=9, K=10, L=11, M=12, N=13）
COL = {
    "名稱":   5,   # F
    "日期":   6,   # G
    "現值":   7,   # H
    "損益":   8,   # I
    "台幣成本": 9,  # J
    "台幣市值": 10, # K
    "累積配息": 11, # L
    "台幣配息": 12, # M
    "配息率":  13,  # N
}

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

STOCK_CONFIG = [
    {"ticker": "PYPL", "name": "PayPal", "currency": "USD"},
    {"ticker": "XYZ",  "name": "XYZ",    "currency": "USD"},
]

FX_PAIRS = {"USD": "USDTWD=X", "CNY": "CNYTWD=X", "JPY": "JPYTWD=X", "ZAR": "ZARTWD=X"}

# 總覽頁用來查各分類的關鍵字
OVERVIEW_ALIASES = {
    "總資產":     ["加總Total", "加總total", "加總TOTAL", "總資產"],
    "台股":       ["台股total", "台股Total", "台股"],
    "銀行":       ["銀行total", "銀行Total", "銀行"],
    "保險":       ["保險total", "保險Total", "保險"],
    "UNCLE 待還": ["uncle待還", "Uncle待還", "UNCLE待還", "uncle待还"],
    "基富通":     ["基富通-台", "基富通-人", "基富通-日"],
    "渣打美股":   ["渣打-pypl", "渣打-sq", "渣打美股"],
    "渣打基金":   ["渣打-大華", "渣打-美金", "渣打-南非", "渣打基金"],
    "台新基金":   ["台新-南非", "台新-美金", "台新基金"],
    "其他投資":   ["懷思投資", "其他投資"],
}


# =============================================================================
# PAGE + CSS
# =============================================================================
st.set_page_config(
    page_title="Jenny All｜投資系統",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
[data-testid="stSidebar"],[data-testid="collapsedControl"],
section[data-testid="stSidebarNav"],button[kind="header"]{display:none!important}
html,body,[class*="css"]{
  font-family:"PingFang TC","Noto Sans TC",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif!important}
.stApp{background:#f7faf9!important;color:#0f2b20!important}
.block-container{padding:0!important;max-width:100%!important}
.j-topbar{background:#fff;border-bottom:1px solid #e5eae8;padding:10px 32px;
  display:flex;align-items:center;gap:24px;box-shadow:0 1px 4px rgba(0,0,0,.05);
  position:sticky;top:0;z-index:999;min-height:72px}
.j-brand-pill{background:#fff;border:1px solid #dfe9e5;border-radius:10px;padding:8px 18px;
  box-shadow:0 1px 5px rgba(0,0,0,.04);display:flex;align-items:center;gap:9px;
  color:#0f2b20;font-size:15px;font-weight:700;min-width:136px;justify-content:center}
.j-logo{width:28px;height:28px;border-radius:6px;display:inline-flex;
  align-items:center;justify-content:center;font-weight:900;color:#fff}
.logo-g{background:#ff7a00}.logo-sc{background:linear-gradient(135deg,#0968b1,#30b36b)}
.logo-ts{background:#d70819}.logo-sheet{background:#10b981}
.stTabs [data-baseweb="tab-list"]{background:#fff;border-bottom:2px solid #e5eae8;
  padding:0 28px;gap:0;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.stTabs [data-baseweb="tab"]{color:#6b8a7a!important;font-size:13.5px!important;
  font-weight:500!important;padding:13px 20px!important;
  border-bottom:3px solid transparent!important;background:transparent!important}
.stTabs [aria-selected="true"]{color:#047857!important;border-bottom-color:#10b981!important;font-weight:700!important}
.stTabs [data-baseweb="tab-panel"]{background:#f7faf9;padding:28px 32px}
[data-testid="stMetric"]{background:#fff!important;border:1px solid #e5eae8!important;
  border-radius:12px!important;padding:18px 22px!important;
  box-shadow:0 1px 4px rgba(0,0,0,.04)!important;min-height:118px}
[data-testid="stMetricLabel"] p{font-size:12px!important;font-weight:700!important;color:#7c968c!important}
[data-testid="stMetricValue"]{font-size:24px!important;font-weight:800!important;color:#0f2b20!important}
[data-testid="stDataFrame"]{border:1px solid #e5eae8!important;border-radius:12px!important;
  overflow:hidden!important;box-shadow:0 1px 4px rgba(0,0,0,.04)!important;background:#fff!important}
.stButton>button{background:#10b981!important;color:#fff!important;border:none!important;
  border-radius:8px!important;font-weight:600!important;font-size:13px!important;
  padding:7px 18px!important;box-shadow:0 2px 6px rgba(16,185,129,.25)!important}
.stButton>button:hover{background:#047857!important}
.j-card{background:#fff;border:1px solid #e5eae8;border-radius:14px;padding:22px 24px;
  margin-bottom:18px;box-shadow:0 1px 4px rgba(0,0,0,.04)}
.j-card-title{font-size:15px;font-weight:800;color:#10b981;margin-bottom:14px;
  padding-bottom:10px;border-bottom:1px solid #f0f5f3}
.j-page-title{font-size:24px;font-weight:800;color:#0f2b20;margin-bottom:3px}
.j-page-sub{font-size:13px;color:#8fa89e;margin-bottom:22px}
.j-group-header{background:#1e3a2f;color:#fff;font-weight:800;font-size:13px;
  padding:6px 12px;border-radius:6px;margin:4px 0}
</style>
""", unsafe_allow_html=True)


# =============================================================================
# HELPERS — 數值 / 格式
# =============================================================================
def numeric(v: Any) -> float | None:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        if isinstance(v, str):
            s = v.replace(",", "").replace("$", "").replace("NT", "").replace("%", "").strip()
            if s in {"", "-", "—", "nan", "None", "載入中…", "#N/A", "#DIV/0!"}:
                return None
            return float(s)
        return float(v)
    except Exception:
        return None

def money(v: Any) -> str:
    n = numeric(v)
    return "-" if n is None else f"{n:,.0f}"

def signed_money(v: Any) -> str:
    n = numeric(v)
    return "-" if n is None else f"{n:+,.0f}"

def ratio_str(v: Any) -> str:
    n = numeric(v)
    if n is None: return "-"
    return f"{n:.1f}%" if abs(n) > 1 else f"{n:.2%}"

def signed_ratio_str(v: Any) -> str:
    n = numeric(v)
    if n is None: return "-"
    return f"{n:+.1f}%" if abs(n) > 1 else f"{n:+.2%}"

def fmt_df(df: pd.DataFrame) -> pd.DataFrame:
    return df.fillna("").astype(str).replace({"nan":"","None":"","NaT":"","NaN":""})

def display_df(df: pd.DataFrame, msg: str = "尚無資料", height: int = 340) -> None:
    if df is None or df.empty:
        st.info(msg)
    else:
        st.dataframe(df, use_container_width=True, hide_index=True, height=height)


# =============================================================================
# HELPERS — Google Sheet 載入
# =============================================================================
@st.cache_data(ttl=600, show_spinner=False)
def download_xlsx(sid: str) -> bytes:
    url = f"https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    if b"<!DOCTYPE" in r.content[:200]:
        raise ValueError("Google Sheet 回傳 HTML（請確認試算表已公開）")
    return r.content

@st.cache_data(ttl=600, show_spinner=False)
def load_local_xlsx(path: str) -> bytes:
    return Path(path).read_bytes()

@st.cache_data(ttl=600, show_spinner=False)
def read_sheet(xlsx_bytes: bytes, sheet_name: str) -> pd.DataFrame:
    return pd.read_excel(BytesIO(xlsx_bytes), sheet_name=sheet_name, header=None, engine="openpyxl")

def workbook_bytes(mode: str, which: str) -> bytes:
    if which == "primary":
        return load_local_xlsx(str(PRIMARY_LOCAL)) if mode == "本機快取" else download_xlsx(PRIMARY_SPREADSHEET_ID)
    return load_local_xlsx(str(MARKET_LOCAL)) if mode == "本機快取" else download_xlsx(MARKET_SPREADSHEET_ID)


# =============================================================================
# 核心解析：你的 Sheet 結構
# 藍色粗體行 = 平台群組標題（F欄有值，其他欄有數字）
# 子項目行   = 標的名稱（F欄）+ 各欄數值
# =============================================================================
def is_group_header(row: pd.Series) -> bool:
    """判斷是否為群組標題列（藍色粗體）：名稱欄有值且台幣市值欄也有數值"""
    name = str(row.iloc[COL["名稱"]] if len(row) > COL["名稱"] else "").strip()
    if not name or name in {"nan", "None", "投資分類"}:
        return False
    # 群組標題的日期欄通常是文字（「日期」）或空白，而子項目有日期
    date_val = str(row.iloc[COL["日期"]] if len(row) > COL["日期"] else "").strip()
    # 如果日期欄是「日期」這個文字，就是標題行的header
    if date_val == "日期":
        return False
    # 群組標題：名稱不含 / 且台幣市值有數值
    mkt = numeric(row.iloc[COL["台幣市值"]] if len(row) > COL["台幣市值"] else None)
    cost = numeric(row.iloc[COL["台幣成本"]] if len(row) > COL["台幣成本"] else None)
    # 子項目有日期，群組標題沒有（或日期是 NaN）
    has_date = pd.to_datetime(date_val, errors="coerce") is not pd.NaT
    try:
        has_date = not pd.isna(pd.to_datetime(date_val, errors="coerce"))
    except Exception:
        has_date = False
    return not has_date and (mkt is not None or cost is not None)

def parse_market_sheet(raw: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """
    解析單一工作表，回傳 (群組摘要列表, 明細列表)
    群組: {名稱, 現值, 損益, 台幣成本, 台幣市值, 累積配息, 台幣配息}
    明細: {群組, 名稱, 日期, 現值, 損益, 台幣成本, 台幣市值, 累積配息, 台幣配息, 配息率}
    """
    groups, details = [], []
    current_group = ""

    for _, row in raw.iterrows():
        if len(row) <= COL["名稱"]:
            continue
        name = str(row.iloc[COL["名稱"]]).strip()
        if not name or name in {"nan", "None", "投資分類", ""}:
            continue
        # 跳過 header 行
        date_val = str(row.iloc[COL["日期"]] if len(row) > COL["日期"] else "").strip()
        if date_val == "日期" or name == "投資分類":
            continue

        def get(col_key):
            idx = COL.get(col_key, -1)
            return numeric(row.iloc[idx]) if idx >= 0 and len(row) > idx else None

        # 判斷是群組標題還是子項目
        try:
            has_date = not pd.isna(pd.to_datetime(date_val, errors="coerce"))
        except Exception:
            has_date = False

        if not has_date:
            # 群組標題列
            current_group = name
            g = {
                "名稱": name,
                "現值":   get("現值"),
                "損益":   get("損益"),
                "台幣成本": get("台幣成本"),
                "台幣市值": get("台幣市值"),
                "累積配息": get("累積配息"),
                "台幣配息": get("台幣配息"),
            }
            if any(v is not None for v in g.values() if isinstance(v, float) or v is None):
                groups.append(g)
        else:
            # 子項目（個股/基金）
            d = {
                "群組":   current_group,
                "名稱":   name,
                "日期":   date_val,
                "現值":   get("現值"),
                "損益":   get("損益"),
                "台幣成本": get("台幣成本"),
                "台幣市值": get("台幣市值"),
                "累積配息": get("累積配息"),
                "台幣配息": get("台幣配息"),
                "配息率": get("配息率"),
            }
            if any(d[k] is not None for k in ["台幣市值", "台幣成本", "損益", "台幣配息"]):
                details.append(d)

    return groups, details


def parse_all_platforms(market_bytes: bytes) -> tuple[dict[str, dict], pd.DataFrame]:
    """
    讀取所有平台工作表，彙整成：
    platform_summary: {平台名稱: {台幣市值, 台幣成本, 損益, 台幣配息}}
    all_details: DataFrame 所有明細
    """
    platform_summary: dict[str, dict] = {}
    all_details: list[dict] = []

    for platform, sheets in DETAIL_GROUPS.items():
        totals = {"台幣市值": 0.0, "台幣成本": 0.0, "損益": 0.0, "台幣配息": 0.0}
        found = False

        for sname in sheets:
            try:
                raw = read_sheet(market_bytes, sname)
                groups, details = parse_market_sheet(raw)

                for g in groups:
                    for k in totals:
                        if g.get(k) is not None:
                            totals[k] += float(g[k])
                            found = True

                for d in details:
                    d["平台"] = platform
                    d["來源表"] = sname
                    all_details.append(d)
            except Exception:
                continue

        if found:
            cost = totals["台幣成本"] or None
            val  = totals["台幣市值"] or None
            profit = totals["損益"] or None
            if profit is None and val and cost:
                profit = val - cost
            platform_summary[platform] = {
                "台幣市值": val,
                "台幣成本": cost,
                "損益":    profit,
                "損益率":  profit / cost if profit and cost else None,
                "台幣配息": totals["台幣配息"] or None,
            }
        else:
            platform_summary[platform] = {
                "台幣市值": None, "台幣成本": None,
                "損益": None, "損益率": None, "台幣配息": None,
            }

    detail_df = pd.DataFrame(all_details) if all_details else pd.DataFrame()
    return platform_summary, detail_df


def value_from_overview(overview: pd.DataFrame, keywords: list[str]) -> float:
    """從總覽工作表 A欄找關鍵字、B欄取值（A=項目名稱, B=金額）"""
    if overview.empty:
        return 0.0
    col_a = overview.iloc[:, 0].astype(str).str.replace(" ", "", regex=False).str.lower()
    for kw in keywords:
        kw_norm = kw.replace(" ", "").lower()
        matches = overview.loc[col_a.str.contains(kw_norm, na=False, regex=False)]
        for _, row in matches.iterrows():
            if len(row) > 1:
                val = numeric(row.iloc[1])
                if val is not None and val != 0:
                    return val
    return 0.0


# =============================================================================
# LIVE PRICE
# =============================================================================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_fund_nav(code: str, pattern: str) -> tuple[str, str]:
    if not HAS_BS4:
        return "-", "缺少 beautifulsoup4"
    url = f"https://www.moneydj.com/funddj/ya/{pattern}.djhtm?a={code}"
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
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
    if not HAS_YF:
        return "-", "缺少 yfinance"
    try:
        t = yf.Ticker(ticker)
        price = getattr(t.fast_info, "last_price", None)
        return (f"{price:,.2f}", "ok") if price else ("-", "無資料")
    except Exception as e:
        return "-", str(e)[:40]

@st.cache_data(ttl=300, show_spinner=False)
def fetch_fx(pair: str) -> tuple[str, str]:
    if not HAS_YF:
        return "-", "缺少 yfinance"
    try:
        t = yf.Ticker(pair)
        rate = getattr(t.fast_info, "last_price", None)
        return (f"{rate:,.4f}", "ok") if rate else ("-", "無資料")
    except Exception as e:
        return "-", str(e)[:40]


# =============================================================================
# LOCAL RECORDS
# =============================================================================
def local_records_path(platform: str) -> Path:
    safe = platform.replace(" ", "_").replace("/", "_")
    return LOCAL_RECORDS_DIR / f"{safe}_investment_records.csv"

def load_local_records(platform: str) -> pd.DataFrame:
    p = local_records_path(platform)
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()

def save_local_records(platform: str, df: pd.DataFrame) -> None:
    LOCAL_RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(local_records_path(platform), index=False, encoding="utf-8-sig")

def load_health_summary() -> list[dict]:
    if not SUMMARY_JSON.exists():
        return []
    return json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))


# =============================================================================
# APP HEADER
# =============================================================================
st.markdown("""
<div class="j-topbar">
  <div class="j-brand-pill"><span class="j-logo logo-sheet">●</span> 投資總覽系統</div>
  <div class="j-brand-pill"><span class="j-logo logo-g">G</span>基富通</div>
  <div class="j-brand-pill"><span class="j-logo logo-sc">S</span>渣打</div>
  <div class="j-brand-pill"><span class="j-logo logo-ts">TS</span>台新</div>
</div>
""", unsafe_allow_html=True)

sc1, sc2, _ = st.columns([2, 1, 9])
with sc1:
    source_mode = st.radio("來源", ["Google Sheet", "本機快取"], horizontal=True, label_visibility="collapsed")
with sc2:
    if st.button("🔄 重新整理"):
        st.cache_data.clear()
        st.rerun()

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

# 解析所有平台資料（快取在 session）
with st.spinner("解析投資資料…"):
    platform_summary, all_detail_df = parse_all_platforms(market_bytes)

tabs = st.tabs(["◈ 總覽", "📌 平台明細", "◷ 每月收入", "📒 2026 細帳", "📊 市值來源", "💹 即時市值", "🔍 資料健康"])


# =============================================================================
# TAB 1 — 總覽
# =============================================================================
with tabs[0]:
    st.markdown(f'<div style="text-align:right;color:#7b9188;font-size:12px;margin-bottom:8px">版本：{APP_VERSION}</div>', unsafe_allow_html=True)
    st.markdown('<div class="j-page-title">總覽</div><div class="j-page-sub">所有帳戶資產彙整</div>', unsafe_allow_html=True)

    try:
        overview = read_sheet(market_bytes, "總覽")
    except Exception:
        overview = pd.DataFrame()

    try:
        invest_items = ["台股", "基富通", "渣打美股", "渣打基金", "台新基金", "其他投資"]
        invest_total_val    = sum(platform_summary.get(p, {}).get("台幣市值") or 0 for p in invest_items)
        invest_total_profit = sum(platform_summary.get(p, {}).get("損益") or 0 for p in invest_items)
        invest_total_div    = sum(platform_summary.get(p, {}).get("台幣配息") or 0 for p in invest_items)
        bank_val    = value_from_overview(overview, ["銀行total", "銀行Total", "銀行"])
        insure_val  = value_from_overview(overview, ["保險total", "保險Total", "保險"])
        uncle_val   = value_from_overview(overview, ["uncle待還", "Uncle待還", "UNCLE待還"])
        total_assets = invest_total_val + bank_val + insure_val
        net_assets   = total_assets - uncle_val

        r1c1, r1c2, r1c3, r1c4, r1c5 = st.columns(5)
        r1c1.metric("🏦 總資產",    money(total_assets))
        r1c2.metric("💰 淨資產",    money(net_assets))
        r1c3.metric("🏛 銀行現金",  money(bank_val))
        r1c4.metric("🛡 保險",      money(insure_val))
        r1c5.metric("👤 UNCLE 待還",money(uncle_val))

        st.markdown("<br>", unsafe_allow_html=True)

        r2cols = st.columns(5)
        icons = {"台股":"📈","基富通":"🟧","渣打美股":"🇺🇸","渣打基金":"💹","台新基金":"🟥"}
        for col, plat in zip(r2cols, invest_items[:5]):
            ps     = platform_summary.get(plat, {})
            val    = ps.get("台幣市值")
            profit = ps.get("損益")
            rate   = ps.get("損益率")
            delta  = f"{signed_money(profit)} ({signed_ratio_str(rate)})" if profit else None
            col.metric(f"{icons.get(plat,'')} {plat}", money(val), delta=delta)

        st.markdown("<br>", unsafe_allow_html=True)

        left, mid, right = st.columns([1.2, 0.9, 1.2])

        with left:
            st.markdown('<div class="j-card"><div class="j-card-title">資產配置</div>', unsafe_allow_html=True)
            chart_data = {}
            for plat in invest_items:
                v = platform_summary.get(plat, {}).get("台幣市值") or 0
                if v > 0: chart_data[plat] = v
            if bank_val > 0:   chart_data["銀行"] = bank_val
            if insure_val > 0: chart_data["保險"] = insure_val
            if chart_data:
                chart_df = pd.DataFrame.from_dict(chart_data, orient="index", columns=["金額"])
                st.bar_chart(chart_df, height=240)
                total_for_pct = sum(chart_data.values())
                alloc_rows = [{"項目": k, "金額": money(v), "占比": ratio_str(v/total_for_pct)} for k, v in chart_data.items()]
                display_df(pd.DataFrame(alloc_rows), height=280)
            else:
                st.info("尚無資產配置資料")
            st.markdown("</div>", unsafe_allow_html=True)

        with mid:
            st.markdown('<div class="j-card"><div class="j-card-title">資產彙總</div>', unsafe_allow_html=True)
            summary_rows = [
                {"項目": "總資產",   "金額": money(total_assets),     "損益": "-"},
                {"項目": "負債",     "金額": money(uncle_val),         "損益": "-"},
                {"項目": "淨資產",   "金額": money(net_assets),        "損益": "-"},
                {"項目": "現金",     "金額": money(bank_val),          "損益": "-"},
                {"項目": "保險",     "金額": money(insure_val),        "損益": "-"},
                {"項目": "投資部位", "金額": money(invest_total_val),
                 "損益": f"{signed_money(invest_total_profit)} ({signed_ratio_str(invest_total_profit/invest_total_val if invest_total_val else None)})"},
                {"項目": "每月配息", "金額": money(invest_total_div),  "損益": "-"},
            ]
            display_df(pd.DataFrame(summary_rows), height=340)
            st.markdown("</div>", unsafe_allow_html=True)

        with right:
            st.markdown('<div class="j-card"><div class="j-card-title">投資平台明細</div>', unsafe_allow_html=True)
            inv_rows = []
            for plat in invest_items:
                ps = platform_summary.get(plat, {})
                inv_rows.append({
                    "平台":     plat,
                    "台幣市值": money(ps.get("台幣市值")),
                    "台幣成本": money(ps.get("台幣成本")),
                    "損益":     signed_money(ps.get("損益")),
                    "損益率":   signed_ratio_str(ps.get("損益率")),
                    "每月配息": money(ps.get("台幣配息")),
                })
            total_ps_row = {
                "平台": "合計",
                "台幣市值": money(invest_total_val),
                "台幣成本": money(sum(platform_summary.get(p, {}).get("台幣成本") or 0 for p in invest_items)),
                "損益":     signed_money(invest_total_profit),
                "損益率":   "-",
                "每月配息": money(invest_total_div),
            }
            display_df(pd.DataFrame(inv_rows + [total_ps_row]), height=360)
            st.markdown("</div>", unsafe_allow_html=True)

    except Exception as e:
        st.warning(f"⚠️ 總覽讀取錯誤：{e}")


# =============================================================================
# TAB 2 — 平台明細
# =============================================================================
with tabs[1]:
    st.markdown('<div class="j-page-title">平台明細</div><div class="j-page-sub">各平台持倉明細</div>', unsafe_allow_html=True)

    selected_platform = st.radio(
        "選擇平台", list(DETAIL_GROUPS.keys()),
        horizontal=True, label_visibility="collapsed",
    )

    ps = platform_summary.get(selected_platform, {})
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("台幣市值",  money(ps.get("台幣市值")))
    m2.metric("台幣成本",  money(ps.get("台幣成本")))
    m3.metric("損益",      signed_money(ps.get("損益")), delta=signed_ratio_str(ps.get("損益率")))
    m4.metric("每月配息",  money(ps.get("台幣配息")))

    # 從 all_detail_df 篩選
    if not all_detail_df.empty and "平台" in all_detail_df.columns:
        plat_df = all_detail_df[all_detail_df["平台"] == selected_platform].copy()
    else:
        plat_df = pd.DataFrame()

    st.markdown(f'<div class="j-card"><div class="j-card-title">{selected_platform}｜持倉明細</div>', unsafe_allow_html=True)
    if plat_df.empty:
        st.warning("尚未從工作表解析到明細，請查看下方原始工作表。")
    else:
        show_cols = ["群組", "名稱", "日期", "台幣成本", "台幣市值", "損益", "配息率", "台幣配息"]
        show_cols = [c for c in show_cols if c in plat_df.columns]
        disp = plat_df[show_cols].copy()
        for col in ["台幣成本", "台幣市值", "台幣配息"]:
            if col in disp: disp[col] = disp[col].apply(money)
        if "損益" in disp: disp["損益"] = disp["損益"].apply(signed_money)
        if "配息率" in disp: disp["配息率"] = disp["配息率"].apply(ratio_str)
        display_df(fmt_df(disp), height=420)
    st.markdown("</div>", unsafe_allow_html=True)

    # 原始工作表
    raw_sheets = DETAIL_GROUPS.get(selected_platform, [])
    if raw_sheets:
        st.markdown('<div class="j-card"><div class="j-card-title">原始工作表</div>', unsafe_allow_html=True)
        raw_sel = st.selectbox("查看原始表", raw_sheets, key=f"raw_{selected_platform}")
        try:
            raw_df = read_sheet(market_bytes, raw_sel)
            clean = raw_df.dropna(how="all").dropna(axis=1, how="all").iloc[:120, :20]
            clean.columns = [str(c) for c in clean.columns]
            display_df(fmt_df(clean), height=460)
        except Exception as e:
            st.warning(f"讀取 {raw_sel} 失敗：{e}")
        st.markdown("</div>", unsafe_allow_html=True)

    # 手動記錄
    st.markdown('<div class="j-card"><div class="j-card-title">投資記錄（手動/匯入）</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader("匯入 CSV", type=["csv"], key=f"upload_{selected_platform}")
    if uploaded:
        try:
            imported = pd.read_csv(uploaded)
            existing = load_local_records(selected_platform)
            combined = pd.concat([existing, imported], ignore_index=True) if not existing.empty else imported
            save_local_records(selected_platform, combined)
            st.success(f"已匯入 {len(imported)} 筆。")
        except Exception as e:
            st.error(f"匯入失敗：{e}")

    with st.form(f"manual_{selected_platform}", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        date   = c1.date_input("日期")
        action = c2.selectbox("動作", ["買入","賣出","配息","除息","轉入","轉出","調整","其他"])
        target = c3.text_input("標的名稱")
        code   = c4.text_input("代號")
        c5, c6, c7, c8 = st.columns(4)
        currency = c5.selectbox("幣別", ["TWD","USD","CNY","JPY","ZAR","其他"])
        units    = c6.number_input("單位/股數", value=0.0)
        price    = c7.number_input("成交價", value=0.0, step=0.01)
        amount   = c8.number_input("金額", value=0.0, step=100.0)
        fee  = st.number_input("手續費", value=0.0, step=10.0)
        note = st.text_input("備註")
        if st.form_submit_button("新增"):
            new_row = pd.DataFrame([{"日期":str(date),"平台":selected_platform,"動作":action,
                "標的名稱":target,"代號":code,"幣別":currency,"單位/股數":units,
                "成交價":price,"金額":amount,"手續費":fee,"備註":note}])
            existing = load_local_records(selected_platform)
            combined = pd.concat([existing, new_row], ignore_index=True) if not existing.empty else new_row
            save_local_records(selected_platform, combined)
            st.success("已新增。")

    display_df(fmt_df(load_local_records(selected_platform)), height=260)
    st.markdown("</div>", unsafe_allow_html=True)


# =============================================================================
# TAB 3 — 每月收入
# =============================================================================
with tabs[2]:
    st.markdown('<div class="j-page-title">每月收入</div><div class="j-page-sub">配息・股利・利息月走勢</div>', unsafe_allow_html=True)
    try:
        monthly = read_sheet(primary_bytes, "每月收入")
        header  = monthly.iloc[0]
        records = []
        # 找合計列
        for ri in range(1, len(monthly)):
            label = str(monthly.iloc[ri, 0]).strip()
            if "合計" in label:
                for ci, hv in enumerate(header):
                    dt  = pd.to_datetime(hv, errors="coerce")
                    amt = numeric(monthly.iloc[ri, ci])
                    if pd.notna(dt) and amt is not None:
                        records.append({"月份": dt, "收入": amt})
                break

        if records:
            st.markdown('<div class="j-card"><div class="j-card-title">月收入走勢</div>', unsafe_allow_html=True)
            st.bar_chart(pd.DataFrame(records).set_index("月份"), height=240, color="#10b981")
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="j-card"><div class="j-card-title">每月收入明細</div>', unsafe_allow_html=True)
        tbl = monthly.iloc[:22, :46].dropna(axis=1, how="all")
        tbl.columns = [str(c) for c in tbl.columns]
        display_df(fmt_df(tbl), height=360)
        st.markdown("</div>", unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"⚠️ 每月收入讀取錯誤：{e}")


# =============================================================================
# TAB 4 — 2026 細帳
# =============================================================================
with tabs[3]:
    st.markdown('<div class="j-page-title">2026 細帳</div><div class="j-page-sub">全年進出帳記錄</div>', unsafe_allow_html=True)
    try:
        ledger = read_sheet(primary_bytes, "2026細帳")
        months = ledger.iloc[0, 1:14]
        records = []
        for ri in range(1, min(len(ledger), 180)):
            cat = ledger.iloc[ri, 0]
            if cat is None or pd.isna(cat): continue
            for offset, mv in enumerate(months, start=1):
                amt = numeric(ledger.iloc[ri, offset])
                if amt and amt != 0:
                    records.append({"月份": str(mv), "項目": str(cat), "金額": amt})
        long_df = pd.DataFrame(records)

        if not long_df.empty:
            inc = long_df[long_df["金額"] > 0]["金額"].sum()
            out = long_df[long_df["金額"] < 0]["金額"].sum()
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("收入合計", money(inc))
            m2.metric("支出合計", money(abs(out)))
            m3.metric("淨收支",   money(inc + out))
            m4.metric("記錄筆數", f"{len(long_df):,}")

            cats = ["全部"] + sorted(long_df["項目"].unique().tolist())
            sel  = st.selectbox("篩選項目", cats)
            view = long_df if sel == "全部" else long_df[long_df["項目"] == sel]
            st.markdown('<div class="j-card"><div class="j-card-title">細帳明細</div>', unsafe_allow_html=True)
            display_df(fmt_df(view), height=340)
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="j-card"><div class="j-card-title">原始資料</div>', unsafe_allow_html=True)
        raw = ledger.iloc[:140, :16].copy()
        raw.columns = [str(c) for c in raw.columns]
        display_df(fmt_df(raw), height=360)
        st.markdown("</div>", unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"⚠️ 2026細帳讀取錯誤：{e}")


# =============================================================================
# TAB 5 — 市值來源
# =============================================================================
with tabs[4]:
    st.markdown('<div class="j-page-title">市值來源</div><div class="j-page-sub">Google Sheet 原始快照</div>', unsafe_allow_html=True)
    sel_sheet = st.selectbox("選擇工作表", MARKET_SHEETS)
    try:
        sheet = read_sheet(market_bytes, sel_sheet)
        clean = sheet.dropna(how="all").dropna(axis=1, how="all").iloc[:200, :25]
        clean.columns = [str(c) for c in clean.columns]
        st.markdown('<div class="j-card"><div class="j-card-title">工作表資料</div>', unsafe_allow_html=True)
        display_df(fmt_df(clean), height=520)
        st.markdown("</div>", unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"⚠️ {sel_sheet} 讀取錯誤：{e}")


# =============================================================================
# TAB 6 — 即時市值
# =============================================================================
with tabs[5]:
    st.markdown('<div class="j-page-title">即時市值</div><div class="j-page-sub">Yahoo Finance（股票/匯率）· MoneyDJ（基金 NAV）</div>', unsafe_allow_html=True)

    # 匯率
    st.markdown('<div class="j-card"><div class="j-card-title">匯率（TWD 換算）</div>', unsafe_allow_html=True)
    fx_rates: dict[str, float] = {}
    fx_cols = st.columns(len(FX_PAIRS))
    for col, (cur, pair) in zip(fx_cols, FX_PAIRS.items()):
        with st.spinner(f"抓取 {cur}…"):
            rate_str, status = fetch_fx(pair)
        col.metric(f"1 {cur} = ? TWD", rate_str,
                   delta="✓ 即時" if status == "ok" else f"⚠ {status}")
        if status == "ok":
            try: fx_rates[cur] = float(rate_str.replace(",", ""))
            except: pass
    st.markdown("</div>", unsafe_allow_html=True)

    # 股票
    st.markdown('<div class="j-card"><div class="j-card-title">股票即時價（Yahoo Finance）</div>', unsafe_allow_html=True)
    stock_rows = []
    for s in STOCK_CONFIG:
        price_str, status = fetch_stock_price(s["ticker"])
        twd = "-"
        if status == "ok" and s["currency"] in fx_rates:
            try: twd = money(float(price_str.replace(",","")) * fx_rates[s["currency"]])
            except: pass
        stock_rows.append({"代號":s["ticker"],"名稱":s["name"],"幣別":s["currency"],
                            "即時價":price_str,"台幣換算":twd,
                            "狀態":"✓" if status=="ok" else f"⚠ {status}"})
    display_df(pd.DataFrame(stock_rows), height=180)
    st.markdown("</div>", unsafe_allow_html=True)

    # 基金 NAV
    st.markdown('<div class="j-card"><div class="j-card-title">基金最新淨值（MoneyDJ）</div>', unsafe_allow_html=True)
    fund_rows = []
    prog = st.progress(0, text="抓取基金淨值…")
    for i, f in enumerate(FUND_CONFIG):
        nav_str, status = fetch_fund_nav(f["code"], f["pattern"])
        cur = f["currency"]
        twd_str = "-"
        if status == "ok":
            if cur == "TWD":
                twd_str = nav_str
            elif cur in fx_rates:
                try: twd_str = f"{float(nav_str.replace(',','')) * fx_rates[cur]:,.4f}"
                except: pass
        fund_rows.append({"基金名稱":f["name"],"代號":f["code"],"幣別":cur,
                          "最新淨值":nav_str,"台幣換算":twd_str,
                          "狀態":"✓" if status=="ok" else f"⚠ {status}"})
        prog.progress((i+1)/len(FUND_CONFIG), text=f"抓取中… {i+1}/{len(FUND_CONFIG)}")
    prog.empty()
    display_df(pd.DataFrame(fund_rows), height=420)
    st.markdown("</div>", unsafe_allow_html=True)

    if not HAS_YF:
        st.info("安裝 `yfinance` 以啟用股票/匯率即時抓取：`pip install yfinance`")
    if not HAS_BS4:
        st.info("安裝 `beautifulsoup4` 與 `lxml` 以啟用基金 NAV：`pip install beautifulsoup4 lxml`")


# =============================================================================
# TAB 7 — 資料健康
# =============================================================================
with tabs[6]:
    st.markdown('<div class="j-page-title">資料健康</div><div class="j-page-sub">工作表結構・解析狀況</div>', unsafe_allow_html=True)

    # 顯示各平台解析結果
    st.markdown('<div class="j-card"><div class="j-card-title">各平台解析結果</div>', unsafe_allow_html=True)
    debug_rows = []
    for plat, ps in platform_summary.items():
        debug_rows.append({
            "平台": plat,
            "台幣市值": money(ps.get("台幣市值")),
            "台幣成本": money(ps.get("台幣成本")),
            "損益":     signed_money(ps.get("損益")),
            "損益率":   signed_ratio_str(ps.get("損益率")),
            "台幣配息": money(ps.get("台幣配息")),
            "狀態": "✓ 有資料" if ps.get("台幣市值") else "⚠ 無資料",
        })
    display_df(pd.DataFrame(debug_rows), height=300)
    st.markdown("</div>", unsafe_allow_html=True)

    # 明細筆數統計
    if not all_detail_df.empty and "平台" in all_detail_df.columns:
        st.markdown('<div class="j-card"><div class="j-card-title">明細解析筆數</div>', unsafe_allow_html=True)
        cnt = all_detail_df.groupby("平台").size().reset_index(name="明細筆數")
        display_df(cnt, height=200)
        st.markdown("</div>", unsafe_allow_html=True)

    # 總覽 A/B 欄原始值（除錯用）
    try:
        ov_raw = read_sheet(market_bytes, "總覽")
        st.markdown('<div class="j-card"><div class="j-card-title">總覽工作表 A/B 欄原始值（除錯）</div>', unsafe_allow_html=True)
        ov_ab = ov_raw.iloc[:45, :2].copy()
        ov_ab.columns = ["A欄（項目）", "B欄（金額）"]
        display_df(fmt_df(ov_ab), height=500)
        st.markdown("</div>", unsafe_allow_html=True)

        # 顯示目前抓到的關鍵值
        st.markdown('<div class="j-card"><div class="j-card-title">關鍵數值確認</div>', unsafe_allow_html=True)
        check_rows = []
        for label, aliases in OVERVIEW_ALIASES.items():
            val = value_from_overview(ov_raw, aliases)
            check_rows.append({"項目": label, "抓到的值": money(val), "搜尋關鍵字": str(aliases[:2])})
        display_df(pd.DataFrame(check_rows), height=300)
        st.markdown("</div>", unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"總覽除錯失敗：{e}")
    if summaries:
        for book in summaries:
            fname = Path(book["file"]).name
            st.markdown(f'<div class="j-card"><div class="j-card-title">{fname}</div>', unsafe_allow_html=True)
            bm1, bm2, bm3 = st.columns(3)
            bm1.metric("檔案大小 MB", book["size_mb"])
            bm2.metric("工作表數",   book["sheet_count"])
            bm3.metric("公式種類",   len(book["workbook_functions"]))
            st.markdown("</div>", unsafe_allow_html=True)
