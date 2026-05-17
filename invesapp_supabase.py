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


APP_VERSION = "2026-05-18-supabase-v9-paste-order-repair"

DEFAULT_SUPABASE_URL = "https://qrvdztqyzxlsfskdgiqp.supabase.co"

PLATFORMS = ["台股", "美股", "基富通", "渣打基金", "台新基金"]
ASSET_TYPES = ["台股", "美股", "基金"]
CURRENCIES = ["TWD", "USD", "CNY", "JPY", "ZAR"]

FX_PAIRS = {
    "TWD": None,
    "USD": "USDTWD=X",
    "CNY": "CNYTWD=X",
    "JPY": "JPYTWD=X",
    "ZAR": "ZARTWD=X",
}

TW_PRESETS = {
    "儒鴻": "1476.TW",
    "大魯閣": "1432.TW",
    "中砂": "1560.TW",
    "中鴻": "2014.TW",
    "凱美": "2375.TW",
    "華碩": "2357.TW",
    "日勝生": "2547.TW",
    "晶華": "2707.TW",
    "中壽": "2823.TW",
    "凱基金": "2883.TW",
    "凱基金乙特": "2883B.TW",
    "聯陽": "3014.TW",
    "景碩": "3189.TW",
    "緯創": "3231.TW",
    "東隆興": "4401.TWO",
    "和碩": "4938.TW",
    "松翰": "5471.TWO",
    "智冠": "5478.TWO",
    "久元": "6261.TWO",
    "台塑化": "6505.TW",
    "上銀": "2049.TW",
    "元大高股息": "0056.TW",
    "元大台灣50": "0050.TW",
    "泰碩": "3338.TW",
    "尼得科超眾": "6230.TW",
    "立積": "4968.TW",
    "鈺齊-KY": "9802.TW",
    "東陽": "1319.TW",
    "華邦電": "2344.TW",
    "元大金": "2885.TW",
    "鴻海": "2317.TW",
    "長榮": "2603.TW",
    "長華*": "8070.TW",
    "群創": "3481.TW",
    "集盛": "1455.TW",
    "華新": "1605.TW",
    "第一銅": "2009.TW",
    "大聯大": "3702.TW",
    "富邦特選高股息30": "00900.TW",
    "群益台灣精選高息": "00919.TW",
    "富邦全球投等債": "00740B.TW",
    "群益半導體收益": "00927.TW",
    "華泰": "2329.TW",
    "圓剛": "2417.TW",
    "楠梓電": "2316.TW",
    "富邦台50": "006208.TW",
    "南亞科": "2408.TW",
    "欣興": "3037.TW",
    "京元電子": "2449.TW",
    "國巨": "2327.TW",
}

TW_STOCK_NAMES_DUPLICATE = [
    "儒鴻","儒鴻","大魯閣","中砂","中砂","中鴻","凱美","華碩",
    "日勝生","日勝生","晶華","晶華","中壽","中壽","凱基金",
    "凱基金乙特","聯陽","景碩","景碩","景碩","緯創","緯創",
    "緯創","緯創","緯創","緯創","緯創","東隆興","東隆興",
    "和碩","松翰","松翰","智冠","久元","久元","久元",
    "台塑化","台塑化","上銀","元大高股息","元大台灣50",
    "泰碩","尼得科超眾","立積","立積","鈺齊-KY","東陽",
    "東陽","東陽","東陽","中砂","中砂","中砂","中砂",
    "中砂","中砂","中砂","中砂","華邦電","華邦電",
    "元大金","元大金","元大金","元大金","元大金",
    "元大金","元大金","元大金","鴻海","長榮","長華*",
    "群創","集盛","華新","第一銅","大聯大",
    "富邦特選高股息30","富邦特選高股息30",
    "群益台灣精選高息","群益台灣精選高息",
    "富邦全球投等債","群益半導體收益",
    "華泰","圓剛","圓剛","中鴻","楠梓電",
    "富邦台50","南亞科","欣興","京元電子","國巨"
]

FUND_PRESETS = {
    "acft94": ("富蘭克林華美新興國家固定收益B-新臺幣","yp010000","TWD","基富通"),
    "acai222": ("柏瑞新興邊境非投資等級債券基金-B類型","yp010000","TWD","基富通"),
    "acft99": ("富蘭克林華美新興國家固定收益B-人民幣","yp010000","CNY","基富通"),
    "shzx0": ("貝萊德全球智慧數據股票入息A6日圓","yp010001","JPY","基富通"),
    "TLZO3": ("安聯收益成長AMgi月收（日圓避險）","yp010001","JPY","基富通"),
    "acob36": ("大華銀新加坡房地產收益基金-美元月配","yp010000","USD","渣打基金"),
    "pizn8": ("東方匯理新興市場債券A美元（月配）","yp010001","USD","渣打基金"),
    "pizo1": ("東方匯理新興市場債券U美元（月配）","yp010001","USD","渣打基金"),
    "pizm9": ("東方匯理新興市場債券U南非幣（月配）","yp010001","ZAR","台新基金"),
    "anzb6": ("高盛新興市場債券Y股美元","yp010001","USD","渣打基金"),
    "ANZH2": ("高盛新興市場債券Y南非幣對沖（月配）","yp010001","ZAR","台新基金"),
}

INVESTMENT_ITEMS_DUPLICATE = [
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '富蘭克林華美新興國家固定收益基金B-新臺幣', '', 'acft94', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'TWD', '基金', '柏瑞新興邊境非投資等級債券證券投資信託基金-B類型', '', 'acai222', 'yp010000'),
    ('基富通', 'CNY', '基金', '富蘭克林華美新興國家固定收益證劵投資信託基金B-人民幣', '', 'acft99', 'yp010000'),
    ('基富通', 'CNY', '基金', '富蘭克林華美新興國家固定收益證劵投資信託基金B-人民幣', '', 'acft99', 'yp010000'),
    ('基富通', 'JPY', '基金', '貝萊德全球智慧數據股票入息Hedged A6日圓穩定配息', '', 'shzx0', 'yp010001'),
    ('基富通', 'JPY', '基金', '貝萊德全球智慧數據股票入息Hedged A6日圓穩定配息', '', 'shzx0', 'yp010001'),
    ('基富通', 'JPY', '基金', '安聯收益成長基金-AMgi月收總收益類股(日圓避險', '', 'TLZO3', 'yp010001'),
    ('基富通', 'JPY', '基金', '安聯收益成長基金-AMgi月收總收益類股(日圓避險', '', 'TLZO3', 'yp010001'),
    ('基富通', 'JPY', '基金', '安聯收益成長基金-AMgi月收總收益類股(日圓避險', '', 'TLZO3', 'yp010001'),
    ('美股', 'USD', '美股', 'PYPL', 'PYPL', '', ''),
    ('美股', 'USD', '美股', 'PYPL', 'PYPL', '', ''),
    ('美股', 'USD', '美股', 'PYPL', 'PYPL', '', ''),
    ('美股', 'USD', '美股', 'XYZ', 'XYZ', '', ''),
    ('渣打基金', 'USD', '基金', '大華銀新加坡房地產收益基金-美元月配(後收)', '', 'acob36', 'yp010000'),
    ('渣打基金', 'USD', '基金', '東方匯理基金新興市場債券A美元(穩定月配息)', '', 'pizn8', 'yp010001'),
    ('渣打基金', 'USD', '基金', '東方匯理基金新興市場債券A美元(穩定月配息)', '', 'pizn8', 'yp010001'),
    ('渣打基金', 'USD', '基金', '東方匯理基金新興市場債券A美元(穩定月配息)', '', 'pizn8', 'yp010001'),
    ('渣打基金', 'USD', '基金', '東方匯理基金新興市場債券A美元(穩定月配息)', '', 'pizn8', 'yp010001'),
    ('渣打基金', 'ZAR', '基金', '東方匯理基金新興市場債券U 南非幣(穩定月配息)', '', 'pizm9', 'yp010001'),
    ('台新基金', 'USD', '基金', '高盛新興市場債券基金Y股美元', '', 'anzb6', 'yp010001'),
    ('台新基金', 'USD', '基金', '東方匯理基金新興市場債券U 美元(穩定月配息)', '', 'pizo1', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)', '', 'ANZH2', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)', '', 'ANZH2', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)', '', 'ANZH2', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)', '', 'ANZH2', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)', '', 'pizm9', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)', '', 'pizm9', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)', '', 'pizm9', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)', '', 'pizm9', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)', '', 'pizm9', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)', '', 'pizm9', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)', '', 'pizm9', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)', '', 'pizm9', 'yp010001'),
    ('台新基金', 'ZAR', '基金', '東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)', '', 'pizm9', 'yp010001'),
]

st.set_page_config(
    page_title="Jenny 投資系統",
    page_icon="📈",
    layout="wide"
)

st.markdown("""
<style>
.stApp {
    background:#f7faf9;
    color:#0f2b20;
}

.block-container {
    padding-top:0.8rem;
    max-width:1600px;
}

.fixed-top {
    position:sticky;
    top:0;
    z-index:999;
    background:#f7faf9;
    padding:8px 0 12px 0;
    border-bottom:1px solid #e4ece8;
}

.hero {
    background:#fff;
    border:1px solid #e5eae8;
    border-radius:16px;
    padding:16px 20px;
    box-shadow:0 1px 6px rgba(0,0,0,.05);
}

[data-testid="stMetric"] {
    background:#fff !important;
    border:1px solid #e5eae8 !important;
    border-radius:14px !important;
    padding:18px 20px !important;
}

[data-testid="stDataFrame"] {
    background:#fff !important;
    border:1px solid #e5eae8 !important;
    border-radius:14px !important;
}

.stButton > button {
    background:#10b981 !important;
    color:#fff !important;
    border-radius:10px !important;
    border:0 !important;
}
</style>
""", unsafe_allow_html=True)



def get_secret(name: str, default: str = "") -> str:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.environ.get(name, default)


@st.cache_resource(show_spinner=False)
def supabase_client() -> Client:
    url = get_secret("SUPABASE_URL", DEFAULT_SUPABASE_URL)
    key = get_secret("SUPABASE_ANON_KEY", "")

    if not key:
        st.error("缺少 SUPABASE_ANON_KEY")
        st.stop()

    return create_client(url, key)


def normalize_number(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or pd.isna(v):
            return default
        if isinstance(v, str):
            v = v.replace(",", "").replace("$", "").strip()
            if v in {"", "-", "—", "nan", "None"}:
                return default
        return float(v)
    except Exception:
        return default


def normalize_text(v: Any, default: str = "") -> str:
    if v is None:
        return default
    try:
        if pd.isna(v):
            return default
    except Exception:
        pass
    return str(v).strip()


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    defaults = {
        "id": None,
        "sort_order": 0,
        "platform": "台股",
        "asset_type": "台股",
        "name": "",
        "ticker": "",
        "fund_code": "",
        "fund_pattern": "",
        "currency": "TWD",
        "original_units": 0.0,
        "units": 0.0,
        "corporate_action": "",
        "avg_cost": 0.0,
        "total_cost_input": 0.0,
        "monthly_dividend_per_unit": 0.0,
        "note": "",
    }
    out = df.copy()
    for col, default in defaults.items():
        if col not in out.columns:
            out[col] = default
    return out


def normalize_payload(r: dict[str, Any] | pd.Series) -> dict[str, Any]:
    platform = normalize_text(r.get("platform", "台股"), "台股")
    asset_type = normalize_text(r.get("asset_type", ""), "")
    if not asset_type:
        asset_type = "基金" if platform in ["基富通", "渣打基金", "台新基金"] else platform

    currency = normalize_text(r.get("currency", ""), "")
    if not currency:
        currency = "TWD" if platform in ["台股", "基富通"] else "USD"

    name = normalize_text(r.get("name", ""), "")
    ticker = normalize_text(r.get("ticker", ""), "")
    fund_code = normalize_text(r.get("fund_code", ""), "")
    fund_pattern = normalize_text(r.get("fund_pattern", ""), "")

    if platform == "台股" and not ticker and name in TW_PRESETS:
        ticker = TW_PRESETS.get(name, "")

    return {
        "sort_order": normalize_number(r.get("sort_order", 0), 0),
        "platform": platform,
        "asset_type": asset_type,
        "name": name,
        "ticker": ticker,
        "fund_code": fund_code,
        "fund_pattern": fund_pattern,
        "currency": currency,
        "original_units": normalize_number(r.get("original_units", 0), 0),
        "units": normalize_number(r.get("units", 0), 0),
        "corporate_action": normalize_text(r.get("corporate_action", ""), ""),
        "avg_cost": normalize_number(r.get("avg_cost", 0), 0),
        "total_cost_input": normalize_number(r.get("total_cost_input", 0), 0),
        "monthly_dividend_per_unit": normalize_number(r.get("monthly_dividend_per_unit", 0), 0),
        "note": normalize_text(r.get("note", ""), ""),
    }


def load_positions() -> pd.DataFrame:
    result = (
        supabase_client()
        .table("positions")
        .select("*")
        .order("sort_order")
        .order("id")
        .execute()
    )
    return ensure_columns(pd.DataFrame(result.data or []))


def add_position(row: dict[str, Any]) -> None:
    payload = normalize_payload(row)
    if payload.get("name"):
        supabase_client().table("positions").insert(payload).execute()


def update_positions(df: pd.DataFrame) -> None:
    sb = supabase_client()
    df = ensure_columns(df)

    for _, r in df.iterrows():
        rid = r.get("id", None)
        is_new = pd.isna(rid) or str(rid).strip() == ""
        payload = normalize_payload(r)

        if not payload["name"]:
            continue

        if is_new:
            sb.table("positions").insert(payload).execute()
        else:
            sb.table("positions").update(payload).eq("id", int(float(rid))).execute()


def delete_position(position_id: int) -> None:
    supabase_client().table("positions").delete().eq("id", int(position_id)).execute()


def mark_position_sold(position_id: int) -> None:
    supabase_client().table("positions").update({
        "units": 0,
        "note": "已賣出 / 已結清",
    }).eq("id", int(position_id)).execute()


def to_float(v: Any) -> float | None:
    try:
        if v is None or pd.isna(v):
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
    if n is None:
        return "-"
    return f"{n:,.{decimals}f}"


def signed_money(v: Any) -> str:
    n = to_float(v)
    if n is None:
        return "-"
    return f"{n:+,.0f}"


def pct(v: Any) -> str:
    n = to_float(v)
    if n is None:
        return "-"
    return f"{n:.2%}"


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
                price = hist["Close"].dropna().iloc[-1]

        if price is None:
            return None, "無價格"

        return float(price), "ok"

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
                    nav = cells[1].get_text(strip=True).replace(",", "")
                    return float(nav), "ok"

        return None, "找不到淨值"

    except Exception as e:
        return None, str(e)[:50]


@st.cache_data(ttl=300, show_spinner=False)
def fetch_fx(currency: str) -> tuple[float | None, str]:
    currency = normalize_text(currency, "TWD")
    if currency == "TWD":
        return 1.0, "ok"
    pair = FX_PAIRS.get(currency)
    if not pair:
        return None, "未知幣別"
    return fetch_yahoo_price(pair)


def calculate_cost_and_value(r: pd.Series, latest_price: float | None, fx: float | None) -> dict[str, Any]:
    """
    通用算法：
    1. 成本：優先採用 total_cost_input；沒有總投入成本時，用 original_units * avg_cost。
    2. 市值：一律採用目前持有 units * 最新價格/淨值 * 匯率。
    3. 不再用總投入成本反推現在股數，避免被 Supabase 舊資料或 0 值弄亂。
    """
    original_units = normalize_number(r.get("original_units", 0), 0)
    units = normalize_number(r.get("units", 0), 0)
    avg_cost = normalize_number(r.get("avg_cost", 0), 0)
    total_cost_input = normalize_number(r.get("total_cost_input", 0), 0)

    cost_original_currency = total_cost_input if total_cost_input > 0 else original_units * avg_cost
    value_original_currency = units * latest_price if latest_price is not None else None

    twd_cost = cost_original_currency * fx if fx is not None else None
    twd_value = value_original_currency * fx if value_original_currency is not None and fx is not None else None

    pnl = twd_value - twd_cost if twd_value is not None and twd_cost is not None else None
    pnl_rate = pnl / twd_cost if pnl is not None and twd_cost else None

    return {
        "成本原幣": cost_original_currency,
        "市值原幣": value_original_currency,
        "台幣成本": twd_cost,
        "台幣市值": twd_value,
        "損益": pnl,
        "損益率": pnl_rate,
    }


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_columns(df)
    if df.empty:
        return df

    rows = []

    for _, r in df.iterrows():
        currency = normalize_text(r.get("currency", "TWD"), "TWD")
        asset_type = normalize_text(r.get("asset_type", ""), "")

        if asset_type in {"台股", "美股"}:
            price, p_status = fetch_yahoo_price(str(r.get("ticker") or ""))
        else:
            price, p_status = fetch_fund_nav(
                str(r.get("fund_code") or ""),
                str(r.get("fund_pattern") or ""),
            )

        fx, fx_status = fetch_fx(currency)
        calc = calculate_cost_and_value(r, price, fx)

        units = normalize_number(r.get("units", 0), 0)
        monthly_div = units * normalize_number(r.get("monthly_dividend_per_unit", 0), 0)
        monthly_div_twd = monthly_div * fx if fx is not None else None

        out = dict(r)
        out.update(calc)
        out.update({
            "即時價格/淨值": price,
            "匯率": fx,
            "每月配息": monthly_div_twd,
            "狀態": "✓" if p_status == "ok" and fx_status == "ok" else f"價格:{p_status} 匯率:{fx_status}",
        })
        rows.append(out)

    return pd.DataFrame(rows)


def format_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    for c in ["即時價格/淨值", "匯率"]:
        if c in out:
            out[c] = out[c].apply(lambda x: money(x, 4))

    for c in ["成本原幣", "市值原幣", "台幣成本", "台幣市值", "損益", "每月配息"]:
        if c in out:
            out[c] = out[c].apply(money)

    if "損益率" in out:
        out["損益率"] = out["損益率"].apply(pct)

    rename_map = {
        "sort_order": "排序",
        "platform": "平台",
        "asset_type": "類型",
        "name": "名稱",
        "ticker": "股票代碼",
        "fund_code": "基金代號",
        "fund_pattern": "基金網址類型",
        "currency": "幣別",
        "original_units": "成本股數",
        "units": "現在股數",
        "avg_cost": "平均成本",
        "total_cost_input": "總投入成本",
        "monthly_dividend_per_unit": "每單位月配息",
        "corporate_action": "股數調整備註",
        "note": "備註",
    }

    return out.rename(columns=rename_map)


def seed_presets() -> None:
    existing = load_positions()
    if not existing.empty:
        return

    sort_order = 1

    for name in TW_STOCK_NAMES_DUPLICATE:
        add_position({
            "sort_order": sort_order,
            "platform": "台股",
            "asset_type": "台股",
            "name": name,
            "ticker": TW_PRESETS.get(name, ""),
            "fund_code": "",
            "fund_pattern": "",
            "currency": "TWD",
            "original_units": 0,
            "units": 0,
            "corporate_action": "",
            "avg_cost": 0,
            "total_cost_input": 0,
            "monthly_dividend_per_unit": 0,
            "note": f"預設台股清單：{name}",
        })
        sort_order += 1

    for platform, currency, asset_type, name, ticker, fund_code, fund_pattern in INVESTMENT_ITEMS_DUPLICATE:
        add_position({
            "sort_order": sort_order,
            "platform": platform,
            "asset_type": asset_type,
            "name": name,
            "ticker": ticker,
            "fund_code": fund_code,
            "fund_pattern": fund_pattern,
            "currency": currency,
            "original_units": 0,
            "units": 0,
            "corporate_action": "",
            "avg_cost": 0,
            "total_cost_input": 0,
            "monthly_dividend_per_unit": 0,
            "note": "預設投資清單",
        })
        sort_order += 1


def build_upload_template(positions: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "sort_order",
        "platform",
        "name",
        "avg_cost",
        "total_cost_input",
        "original_units",
        "units",
        "monthly_dividend_per_unit",
        "corporate_action",
    ]
    if positions.empty:
        return pd.DataFrame(columns=cols)
    return ensure_columns(positions)[cols].sort_values(["sort_order"]).copy()


def read_uploaded_table(uploaded_file) -> pd.DataFrame:
    filename = uploaded_file.name.lower()
    if filename.endswith(".csv"):
        try:
            return pd.read_csv(uploaded_file, encoding="utf-8-sig")
        except UnicodeDecodeError:
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file, encoding="big5")
    if filename.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)
    raise ValueError("只支援 CSV / Excel 檔案")


def apply_batch_update(upload_df: pd.DataFrame, current_positions: pd.DataFrame) -> tuple[int, int, list[str]]:
    sb = supabase_client()
    current = ensure_columns(current_positions)

    if "sort_order" not in upload_df.columns:
        raise ValueError("上傳檔案必須包含 sort_order 欄位，因為名稱可能重複。")

    required_cols = ["sort_order", "platform", "name", "avg_cost", "total_cost_input", "original_units", "units"]
    missing = [c for c in required_cols if c not in upload_df.columns]
    if missing:
        raise ValueError("上傳檔案缺少欄位：" + ", ".join(missing))

    updated = 0
    inserted = 0
    skipped: list[str] = []

    current_by_order = {}
    if not current.empty:
        for _, row in current.iterrows():
            so = normalize_number(row.get("sort_order", 0), 0)
            if so:
                current_by_order[so] = row

    for i, r in upload_df.iterrows():
        payload = normalize_payload(r)
        if not payload["name"]:
            skipped.append(f"第 {i + 2} 列：name 空白")
            continue

        so = payload["sort_order"]
        if not so:
            skipped.append(f"第 {i + 2} 列：sort_order 空白或 0")
            continue

        old_row = current_by_order.get(so)
        if old_row is not None:
            merged = normalize_payload(old_row)
            merged.update(payload)
            sb.table("positions").update(merged).eq("id", int(old_row["id"])).execute()
            updated += 1
        else:
            sb.table("positions").insert(payload).execute()
            inserted += 1

    return updated, inserted, skipped



def canonical_order_rows() -> list[dict[str, Any]]:
    """
    預設順序表。只用來修復 sort_order，不會修改成本、股數、名稱、代碼。
    重複名稱用目前資料中的 id 由小到大對應。
    """
    rows: list[dict[str, Any]] = []
    order = 1

    for name in TW_STOCK_NAMES_DUPLICATE:
        rows.append({
            "target_order": order,
            "platform": "台股",
            "asset_type": "台股",
            "name": name,
            "currency": "TWD",
        })
        order += 1

    for platform, currency, asset_type, name, ticker, fund_code, fund_pattern in INVESTMENT_ITEMS_DUPLICATE:
        rows.append({
            "target_order": order,
            "platform": platform,
            "asset_type": asset_type,
            "name": name,
            "currency": currency,
        })
        order += 1

    return rows


def build_sort_repair_preview(current_positions: pd.DataFrame) -> pd.DataFrame:
    """
    依照 canonical_order_rows 修復 sort_order。
    duplicate rows 用 platform + name + currency 分組，按 id 由小到大配對。
    無法配對的列排到最後，保留原本相對順序。
    """
    current = ensure_columns(current_positions).copy()
    if current.empty:
        return pd.DataFrame()

    current["_old_sort_order"] = current["sort_order"].apply(lambda x: normalize_number(x, 0))
    current["_id_sort"] = current["id"].apply(lambda x: normalize_number(x, 999999999))
    current["_matched"] = False
    current["_new_sort_order"] = None
    current["_match_note"] = ""

    # Normalize for matching.
    current["_match_platform"] = current["platform"].astype(str).str.strip()
    current["_match_name"] = current["name"].astype(str).str.strip()
    current["_match_currency"] = current["currency"].astype(str).str.strip()

    # Build queue by key.
    buckets: dict[tuple[str, str, str], list[int]] = {}
    for idx, row in current.sort_values(["_id_sort"]).iterrows():
        key = (
            normalize_text(row.get("_match_platform", "")),
            normalize_text(row.get("_match_name", "")),
            normalize_text(row.get("_match_currency", "")),
        )
        buckets.setdefault(key, []).append(idx)

    for target in canonical_order_rows():
        key = (
            normalize_text(target["platform"]),
            normalize_text(target["name"]),
            normalize_text(target["currency"]),
        )
        bucket = buckets.get(key, [])
        if bucket:
            idx = bucket.pop(0)
            current.at[idx, "_new_sort_order"] = target["target_order"]
            current.at[idx, "_matched"] = True
            current.at[idx, "_match_note"] = "已依預設清單配對"

    # Unmatched rows go after canonical rows, sorted by old sort then id.
    next_order = len(canonical_order_rows()) + 1
    unmatched = current[current["_matched"] == False].sort_values(["_old_sort_order", "_id_sort"])
    for idx, row in unmatched.iterrows():
        current.at[idx, "_new_sort_order"] = next_order
        current.at[idx, "_match_note"] = "未在預設清單，排到最後"
        next_order += 1

    preview_cols = [
        "id",
        "platform",
        "currency",
        "name",
        "_old_sort_order",
        "_new_sort_order",
        "_match_note",
        "ticker",
        "fund_code",
        "units",
        "avg_cost",
        "total_cost_input",
    ]

    return current[preview_cols].rename(columns={
        "_old_sort_order": "目前排序",
        "_new_sort_order": "修復後排序",
        "_match_note": "修復狀態",
    })


def apply_sort_repair(preview_df: pd.DataFrame) -> int:
    if preview_df.empty:
        return 0

    sb = supabase_client()
    count = 0

    for _, r in preview_df.iterrows():
        rid = r.get("id")
        new_order = r.get("修復後排序")
        if pd.isna(rid) or pd.isna(new_order):
            continue
        sb.table("positions").update({
            "sort_order": float(new_order)
        }).eq("id", int(float(rid))).execute()
        count += 1

    return count



CURRENCY_ALIAS = {
    "台幣": "TWD",
    "新台幣": "TWD",
    "臺幣": "TWD",
    "TWD": "TWD",
    "人民幣": "CNY",
    "CNY": "CNY",
    "日幣": "JPY",
    "日圓": "JPY",
    "JPY": "JPY",
    "美金": "USD",
    "美元": "USD",
    "美股": "USD",
    "USD": "USD",
    "南非幣": "ZAR",
    "ZAR": "ZAR",
}


def normalize_match_name(value: Any) -> str:
    return normalize_text(value).lower().replace(" ", "")


def parse_pasted_order_text(text: str) -> list[dict[str, Any]]:
    """
    解析使用者貼上的三欄清單：
    平台<TAB或空白>幣別/類別<TAB或空白>名稱
    完全依貼上順序產生 target_order。
    """
    rows: list[dict[str, Any]] = []
    order = 1

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if "\t" in line:
            parts = [p.strip() for p in line.split("\t") if p.strip()]
        else:
            # 若沒有 tab，最多切成三段，第三段保留基金全名。
            parts = line.split(maxsplit=2)

        if len(parts) < 3:
            continue

        raw_platform, raw_currency, name = parts[0], parts[1], parts[2]
        currency = CURRENCY_ALIAS.get(raw_currency, raw_currency)

        rows.append({
            "target_order": order,
            "raw_platform": raw_platform,
            "raw_currency": raw_currency,
            "currency": currency,
            "name": name.strip(),
        })
        order += 1

    return rows


def platform_candidates_from_raw(raw_platform: str, raw_currency: str) -> list[str]:
    raw_platform = normalize_text(raw_platform)
    raw_currency = normalize_text(raw_currency)

    if raw_platform == "基富通":
        return ["基富通"]

    if raw_platform == "渣打":
        if raw_currency == "美股":
            return ["美股", "渣打"]
        return ["渣打基金", "渣打"]

    if raw_platform == "台新":
        return ["台新基金", "台新"]

    return [raw_platform]


def build_pasted_sort_repair_preview(current_positions: pd.DataFrame, pasted_text: str) -> pd.DataFrame:
    current = ensure_columns(current_positions).copy()
    targets = parse_pasted_order_text(pasted_text)

    if current.empty or not targets:
        return pd.DataFrame()

    current["_old_sort_order"] = current["sort_order"].apply(lambda x: normalize_number(x, 0))
    current["_id_sort"] = current["id"].apply(lambda x: normalize_number(x, 999999999))
    current["_matched"] = False
    current["_new_sort_order"] = None
    current["_match_note"] = ""

    # 分桶：平台 + 幣別 + 名稱。名稱忽略大小寫與空格。
    buckets: dict[tuple[str, str, str], list[int]] = {}
    for idx, row in current.sort_values(["_id_sort"]).iterrows():
        key = (
            normalize_text(row.get("platform", "")),
            normalize_text(row.get("currency", "")),
            normalize_match_name(row.get("name", "")),
        )
        buckets.setdefault(key, []).append(idx)

    for target in targets:
        name_key = normalize_match_name(target["name"])
        currency = normalize_text(target["currency"])
        candidates = platform_candidates_from_raw(target["raw_platform"], target["raw_currency"])

        matched_idx = None
        matched_key = None

        for platform in candidates:
            key = (platform, currency, name_key)
            if buckets.get(key):
                matched_idx = buckets[key].pop(0)
                matched_key = key
                break

        # 美股名稱可能存在 name=PYPL, ticker=PYPL；若名稱大小寫不同，上面已可配。
        if matched_idx is not None:
            current.at[matched_idx, "_new_sort_order"] = target["target_order"]
            current.at[matched_idx, "_matched"] = True
            current.at[matched_idx, "_match_note"] = (
                f"依貼上清單配對：{target['raw_platform']} / {target['raw_currency']}"
            )

    next_order = len(targets) + 1
    unmatched = current[current["_matched"] == False].sort_values(["_old_sort_order", "_id_sort"])
    for idx, row in unmatched.iterrows():
        current.at[idx, "_new_sort_order"] = next_order
        current.at[idx, "_match_note"] = "貼上清單未配對，保留在最後"
        next_order += 1

    preview_cols = [
        "id",
        "platform",
        "currency",
        "name",
        "_old_sort_order",
        "_new_sort_order",
        "_match_note",
        "ticker",
        "fund_code",
        "units",
        "avg_cost",
        "total_cost_input",
    ]

    return current[preview_cols].rename(columns={
        "_old_sort_order": "目前排序",
        "_new_sort_order": "修復後排序",
        "_match_note": "修復狀態",
    })


def pasted_order_repair_section(current_positions: pd.DataFrame) -> None:
    st.markdown("#### 📋 依你貼上的原始清單修復排序")
    st.warning("這裡只會更新 sort_order，不會改成本、股數、名稱、代碼。重複列數完全以你貼上的文字為準。")

    if current_positions.empty:
        st.info("目前沒有資料可修復。")
        return

    backup = ensure_columns(current_positions).sort_values(["sort_order", "id"], na_position="last")
    st.download_button(
        "⬇️ 先下載完整備份 CSV",
        data=backup.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
        file_name="positions_backup_before_paste_order_repair.csv",
        mime="text/csv",
        key="download_backup_before_paste_order_repair",
    )

    pasted = st.text_area(
        "貼上你的原始三欄清單：平台、幣別/類別、名稱",
        height=320,
        placeholder="基富通\t台幣\t富蘭克林華美新興國家固定收益基金B-新臺幣\n渣打\t美股\tpypl\n台新\t南非幣\t高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)",
        key="pasted_order_text",
    )

    targets = parse_pasted_order_text(pasted)
    if pasted:
        st.caption(f"已解析 {len(targets)} 列。這個列數會成為排序修復基準。")

    if not targets:
        return

    preview = build_pasted_sort_repair_preview(current_positions, pasted)

    if preview.empty:
        st.error("無法建立預覽，請確認貼上的文字至少有三欄。")
        return

    st.dataframe(preview, use_container_width=True, hide_index=True, height=520)

    not_matched_count = int(preview["修復狀態"].astype(str).str.contains("未配對").sum())
    if not_matched_count:
        st.warning(f"有 {not_matched_count} 筆目前資料未在貼上清單配對，會被排到最後。")

    st.download_button(
        "⬇️ 下載貼上清單排序修復預覽 CSV",
        data=preview.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
        file_name="pasted_order_repair_preview.csv",
        mime="text/csv",
        key="download_pasted_order_repair_preview",
    )

    confirm = st.checkbox("我已下載備份，確認只更新 sort_order", key="confirm_pasted_order_repair")
    if st.button("✅ 套用貼上清單排序", key="apply_pasted_order_repair", disabled=not confirm):
        n = apply_sort_repair(preview)
        st.success(f"已更新 {n} 筆 sort_order。")
        st.rerun()


def sort_repair_section(current_positions: pd.DataFrame) -> None:
    st.markdown("#### 🧭 修復排序")
    st.warning("這個功能只會更新 sort_order，不會修改成本、股數、名稱、ticker、fund_code。請先下載備份。")

    if current_positions.empty:
        st.info("目前沒有資料可修復。")
        return

    backup = ensure_columns(current_positions).sort_values(["sort_order", "id"], na_position="last")
    st.download_button(
        "⬇️ 修復前先下載完整備份 CSV",
        data=backup.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
        file_name="positions_backup_before_sort_repair.csv",
        mime="text/csv",
        key="download_backup_before_sort_repair",
    )

    preview = build_sort_repair_preview(current_positions)

    st.caption("預覽：系統會依預設清單順序重排。重複名稱用 id 由小到大對應。")
    st.dataframe(preview, use_container_width=True, hide_index=True, height=520)

    csv = preview.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        "⬇️ 下載排序修復預覽 CSV",
        data=csv,
        file_name="sort_repair_preview.csv",
        mime="text/csv",
        key="download_sort_repair_preview",
    )

    confirm = st.checkbox("我已下載備份，確認只更新 sort_order", key="confirm_sort_repair")
    if st.button("✅ 套用排序修復", key="apply_sort_repair", disabled=not confirm):
        n = apply_sort_repair(preview)
        st.success(f"已更新 {n} 筆 sort_order。")
        st.rerun()


def upload_batch_section(current_positions: pd.DataFrame) -> None:
    st.markdown("#### 📤 CSV / Excel 批次更新")
    st.caption("名稱可重複，更新依據是 sort_order。建議先下載目前資料，修改成本與股數後再上傳。")

    template = build_upload_template(current_positions)
    csv_bytes = template.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

    st.download_button(
        "⬇️ 下載目前資料批次更新範例 CSV",
        data=csv_bytes,
        file_name="positions_upload_template.csv",
        mime="text/csv",
    )

    uploaded = st.file_uploader("上傳 CSV / Excel", type=["csv", "xlsx", "xls"], key="batch_upload_file")

    if uploaded is not None:
        try:
            upload_df = read_uploaded_table(uploaded)
            st.dataframe(upload_df.head(50), use_container_width=True, hide_index=True)

            if st.button("✅ 執行批次更新", key="run_batch_update"):
                updated, inserted, skipped = apply_batch_update(upload_df, current_positions)
                st.success(f"批次更新完成：更新 {updated} 筆，新增 {inserted} 筆，略過 {len(skipped)} 筆。")
                if skipped:
                    st.warning("\n".join(skipped[:20]))
                st.rerun()

        except Exception as e:
            st.error(f"上傳檔案處理失敗：{e}")


def editable_platform_table(platform_name: str, current_positions: pd.DataFrame, editor_key: str) -> None:
    st.markdown("#### ✏️ 編輯 / 新增")
    st.caption("新增列請拉到表格最下方直接輸入；按儲存後會寫入 Supabase。")

    cols = [
        "sort_order",
        "id",
        "platform",
        "asset_type",
        "name",
        "ticker",
        "fund_code",
        "fund_pattern",
        "currency",
        "original_units",
        "units",
        "corporate_action",
        "avg_cost",
        "total_cost_input",
        "monthly_dividend_per_unit",
        "note",
    ]

    current_positions = ensure_columns(current_positions)

    if current_positions.empty:
        base = pd.DataFrame(columns=cols)
    else:
        base = (
            current_positions[current_positions["platform"] == platform_name][cols]
            .sort_values(["sort_order", "id"], na_position="last")
            .copy()
        )

    next_sort = 1
    if not current_positions.empty:
        next_sort = int(current_positions["sort_order"].fillna(0).max()) + 1

    blank = {
        "sort_order": next_sort,
        "id": None,
        "platform": platform_name,
        "asset_type": "基金" if platform_name in ["基富通", "渣打基金", "台新基金"] else platform_name,
        "name": "",
        "ticker": "",
        "fund_code": "",
        "fund_pattern": "yp010001" if platform_name in ["基富通", "渣打基金", "台新基金"] else "",
        "currency": "TWD" if platform_name in ["台股", "基富通"] else "USD",
        "original_units": 0.0,
        "units": 0.0,
        "corporate_action": "",
        "avg_cost": 0.0,
        "total_cost_input": 0.0,
        "monthly_dividend_per_unit": 0.0,
        "note": "",
    }

    base = pd.concat([base, pd.DataFrame([blank])], ignore_index=True)

    edited = st.data_editor(
        base,
        use_container_width=True,
        hide_index=True,
        height=360,
        num_rows="dynamic",
        column_order=[
            "sort_order",
            "platform",
            "asset_type",
            "name",
            "ticker",
            "fund_code",
            "fund_pattern",
            "currency",
            "original_units",
            "units",
            "avg_cost",
            "total_cost_input",
            "monthly_dividend_per_unit",
            "corporate_action",
            "note",
        ],
        column_config={
            "sort_order": st.column_config.NumberColumn("排序", step=1),
            "platform": st.column_config.SelectboxColumn("平台", options=PLATFORMS, required=True),
            "asset_type": st.column_config.SelectboxColumn("類型", options=ASSET_TYPES, required=True),
            "currency": st.column_config.SelectboxColumn("幣別", options=CURRENCIES, required=True),
        },
        key=editor_key,
    )

    c1, c2, c3, c4 = st.columns([1, 1.4, 1.4, 1.4])

    if c1.button("💾 儲存此頁變更", key=f"save_{editor_key}"):
        update_positions(edited)
        st.success("已儲存")
        st.rerun()

    platform_rows = current_positions[current_positions["platform"] == platform_name].copy()

    if not platform_rows.empty:
        platform_rows["選項"] = (
            platform_rows["sort_order"].astype(str)
            + "｜"
            + platform_rows["name"].astype(str)
            + "｜"
            + platform_rows["ticker"].fillna("").astype(str)
            + platform_rows["fund_code"].fillna("").astype(str)
            + "｜ID "
            + platform_rows["id"].astype(str)
        )
        options = [""] + platform_rows["選項"].tolist()
    else:
        options = [""]

    copy_choice = c2.selectbox("複製股票/基金名稱", options, key=f"copy_name_{editor_key}")
    if c2.button("📋 複製選取品項", key=f"copybtn_{editor_key}") and copy_choice:
        row = platform_rows[platform_rows["選項"] == copy_choice]
        if row.empty:
            st.error("找不到此品項")
        else:
            r = row.iloc[0].to_dict()
            r.pop("id", None)
            r.pop("選項", None)
            r["sort_order"] = next_sort
            add_position(r)
            st.success("已複製")
            st.rerun()

    sold_choice = c3.selectbox("賣出 / 結清品項", options, key=f"sold_name_{editor_key}")
    if c3.button("✅ 標記賣出 / 結清", key=f"soldbtn_{editor_key}") and sold_choice:
        row = platform_rows[platform_rows["選項"] == sold_choice]
        if row.empty:
            st.error("找不到此品項")
        else:
            mark_position_sold(int(row.iloc[0]["id"]))
            st.success(f"已標記賣出 / 結清：{row.iloc[0]['name']}")
            st.rerun()

    delete_choice = c4.selectbox("刪除股票/基金名稱", options, key=f"delete_name_{editor_key}")
    if c4.button("🗑️ 刪除選取品項", key=f"deletebtn_{editor_key}") and delete_choice:
        row = platform_rows[platform_rows["選項"] == delete_choice]
        if row.empty:
            st.error("找不到此品項")
        else:
            delete_position(int(row.iloc[0]["id"]))
            st.success(f"已刪除：{row.iloc[0]['name']}")
            st.rerun()


st.title("📈 Jenny 投資即時市值系統")
st.caption(f"版本：{APP_VERSION}｜Supabase 永久資料庫")

try:
    positions = load_positions()
except Exception as e:
    st.error(f"Supabase 讀取失敗：{e}")
    st.stop()
enriched = enrich(positions)

total_value = enriched["台幣市值"].dropna().sum() if not enriched.empty and "台幣市值" in enriched else 0
total_cost = enriched["台幣成本"].dropna().sum() if not enriched.empty and "台幣成本" in enriched else 0
total_pnl = enriched["損益"].dropna().sum() if not enriched.empty and "損益" in enriched else 0
total_div = enriched["每月配息"].dropna().sum() if not enriched.empty and "每月配息" in enriched else 0
total_rate = total_pnl / total_cost if total_cost else None

with st.container():
    st.markdown('<div class="fixed-top"><div class="hero">', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("總台幣市值", money(total_value), delta=f"{signed_money(total_pnl)} / {pct(total_rate)}")
    c2.metric("總台幣成本", money(total_cost))
    c3.metric("每月配息", money(total_div))
    c4.metric("投資筆數", f"{len(positions):,}")
    if c5.button("🔄 更新即時價"):
        st.cache_data.clear()
        st.rerun()
    st.markdown("</div></div>", unsafe_allow_html=True)


tabs = st.tabs([
    "總覽",
    "台股",
    "美股",
    "基富通",
    "渣打基金",
    "台新基金",
    "匯率",
    "批次更新",
    "資料安全",
    "修復排序",
    "貼上清單修復",
])

show_cols = [
    "sort_order",
    "platform",
    "asset_type",
    "name",
    "ticker",
    "fund_code",
    "currency",
    "total_cost_input",
    "original_units",
    "units",
    "avg_cost",
    "即時價格/淨值",
    "匯率",
    "成本原幣",
    "市值原幣",
    "台幣成本",
    "台幣市值",
    "損益",
    "損益率",
    "每月配息",
    "corporate_action",
    "狀態",
]


with tabs[0]:
    st.subheader("資產配置")

    if not enriched.empty:
        summary = (
            enriched.groupby("platform", dropna=False)
            .agg(
                台幣成本=("台幣成本", "sum"),
                台幣市值=("台幣市值", "sum"),
                損益=("損益", "sum"),
                每月配息=("每月配息", "sum"),
                筆數=("id", "count"),
            )
            .reset_index()
        )

        summary["損益率"] = summary.apply(
            lambda r: r["損益"] / r["台幣成本"] if r["台幣成本"] else None,
            axis=1,
        )

        left, right = st.columns([1, 1.7])

        with left:
            st.bar_chart(summary.set_index("platform")[["台幣市值"]], height=330)

        with right:
            st.dataframe(format_df(summary), use_container_width=True, hide_index=True, height=330)

        st.subheader("全部投資產品")
        st.dataframe(format_df(enriched[show_cols]), use_container_width=True, hide_index=True, height=560)
    else:
        st.info("目前沒有資料。")


for idx, platform in enumerate(PLATFORMS, start=1):
    with tabs[idx]:
        st.subheader(platform)

        view = enriched[enriched["platform"] == platform].copy() if not enriched.empty else pd.DataFrame()

        if view.empty:
            st.info(f"尚無 {platform} 資料")
        else:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("台幣市值", money(view["台幣市值"].dropna().sum()))
            m2.metric("台幣成本", money(view["台幣成本"].dropna().sum()))
            m3.metric("損益", signed_money(view["損益"].dropna().sum()))
            m4.metric("每月配息", money(view["每月配息"].dropna().sum()))

            st.markdown("#### 即時計算結果")
            st.caption("市值 = 現在股數 / 單位數 × 即時價格 / 淨值 × 匯率")
            st.dataframe(format_df(view[show_cols]), use_container_width=True, hide_index=True, height=360)

        editable_platform_table(platform, positions, f"editor_{platform}")


with tabs[6]:
    st.subheader("匯率")
    rows = []
    for cur in CURRENCIES:
        rate, status = fetch_fx(cur)
        rows.append({
            "幣別": cur,
            "對台幣匯率": money(rate, 4),
            "狀態": "✓" if status == "ok" else f"⚠ {status}",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


with tabs[7]:
    upload_batch_section(positions)


with tabs[8]:
    st.subheader("資料安全")
    st.error("安全版 v7：不會自動建立預設資料，也不會自動清空資料。")

    st.markdown("#### 目前 Supabase 資料匯出")
    if positions.empty:
        st.warning("目前 positions 是空的。若不是你預期的結果，請先不要按任何 seed，優先到 Supabase 檢查備份 / Log / Restore。")
    else:
        export_df = ensure_columns(positions).sort_values(["sort_order", "id"], na_position="last")
        st.download_button(
            "⬇️ 下載目前 Supabase positions 備份 CSV",
            data=export_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
            file_name="positions_backup_before_update.csv",
            mime="text/csv",
            key="download_positions_backup_safe",
        )
        st.dataframe(export_df.head(100), use_container_width=True, hide_index=True)

    st.markdown("#### 手動建立預設清單")
    st.caption("只有在 positions 完全空白，而且你確定要重建預設清單時才按。")

    confirm_seed = st.checkbox("我確認 positions 是空的，且我要建立預設清單", key="confirm_manual_seed")
    if st.button("手動建立預設清單", key="manual_seed_button", disabled=not confirm_seed):
        latest = load_positions()
        if not latest.empty:
            st.error("positions 不是空的，已取消建立，避免覆蓋或混入資料。")
        else:
            seed_presets()
            st.success("已手動建立預設清單。")
            st.rerun()


with tabs[9]:
    st.subheader("修復排序")
    sort_repair_section(positions)


with tabs[10]:
    st.subheader("貼上清單修復")
    pasted_order_repair_section(positions)
