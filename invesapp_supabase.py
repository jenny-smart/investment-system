from __future__ import annotations

import os
from typing import Any

import pandas as pd
import requests
import streamlit as st
from supabase import create_client, Client

try:
    import yfinance as yf
    HAS_YF = True
except Exception:
    HAS_YF = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except Exception:
    HAS_BS4 = False


APP_VERSION = "2026-05-17-v3-premium"

DEFAULT_SUPABASE_URL = "https://qrvdztqyzxlsfskdgiqp.supabase.co"

PLATFORMS   = ["台股", "美股", "基富通", "渣打基金", "台新基金"]
ASSET_TYPES = ["台股", "美股", "基金"]
CURRENCIES  = ["TWD", "USD", "CNY", "JPY", "ZAR"]
FX_PAIRS    = {"TWD": None, "USD": "USDTWD=X", "CNY": "CNYTWD=X", "JPY": "JPYTWD=X", "ZAR": "ZARTWD=X"}

SORT_OPTIONS = {
    "名稱 A→Z":   ("name", True),
    "名稱 Z→A":   ("name", False),
    "代碼 A→Z":   ("ticker_or_code", True),
    "台幣市值 ↓":  ("台幣市值", False),
    "台幣市值 ↑":  ("台幣市值", True),
    "損益 ↓":     ("損益", False),
    "損益率 ↓":   ("損益率", False),
    "每月配息 ↓":  ("每月配息", False),
}

TW_PRESETS = {
    "儒鴻": "1476.TW", "大魯閣": "1432.TW", "中砂": "1560.TW", "中鴻": "2014.TW",
    "凱美": "2375.TW", "華碩": "2357.TW", "日勝生": "2547.TW", "晶華": "2707.TW",
    "中壽": "2823.TW", "凱基金": "2883.TW", "凱基金乙特": "2883B.TW", "聯陽": "3014.TW",
    "景碩": "3189.TW", "緯創": "3231.TW", "東隆興": "4401.TWO", "和碩": "4938.TW",
    "松翰": "5471.TWO", "智冠": "5478.TWO", "久元": "6261.TWO", "台塑化": "6505.TW",
    "上銀": "2049.TW", "元大高股息": "0056.TW", "元大台灣50": "0050.TW",
    "泰碩": "3338.TW", "尼得科超眾": "6230.TW", "立積": "4968.TW", "鈺齊-KY": "9802.TW",
    "東陽": "1319.TW", "華邦電": "2344.TW", "元大金": "2885.TW", "鴻海": "2317.TW",
    "長榮": "2603.TW", "長華*": "8070.TW", "群創": "3481.TW", "集盛": "1455.TW",
    "華新": "1605.TW", "第一銅": "2009.TW", "大聯大": "3702.TW",
    "富邦特選高股息30": "00900.TW", "群益台灣精選高息": "00919.TW",
    "富邦全球投等債": "00740B.TW", "群益半導體收益": "00927.TW", "華泰": "2329.TW",
    "圓剛": "2417.TW", "楠梓電": "2316.TW", "富邦台50": "006208.TW",
    "南亞科": "2408.TW", "欣興": "3037.TW", "京元電子": "2449.TW", "國巨": "2327.TW",
}

FUND_PRESETS = {
    "acft94":  ("富蘭克林華美新興國家固定收益B-新臺幣", "yp010000", "TWD", "基富通"),
    "acai222": ("柏瑞新興邊境非投資等級債券基金-B類型", "yp010000", "TWD", "基富通"),
    "acft99":  ("富蘭克林華美新興國家固定收益B-人民幣", "yp010000", "CNY", "基富通"),
    "shzx0":   ("貝萊德全球智慧數據股票入息A6日圓",    "yp010001", "JPY", "基富通"),
    "TLZO3":   ("安聯收益成長AMgi月收（日圓避險）",    "yp010001", "JPY", "基富通"),
    "acob36":  ("大華銀新加坡房地產收益基金-美元月配", "yp010000", "USD", "渣打基金"),
    "pizn8":   ("東方匯理新興市場債券A美元（月配）",   "yp010001", "USD", "渣打基金"),
    "pizo1":   ("東方匯理新興市場債券U美元（月配）",   "yp010001", "USD", "渣打基金"),
    "pizm9":   ("東方匯理新興市場債券U南非幣（月配）", "yp010001", "ZAR", "台新基金"),
    "anzb6":   ("高盛新興市場債券Y股美元",            "yp010001", "USD", "渣打基金"),
    "ANZH2":   ("高盛新興市場債券Y南非幣對沖（月配）", "yp010001", "ZAR", "台新基金"),
}

# ── Streamlit 頁面設定 ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="Jenny 投資系統",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=DM+Mono:wght@400;500&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; }

html, body, [class*="css"] {
    font-family: 'DM Sans', 'PingFang TC', 'Noto Sans TC', sans-serif !important;
}

/* ── 背景 ── */
.stApp {
    background: #0d1117 !important;
    color: #e6edf3 !important;
}
.block-container {
    padding: 0 !important;
    max-width: 100% !important;
}

/* ── 隱藏側邊欄 ── */
[data-testid="stSidebar"],
[data-testid="collapsedControl"],
button[kind="header"] { display: none !important; }

/* ── 頂部導覽列 ── */
.j-navbar {
    background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
    border-bottom: 1px solid #21262d;
    padding: 0 32px;
    display: flex;
    align-items: center;
    gap: 20px;
    height: 64px;
    position: sticky;
    top: 0;
    z-index: 1000;
    box-shadow: 0 1px 0 rgba(255,255,255,.06), 0 4px 24px rgba(0,0,0,.4);
}
.j-logo-mark {
    width: 36px; height: 36px;
    background: linear-gradient(135deg, #10b981, #059669);
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-weight: 900; font-size: 18px; color: #fff;
    box-shadow: 0 0 20px rgba(16,185,129,.4);
    flex-shrink: 0;
}
.j-nav-title {
    font-size: 16px; font-weight: 700; color: #e6edf3;
    letter-spacing: -.3px;
}
.j-nav-sub {
    font-size: 11px; color: #8b949e;
}
.j-nav-sep {
    flex: 1;
}
.j-nav-badge {
    background: rgba(16,185,129,.12);
    border: 1px solid rgba(16,185,129,.25);
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 11px;
    color: #10b981;
    font-family: 'DM Mono', monospace;
    font-weight: 500;
}

/* ── 指標卡片 ── */
.j-metrics-bar {
    background: #161b22;
    border-bottom: 1px solid #21262d;
    padding: 20px 32px;
    display: flex;
    gap: 1px;
}
.j-metric {
    flex: 1;
    background: #0d1117;
    padding: 16px 20px;
    border-radius: 0;
    position: relative;
}
.j-metric:first-child { border-radius: 10px 0 0 10px; }
.j-metric:last-child  { border-radius: 0 10px 10px 0; }
.j-metric-label {
    font-size: 10px; font-weight: 600;
    color: #8b949e; text-transform: uppercase;
    letter-spacing: 1px; margin-bottom: 6px;
}
.j-metric-value {
    font-size: 22px; font-weight: 700;
    color: #e6edf3;
    font-family: 'DM Mono', monospace;
    letter-spacing: -.5px;
}
.j-metric-delta {
    font-size: 11px; font-weight: 500;
    margin-top: 4px;
}
.j-metric-delta.pos { color: #3fb950; }
.j-metric-delta.neg { color: #f85149; }
.j-metric-delta.neu { color: #8b949e; }

/* ── Tab ── */
.stTabs [data-baseweb="tab-list"] {
    background: #161b22 !important;
    border-bottom: 1px solid #21262d !important;
    padding: 0 32px !important;
    gap: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    color: #8b949e !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    padding: 14px 20px !important;
    border-bottom: 2px solid transparent !important;
    background: transparent !important;
    transition: color .15s !important;
}
.stTabs [aria-selected="true"] {
    color: #e6edf3 !important;
    border-bottom-color: #10b981 !important;
    font-weight: 600 !important;
}
.stTabs [data-baseweb="tab-panel"] {
    background: #0d1117;
    padding: 28px 32px;
}

/* ── 卡片 ── */
.j-card {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 12px;
    padding: 20px 22px;
    margin-bottom: 16px;
}
.j-card-title {
    font-size: 13px; font-weight: 700;
    color: #8b949e; text-transform: uppercase;
    letter-spacing: 1px; margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid #21262d;
}
.j-section-title {
    font-size: 18px; font-weight: 700;
    color: #e6edf3; margin-bottom: 4px;
}
.j-section-sub {
    font-size: 12px; color: #8b949e;
    margin-bottom: 20px;
}

/* ── Platform 摘要 Metric ── */
[data-testid="stMetric"] {
    background: #161b22 !important;
    border: 1px solid #21262d !important;
    border-radius: 12px !important;
    padding: 16px 18px !important;
    box-shadow: none !important;
}
[data-testid="stMetricLabel"] p {
    font-size: 10px !important; font-weight: 700 !important;
    color: #8b949e !important; text-transform: uppercase !important;
    letter-spacing: 1px !important;
}
[data-testid="stMetricValue"] {
    font-size: 20px !important; font-weight: 700 !important;
    color: #e6edf3 !important;
    font-family: 'DM Mono', monospace !important;
}
[data-testid="stMetricDelta"] { font-size: 11px !important; }

/* ── 資料表格 ── */
[data-testid="stDataFrame"] {
    background: #161b22 !important;
    border: 1px solid #21262d !important;
    border-radius: 12px !important;
    overflow: hidden !important;
}
.dvn-scroller { background: #161b22 !important; }

/* ── 按鈕 ── */
.stButton > button {
    background: linear-gradient(135deg, #10b981, #059669) !important;
    color: #fff !important; border: none !important;
    border-radius: 8px !important; font-weight: 600 !important;
    font-size: 13px !important; padding: 8px 20px !important;
    box-shadow: 0 0 0 1px rgba(16,185,129,.3), 0 4px 12px rgba(16,185,129,.2) !important;
    transition: all .15s !important;
}
.stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 0 0 1px rgba(16,185,129,.5), 0 6px 20px rgba(16,185,129,.3) !important;
}

/* ── 輸入框 ── */
[data-baseweb="select"] > div,
[data-baseweb="input"] input {
    background: #21262d !important;
    border-color: #30363d !important;
    border-radius: 8px !important;
    color: #e6edf3 !important;
    font-size: 13px !important;
}
[data-testid="stRadio"] > div { flex-direction: row !important; flex-wrap: wrap !important; gap: 8px !important; }
[data-testid="stRadio"] label {
    background: #21262d !important;
    border: 1px solid #30363d !important;
    border-radius: 20px !important;
    padding: 5px 14px !important;
    font-size: 12px !important;
    color: #8b949e !important;
    cursor: pointer !important;
    transition: all .15s !important;
}
[data-testid="stRadio"] label:has(input:checked) {
    background: rgba(16,185,129,.15) !important;
    border-color: #10b981 !important;
    color: #3fb950 !important;
    font-weight: 600 !important;
}

/* ── 排序工具列 ── */
.j-toolbar {
    display: flex; align-items: center; gap: 12px;
    margin-bottom: 16px; flex-wrap: wrap;
}

/* ── 狀態標籤 ── */
.j-badge-ok  { color: #3fb950; font-size: 11px; }
.j-badge-err { color: #f85149; font-size: 11px; }

/* ── 基金市值摘要列 ── */
.j-fund-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 0; border-bottom: 1px solid #21262d;
    font-size: 13px;
}
.j-fund-row:last-child { border-bottom: none; }
.j-fund-name { color: #e6edf3; font-weight: 500; flex: 1; }
.j-fund-code { color: #8b949e; font-family: 'DM Mono', monospace; font-size: 11px; width: 80px; }
.j-fund-nav  { color: #e6edf3; font-family: 'DM Mono', monospace; width: 80px; text-align: right; }
.j-fund-twd  { color: #3fb950; font-family: 'DM Mono', monospace; width: 100px; text-align: right; font-weight: 600; }
.j-fund-status { width: 60px; text-align: right; }

/* ── 損益色 ── */
.pos-val { color: #3fb950 !important; }
.neg-val { color: #f85149 !important; }
</style>
""", unsafe_allow_html=True)


# ── 工具函式 ───────────────────────────────────────────────────────────────
def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.environ.get(name, default)

def to_float(v: Any) -> float | None:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        if isinstance(v, str):
            v = v.replace(",", "").replace("$", "").strip()
            if v in {"", "-", "—"}:
                return None
        return float(v)
    except Exception:
        return None

def money(v: Any, decimals: int = 0) -> str:
    n = to_float(v)
    return "-" if n is None else f"{n:,.{decimals}f}"

def signed_money(v: Any) -> str:
    n = to_float(v)
    return "-" if n is None else f"{n:+,.0f}"

def pct(v: Any, signed: bool = False) -> str:
    n = to_float(v)
    if n is None:
        return "-"
    return (f"{n:+.2%}" if signed else f"{n:.2%}")


# ── Supabase ───────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def supabase_client() -> Client:
    url = get_secret("SUPABASE_URL", DEFAULT_SUPABASE_URL)
    key = get_secret("SUPABASE_ANON_KEY", "")
    if not key:
        st.error("❌ 缺少 SUPABASE_ANON_KEY，請到 Streamlit Cloud → Settings → Secrets 設定。")
        st.stop()
    return create_client(url, key)

def load_positions() -> pd.DataFrame:
    res = supabase_client().table("positions").select("*").order("platform").order("id").execute()
    return pd.DataFrame(res.data or [])

def add_position(row: dict[str, Any]) -> None:
    supabase_client().table("positions").insert(row).execute()

def update_positions(df: pd.DataFrame) -> None:
    sb = supabase_client()
    for _, r in df.iterrows():
        rid = r.get("id", None)
        is_new = pd.isna(rid) if isinstance(rid, float) else (str(rid).strip() in {"", "None", "nan"})
        payload = {
            "platform": str(r.get("platform") or "台股"),
            "asset_type": str(r.get("asset_type") or "台股"),
            "name": str(r.get("name") or "").strip(),
            "ticker": str(r.get("ticker") or "").strip(),
            "fund_code": str(r.get("fund_code") or "").strip(),
            "fund_pattern": str(r.get("fund_pattern") or "").strip(),
            "currency": str(r.get("currency") or "TWD"),
            "units": float(r.get("units") or 0),
            "avg_cost": float(r.get("avg_cost") or 0),
            "monthly_dividend_per_unit": float(r.get("monthly_dividend_per_unit") or 0),
            "note": str(r.get("note") or ""),
        }
        if not any([payload["name"], payload["ticker"], payload["fund_code"]]):
            continue
        if is_new:
            sb.table("positions").insert(payload).execute()
        else:
            sb.table("positions").update(payload).eq("id", int(rid)).execute()

def delete_position(pid: int) -> None:
    supabase_client().table("positions").delete().eq("id", pid).execute()


# ── 即時價格 ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def fetch_yahoo_price(ticker: str) -> tuple[float | None, str]:
    if not ticker:
        return None, "無代碼"
    if not HAS_YF:
        return None, "缺少 yfinance"
    try:
        t = yf.Ticker(ticker)
        price = getattr(t.fast_info, "last_price", None)
        if price is None:
            hist = t.history(period="5d")
            if not hist.empty:
                price = float(hist["Close"].dropna().iloc[-1])
        return (float(price), "ok") if price is not None else (None, "無價格")
    except Exception as e:
        return None, str(e)[:50]

@st.cache_data(ttl=300, show_spinner=False)
def fetch_fund_nav(code: str, pattern: str) -> tuple[float | None, str]:
    if not code or not pattern:
        return None, "無基金代碼"
    if not HAS_BS4:
        return None, "缺少 beautifulsoup4"
    try:
        url = f"https://www.moneydj.com/funddj/ya/{pattern}.djhtm?a={code}"
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        table = soup.select_one("#article form table")
        if table:
            rows = table.find_all("tr")
            if len(rows) >= 2:
                cells = rows[1].find_all("td")
                if len(cells) >= 2:
                    raw = cells[1].get_text(strip=True).replace(",", "")
                    return float(raw), "ok"
        return None, "找不到淨值"
    except Exception as e:
        return None, str(e)[:50]

@st.cache_data(ttl=300, show_spinner=False)
def fetch_fx(currency: str) -> tuple[float | None, str]:
    if currency == "TWD":
        return 1.0, "ok"
    pair = FX_PAIRS.get(currency)
    if not pair:
        return None, "未知幣別"
    return fetch_yahoo_price(pair)

def fetch_all_fund_navs() -> pd.DataFrame:
    """一次抓所有基金最新淨值，回傳 DataFrame"""
    fx_cache: dict[str, tuple[float | None, str]] = {}
    rows = []
    for code, (name, pattern, currency, platform) in FUND_PRESETS.items():
        nav, nav_status = fetch_fund_nav(code, pattern)
        if currency not in fx_cache:
            fx_cache[currency] = fetch_fx(currency)
        fx, fx_status = fx_cache[currency]
        twd = nav * fx if nav is not None and fx is not None else None
        rows.append({
            "平台":     platform,
            "基金名稱": name,
            "代號":     code,
            "幣別":     currency,
            "最新淨值": money(nav, 4),
            "匯率":     money(fx, 4),
            "台幣換算": money(twd, 2),
            "狀態":     "✓" if nav_status == "ok" and fx_status == "ok" else f"⚠ {nav_status}",
            "_nav_raw": nav,
            "_twd_raw": twd,
        })
    return pd.DataFrame(rows)


# ── 計算市值 ───────────────────────────────────────────────────────────────
def enrich(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    rows = []
    fx_cache: dict[str, tuple[float | None, str]] = {}
    for _, r in df.iterrows():
        currency = str(r.get("currency") or "TWD")
        units    = float(r.get("units") or 0)
        avg_cost = float(r.get("avg_cost") or 0)

        if r.get("asset_type") in {"台股", "美股"}:
            price, p_status = fetch_yahoo_price(str(r.get("ticker") or ""))
        else:
            price, p_status = fetch_fund_nav(str(r.get("fund_code") or ""), str(r.get("fund_pattern") or ""))

        if currency not in fx_cache:
            fx_cache[currency] = fetch_fx(currency)
        fx, fx_status = fx_cache[currency]

        orig_cost  = units * avg_cost
        orig_value = units * price if price is not None else None
        twd_cost   = orig_cost  * fx if fx is not None else None
        twd_value  = orig_value * fx if orig_value is not None and fx is not None else None
        pnl        = twd_value - twd_cost if twd_value is not None and twd_cost is not None else None
        pnl_rate   = pnl / twd_cost if pnl is not None and twd_cost else None
        md_twd     = units * float(r.get("monthly_dividend_per_unit") or 0) * (fx or 1)

        ticker_or_code = str(r.get("ticker") or r.get("fund_code") or "")

        out = dict(r)
        out.update({
            "ticker_or_code":  ticker_or_code,
            "即時價格/淨值":   price,
            "匯率":            fx,
            "台幣成本":        twd_cost,
            "台幣市值":        twd_value,
            "損益":            pnl,
            "損益率":          pnl_rate,
            "每月配息":        md_twd if md_twd else None,
            "狀態": "✓" if p_status == "ok" and fx_status == "ok" else f"價:{p_status}",
        })
        rows.append(out)
    return pd.DataFrame(rows)

def sort_df(df: pd.DataFrame, sort_key: str) -> pd.DataFrame:
    col, asc = SORT_OPTIONS.get(sort_key, ("name", True))
    if col in df.columns:
        return df.sort_values(col, ascending=asc, na_position="last").reset_index(drop=True)
    return df

def format_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in ["即時價格/淨值", "匯率"]:
        if c in out:
            out[c] = out[c].apply(lambda x: money(x, 4))
    for c in ["台幣成本", "台幣市值", "每月配息"]:
        if c in out:
            out[c] = out[c].apply(money)
    if "損益" in out:
        out["損益"] = out["損益"].apply(signed_money)
    if "損益率" in out:
        out["損益率"] = out["損益率"].apply(lambda x: pct(x, signed=True))
    return out.fillna("").astype(str).replace({"nan": "", "None": ""})


# ── Seed ───────────────────────────────────────────────────────────────────
def seed_presets() -> None:
    existing = load_positions()
    if not existing.empty:
        return
    for name, ticker in TW_PRESETS.items():
        add_position({"platform":"台股","asset_type":"台股","name":name,"ticker":ticker,
                      "fund_code":"","fund_pattern":"","currency":"TWD","units":0,
                      "avg_cost":0,"monthly_dividend_per_unit":0,"note":"預設"})
    for ticker, name in [("PYPL","PayPal"),("XYZ","Block")]:
        add_position({"platform":"美股","asset_type":"美股","name":name,"ticker":ticker,
                      "fund_code":"","fund_pattern":"","currency":"USD","units":0,
                      "avg_cost":0,"monthly_dividend_per_unit":0,"note":"預設"})
    for code, (name, pattern, currency, platform) in FUND_PRESETS.items():
        add_position({"platform":platform,"asset_type":"基金","name":name,"ticker":"",
                      "fund_code":code,"fund_pattern":pattern,"currency":currency,"units":0,
                      "avg_cost":0,"monthly_dividend_per_unit":0,"note":"預設"})


# ── 編輯器元件 ─────────────────────────────────────────────────────────────
def editable_platform_table(platform_name: str, current_positions: pd.DataFrame, editor_key: str) -> None:
    st.markdown("---")
    st.markdown("**✏️ 編輯 / 新增持倉**")
    st.caption("直接在表格輸入或新增列，按儲存後寫入 Supabase。")
    cols = ["id","platform","asset_type","name","ticker","fund_code","fund_pattern",
            "currency","units","avg_cost","monthly_dividend_per_unit","note"]
    base = current_positions[current_positions["platform"] == platform_name][cols].copy() \
           if not current_positions.empty else pd.DataFrame(columns=cols)
    blank = {"id": None, "platform": platform_name,
             "asset_type": "基金" if platform_name in ["基富通","渣打基金","台新基金"] else platform_name,
             "name":"","ticker":"","fund_code":"",
             "fund_pattern": "yp010001" if platform_name in ["基富通","渣打基金","台新基金"] else "",
             "currency": "TWD" if platform_name in ["台股","基富通"] else "USD",
             "units":0.0,"avg_cost":0.0,"monthly_dividend_per_unit":0.0,"note":""}
    base = pd.concat([base, pd.DataFrame([blank])], ignore_index=True)
    edited = st.data_editor(
        base, use_container_width=True, hide_index=True, height=320, num_rows="dynamic",
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "platform": st.column_config.SelectboxColumn("平台", options=PLATFORMS, required=True),
            "asset_type": st.column_config.SelectboxColumn("類型", options=ASSET_TYPES, required=True),
            "currency": st.column_config.SelectboxColumn("幣別", options=CURRENCIES, required=True),
            "units": st.column_config.NumberColumn("單位數/股數", min_value=0, step=1.0, format="%.4f"),
            "avg_cost": st.column_config.NumberColumn("平均成本（原幣）", min_value=0, step=0.01, format="%.4f"),
            "monthly_dividend_per_unit": st.column_config.NumberColumn("每單位月配息", min_value=0, step=0.0001, format="%.4f"),
            "ticker": st.column_config.TextColumn("股票代碼"),
            "fund_code": st.column_config.TextColumn("基金代號"),
            "fund_pattern": st.column_config.TextColumn("基金 pattern"),
            "name": st.column_config.TextColumn("產品名稱"),
            "note": st.column_config.TextColumn("備註"),
        }, key=editor_key,
    )
    c1, c2, c3 = st.columns([1, 1, 2])
    if c1.button("💾 儲存", key=f"save_{editor_key}"):
        update_positions(edited)
        st.success("已儲存")
        st.rerun()
    copy_id = c2.number_input("複製 ID", value=0, step=1, key=f"copy_{editor_key}")
    if c2.button("📋 複製", key=f"copybtn_{editor_key}") and copy_id:
        row = current_positions[current_positions["id"] == int(copy_id)]
        if not row.empty:
            r = row.iloc[0].to_dict(); r.pop("id", None)
            r["name"] = str(r.get("name","")) + "（複製）"
            add_position(r); st.success("已複製"); st.rerun()
    del_id = c3.number_input("刪除 ID", value=0, step=1, key=f"del_{editor_key}")
    if c3.button("🗑️ 刪除", key=f"delbtn_{editor_key}") and del_id:
        delete_position(int(del_id)); st.success(f"已刪除 ID {del_id}"); st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# APP 主體
# ════════════════════════════════════════════════════════════════════════════

# ── 導覽列 ──
st.markdown(f"""
<div class="j-navbar">
  <div class="j-logo-mark">◈</div>
  <div>
    <div class="j-nav-title">Jenny 投資系統</div>
    <div class="j-nav-sub">Supabase · 即時市值</div>
  </div>
  <div class="j-nav-sep"></div>
  <div class="j-nav-badge">v {APP_VERSION.split("-v")[-1]}</div>
</div>
""", unsafe_allow_html=True)

# ── 初始化 ──
try:
    seed_presets()
except Exception as e:
    st.error(f"Supabase 初始化失敗：{e}")
    st.stop()

positions = load_positions()

# ── 排序選擇（全域）──
sort_col1, sort_col2, sort_col3 = st.columns([3, 1, 1])
with sort_col1:
    sort_key = st.radio(
        "排序", list(SORT_OPTIONS.keys()),
        horizontal=True, label_visibility="collapsed",
        index=2,  # 預設台幣市值↓
    )
with sort_col3:
    if st.button("🔄 更新即時價格"):
        st.cache_data.clear()
        st.rerun()

# ── 載入並計算 ──
with st.spinner("抓取即時價格與匯率…"):
    enriched = enrich(positions)

total_value = to_float(enriched["台幣市值"].sum()) if not enriched.empty and "台幣市值" in enriched else 0
total_cost  = to_float(enriched["台幣成本"].sum()) if not enriched.empty and "台幣成本" in enriched else 0
total_pnl   = to_float(enriched["損益"].sum())     if not enriched.empty and "損益" in enriched else 0
total_div   = to_float(enriched["每月配息"].sum())  if not enriched.empty and "每月配息" in enriched else 0
total_rate  = total_pnl / total_cost if total_cost else None
delta_cls   = "pos" if (total_pnl or 0) >= 0 else "neg"

# ── 指標列 ──
st.markdown(f"""
<div class="j-metrics-bar">
  <div class="j-metric">
    <div class="j-metric-label">總台幣市值</div>
    <div class="j-metric-value">{money(total_value)}</div>
    <div class="j-metric-delta {delta_cls}">{signed_money(total_pnl)} &nbsp;·&nbsp; {pct(total_rate, signed=True)}</div>
  </div>
  <div class="j-metric">
    <div class="j-metric-label">總台幣成本</div>
    <div class="j-metric-value">{money(total_cost)}</div>
    <div class="j-metric-delta neu">投入成本</div>
  </div>
  <div class="j-metric">
    <div class="j-metric-label">每月配息</div>
    <div class="j-metric-value">{money(total_div)}</div>
    <div class="j-metric-delta neu">台幣 / 月</div>
  </div>
  <div class="j-metric">
    <div class="j-metric-label">投資筆數</div>
    <div class="j-metric-value">{len(positions):,}</div>
    <div class="j-metric-delta neu">持倉產品</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Tab ──
show_cols = ["id","platform","asset_type","name","ticker","fund_code","currency",
             "units","avg_cost","即時價格/淨值","匯率","台幣成本","台幣市值",
             "損益","損益率","每月配息","狀態"]

tabs = st.tabs(["◈ 總覽", "📈 台股", "🇺🇸 美股", "🟧 基富通", "💹 渣打基金", "🟥 台新基金", "💱 匯率", "📡 基金市值", "✏️ 編輯"])

# ────────────────────────────────────────────────────────────────────────────
# TAB 0 — 總覽
# ────────────────────────────────────────────────────────────────────────────
with tabs[0]:
    st.markdown('<div class="j-section-title">資產配置總覽</div>', unsafe_allow_html=True)
    st.markdown('<div class="j-section-sub">所有平台即時計算結果</div>', unsafe_allow_html=True)

    if not enriched.empty:
        summary = enriched.groupby("platform", dropna=False).agg(
            台幣成本=("台幣成本","sum"),
            台幣市值=("台幣市值","sum"),
            損益=("損益","sum"),
            每月配息=("每月配息","sum"),
            筆數=("id","count"),
        ).reset_index()
        summary["損益率"] = summary.apply(
            lambda r: r["損益"] / r["台幣成本"] if r["台幣成本"] else None, axis=1)

        left, right = st.columns([1, 1.6])
        with left:
            st.markdown('<div class="j-card"><div class="j-card-title">平台市值分布</div>', unsafe_allow_html=True)
            st.bar_chart(summary.set_index("platform")[["台幣市值"]], height=280, color="#10b981")
            st.markdown("</div>", unsafe_allow_html=True)
        with right:
            st.markdown('<div class="j-card"><div class="j-card-title">平台彙總</div>', unsafe_allow_html=True)
            st.dataframe(format_df(summary), use_container_width=True, hide_index=True, height=280)
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="j-card"><div class="j-card-title">全部持倉明細</div>', unsafe_allow_html=True)
        sorted_all = sort_df(enriched, sort_key)
        valid_cols = [c for c in show_cols if c in sorted_all.columns]
        st.dataframe(format_df(sorted_all[valid_cols]), use_container_width=True, hide_index=True, height=500)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("尚無持倉資料，請到「✏️ 編輯」頁新增。")

# ────────────────────────────────────────────────────────────────────────────
# TAB 1-5 — 各平台
# ────────────────────────────────────────────────────────────────────────────
for idx, platform in enumerate(PLATFORMS, start=1):
    with tabs[idx]:
        st.markdown(f'<div class="j-section-title">{platform}</div>', unsafe_allow_html=True)
        view = enriched[enriched["platform"] == platform].copy() if not enriched.empty else pd.DataFrame()

        if view.empty:
            st.info(f"尚無 {platform} 持倉資料。")
        else:
            m1, m2, m3, m4 = st.columns(4)
            plat_val  = to_float(view["台幣市值"].sum())
            plat_cost = to_float(view["台幣成本"].sum())
            plat_pnl  = to_float(view["損益"].sum())
            plat_div  = to_float(view["每月配息"].sum())
            plat_rate = plat_pnl / plat_cost if plat_cost else None
            m1.metric("台幣市值", money(plat_val))
            m2.metric("台幣成本", money(plat_cost))
            m3.metric("損益",     signed_money(plat_pnl), delta=pct(plat_rate, signed=True))
            m4.metric("每月配息", money(plat_div))

            st.markdown('<div class="j-card"><div class="j-card-title">即時計算結果</div>', unsafe_allow_html=True)
            sorted_view = sort_df(view, sort_key)
            valid_cols  = [c for c in show_cols if c in sorted_view.columns]
            st.dataframe(format_df(sorted_view[valid_cols]), use_container_width=True, hide_index=True, height=360)
            st.markdown("</div>", unsafe_allow_html=True)

        editable_platform_table(platform, positions, f"editor_{platform}")

# ────────────────────────────────────────────────────────────────────────────
# TAB 6 — 匯率
# ────────────────────────────────────────────────────────────────────────────
with tabs[6]:
    st.markdown('<div class="j-section-title">即時匯率</div>', unsafe_allow_html=True)
    st.markdown('<div class="j-section-sub">Yahoo Finance 即時報價（5 分鐘快取）</div>', unsafe_allow_html=True)
    fx_rows = []
    cols6 = st.columns(len(CURRENCIES))
    for i, cur in enumerate(CURRENCIES):
        rate, status = fetch_fx(cur)
        cols6[i].metric(f"1 {cur} → TWD", money(rate, 4),
                        delta="即時 ✓" if status == "ok" else f"⚠ {status}")
        fx_rows.append({"幣別": cur, "對台幣匯率": money(rate, 4),
                        "狀態": "✓" if status == "ok" else f"⚠ {status}"})
    st.markdown('<div class="j-card" style="margin-top:16px"><div class="j-card-title">匯率明細</div>', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(fx_rows), use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────────────
# TAB 7 — 基金市值（全部一次抓）
# ────────────────────────────────────────────────────────────────────────────
with tabs[7]:
    st.markdown('<div class="j-section-title">📡 基金最新淨值</div>', unsafe_allow_html=True)
    st.markdown('<div class="j-section-sub">MoneyDJ 即時 NAV · 自動換算台幣（5 分鐘快取）</div>', unsafe_allow_html=True)

    prog = st.progress(0, text="抓取基金淨值中…")
    fund_data = []
    fx_c: dict[str, tuple] = {}
    codes = list(FUND_PRESETS.items())
    for i, (code, (name, pattern, currency, platform)) in enumerate(codes):
        nav, nav_status = fetch_fund_nav(code, pattern)
        if currency not in fx_c:
            fx_c[currency] = fetch_fx(currency)
        fx, fx_status = fx_c[currency]
        twd = nav * fx if nav is not None and fx is not None else None
        fund_data.append({
            "平台": platform, "基金名稱": name, "代號": code, "幣別": currency,
            "最新淨值": money(nav, 4), "匯率": money(fx, 4),
            "台幣換算": money(twd, 2),
            "狀態": "✓" if nav_status == "ok" and fx_status == "ok" else f"⚠ {nav_status}",
            "_twd": twd or 0,
        })
        prog.progress((i + 1) / len(codes), text=f"抓取中… {i+1}/{len(codes)}  {name[:12]}")
    prog.empty()

    fund_df = pd.DataFrame(fund_data)

    # 小計
    total_fund_twd = fund_df["_twd"].sum()
    st.metric("所有基金台幣淨值合計（NAV × 匯率 × 1單位）", money(total_fund_twd, 2))

    # 依平台分組顯示
    for plat in ["基富通", "渣打基金", "台新基金"]:
        plat_df = fund_df[fund_df["平台"] == plat].copy()
        if plat_df.empty:
            continue
        st.markdown(f'<div class="j-card"><div class="j-card-title">{plat}</div>', unsafe_allow_html=True)
        display_cols = ["基金名稱", "代號", "幣別", "最新淨值", "匯率", "台幣換算", "狀態"]
        st.dataframe(plat_df[display_cols], use_container_width=True, hide_index=True, height=200)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="j-card"><div class="j-card-title">全部基金合計</div>', unsafe_allow_html=True)
    display_cols = ["平台", "基金名稱", "代號", "幣別", "最新淨值", "匯率", "台幣換算", "狀態"]
    st.dataframe(fund_df[display_cols], use_container_width=True, hide_index=True, height=420)
    st.markdown("</div>", unsafe_allow_html=True)

    if not HAS_BS4:
        st.warning("請安裝 beautifulsoup4 與 lxml：`pip install beautifulsoup4 lxml`")

# ────────────────────────────────────────────────────────────────────────────
# TAB 8 — 新增 / 編輯
# ────────────────────────────────────────────────────────────────────────────
with tabs[8]:
    st.markdown('<div class="j-section-title">新增 / 編輯持倉</div>', unsafe_allow_html=True)
    st.markdown('<div class="j-section-sub">在此 key 資料：單位數、成本、代碼等。各平台頁是即時計算結果不能直接編輯。</div>', unsafe_allow_html=True)

    with st.expander("➕ 快速新增單筆", expanded=False):
        with st.form("add_single", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            platform_   = c1.selectbox("平台", PLATFORMS)
            asset_type_ = c2.selectbox("類型", ASSET_TYPES)
            currency_   = c3.selectbox("幣別", CURRENCIES)
            name_       = st.text_input("產品名稱")
            c4, c5, c6 = st.columns(3)
            ticker_     = c4.text_input("股票代碼（台股例：1476.TW）")
            fund_code_  = c5.text_input("基金代號（例：acft94）")
            fund_pat_   = c6.text_input("基金 pattern（yp010000 / yp010001）")
            c7, c8, c9 = st.columns(3)
            units_      = c7.number_input("單位數/股數", value=0.0, step=1.0)
            avg_cost_   = c8.number_input("平均成本（原幣）", value=0.0, step=0.01)
            md_         = c9.number_input("每單位月配息", value=0.0, step=0.0001, format="%.4f")
            note_       = st.text_input("備註")
            if st.form_submit_button("新增"):
                if not name_:
                    st.error("請輸入產品名稱")
                else:
                    add_position({"platform":platform_,"asset_type":asset_type_,"name":name_,
                                  "ticker":ticker_,"fund_code":fund_code_,"fund_pattern":fund_pat_,
                                  "currency":currency_,"units":units_,"avg_cost":avg_cost_,
                                  "monthly_dividend_per_unit":md_,"note":note_})
                    st.success("已新增"); st.rerun()

    st.markdown("**全部持倉管理表**")
    cols_ = ["id","platform","asset_type","name","ticker","fund_code","fund_pattern",
             "currency","units","avg_cost","monthly_dividend_per_unit","note"]
    base_ = positions[cols_].copy() if not positions.empty else pd.DataFrame(columns=cols_)
    edited_ = st.data_editor(
        base_, use_container_width=True, hide_index=True, height=560, num_rows="dynamic",
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "platform": st.column_config.SelectboxColumn("平台", options=PLATFORMS, required=True),
            "asset_type": st.column_config.SelectboxColumn("類型", options=ASSET_TYPES, required=True),
            "currency": st.column_config.SelectboxColumn("幣別", options=CURRENCIES, required=True),
            "units": st.column_config.NumberColumn("單位數/股數", min_value=0, step=1.0, format="%.4f"),
            "avg_cost": st.column_config.NumberColumn("平均成本", min_value=0, step=0.01, format="%.4f"),
            "monthly_dividend_per_unit": st.column_config.NumberColumn("每單位月配息", min_value=0, step=0.0001, format="%.4f"),
        }, key="editor_main",
    )
    ca, cb, cc = st.columns([1, 1, 2])
    if ca.button("💾 儲存表格"):
        update_positions(edited_); st.success("已儲存"); st.rerun()
    cp_id = cb.number_input("複製 ID", value=0, step=1, key="cp_main")
    if cb.button("📋 複製", key="cpbtn_main") and cp_id:
        row = positions[positions["id"] == int(cp_id)]
        if not row.empty:
            r = row.iloc[0].to_dict(); r.pop("id", None)
            r["name"] = str(r.get("name","")) + "（複製）"
            add_position(r); st.success("已複製"); st.rerun()
    dl_id = cc.number_input("刪除 ID", value=0, step=1, key="dl_main")
    if cc.button("🗑️ 刪除", key="dlbtn_main") and dl_id:
        delete_position(int(dl_id)); st.success(f"已刪除 {dl_id}"); st.rerun()
