from __future__ import annotations

import os
import re
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


APP_VERSION = "2026-05-19-supabase-v18-market-value-units"

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

US_STOCK_EXCHANGES = {
    "PYPL": "NASDAQ",
    "XYZ": "NYSE",
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
        "purchase_ym": "",
        "dividend_received_total": 0.0,
        "dividend_note": "",
        "note": "",
    }
    out = df.copy()
    for col, default in defaults.items():
        if col not in out.columns:
            out[col] = default
    return out


def infer_fund_fields(
    name: Any,
    fund_code: Any = "",
    fund_pattern: Any = "",
) -> tuple[str, str]:
    code = normalize_text(fund_code)
    pattern = normalize_text(fund_pattern)

    if re.fullmatch(r"[A-Z]\d{5}", code.upper()):
        return code.upper(), pattern or "anue"

    for preset_code, (_, preset_pattern, _, _) in FUND_PRESETS.items():
        if code and preset_code.lower() == code.lower():
            return preset_code, pattern or preset_pattern

    if code and pattern:
        return code, pattern

    clean_name = normalize_text(name)

    rules = [
        ("acft94", "yp010000", ["富蘭克林華美新興國家固定收益"], ["新臺幣", "新台幣"]),
        ("acai222", "yp010000", ["柏瑞新興邊境非投資等級債券"], []),
        ("acft99", "yp010000", ["富蘭克林華美新興國家固定收益"], ["人民幣"]),
        ("shzx0", "yp010001", ["貝萊德全球智慧數據股票入息"], []),
        ("TLZO3", "yp010001", ["安聯收益成長"], []),
        ("acob36", "yp010000", ["大華銀新加坡房地產收益"], []),
        ("pizn8", "yp010001", ["東方匯理", "新興市場債券A美元"], []),
        ("pizo1", "yp010001", ["東方匯理"], ["新興市場債券U 美元", "新興市場債券Ｕ 美元", "新興市場債券U美元"]),
        ("pizm9", "yp010001", ["東方匯理", "南非幣"], []),
        ("anzb6", "yp010001", ["高盛新興市場債券基金Y股美元"], []),
        ("ANZH2", "yp010001", ["高盛新興市場債券基金Ｙ", "南非幣"], []),
    ]

    for preset_code, preset_pattern, must_terms, any_terms in rules:
        if not all(term in clean_name for term in must_terms):
            continue
        if any_terms and not any(term in clean_name for term in any_terms):
            continue
        return code or preset_code, pattern or preset_pattern

    for preset_code, (preset_name, preset_pattern, _, _) in FUND_PRESETS.items():
        if preset_name and (preset_name in clean_name or clean_name in preset_name):
            return code or preset_code, pattern or preset_pattern

    return code, pattern


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
    if asset_type == "基金" or platform in ["基富通", "渣打基金", "台新基金"]:
        fund_code, fund_pattern = infer_fund_fields(name, fund_code, fund_pattern)

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
        "purchase_ym": normalize_text(r.get("purchase_ym", ""), ""),
        "dividend_received_total": normalize_number(r.get("dividend_received_total", 0), 0),
        "dividend_note": normalize_text(r.get("dividend_note", ""), ""),
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


def normalize_ticker(ticker: str) -> str:
    t = normalize_text(ticker).strip()
    if not t:
        return ""
    t = t.replace(" ", "")
    return t.upper()


def parse_google_finance_price(html: str, ticker: str = "", exchange: str = "") -> float | None:
    """
    Google Finance 頁面常見價格格式：
    <div class="YMlKec fxKbKc">$68.12</div>
    另有初始化資料：["PYPL","NASDAQ"],"PayPal Holdings Inc",0,"USD",[68.12,...]
    """
    ticker = normalize_ticker(ticker)
    exchange = normalize_text(exchange).upper()

    if ticker and exchange:
        anchor = f'["{ticker}","{exchange}"]'
        anchor_pos = html.find(anchor)
        if anchor_pos >= 0:
            around = html[anchor_pos:anchor_pos + 900]
            match = re.search(
                r'"[A-Z]{3}",\s*\[\s*([0-9]+(?:\.[0-9]+)?)',
                around,
            )
            if match:
                val = float(match.group(1))
                if 0 < val < 100000:
                    return val

    class_match = re.search(
        r'class="[^"]*\bYMlKec\b[^"]*\bfxKbKc\b[^"]*"[^>]*>\s*[$A-Z]*\s*([0-9,]+(?:\.[0-9]+)?)',
        html,
    )
    if class_match:
        val = float(class_match.group(1).replace(",", ""))
        if 0 < val < 100000:
            return val

    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    text = text.replace(",", "")

    # 優先抓美元價格
    matches = re.findall(r"\$\s*([0-9]+(?:\.[0-9]+)?)", text)
    for m in matches:
        val = float(m)
        if 0 < val < 100000:
            return val

    # fallback：抓 quote 頁附近常見小數
    matches = re.findall(r"(?<!\d)([0-9]+\.[0-9]{1,4})(?!\d)", text)
    for m in matches:
        val = float(m)
        if 0 < val < 100000:
            return val

    return None


@st.cache_data(ttl=300, show_spinner=False)
def fetch_google_finance_price(ticker: str, exchange: str | None = None) -> tuple[float | None, str]:
    ticker = normalize_ticker(ticker)
    if not ticker:
        return None, "Google 無 ticker"

    exchange = exchange or US_STOCK_EXCHANGES.get(ticker, "NASDAQ")
    url = f"https://www.google.com/finance/quote/{ticker}:{exchange}"

    try:
        r = requests.get(
            url,
            timeout=20,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8",
            },
        )
        r.raise_for_status()

        price = parse_google_finance_price(r.text, ticker, exchange)
        if price is None:
            return None, f"Google 無價格:{ticker}:{exchange}"

        return float(price), "ok"

    except Exception as e:
        return None, f"Google 錯誤:{str(e)[:40]}"


@st.cache_data(ttl=300, show_spinner=False)
def fetch_yahoo_price(ticker: str) -> tuple[float | None, str]:
    ticker = normalize_ticker(ticker)

    if not ticker:
        return None, "無 ticker"

    if not HAS_YF:
        return None, "缺少 yfinance"

    try:
        t = yf.Ticker(ticker)
        price = None

        try:
            price = getattr(t.fast_info, "last_price", None)
        except Exception:
            price = None

        if price is None:
            hist = t.history(period="7d", auto_adjust=False)
            if not hist.empty and "Close" in hist:
                close = hist["Close"].dropna()
                if not close.empty:
                    price = close.iloc[-1]

        if price is None:
            return None, f"Yahoo 無價格:{ticker}"

        return float(price), "ok"

    except Exception as e:
        return None, f"Yahoo 錯誤:{str(e)[:40]}"


@st.cache_data(ttl=300, show_spinner=False)
def fetch_stock_price(ticker: str, asset_type: str = "") -> tuple[float | None, str]:
    """
    股票價格：
    1. 先用 Yahoo Finance
    2. 美股失敗時用 Google Finance fallback
    """
    ticker = normalize_ticker(ticker)

    price, status = fetch_yahoo_price(ticker)
    if price is not None:
        return price, "Yahoo"

    if asset_type == "美股" or ticker in US_STOCK_EXCHANGES:
        g_price, g_status = fetch_google_finance_price(
            ticker,
            US_STOCK_EXCHANGES.get(ticker),
        )
        if g_price is not None:
            return g_price, "Google"

        return None, f"{status}; {g_status}"

    return None, status


@st.cache_data(ttl=300, show_spinner=False)
def fetch_anue_fund_nav(code: str) -> tuple[float | None, str]:
    """
    鉅亨買基金 API。
    網頁 URL 是 https://www.anuefund.com/fund/detail/A45089，
    實際淨值資料在 /anuefundApi/FundDetail/FundInfo。
    """
    code = normalize_text(code).upper()
    if not code:
        return None, "鉅亨無 fund_code"

    try:
        url = (
            "https://www.anuefund.com/anuefundApi/FundDetail/FundInfo"
            f"?fundDetailEnum=FundINFO&FundID={code}"
        )
        r = requests.get(
            url,
            timeout=20,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Referer": f"https://www.anuefund.com/fund/detail/{code}",
            },
        )
        r.raise_for_status()
        payload = r.json()
        header = ((payload.get("data") or {}).get("hearder") or {})
        nav = to_float(header.get("nav"))
        if nav is None:
            return None, f"鉅亨找不到淨值:{code}"
        return nav, "ok"
    except Exception as e:
        return None, f"鉅亨錯誤:{str(e)[:40]}"


@st.cache_data(ttl=300, show_spinner=False)
def fetch_fund_nav(code: str, pattern: str) -> tuple[float | None, str]:
    """
    基金淨值：
    1. 鉅亨買基金代碼如 A45089 走 Anue API
    2. 其餘走 MoneyDJ
    URL 範例：
    https://www.anuefund.com/fund/detail/A45089
    https://www.moneydj.com/funddj/ya/yp010000.djhtm?a=acft94
    """
    code = normalize_text(code)
    pattern = normalize_text(pattern)

    if re.fullmatch(r"[A-Z]\d{5}", code.upper()) or pattern.lower() == "anue":
        return fetch_anue_fund_nav(code)

    if not code or not pattern:
        return None, "無 fund_code/fund_pattern"

    if not HAS_BS4:
        return None, "缺少 beautifulsoup4"

    try:
        url = f"https://www.moneydj.com/funddj/ya/{pattern}.djhtm?a={code}"

        r = requests.get(
            url,
            timeout=20,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
                "Referer": "https://www.moneydj.com/",
            },
        )

        r.raise_for_status()
        soup = BeautifulSoup(r.content, "lxml", from_encoding="big5")

        header_table = soup.find("table", class_="t01")
        if header_table is not None:
            cells = [td.get_text(" ", strip=True).replace(",", "") for td in header_table.find_all("td")]
            for txt in cells:
                val = to_float(txt)
                if val is not None and 0 < val < 10000:
                    return val, "ok"

        candidates: list[float] = []

        for td in soup.find_all("td"):
            txt = td.get_text(" ", strip=True).replace(",", "")
            if not txt:
                continue

            if re.fullmatch(r"\d+(?:\.\d+)?", txt):
                val = float(txt)
                if 0 < val < 10000:
                    candidates.append(val)

        decimal_candidates = [
            x for x in candidates
            if isinstance(x, float) and not float(x).is_integer()
        ]

        if decimal_candidates:
            return float(decimal_candidates[0]), "ok"

        text = soup.get_text(" ", strip=True).replace(",", "")
        nums = re.findall(r"(?<!\d)(\d+\.\d+)(?!\d)", text)

        for n in nums:
            val = float(n)
            if 0 < val < 10000:
                return val, "ok"

        return None, f"MoneyDJ 找不到淨值:{code}"

    except Exception as e:
        return None, f"MoneyDJ 錯誤:{str(e)[:40]}"


@st.cache_data(ttl=300, show_spinner=False)
def fetch_fx(currency: str) -> tuple[float | None, str]:
    """
    強化版匯率：
    - ZAR 固定走 ZARTWD=X
    - USD 固定走 USDTWD=X
    - JPY 固定走 JPYTWD=X
    - CNY 固定走 CNYTWD=X
    """
    currency = normalize_text(currency, "TWD").upper()

    alias = {
        "台幣": "TWD",
        "新台幣": "TWD",
        "臺幣": "TWD",
        "美金": "USD",
        "美元": "USD",
        "人民幣": "CNY",
        "日幣": "JPY",
        "日圓": "JPY",
        "南非幣": "ZAR",
    }

    currency = alias.get(currency, currency)

    if currency == "TWD":
        return 1.0, "ok"

    direct_pairs = {
        "USD": "USDTWD=X",
        "CNY": "CNYTWD=X",
        "JPY": "JPYTWD=X",
        "ZAR": "ZARTWD=X",
    }

    pair = direct_pairs.get(currency)

    if not pair:
        return None, f"未知幣別:{currency}"

    price, status = fetch_yahoo_price(pair)

    if price is None:
        return None, f"匯率抓取失敗:{currency}"

    return float(price), status


def calculate_cost_and_value(r: pd.Series, latest_price: float | None, fx: float | None) -> dict[str, Any]:
    """
    通用算法：
    1. 成本：優先採用 total_cost_input；沒有總投入成本時，用 original_units * avg_cost。
    2. 市值：優先採用目前持有 units * 最新價格/淨值 * 匯率。
       若 units 尚未填但 original_units 有值，且不是已賣出/結清，先用 original_units 避免現值整欄為 0。
    3. 不再用總投入成本反推現在股數，避免被 Supabase 舊資料或 0 值弄亂。
    """
    original_units = normalize_number(r.get("original_units", 0), 0)
    units = normalize_number(r.get("units", 0), 0)
    avg_cost = normalize_number(r.get("avg_cost", 0), 0)
    total_cost_input = normalize_number(r.get("total_cost_input", 0), 0)
    note = normalize_text(r.get("note", ""))
    is_closed = any(term in note for term in ["已賣出", "已結清", "結清", "賣出"])
    market_units = units if units > 0 or is_closed else original_units

    cost_original_currency = total_cost_input if total_cost_input > 0 else original_units * avg_cost
    value_original_currency = market_units * latest_price if latest_price is not None else None

    twd_cost = cost_original_currency * fx if fx is not None else None
    twd_value = value_original_currency * fx if value_original_currency is not None and fx is not None else None

    pnl = twd_value - twd_cost if twd_value is not None and twd_cost is not None else None
    pnl_rate = pnl / twd_cost if pnl is not None and twd_cost else None

    dividend_received_total = normalize_number(r.get("dividend_received_total", 0), 0)
    total_pnl_with_dividend = (
        pnl + dividend_received_total
        if pnl is not None
        else None
    )
    total_pnl_rate_with_dividend = (
        total_pnl_with_dividend / twd_cost
        if total_pnl_with_dividend is not None and twd_cost
        else None
    )

    return {
        "成本原幣": cost_original_currency,
        "市值原幣": value_original_currency,
        "台幣成本": twd_cost,
        "台幣市值": twd_value,
        "價差損益": pnl,
        "價差損益率": pnl_rate,
        "累計已領配息": dividend_received_total,
        "含息總損益": total_pnl_with_dividend,
        "含息總損益率": total_pnl_rate_with_dividend,
        "市值股數": market_units,
        # 保留舊欄位名稱給既有總覽相容：損益 = 含息總損益
        "損益": total_pnl_with_dividend,
        "損益率": total_pnl_rate_with_dividend,
    }


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_columns(df)

    if df.empty:
        return df

    rows = []

    for _, r in df.iterrows():

        name = normalize_text(r.get("name", ""))
        currency = normalize_text(r.get("currency", "TWD")).upper()

        # 自動修正錯置幣別
        if "南非幣" in name:
            currency = "ZAR"

        elif (
            "美元" in name
            or "美金" in name
            or normalize_text(r.get("asset_type")) == "美股"
        ):
            currency = "USD"

        elif "人民幣" in name:
            currency = "CNY"

        elif "日圓" in name or "日幣" in name:
            currency = "JPY"

        platform = normalize_text(r.get("platform", ""))
        asset_type = normalize_text(r.get("asset_type", ""))

        if platform == "台股":
            asset_type = "台股"
        elif platform == "美股":
            asset_type = "美股"
        elif platform in ["基富通", "渣打基金", "台新基金"]:
            asset_type = "基金"

        # 美股 / 台股
        if asset_type in {"台股", "美股"}:

            ticker = normalize_text(r.get("ticker", ""))

            if not ticker and name:
                ticker = name.upper()

            price, p_status = fetch_stock_price(ticker, asset_type)

        # 基金
        else:

            fund_code = normalize_text(r.get("fund_code", ""))
            fund_pattern = normalize_text(r.get("fund_pattern", ""))
            fund_code, fund_pattern = infer_fund_fields(name, fund_code, fund_pattern)

            price, p_status = fetch_fund_nav(
                fund_code,
                fund_pattern,
            )

        fx, fx_status = fetch_fx(currency)

        calc = calculate_cost_and_value(r, price, fx)

        units = normalize_number(r.get("units", 0), 0)

        monthly_div = (
            units
            * normalize_number(
                r.get("monthly_dividend_per_unit", 0),
                0,
            )
        )

        monthly_div_twd = (
            monthly_div * fx
            if fx is not None
            else None
        )

        out = dict(r)

        out["currency"] = currency
        out["asset_type"] = asset_type
        if asset_type == "基金":
            out["fund_code"] = fund_code
            out["fund_pattern"] = fund_pattern

        out.update(calc)

        out.update({
            "即時價格/淨值": price,
            "匯率": fx,
            "每月配息": monthly_div_twd,
            "狀態":
                "✓"
                if price is not None and fx is not None
                else f"價格:{p_status} 匯率:{fx_status}",
        })

        rows.append(out)

    return pd.DataFrame(rows)


def format_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    for c in ["即時價格/淨值", "匯率"]:
        if c in out:
            out[c] = out[c].apply(lambda x: money(x, 4))

    for c in ["成本原幣", "市值原幣", "台幣成本", "台幣市值", "價差損益", "累計已領配息", "含息總損益", "損益", "每月配息"]:
        if c in out:
            out[c] = out[c].apply(money)

    for rate_col in ["價差損益率", "含息總損益率", "損益率"]:
        if rate_col in out:
            out[rate_col] = out[rate_col].apply(pct)

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
        "市值股數": "市值股數",
        "avg_cost": "平均成本",
        "total_cost_input": "總投入成本",
        "monthly_dividend_per_unit": "每單位月配息預估",
        "purchase_ym": "購買年月",
        "dividend_received_total": "累計已領配息輸入",
        "dividend_note": "配息備註",
        "corporate_action": "股數調整備註",
        "note": "備註",
    }

    return out.rename(columns=rename_map)


def right_align_numbers(df: pd.DataFrame) -> Any:
    if df.empty:
        return df

    numeric_cols: list[str] = []
    numeric_name_keywords = [
        "排序",
        "成本",
        "股數",
        "投入",
        "價格",
        "淨值",
        "匯率",
        "市值",
        "損益",
        "配息",
        "筆數",
        "rate",
        "率",
    ]

    for col in df.columns:
        if any(key in str(col) for key in numeric_name_keywords):
            numeric_cols.append(col)
            continue

        sample = df[col].dropna().astype(str).head(20)
        if sample.empty:
            continue
        matches = sample.str.match(r"^\s*[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?\s*$|^\s*-\s*$")
        if matches.mean() >= 0.8:
            numeric_cols.append(col)

    if not numeric_cols:
        return df

    return df.style.set_properties(subset=numeric_cols, **{"text-align": "right"})


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
            "purchase_ym": "",
            "dividend_received_total": 0,
            "dividend_note": "",
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
            "purchase_ym": "",
            "dividend_received_total": 0,
            "dividend_note": "",
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
        "purchase_ym",
        "dividend_received_total",
        "dividend_note",
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

    st.dataframe(right_align_numbers(preview), use_container_width=True, hide_index=True, height=520)

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
    st.dataframe(right_align_numbers(preview), use_container_width=True, hide_index=True, height=520)

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
            st.dataframe(right_align_numbers(upload_df.head(50)), use_container_width=True, hide_index=True)

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
        "purchase_ym",
        "dividend_received_total",
        "dividend_note",
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
        "purchase_ym": "",
        "dividend_received_total": 0.0,
        "dividend_note": "",
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
            "purchase_ym",
            "dividend_received_total",
            "monthly_dividend_per_unit",
            "dividend_note",
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

def render_channel_overview_cards(enriched: pd.DataFrame) -> None:
    """
    總覽上方卡片：
    顯示每個投資管道的台幣市值、台幣成本、含息損益、損益率。
    """
    st.markdown("### 💎 所有投資管道總覽")

    if enriched.empty:
        st.info("目前沒有資料。")
        return

    summary = (
        enriched.groupby("platform", dropna=False)
        .agg(
            台幣成本=("台幣成本", "sum"),
            台幣市值=("台幣市值", "sum"),
            含息總損益=("含息總損益", "sum"),
            累計已領配息=("累計已領配息", "sum"),
            價格缺漏=("即時價格/淨值", lambda s: int(s.isna().sum())),
            匯率缺漏=("匯率", lambda s: int(s.isna().sum())),
            股數缺漏=("市值股數", lambda s: int((s.fillna(0) <= 0).sum())),
            筆數=("id", "count"),
        )
        .reset_index()
    )

    summary["含息總損益率"] = summary.apply(
        lambda r: r["含息總損益"] / r["台幣成本"] if r["台幣成本"] else None,
        axis=1,
    )

    order = ["台股", "美股", "基富通", "渣打基金", "台新基金"]
    summary["_order"] = summary["platform"].apply(
        lambda x: order.index(x) if x in order else 999
    )
    summary = summary.sort_values(["_order", "platform"])

    card_cols = st.columns(5)

    icons = {
        "台股": "📈",
        "美股": "🇺🇸",
        "基富通": "🟧",
        "渣打基金": "🏦",
        "台新基金": "🟥",
    }

    for i, (_, r) in enumerate(summary.iterrows()):
        platform = r["platform"]
        value = r["台幣市值"] or 0
        cost = r["台幣成本"] or 0
        pnl = r["含息總損益"] or 0
        rate = r["含息總損益率"]

        with card_cols[i % 5]:
            st.metric(
                f"{icons.get(platform, '💼')} {platform}",
                money(value),
                delta=f"{signed_money(pnl)} / {pct(rate)}",
            )
            status = "抓價 ✓"
            if r["價格缺漏"] or r["匯率缺漏"] or r["股數缺漏"]:
                status = (
                    f"價格缺 {int(r['價格缺漏'])}｜"
                    f"匯率缺 {int(r['匯率缺漏'])}｜"
                    f"股數缺 {int(r['股數缺漏'])}"
                )
            st.caption(
                f"成本 {money(cost)}"
            )
            st.caption(
                f"損益 / 淨利率 {signed_money(pnl)} / {pct(rate)}｜已領息 {money(r['累計已領配息'])}｜{int(r['筆數'])} 筆｜{status}"
            )


def render_fx_overview_cards() -> None:
    st.markdown("### 💱 匯率總覽")

    fx_cols = st.columns(len(CURRENCIES))

    for i, cur in enumerate(CURRENCIES):
        rate, status = fetch_fx(cur)

        with fx_cols[i]:
            st.metric(
                cur,
                money(rate, 4),
                delta="ok" if status == "ok" else status,
            )


st.title("📈 Jenny 投資即時市值系統")
st.caption(f"版本：{APP_VERSION}｜Supabase 永久資料庫")

with st.expander("資料庫欄位提醒：第一次使用 v15 請先確認 Supabase 欄位"):
    st.code("""
alter table positions
add column if not exists purchase_ym text default '';

alter table positions
add column if not exists dividend_received_total numeric default 0;

alter table positions
add column if not exists dividend_note text default '';
""", language="sql")
    st.caption("purchase_ym = 購買年月；dividend_received_total = 已實際入帳配息累計台幣；dividend_note = 配息月份 / 入帳月份備註。")

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
    c1.metric("總台幣市值", money(total_value), delta=f"含息損益 {signed_money(total_pnl)} / {pct(total_rate)}")
    c2.metric("總台幣成本", money(total_cost))
    c3.metric("預估每月配息", money(total_div))
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
    "全部歸零重建",
    "抓價測試",
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
    "市值股數",
    "avg_cost",
    "purchase_ym",
    "即時價格/淨值",
    "匯率",
    "成本原幣",
    "市值原幣",
    "台幣成本",
    "台幣市值",
    "價差損益",
    "價差損益率",
    "累計已領配息",
    "含息總損益",
    "含息總損益率",
    "每月配息",
    "dividend_note",
    "corporate_action",
    "狀態",
]


with tabs[0]:
    render_channel_overview_cards(enriched)
    render_fx_overview_cards()

    st.markdown("### 📈 資產配置圖")
    if not enriched.empty:
        chart_summary = (
            enriched.groupby("platform", dropna=False)
            .agg(台幣市值=("台幣市值", "sum"))
            .reset_index()
        )
        st.bar_chart(chart_summary.set_index("platform")[["台幣市值"]], height=320)

        st.markdown("### 📋 全部投資產品")
        st.dataframe(
            right_align_numbers(format_df(enriched[show_cols])),
            use_container_width=True,
            hide_index=True,
            height=560,
        )
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
            st.caption("市值 = 現在股數 / 單位數 × 即時價格 / 淨值 × 匯率｜含息總損益 = 台幣市值 - 台幣成本 + 累計已領配息")
            st.dataframe(right_align_numbers(format_df(view[show_cols])), use_container_width=True, hide_index=True, height=360)

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
    st.dataframe(right_align_numbers(pd.DataFrame(rows)), use_container_width=True, hide_index=True)


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
        st.dataframe(right_align_numbers(export_df.head(100)), use_container_width=True, hide_index=True)

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


def infer_asset_from_pasted(raw_platform: str, raw_currency: str, name: str) -> dict[str, Any]:
    raw_platform = normalize_text(raw_platform)
    raw_currency = normalize_text(raw_currency)
    clean_name = normalize_text(name)
    lower_name = clean_name.lower()

    currency = CURRENCY_ALIAS.get(raw_currency, raw_currency)

    if raw_platform == "基富通":
        platform = "基富通"
    elif raw_platform == "渣打":
        platform = "美股" if raw_currency == "美股" else "渣打基金"
    elif raw_platform == "台新":
        platform = "台新基金"
    else:
        platform = raw_platform

    if raw_currency == "美股" or lower_name in {"pypl", "xyz"}:
        asset_type = "美股"
        ticker = clean_name.upper()
        fund_code = ""
        fund_pattern = ""
        currency = "USD"
        name_out = clean_name.upper()
    else:
        asset_type = "基金" if platform in ["基富通", "渣打基金", "台新基金"] else "台股"
        ticker = ""
        fund_code = ""
        fund_pattern = ""

        if "富蘭克林華美新興國家固定收益" in clean_name and ("新臺幣" in clean_name or "新台幣" in clean_name):
            fund_code, fund_pattern = "acft94", "yp010000"
        elif "柏瑞新興邊境非投資等級債券" in clean_name:
            fund_code, fund_pattern = "acai222", "yp010000"
        elif "富蘭克林華美新興國家固定收益" in clean_name and "人民幣" in clean_name:
            fund_code, fund_pattern = "acft99", "yp010000"
        elif "貝萊德全球智慧數據股票入息" in clean_name:
            fund_code, fund_pattern = "shzx0", "yp010001"
        elif "安聯收益成長" in clean_name:
            fund_code, fund_pattern = "TLZO3", "yp010001"
        elif "大華銀新加坡房地產收益" in clean_name:
            fund_code, fund_pattern = "acob36", "yp010000"
        elif "東方匯理" in clean_name and "新興市場債券A美元" in clean_name:
            fund_code, fund_pattern = "pizn8", "yp010001"
        elif "東方匯理" in clean_name and ("新興市場債券U 美元" in clean_name or "新興市場債券Ｕ 美元" in clean_name or "新興市場債券U美元" in clean_name):
            fund_code, fund_pattern = "pizo1", "yp010001"
        elif "東方匯理" in clean_name and "南非幣" in clean_name:
            fund_code, fund_pattern = "pizm9", "yp010001"
            currency = "ZAR"
        elif "高盛新興市場債券基金Y股美元" in clean_name:
            fund_code, fund_pattern = "anzb6", "yp010001"
        elif "高盛新興市場債券基金Ｙ" in clean_name and "南非幣" in clean_name:
            fund_code, fund_pattern = "ANZH2", "yp010001"
            currency = "ZAR"

        name_out = clean_name

    return {
        "platform": platform,
        "asset_type": asset_type,
        "name": name_out,
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
        "purchase_ym": "",
        "dividend_received_total": 0,
        "dividend_note": "",
        "note": f"依原始清單重建：{raw_platform} / {raw_currency}",
    }


def build_reset_seed_df_from_pasted(pasted_text: str) -> pd.DataFrame:
    targets = parse_pasted_order_text(pasted_text)
    rows = []

    for t in targets:
        row = infer_asset_from_pasted(t["raw_platform"], t["raw_currency"], t["name"])
        row["sort_order"] = t["target_order"]
        row["原始平台"] = t["raw_platform"]
        row["原始幣別"] = t["raw_currency"]
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    cols = [
        "sort_order",
        "原始平台",
        "原始幣別",
        "platform",
        "asset_type",
        "name",
        "ticker",
        "fund_code",
        "fund_pattern",
        "currency",
        "total_cost_input",
        "original_units",
        "units",
        "avg_cost",
        "monthly_dividend_per_unit",
        "purchase_ym",
        "dividend_received_total",
        "dividend_note",
        "corporate_action",
        "note",
    ]
    return pd.DataFrame(rows)[cols]


def delete_all_positions() -> int:
    current = load_positions()
    if current.empty:
        return 0

    sb = supabase_client()
    count = 0

    for _, r in current.iterrows():
        rid = r.get("id")
        if pd.isna(rid):
            continue
        sb.table("positions").delete().eq("id", int(float(rid))).execute()
        count += 1

    return count


def rebuild_positions_from_seed_df(seed_df: pd.DataFrame) -> int:
    if seed_df.empty:
        return 0

    insert_cols = [
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
        "corporate_action",
        "avg_cost",
        "total_cost_input",
        "monthly_dividend_per_unit",
        "purchase_ym",
        "dividend_received_total",
        "dividend_note",
        "note",
    ]

    sb = supabase_client()
    count = 0

    for _, r in seed_df.iterrows():
        payload = {col: r.get(col) for col in insert_cols}
        payload = normalize_payload(payload)
        sb.table("positions").insert(payload).execute()
        count += 1

    return count



def force_zero_all_positions() -> int:
    """
    強制把目前 positions 的成本、股數、配息全部歸零。
    不改排序、不改名稱、不改平台、不改 ticker / fund_code。
    """
    current = load_positions()
    if current.empty:
        return 0

    sb = supabase_client()
    count = 0

    zero_payload = {
        "original_units": 0,
        "units": 0,
        "avg_cost": 0,
        "total_cost_input": 0,
        "monthly_dividend_per_unit": 0,
        "dividend_received_total": 0,
        "dividend_note": "",
        "corporate_action": "",
    }

    for _, r in current.iterrows():
        rid = r.get("id")
        if pd.isna(rid):
            continue

        sb.table("positions").update(zero_payload).eq(
            "id",
            int(float(rid))
        ).execute()

        count += 1

    return count


def full_reset_rebuild_section(current_positions: pd.DataFrame) -> None:
    st.markdown("#### 🧨 全部歸零並依原始清單重建")
    st.error("這會刪除 positions 全部資料，重新建立成本、股數、配息皆為 0 的乾淨清單。請務必先下載備份。")

    backup = ensure_columns(current_positions).sort_values(["sort_order", "id"], na_position="last")
    st.download_button(
        "⬇️ 下載目前資料備份 CSV",
        data=backup.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
        file_name="positions_backup_before_FULL_RESET.csv",
        mime="text/csv",
        key="download_backup_before_full_reset",
        disabled=backup.empty,
    )

    pasted = st.text_area(
        "貼上你的原始三欄清單：平台、幣別/類別、名稱。重建順序與重複列數會完全依這份文字。",
        height=360,
        key="full_reset_pasted_order_text",
    )

    seed_df = build_reset_seed_df_from_pasted(pasted)

    if pasted and seed_df.empty:
        st.warning("沒有解析到資料。請確認每列至少有：平台、幣別/類別、名稱。")
        return

    if not seed_df.empty:
        st.success(f"已解析 {len(seed_df)} 筆，將以這些資料重建。")
        st.dataframe(right_align_numbers(seed_df), use_container_width=True, hide_index=True, height=520)

        st.download_button(
            "⬇️ 下載即將重建的乾淨清單 CSV",
            data=seed_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
            file_name="positions_clean_rebuild_preview.csv",
            mime="text/csv",
            key="download_clean_rebuild_preview",
        )

    typed = st.text_input("若確認要全部刪除並重建，請輸入 RESET", key="full_reset_confirm_text")
    confirm_backup = st.checkbox("我已下載備份，確認要全部歸零重建", key="full_reset_confirm_backup")

    st.markdown("#### 只歸零目前資料")
    st.caption("如果你不想刪除重建，只想把現有所有成本、股數、配息歸零，可用這個。")
    zero_only_confirm = st.checkbox("我確認只把目前資料全部歸零，不刪除列", key="zero_only_confirm")
    if st.button("🧹 只歸零目前所有資料", key="zero_only_button", disabled=not zero_only_confirm):
        zeroed = force_zero_all_positions()
        st.success(f"已強制歸零 {zeroed} 筆資料。")
        st.cache_data.clear()
        st.rerun()

    disabled = not (typed == "RESET" and confirm_backup and not seed_df.empty)

    if st.button("🧨 刪除全部 positions 並重建", key="run_full_reset_rebuild", disabled=disabled):
        deleted = delete_all_positions()
        inserted = rebuild_positions_from_seed_df(seed_df)
        zeroed = force_zero_all_positions()
        st.success(f"完成：已刪除 {deleted} 筆，重建 {inserted} 筆，強制歸零 {zeroed} 筆。")
        st.cache_data.clear()
        st.rerun()


with tabs[11]:
    st.subheader("全部歸零重建")
    full_reset_rebuild_section(positions)


def price_test_section() -> None:
    st.subheader("抓價測試")
    st.caption("用這裡確認美股 ticker、基金 MoneyDJ 代碼與匯率是否能抓到。")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("#### 美股 / 台股")
        ticker = st.text_input("Ticker", value="PYPL", key="test_ticker")
        if st.button("測試股票價格", key="test_yahoo_price"):
            normalized = normalize_ticker(ticker)
            y_price, y_status = fetch_yahoo_price(normalized)
            g_price, g_status = fetch_google_finance_price(
                normalized,
                US_STOCK_EXCHANGES.get(normalized),
            )
            final_price, final_status = fetch_stock_price(normalized, "美股")
            st.write({
                "ticker": normalized,
                "exchange": US_STOCK_EXCHANGES.get(normalized, "NASDAQ"),
                "yahoo_price": y_price,
                "yahoo_status": y_status,
                "google_price": g_price,
                "google_status": g_status,
                "final_price": final_price,
                "final_status": final_status,
            })

    with c2:
        st.markdown("#### 基金")
        fund_pattern = st.text_input("fund_pattern", value="yp010000", key="test_fund_pattern")
        fund_code = st.text_input("fund_code", value="acft94", key="test_fund_code")
        st.caption("MoneyDJ 用 acft94 + yp010000；鉅亨用 A45089 + anue。")
        if st.button("測試基金淨值", key="test_moneydj_nav"):
            nav, status = fetch_fund_nav(fund_code, fund_pattern)
            fund_url = (
                f"https://www.anuefund.com/fund/detail/{fund_code}"
                if fund_pattern.lower() == "anue" or re.fullmatch(r"[A-Z]\d{5}", fund_code.upper())
                else f"https://www.moneydj.com/funddj/ya/{fund_pattern}.djhtm?a={fund_code}"
            )
            st.write({
                "url": fund_url,
                "nav": nav,
                "status": status,
            })

    st.markdown("#### 匯率")
    fx_rows = []
    for cur in ["USD", "ZAR", "CNY", "JPY", "TWD"]:
        rate, status = fetch_fx(cur)
        fx_rows.append({"currency": cur, "rate": rate, "status": status})
    st.dataframe(right_align_numbers(pd.DataFrame(fx_rows)), use_container_width=True, hide_index=True)


with tabs[12]:
    price_test_section()
