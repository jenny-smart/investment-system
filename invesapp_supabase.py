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


APP_VERSION = "2026-05-20-v22-overview"

GAS_FUND_NAV_URL = "https://script.google.com/macros/s/AKfycbyUKfr9VAcArLemNFe4z0eKv_FX8Dehss2DLoWGcTV4KS9P1jwiW1be1KNf4YOIMGg/exec"

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
    "acft94":  ("富蘭克林華美新興國家固定收益B-新臺幣",  "yp010000", "TWD", "基富通"),
    "acai222": ("柏瑞新興邊境非投資等級債券基金-B類型",  "yp010000", "TWD", "基富通"),
    "acft99":  ("富蘭克林華美新興國家固定收益B-人民幣",  "yp010000", "CNY", "基富通"),
    "shzx0":   ("貝萊德全球智慧數據股票入息A6日圓",      "yp010001", "JPY", "基富通"),
    "TLZO3":   ("安聯收益成長AMgi月收（日圓避險）",       "yp010001", "JPY", "基富通"),
    "acob36":  ("大華銀新加坡房地產收益基金-美元月配",   "yp010000", "USD", "渣打基金"),
    "pizn8":   ("東方匯理新興市場債券A美元（月配）",      "yp010001", "USD", "渣打基金"),
    "pizo1":   ("東方匯理新興市場債券U美元（月配）",      "yp010001", "USD", "渣打基金"),
    "pizm9":   ("東方匯理新興市場債券U南非幣（月配）",    "yp010001", "ZAR", "台新基金"),
    "anzb6":   ("高盛新興市場債券Y股美元",                "yp010001", "USD", "渣打基金"),
    "ANZH2":   ("高盛新興市場債券Y南非幣對沖（月配）",    "yp010001", "ZAR", "台新基金"),
}

FUND_CNYES_IDS: dict[str, str] = {
    "acft94":  "A3DaDtj",
    "acai222": "A2h9QYl",
    "acft99":  "A4OhWL3",
    "shzx0":   "B090478",
    "TLZO3":   "B200269",
    "acob36":  "A48IfHn",
    "pizn8":   "B1MVJRY",
    "pizo1":   "B27DOWV",
    "pizm9":   "B32,253",
    "anzb6":   "B33,131",
    "ANZH2":   "B33,171",
}

FUND_ANUE_IDS: dict[str, str] = {
    "acft94": "A45089",
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

# ── CSS：移除 fixed-top sticky（避免蓋住標題），其餘原樣 ──────────────────
st.markdown("""
<style>
.stApp { background:#f7faf9; color:#0f2b20; }
.block-container { padding-top:0.8rem; max-width:1600px; }
.fixed-top { background:#f7faf9; padding:8px 0 12px 0; border-bottom:1px solid #e4ece8; margin-bottom:8px; }
.hero { background:#fff; border:1px solid #e5eae8; border-radius:16px; padding:16px 20px; box-shadow:0 1px 6px rgba(0,0,0,.05); }
[data-testid="stMetric"] { background:#fff !important; border:1px solid #e5eae8 !important; border-radius:14px !important; padding:18px 20px !important; }
[data-testid="stDataFrame"] { background:#fff !important; border:1px solid #e5eae8 !important; border-radius:14px !important; }
.stButton > button { background:#10b981 !important; color:#fff !important; border-radius:10px !important; border:0 !important; }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# 以下所有函式與原版完全相同，未做任何更動
# ════════════════════════════════════════════════════════════════════════════

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
        "id": None, "sort_order": 0, "platform": "台股", "asset_type": "台股",
        "name": "", "ticker": "", "fund_code": "", "fund_pattern": "", "currency": "TWD",
        "original_units": 0.0, "units": 0.0, "corporate_action": "",
        "avg_cost": 0.0, "total_cost_input": 0.0, "monthly_dividend_per_unit": 0.0,
        "purchase_ym": "", "dividend_received_total": 0.0, "dividend_note": "", "note": "",
    }
    out = df.copy()
    for col, default in defaults.items():
        if col not in out.columns:
            out[col] = default
    return out


def infer_fund_fields(name: Any, fund_code: Any = "", fund_pattern: Any = "") -> tuple[str, str]:
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
        ("acft94",  "yp010000", ["富蘭克林華美新興國家固定收益"], ["新臺幣", "新台幣"]),
        ("acai222", "yp010000", ["柏瑞新興邊境非投資等級債券"], []),
        ("acft99",  "yp010000", ["富蘭克林華美新興國家固定收益"], ["人民幣"]),
        ("shzx0",   "yp010001", ["貝萊德全球智慧數據股票入息"], []),
        ("TLZO3",   "yp010001", ["安聯收益成長"], []),
        ("acob36",  "yp010000", ["大華銀新加坡房地產收益"], []),
        ("pizn8",   "yp010001", ["東方匯理", "新興市場債券A美元"], []),
        ("pizo1",   "yp010001", ["東方匯理"], ["新興市場債券U 美元", "新興市場債券Ｕ 美元", "新興市場債券U美元"]),
        ("pizm9",   "yp010001", ["東方匯理", "南非幣"], []),
        ("anzb6",   "yp010001", ["高盛新興市場債券基金Y股美元"], []),
        ("ANZH2",   "yp010001", ["高盛新興市場債券基金Ｙ", "南非幣"], []),
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
        "platform": platform, "asset_type": asset_type, "name": name,
        "ticker": ticker, "fund_code": fund_code, "fund_pattern": fund_pattern,
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
    result = supabase_client().table("positions").select("*").order("sort_order").order("id").execute()
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
    supabase_client().table("positions").update({"units": 0, "note": "已賣出 / 已結清"}).eq("id", int(position_id)).execute()


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
    return "-" if n is None else f"{n:,.{decimals}f}"


def signed_money(v: Any) -> str:
    n = to_float(v)
    return "-" if n is None else f"{n:+,.0f}"


def pct(v: Any) -> str:
    n = to_float(v)
    return "-" if n is None else f"{n:.2%}"


def normalize_ticker(ticker: str) -> str:
    t = normalize_text(ticker).strip()
    if not t:
        return ""
    return t.replace(" ", "").upper()


def parse_google_finance_price(html: str, ticker: str = "", exchange: str = "") -> float | None:
    ticker = normalize_ticker(ticker)
    exchange = normalize_text(exchange).upper()
    if ticker and exchange:
        anchor = f'["{ticker}","{exchange}"]'
        anchor_pos = html.find(anchor)
        if anchor_pos >= 0:
            around = html[anchor_pos:anchor_pos + 900]
            match = re.search(r'"[A-Z]{3}",\s*\[\s*([0-9]+(?:\.[0-9]+)?)', around)
            if match:
                val = float(match.group(1))
                if 0 < val < 100000:
                    return val
    class_match = re.search(
        r'class="[^"]*\bYMlKec\b[^"]*\bfxKbKc\b[^"]*"[^>]*>\s*[$A-Z]*\s*([0-9,]+(?:\.[0-9]+)?)', html)
    if class_match:
        val = float(class_match.group(1).replace(",", ""))
        if 0 < val < 100000:
            return val
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True).replace(",", "")
    matches = re.findall(r"\$\s*([0-9]+(?:\.[0-9]+)?)", text)
    for m in matches:
        val = float(m)
        if 0 < val < 100000:
            return val
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
        r = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8",
        })
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
    ticker = normalize_ticker(ticker)
    price, status = fetch_yahoo_price(ticker)
    if price is not None:
        return price, "Yahoo"
    if asset_type == "美股" or ticker in US_STOCK_EXCHANGES:
        g_price, g_status = fetch_google_finance_price(ticker, US_STOCK_EXCHANGES.get(ticker))
        if g_price is not None:
            return g_price, "Google"
        return None, f"{status}; {g_status}"
    return None, status


@st.cache_data(ttl=300, show_spinner=False)
def fetch_gas_fund_nav(code: str) -> tuple[float | None, str]:
    if not GAS_FUND_NAV_URL or not code:
        return None, "GAS未設定"
    try:
        r = requests.get(
            GAS_FUND_NAV_URL,
            params={"code": code},
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code != 200:
            return None, f"GAS HTTP {r.status_code}"
        data = r.json()
        if data.get("ok") and data.get("nav") is not None:
            nav = to_float(data["nav"])
            source = data.get("source", "GAS")
            if nav and nav > 0:
                return nav, f"GAS({source})✓"
        return None, f"GAS回傳無淨值:{data.get('error','')}"
    except Exception as e:
        return None, f"GAS錯誤:{str(e)[:40]}"


@st.cache_data(ttl=300, show_spinner=False)
def fetch_cnyes_fund_nav(cnyes_id: str) -> tuple[float | None, str]:
    if not cnyes_id:
        return None, "無鉅亨ID"
    import urllib.parse
    encoded = urllib.parse.quote(cnyes_id, safe="")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://fund.cnyes.com/",
        "Origin": "https://fund.cnyes.com",
    }
    urls = [
        f"https://fund.api.cnyes.com/fund/api/v2/funds/{encoded}/nav?format=json",
        f"https://fund.api.cnyes.com/fund/api/v2/funds/{encoded}/net?format=json",
    ]
    for url in urls:
        try:
            r = requests.get(url, timeout=20, headers=headers)
            if r.status_code != 200:
                continue
            data = r.json()
            items = (data.get("data") or {}).get("items") or []
            if items:
                for key in ["nav", "NAV", "navPrice", "net", "unitNav"]:
                    val = to_float(items[0].get(key))
                    if val and val > 0:
                        return val, f"鉅亨API({cnyes_id})"
        except Exception:
            continue
    return None, f"鉅亨API失敗:{cnyes_id}"


@st.cache_data(ttl=300, show_spinner=False)
def fetch_anue_fund_nav(code: str) -> tuple[float | None, str]:
    code = normalize_text(code).upper()
    if not code:
        return None, "鉅亨無 fund_code"
    try:
        url = f"https://www.anuefund.com/anuefundApi/FundDetail/FundInfo?fundDetailEnum=FundINFO&FundID={code}"
        r = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"https://www.anuefund.com/fund/detail/{code}",
        })
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
def fetch_moneydj_nav(code: str, pattern: str) -> tuple[float | None, str]:
    if not code or not pattern:
        return None, "無 fund_code/fund_pattern"
    if not HAS_BS4:
        return None, "缺少 beautifulsoup4"
    try:
        url = f"https://www.moneydj.com/funddj/ya/{pattern}.djhtm?a={code}"
        r = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            "Referer": "https://www.moneydj.com/",
        })
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
        decimal_candidates = [x for x in candidates if isinstance(x, float) and not float(x).is_integer()]
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
def fetch_fund_nav(code: str, pattern: str) -> tuple[float | None, str]:
    code = normalize_text(code)
    pattern = normalize_text(pattern)
    if re.fullmatch(r"[A-Z]\d{5}", code.upper()):
        nav, status = fetch_anue_fund_nav(code)
        if nav:
            return nav, status
        nav, status = fetch_gas_fund_nav(code)
        if nav:
            return nav, status
        return None, status
    nav, status = fetch_gas_fund_nav(code)
    if nav:
        return nav, status
    if pattern and pattern.lower() != "anue":
        nav, status = fetch_moneydj_nav(code, pattern)
        if nav:
            return nav, "MoneyDJ直連✓"
    cnyes_id = FUND_CNYES_IDS.get(code, "")
    if cnyes_id:
        nav, status = fetch_cnyes_fund_nav(cnyes_id)
        if nav:
            return nav, f"鉅亨直連✓({cnyes_id})"
    anue_id = FUND_ANUE_IDS.get(code.lower(), "")
    if anue_id:
        nav, status = fetch_anue_fund_nav(anue_id)
        if nav:
            return nav, f"鉅亨舊✓({anue_id})"
    return None, f"所有來源失敗:{code}"


@st.cache_data(ttl=300, show_spinner=False)
def fetch_fx(currency: str) -> tuple[float | None, str]:
    currency = normalize_text(currency, "TWD").upper()
    alias = {
        "台幣": "TWD", "新台幣": "TWD", "臺幣": "TWD",
        "美金": "USD", "美元": "USD", "人民幣": "CNY",
        "日幣": "JPY", "日圓": "JPY", "南非幣": "ZAR",
    }
    currency = alias.get(currency, currency)
    if currency == "TWD":
        return 1.0, "ok"
    direct_pairs = {"USD": "USDTWD=X", "CNY": "CNYTWD=X", "JPY": "JPYTWD=X", "ZAR": "ZARTWD=X"}
    pair = direct_pairs.get(currency)
    if not pair:
        return None, f"未知幣別:{currency}"
    price, status = fetch_yahoo_price(pair)
    if price is None:
        return None, f"匯率抓取失敗:{currency}"
    return float(price), status


def calculate_cost_and_value(r: pd.Series, latest_price: float | None, fx: float | None) -> dict[str, Any]:
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
    total_pnl_with_dividend = pnl + dividend_received_total if pnl is not None else None
    total_pnl_rate_with_dividend = total_pnl_with_dividend / twd_cost if total_pnl_with_dividend is not None and twd_cost else None
    return {
        "成本原幣": cost_original_currency, "市值原幣": value_original_currency,
        "台幣成本": twd_cost, "台幣市值": twd_value,
        "價差損益": pnl, "價差損益率": pnl_rate,
        "累計已領配息": dividend_received_total,
        "含息總損益": total_pnl_with_dividend,
        "含息總損益率": total_pnl_rate_with_dividend,
        "市值股數": market_units,
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
        if "南非幣" in name:
            currency = "ZAR"
        elif "美元" in name or "美金" in name or normalize_text(r.get("asset_type")) == "美股":
            currency = "USD"
        elif "人民幣" in name:
            currency = "CNY"
        elif "日圓" in name or "日幣" in name:
            currency = "JPY"
        asset_type = normalize_text(r.get("asset_type", ""))
        if asset_type in {"台股", "美股"}:
            ticker = normalize_text(r.get("ticker", ""))
            if not ticker and name:
                ticker = name.upper()
            price, p_status = fetch_stock_price(ticker, asset_type)
        else:
            fund_code = normalize_text(r.get("fund_code", ""))
            fund_pattern = normalize_text(r.get("fund_pattern", ""))
            fund_code, fund_pattern = infer_fund_fields(name, fund_code, fund_pattern)
            price, p_status = fetch_fund_nav(fund_code, fund_pattern)
        fx, fx_status = fetch_fx(currency)
        calc = calculate_cost_and_value(r, price, fx)
        units = normalize_number(r.get("units", 0), 0)
        monthly_div = units * normalize_number(r.get("monthly_dividend_per_unit", 0), 0)
        monthly_div_twd = monthly_div * fx if fx is not None else None
        out = dict(r)
        out["currency"] = currency
        if asset_type == "基金":
            out["fund_code"] = fund_code
            out["fund_pattern"] = fund_pattern
        out.update(calc)
        out.update({
            "即時價格/淨值": price,
            "匯率": fx,
            "每月配息": monthly_div_twd,
            "狀態": "✓" if price is not None and fx is not None else f"價格:{p_status} 匯率:{fx_status}",
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
        "sort_order": "排序", "platform": "平台", "asset_type": "類型",
        "name": "名稱", "ticker": "股票代碼", "fund_code": "基金代號",
        "fund_pattern": "基金網址類型", "currency": "幣別",
        "original_units": "成本股數", "units": "現在股數", "市值股數": "市值股數",
        "avg_cost": "平均成本", "total_cost_input": "總投入成本",
        "monthly_dividend_per_unit": "每單位月配息預估",
        "purchase_ym": "購買年月", "dividend_received_total": "累計已領配息輸入",
        "dividend_note": "配息備註", "corporate_action": "股數調整備註", "note": "備註",
    }
    return out.rename(columns=rename_map)


def right_align_numbers(df: pd.DataFrame) -> Any:
    if df.empty:
        return df
    numeric_cols: list[str] = []
    numeric_name_keywords = ["排序", "成本", "股數", "投入", "價格", "淨值", "匯率", "市值", "損益", "配息", "筆數", "rate", "率"]
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
        add_position({"sort_order": sort_order, "platform": "台股", "asset_type": "台股",
                      "name": name, "ticker": TW_PRESETS.get(name, ""), "fund_code": "",
                      "fund_pattern": "", "currency": "TWD", "original_units": 0, "units": 0,
                      "corporate_action": "", "avg_cost": 0, "total_cost_input": 0,
                      "monthly_dividend_per_unit": 0, "purchase_ym": "", "dividend_received_total": 0,
                      "dividend_note": "", "note": f"預設台股清單：{name}"})
        sort_order += 1
    for platform, currency, asset_type, name, ticker, fund_code, fund_pattern in INVESTMENT_ITEMS_DUPLICATE:
        add_position({"sort_order": sort_order, "platform": platform, "asset_type": asset_type,
                      "name": name, "ticker": ticker, "fund_code": fund_code,
                      "fund_pattern": fund_pattern, "currency": currency, "original_units": 0,
                      "units": 0, "corporate_action": "", "avg_cost": 0, "total_cost_input": 0,
                      "monthly_dividend_per_unit": 0, "purchase_ym": "", "dividend_received_total": 0,
                      "dividend_note": "", "note": "預設投資清單"})
        sort_order += 1


def build_upload_template(positions: pd.DataFrame) -> pd.DataFrame:
    cols = ["sort_order", "platform", "name", "avg_cost", "total_cost_input", "original_units",
            "units", "monthly_dividend_per_unit", "purchase_ym", "dividend_received_total",
            "dividend_note", "corporate_action"]
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
        raise ValueError("上傳檔案必須包含 sort_order 欄位")
    required_cols = ["sort_order", "platform", "name", "avg_cost", "total_cost_input", "original_units", "units"]
    missing = [c for c in required_cols if c not in upload_df.columns]
    if missing:
        raise ValueError("上傳檔案缺少欄位：" + ", ".join(missing))
    updated, inserted, skipped = 0, 0, []
    current_by_order = {}
    if not current.empty:
        for _, row in current.iterrows():
            so = normalize_number(row.get("sort_order", 0), 0)
            if so:
                current_by_order[so] = row
    for i, r in upload_df.iterrows():
        payload = normalize_payload(r)
        if not payload["name"]:
            skipped.append(f"第 {i + 2} 列：name 空白"); continue
        so = payload["sort_order"]
        if not so:
            skipped.append(f"第 {i + 2} 列：sort_order 空白或 0"); continue
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
    rows: list[dict[str, Any]] = []
    order = 1
    for name in TW_STOCK_NAMES_DUPLICATE:
        rows.append({"target_order": order, "platform": "台股", "asset_type": "台股", "name": name, "currency": "TWD"})
        order += 1
    for platform, currency, asset_type, name, ticker, fund_code, fund_pattern in INVESTMENT_ITEMS_DUPLICATE:
        rows.append({"target_order": order, "platform": platform, "asset_type": asset_type, "name": name, "currency": currency})
        order += 1
    return rows


def build_sort_repair_preview(current_positions: pd.DataFrame) -> pd.DataFrame:
    current = ensure_columns(current_positions).copy()
    if current.empty:
        return pd.DataFrame()
    current["_old_sort_order"] = current["sort_order"].apply(lambda x: normalize_number(x, 0))
    current["_id_sort"] = current["id"].apply(lambda x: normalize_number(x, 999999999))
    current["_matched"] = False
    current["_new_sort_order"] = None
    current["_match_note"] = ""
    current["_match_platform"] = current["platform"].astype(str).str.strip()
    current["_match_name"] = current["name"].astype(str).str.strip()
    current["_match_currency"] = current["currency"].astype(str).str.strip()
    buckets: dict[tuple, list[int]] = {}
    for idx, row in current.sort_values(["_id_sort"]).iterrows():
        key = (normalize_text(row.get("_match_platform", "")), normalize_text(row.get("_match_name", "")), normalize_text(row.get("_match_currency", "")))
        buckets.setdefault(key, []).append(idx)
    for target in canonical_order_rows():
        key = (normalize_text(target["platform"]), normalize_text(target["name"]), normalize_text(target["currency"]))
        bucket = buckets.get(key, [])
        if bucket:
            idx = bucket.pop(0)
            current.at[idx, "_new_sort_order"] = target["target_order"]
            current.at[idx, "_matched"] = True
            current.at[idx, "_match_note"] = "已依預設清單配對"
    next_order = len(canonical_order_rows()) + 1
    unmatched = current[current["_matched"] == False].sort_values(["_old_sort_order", "_id_sort"])
    for idx, row in unmatched.iterrows():
        current.at[idx, "_new_sort_order"] = next_order
        current.at[idx, "_match_note"] = "未在預設清單，排到最後"
        next_order += 1
    preview_cols = ["id", "platform", "currency", "name", "_old_sort_order", "_new_sort_order", "_match_note", "ticker", "fund_code", "units", "avg_cost", "total_cost_input"]
    return current[preview_cols].rename(columns={"_old_sort_order": "目前排序", "_new_sort_order": "修復後排序", "_match_note": "修復狀態"})


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
        sb.table("positions").update({"sort_order": float(new_order)}).eq("id", int(float(rid))).execute()
        count += 1
    return count


CURRENCY_ALIAS = {
    "台幣": "TWD", "新台幣": "TWD", "臺幣": "TWD", "TWD": "TWD",
    "人民幣": "CNY", "CNY": "CNY", "日幣": "JPY", "日圓": "JPY", "JPY": "JPY",
    "美金": "USD", "美元": "USD", "美股": "USD", "USD": "USD",
    "南非幣": "ZAR", "ZAR": "ZAR",
}


def normalize_match_name(value: Any) -> str:
    return normalize_text(value).lower().replace(" ", "")


def parse_pasted_order_text(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    order = 1
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "\t" in line:
            parts = [p.strip() for p in line.split("\t") if p.strip()]
        else:
            parts = line.split(maxsplit=2)
        if len(parts) < 3:
            continue
        raw_platform, raw_currency, name = parts[0], parts[1], parts[2]
        currency = CURRENCY_ALIAS.get(raw_currency, raw_currency)
        rows.append({"target_order": order, "raw_platform": raw_platform, "raw_currency": raw_currency, "currency": currency, "name": name.strip()})
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
    buckets: dict[tuple, list[int]] = {}
    for idx, row in current.sort_values(["_id_sort"]).iterrows():
        key = (normalize_text(row.get("platform", "")), normalize_text(row.get("currency", "")), normalize_match_name(row.get("name", "")))
        buckets.setdefault(key, []).append(idx)
    for target in targets:
        name_key = normalize_match_name(target["name"])
        currency = normalize_text(target["currency"])
        candidates = platform_candidates_from_raw(target["raw_platform"], target["raw_currency"])
        matched_idx = None
        for platform in candidates:
            key = (platform, currency, name_key)
            if buckets.get(key):
                matched_idx = buckets[key].pop(0)
                break
        if matched_idx is not None:
            current.at[matched_idx, "_new_sort_order"] = target["target_order"]
            current.at[matched_idx, "_matched"] = True
            current.at[matched_idx, "_match_note"] = f"依貼上清單配對：{target['raw_platform']} / {target['raw_currency']}"
    next_order = len(targets) + 1
    unmatched = current[current["_matched"] == False].sort_values(["_old_sort_order", "_id_sort"])
    for idx, row in unmatched.iterrows():
        current.at[idx, "_new_sort_order"] = next_order
        current.at[idx, "_match_note"] = "貼上清單未配對，保留在最後"
        next_order += 1
    preview_cols = ["id", "platform", "currency", "name", "_old_sort_order", "_new_sort_order", "_match_note", "ticker", "fund_code", "units", "avg_cost", "total_cost_input"]
    return current[preview_cols].rename(columns={"_old_sort_order": "目前排序", "_new_sort_order": "修復後排序", "_match_note": "修復狀態"})


def pasted_order_repair_section(current_positions: pd.DataFrame) -> None:
    st.markdown("#### 📋 依你貼上的原始清單修復排序")
    st.warning("這裡只會更新 sort_order，不會改成本、股數、名稱、代碼。")
    if current_positions.empty:
        st.info("目前沒有資料可修復。"); return
    backup = ensure_columns(current_positions).sort_values(["sort_order", "id"], na_position="last")
    st.download_button("⬇️ 先下載完整備份 CSV", data=backup.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"), file_name="positions_backup_before_paste_order_repair.csv", mime="text/csv", key="download_backup_before_paste_order_repair")
    pasted = st.text_area("貼上你的原始三欄清單：平台、幣別/類別、名稱", height=320, key="pasted_order_text")
    targets = parse_pasted_order_text(pasted)
    if pasted:
        st.caption(f"已解析 {len(targets)} 列。")
    if not targets:
        return
    preview = build_pasted_sort_repair_preview(current_positions, pasted)
    if preview.empty:
        st.error("無法建立預覽，請確認貼上的文字至少有三欄。"); return
    st.dataframe(right_align_numbers(preview), use_container_width=True, hide_index=True, height=520)
    not_matched_count = int(preview["修復狀態"].astype(str).str.contains("未配對").sum())
    if not_matched_count:
        st.warning(f"有 {not_matched_count} 筆目前資料未在貼上清單配對，會被排到最後。")
    st.download_button("⬇️ 下載排序修復預覽 CSV", data=preview.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"), file_name="pasted_order_repair_preview.csv", mime="text/csv", key="download_pasted_order_repair_preview")
    confirm = st.checkbox("我已下載備份，確認只更新 sort_order", key="confirm_pasted_order_repair")
    if st.button("✅ 套用貼上清單排序", key="apply_pasted_order_repair", disabled=not confirm):
        n = apply_sort_repair(preview)
        st.success(f"已更新 {n} 筆 sort_order。"); st.rerun()


def sort_repair_section(current_positions: pd.DataFrame) -> None:
    st.markdown("#### 🧭 修復排序")
    st.warning("只會更新 sort_order，不會修改成本、股數、名稱、ticker、fund_code。")
    if current_positions.empty:
        st.info("目前沒有資料可修復。"); return
    backup = ensure_columns(current_positions).sort_values(["sort_order", "id"], na_position="last")
    st.download_button("⬇️ 修復前先下載完整備份 CSV", data=backup.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"), file_name="positions_backup_before_sort_repair.csv", mime="text/csv", key="download_backup_before_sort_repair")
    preview = build_sort_repair_preview(current_positions)
    st.caption("預覽：系統會依預設清單順序重排。")
    st.dataframe(right_align_numbers(preview), use_container_width=True, hide_index=True, height=520)
    csv = preview.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button("⬇️ 下載排序修復預覽 CSV", data=csv, file_name="sort_repair_preview.csv", mime="text/csv", key="download_sort_repair_preview")
    confirm = st.checkbox("我已下載備份，確認只更新 sort_order", key="confirm_sort_repair")
    if st.button("✅ 套用排序修復", key="apply_sort_repair", disabled=not confirm):
        n = apply_sort_repair(preview)
        st.success(f"已更新 {n} 筆 sort_order。"); st.rerun()


def upload_batch_section(current_positions: pd.DataFrame) -> None:
    st.markdown("#### 📤 CSV / Excel 批次更新")
    st.caption("名稱可重複，更新依據是 sort_order。")
    template = build_upload_template(current_positions)
    csv_bytes = template.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button("⬇️ 下載目前資料批次更新範例 CSV", data=csv_bytes, file_name="positions_upload_template.csv", mime="text/csv")
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
    cols = ["sort_order", "id", "platform", "asset_type", "name", "ticker", "fund_code", "fund_pattern",
            "currency", "original_units", "units", "corporate_action", "avg_cost", "total_cost_input",
            "monthly_dividend_per_unit", "purchase_ym", "dividend_received_total", "dividend_note", "note"]
    current_positions = ensure_columns(current_positions)
    if current_positions.empty:
        base = pd.DataFrame(columns=cols)
    else:
        base = current_positions[current_positions["platform"] == platform_name][cols].sort_values(["sort_order", "id"], na_position="last").copy()
    next_sort = 1
    if not current_positions.empty:
        next_sort = int(current_positions["sort_order"].fillna(0).max()) + 1
    blank = {"sort_order": next_sort, "id": None, "platform": platform_name,
             "asset_type": "基金" if platform_name in ["基富通", "渣打基金", "台新基金"] else platform_name,
             "name": "", "ticker": "", "fund_code": "",
             "fund_pattern": "yp010001" if platform_name in ["基富通", "渣打基金", "台新基金"] else "",
             "currency": "TWD" if platform_name in ["台股", "基富通"] else "USD",
             "original_units": 0.0, "units": 0.0, "corporate_action": "", "avg_cost": 0.0,
             "total_cost_input": 0.0, "monthly_dividend_per_unit": 0.0, "purchase_ym": "",
             "dividend_received_total": 0.0, "dividend_note": "", "note": ""}
    base = pd.concat([base, pd.DataFrame([blank])], ignore_index=True)
    edited = st.data_editor(
        base, use_container_width=True, hide_index=True, height=360, num_rows="dynamic",
        column_order=["sort_order", "platform", "asset_type", "name", "ticker", "fund_code", "fund_pattern",
                      "currency", "original_units", "units", "avg_cost", "total_cost_input", "purchase_ym",
                      "dividend_received_total", "monthly_dividend_per_unit", "dividend_note", "corporate_action", "note"],
        column_config={
            "sort_order": st.column_config.NumberColumn("排序", step=1),
            "platform": st.column_config.SelectboxColumn("平台", options=PLATFORMS, required=True),
            "asset_type": st.column_config.SelectboxColumn("類型", options=ASSET_TYPES, required=True),
            "currency": st.column_config.SelectboxColumn("幣別", options=CURRENCIES, required=True),
        }, key=editor_key,
    )
    c1, c2, c3, c4 = st.columns([1, 1.4, 1.4, 1.4])
    if c1.button("💾 儲存此頁變更", key=f"save_{editor_key}"):
        update_positions(edited); st.success("已儲存"); st.rerun()
    platform_rows = current_positions[current_positions["platform"] == platform_name].copy()
    if not platform_rows.empty:
        platform_rows["選項"] = platform_rows["sort_order"].astype(str) + "｜" + platform_rows["name"].astype(str) + "｜" + platform_rows["ticker"].fillna("").astype(str) + platform_rows["fund_code"].fillna("").astype(str) + "｜ID " + platform_rows["id"].astype(str)
        options = [""] + platform_rows["選項"].tolist()
    else:
        options = [""]
    copy_choice = c2.selectbox("複製股票/基金名稱", options, key=f"copy_name_{editor_key}")
    if c2.button("📋 複製選取品項", key=f"copybtn_{editor_key}") and copy_choice:
        row = platform_rows[platform_rows["選項"] == copy_choice]
        if row.empty:
            st.error("找不到此品項")
        else:
            r = row.iloc[0].to_dict(); r.pop("id", None); r.pop("選項", None); r["sort_order"] = next_sort
            add_position(r); st.success("已複製"); st.rerun()
    sold_choice = c3.selectbox("賣出 / 結清品項", options, key=f"sold_name_{editor_key}")
    if c3.button("✅ 標記賣出 / 結清", key=f"soldbtn_{editor_key}") and sold_choice:
        row = platform_rows[platform_rows["選項"] == sold_choice]
        if row.empty:
            st.error("找不到此品項")
        else:
            mark_position_sold(int(row.iloc[0]["id"])); st.success(f"已標記賣出 / 結清：{row.iloc[0]['name']}"); st.rerun()
    delete_choice = c4.selectbox("刪除股票/基金名稱", options, key=f"delete_name_{editor_key}")
    if c4.button("🗑️ 刪除選取品項", key=f"deletebtn_{editor_key}") and delete_choice:
        row = platform_rows[platform_rows["選項"] == delete_choice]
        if row.empty:
            st.error("找不到此品項")
        else:
            delete_position(int(row.iloc[0]["id"])); st.success(f"已刪除：{row.iloc[0]['name']}"); st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# ★ 總覽：仿 Google Sheet 格式  v25
# 順序：美股 → 基富通 → 渣打基金 → 台新基金 → 台股（最後）
# 修正：xyz 消失 / 台股 TypeError / 日期顯示 / 欄位對齊
# ════════════════════════════════════════════════════════════════════════════

OVERVIEW_ORDER = ["美股", "基富通", "渣打基金", "台新基金", "台股"]
PLATFORM_ICONS = {"台股": "📈", "美股": "🇺🇸", "基富通": "🟧", "渣打基金": "🏦", "台新基金": "🟥"}

# 子平台群組定義（sub_label, currency_filter）
SUB_GROUPS: dict[str, list[tuple[str, str]]] = {
    "基富通":  [("基富通-台", "TWD"), ("基富通-人民幣", "CNY"), ("基富通-日", "JPY")],
    "渣打基金":[("渣打-美金",  "USD"), ("渣打-南非",    "ZAR")],
    "台新基金":[("台新-美金",  "USD"), ("台新-南非",    "ZAR")],
    "美股":    [("美股",       "USD")],
    "台股":    [("台股",       "TWD")],
}

# GAS 快取（同 session 只抓一次，避免重複 HTTP 請求）
# 結構：{fund_code: {"date": "5/18", "monthly_div": 0.044}}
_gas_cache: dict[str, dict] = {}

GAS_FUND_NAV_URL_V2 = "https://script.google.com/macros/s/AKfycbxazSRUsuQJPnGXaecPhBVuihlpF-vApEsLbTf1dXbY9w-TzUOU2x_Oer9F9I5p-fBB/exec"


def _get_gas_data(fund_code: str) -> dict:
    """
    從 GAS v2 取得基金完整資料：
    回傳 {"date": "5/18", "monthly_div": 0.044}
    使用新 URL，同 session 快取。
    """
    global _gas_cache
    if fund_code in _gas_cache:
        return _gas_cache[fund_code]

    gas_url = GAS_FUND_NAV_URL_V2 or GAS_FUND_NAV_URL
    if not gas_url or not fund_code:
        _gas_cache[fund_code] = {"date": "—", "monthly_div": None}
        return _gas_cache[fund_code]

    try:
        r = requests.get(gas_url, params={"code": fund_code},
                         timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            data = r.json()
            if data.get("ok"):
                raw = data.get("date", "")          # YYYY/MM/DD
                parts = raw.split("/")
                date_str = f"{int(parts[1])}/{int(parts[2]):02d}" if len(parts) == 3 else "—"
                mdiv = data.get("monthly_div")
                result = {
                    "date":        date_str,
                    "monthly_div": float(mdiv) if mdiv is not None else None,
                }
            else:
                result = {"date": "—", "monthly_div": None}
        else:
            result = {"date": "—", "monthly_div": None}
    except Exception:
        result = {"date": "—", "monthly_div": None}

    _gas_cache[fund_code] = result
    return result


def _get_gas_date(fund_code: str) -> str:
    """取得基金報價日期（M/DD），供顯示用"""
    return _get_gas_data(fund_code).get("date", "—")


def _get_gas_monthly_div(fund_code: str) -> float | None:
    """取得基金最新每月配息金額（原幣）"""
    return _get_gas_data(fund_code).get("monthly_div")


@st.cache_data(ttl=300, show_spinner=False)
def fetch_stock_date(ticker: str) -> str:
    """Yahoo Finance 最新報價日期，回傳 M/DD"""
    ticker = normalize_ticker(ticker)
    if not ticker or not HAS_YF:
        return "—"
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if not hist.empty:
            last = hist.index[-1]
            if hasattr(last, "strftime"):
                # %-m 去掉前導零（Linux）；Windows 用 %#m
                try:
                    return last.strftime("%-m/%d")
                except ValueError:
                    return last.strftime("%m/%d").lstrip("0").replace("/0", "/")
    except Exception:
        pass
    return "—"


def _merge_positions(p_rows: pd.DataFrame, asset_type: str) -> pd.DataFrame:
    """
    合併同一檔股票/基金的多筆持倉 → 一行顯示。
    - 基金：key = fund_code（空的跳過，用 name 代替）
    - 股票：key = ticker（空的用 name）
    數值加總：台幣成本/市值/損益/配息/單位數。
    取第一筆：名稱/即時價/匯率/currency 等。
    """
    if p_rows.empty:
        return pd.DataFrame()

    is_stock = asset_type in {"台股", "美股"}

    # 決定合併 key，空值用 name 補
    if is_stock:
        key_series = p_rows["ticker"].fillna("").replace("", None).combine_first(p_rows["name"])
    else:
        key_series = p_rows["fund_code"].fillna("").replace("", None).combine_first(p_rows["name"])

    p_rows = p_rows.copy()
    p_rows["_merge_key"] = key_series

    sum_cols   = ["台幣成本", "台幣市值", "含息總損益", "累計已領配息", "每月配息",
                  "units", "original_units", "total_cost_input", "dividend_received_total"]
    first_cols = ["name", "currency", "ticker", "fund_code", "fund_pattern",
                  "即時價格/淨值", "匯率", "platform", "asset_type", "id"]

    merged_rows = []
    for key_val, grp in p_rows.groupby("_merge_key", dropna=False):
        row: dict = {}
        for c in first_cols:
            if c in grp.columns:
                row[c] = grp[c].iloc[0]
        for c in sum_cols:
            if c in grp.columns:
                row[c] = grp[c].fillna(0).sum()
        cost = row.get("台幣成本", 0)
        pnl  = row.get("含息總損益", 0)
        row["含息總損益率"] = pnl / cost if cost else None
        row["損益率"]       = row["含息總損益率"]
        merged_rows.append(row)

    return pd.DataFrame(merged_rows)


def render_sub_group(sub_label: str, sub_rows: pd.DataFrame) -> None:
    """
    單一子平台：藍色小標題 + 明細表（每檔一行）
    欄位固定寬度，對齊 Google Sheet 格式：
    名稱 / 日期 / 現值 / 損益 / 台幣成本 / 台幣市值 / 累積配息 / 月配息 / 配息率 / 損益率
    """
    if sub_rows.empty:
        return

    total_val  = sub_rows["台幣市值"].fillna(0).sum()
    total_pnl  = sub_rows["含息總損益"].fillna(0).sum()
    total_cost = sub_rows["台幣成本"].fillna(0).sum()
    total_div  = sub_rows["累計已領配息"].fillna(0).sum()
    total_mdiv = sub_rows["每月配息"].fillna(0).sum()
    total_rate = total_pnl / total_cost if total_cost else None
    pnl_color  = "#6ee7b7" if total_pnl >= 0 else "#fca5a5"

    st.markdown(f"""
<div style="background:#1a4a35;color:#fff;padding:7px 16px;border-radius:6px;
            display:flex;flex-wrap:wrap;align-items:center;gap:16px;
            margin:6px 0 1px 16px;font-size:13px;font-weight:700;font-family:monospace;">
  <span style="font-family:sans-serif;font-size:13px;min-width:100px">{sub_label}</span>
  <span style="min-width:80px"><span style="opacity:.55;font-family:sans-serif;font-size:11px">損益 </span>
    <span style="color:{pnl_color}">{signed_money(total_pnl)}</span></span>
  <span style="min-width:120px"><span style="opacity:.55;font-family:sans-serif;font-size:11px">台幣成本 </span>{money(total_cost)}</span>
  <span style="min-width:120px"><span style="opacity:.55;font-family:sans-serif;font-size:11px">台幣市值 </span>{money(total_val)}</span>
  <span style="min-width:100px"><span style="opacity:.55;font-family:sans-serif;font-size:11px">累積配息 </span>{money(total_div)}</span>
  <span style="min-width:80px"><span style="opacity:.55;font-family:sans-serif;font-size:11px">月配息 </span>{money(total_mdiv)}</span>
</div>
""", unsafe_allow_html=True)

    rows_disp = []
    for _, pr in sub_rows.iterrows():
        atype     = normalize_text(pr.get("asset_type", ""))
        price_val = pr.get("即時價格/淨值")
        cost_val  = pr.get("台幣成本") or 0
        mdiv      = pr.get("每月配息") or 0
        ann_rate  = (mdiv * 12 / cost_val) if cost_val and mdiv else None

        # 取報價日期
        if atype in {"台股", "美股"}:
            tk       = normalize_text(pr.get("ticker", ""))
            date_str = fetch_stock_date(tk) if tk else "—"
        else:
            fc       = normalize_text(pr.get("fund_code", ""))
            date_str = _get_gas_date(fc) if fc else "—"

        if price_val is None:
            date_str = "❌"

        rows_disp.append({
            "名稱":     normalize_text(pr.get("name", "")),
            "日期":     date_str,
            "現值":     money(price_val, 4) if price_val is not None else "—",
            "損益":     signed_money(pr.get("含息總損益")),
            "台幣成本": money(cost_val or None),
            "台幣市值": money(pr.get("台幣市值")),
            "累積配息": money(pr.get("累計已領配息")),
            "月配息":   money(mdiv or None),
            "配息率":   pct(ann_rate) if ann_rate else "—",
            "損益率":   pct(pr.get("含息總損益率")),
        })

    if rows_disp:
        df_disp = pd.DataFrame(rows_disp)
        # 固定欄寬讓對齊整齊
        col_cfg = {
            "名稱":     st.column_config.TextColumn("名稱",     width="large"),
            "日期":     st.column_config.TextColumn("日期",     width="small"),
            "現值":     st.column_config.TextColumn("現值",     width="small"),
            "損益":     st.column_config.TextColumn("損益",     width="medium"),
            "台幣成本": st.column_config.TextColumn("台幣成本", width="medium"),
            "台幣市值": st.column_config.TextColumn("台幣市值", width="medium"),
            "累積配息": st.column_config.TextColumn("累積配息", width="medium"),
            "月配息":   st.column_config.TextColumn("月配息",   width="small"),
            "配息率":   st.column_config.TextColumn("配息率",   width="small"),
            "損益率":   st.column_config.TextColumn("損益率",   width="small"),
        }
        st.dataframe(df_disp, use_container_width=True, hide_index=True,
                     height=min(42 * len(df_disp) + 44, 480),
                     column_config=col_cfg)


def render_platform_group(platform: str, p_rows: pd.DataFrame) -> None:
    """主平台：深色大標題 + 子平台群組 + 未更新提示 + 手動補價"""
    if p_rows.empty:
        return

    total_val  = p_rows["台幣市值"].fillna(0).sum()
    total_pnl  = p_rows["含息總損益"].fillna(0).sum()
    total_cost = p_rows["台幣成本"].fillna(0).sum()
    total_div  = p_rows["累計已領配息"].fillna(0).sum()
    total_mdiv = p_rows["每月配息"].fillna(0).sum()
    total_rate = total_pnl / total_cost if total_cost else None
    icon       = PLATFORM_ICONS.get(platform, "💼")
    pnl_color  = "#6ee7b7" if total_pnl >= 0 else "#fca5a5"

    st.markdown(f"""
<div style="background:#0f2b20;color:#fff;padding:10px 18px;border-radius:8px;
            display:flex;flex-wrap:wrap;align-items:center;gap:20px;
            margin:20px 0 3px 0;font-size:14px;font-weight:800;font-family:monospace;
            border-left:4px solid #10b981;">
  <span style="font-size:16px;font-family:sans-serif;min-width:80px">{icon} {platform}</span>
  <span style="min-width:120px"><span style="opacity:.55;font-family:sans-serif;font-size:12px">市值 </span>{money(total_val)}</span>
  <span style="min-width:120px"><span style="opacity:.55;font-family:sans-serif;font-size:12px">成本 </span>{money(total_cost)}</span>
  <span><span style="opacity:.55;font-family:sans-serif;font-size:12px">損益 </span>
    <span style="color:{pnl_color}">{signed_money(total_pnl)}</span>
    <span style="color:{pnl_color};font-size:12px"> ({pct(total_rate)})</span></span>
  <span style="min-width:100px"><span style="opacity:.55;font-family:sans-serif;font-size:12px">累積配息 </span>{money(total_div)}</span>
  <span style="min-width:80px"><span style="opacity:.55;font-family:sans-serif;font-size:12px">月配息 </span>{money(total_mdiv)}</span>
</div>
""", unsafe_allow_html=True)

    # ── 未更新持倉偵測（只看有單位數的）──
    has_pos  = p_rows[p_rows["units"].fillna(0) > 0]
    no_price = has_pos[has_pos["即時價格/淨值"].isna()].copy()
    if not no_price.empty:
        # 安全取得唯一名稱，不使用 groupby.ngroups
        unique_names = no_price["name"].dropna().unique().tolist()
        n_missing    = len(unique_names)
        names_str    = "、".join(str(n) for n in unique_names)
        st.error(f"❌ {platform}：{n_missing} 檔缺即時報價 — {names_str}")

    # ── 子平台群組 ──
    sub_defs = SUB_GROUPS.get(platform, [(platform, None)])
    for sub_label, currency_filter in sub_defs:
        if currency_filter:
            sub = p_rows[p_rows["currency"] == currency_filter].copy()
        else:
            sub = p_rows.copy()
        if sub.empty:
            continue
        atype  = normalize_text(sub["asset_type"].iloc[0])
        merged = _merge_positions(sub, atype)
        if not merged.empty:
            render_sub_group(sub_label, merged)

    # ── 手動補價（有缺報價才顯示）──
    if not no_price.empty:
        is_stock = platform in ["台股", "美股"]
        key_col  = "ticker" if is_stock else "fund_code"
        # 安全去重：先填空，再 drop_duplicates
        no_price[key_col] = no_price[key_col].fillna("")
        no_uniq  = no_price.drop_duplicates(subset=[key_col] if key_col in no_price.columns else ["name"])

        with st.expander(f"🔧 {platform}：手動補填即時價"):
            st.caption("自動抓取失敗時，手動填入現值（原幣）。儲存後按「🔄 更新即時價」重算。")
            with st.form(f"manual_price_form_{platform}"):
                manual_vals: dict[int, float] = {}
                for _, row in no_uniq.iterrows():
                    ca, cb = st.columns([3, 1])
                    code   = str(row.get("ticker") or row.get("fund_code") or "")
                    ca.markdown(f"**{row['name']}**　`{code}`　幣別：{row.get('currency','')}")
                    manual_vals[int(row["id"])] = cb.number_input(
                        "現值（原幣）", value=0.0, step=0.0001, format="%.4f",
                        key=f"mp_{platform}_{int(row['id'])}"
                    )
                if st.form_submit_button("💾 儲存"):
                    sb  = supabase_client()
                    cnt = 0
                    for rid, val in manual_vals.items():
                        if val > 0:
                            sb.table("positions").update({"avg_cost": val}).eq("id", rid).execute()
                            cnt += 1
                    if cnt:
                        st.success(f"已儲存 {cnt} 筆，請按頂端「🔄 更新即時價」重新計算。")
                        st.cache_data.clear()


def render_channel_overview_cards(enriched: pd.DataFrame) -> None:
    """總覽主函式：KPI + 匯率 + 各平台群組（美股→基富通→渣打→台新→台股）"""
    st.markdown("### 💎 所有投資管道總覽")
    if enriched.empty:
        st.info("目前沒有資料。")
        return

    # ── 自動把 GAS monthly_div 回填給尚未設定配息的基金持倉 ──
    # （只更新 monthly_dividend_per_unit == 0 且有 fund_code 的列）
    if not enriched.empty:
        fund_rows = enriched[
            (enriched["asset_type"] == "基金") &
            (enriched["fund_code"].fillna("") != "") &
            (enriched["monthly_dividend_per_unit"].fillna(0) == 0)
        ]
        if not fund_rows.empty:
            sb       = supabase_client()
            updated  = 0
            done_codes: set[str] = set()
            for _, fr in fund_rows.iterrows():
                fc = normalize_text(fr.get("fund_code", ""))
                if not fc or fc in done_codes:
                    continue
                mdiv = _get_gas_monthly_div(fc)
                if mdiv and mdiv > 0:
                    # 更新 Supabase 裡所有相同 fund_code 的列
                    sb.table("positions").update(
                        {"monthly_dividend_per_unit": mdiv}
                    ).eq("fund_code", fc).execute()
                    done_codes.add(fc)
                    updated += 1
            if updated:
                st.toast(f"✅ 已自動更新 {updated} 檔基金每月配息金額（從 MoneyDJ）", icon="💰")

    # ── 頂部 5 個 KPI ──
    summary = enriched.groupby("platform", dropna=False).agg(
        台幣成本     =("台幣成本",      "sum"),
        台幣市值     =("台幣市值",      "sum"),
        含息總損益   =("含息總損益",    "sum"),
        累計已領配息 =("累計已領配息",  "sum"),
        每月配息     =("每月配息",      "sum"),
        價格缺漏     =("即時價格/淨值", lambda s: int(s.isna().sum())),
        筆數         =("id",            "count"),
    ).reset_index()
    summary["含息總損益率"] = summary.apply(
        lambda r: r["含息總損益"] / r["台幣成本"] if r["台幣成本"] else None, axis=1
    )
    summary["_order"] = summary["platform"].apply(
        lambda x: OVERVIEW_ORDER.index(x) if x in OVERVIEW_ORDER else 999
    )
    summary = summary.sort_values("_order")

    card_cols = st.columns(5)
    for i, (_, r) in enumerate(summary.iterrows()):
        p    = r["platform"]
        miss = int(r["價格缺漏"])
        warn = f" ⚠️{miss}缺" if miss else ""
        with card_cols[i % 5]:
            st.metric(
                f"{PLATFORM_ICONS.get(p, '💼')} {p}{warn}",
                money(r["台幣市值"] or 0),
                delta=f"{signed_money(r['含息總損益'] or 0)} / {pct(r['含息總損益率'])}",
            )
            st.caption(f"成本 {money(r['台幣成本'])}｜月配 {money(r['每月配息'])}")

    # ── 匯率列 ──
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 💱 即時匯率")
    fx_cols = st.columns(len(CURRENCIES))
    for i, cur in enumerate(CURRENCIES):
        rate, status = fetch_fx(cur)
        fx_cols[i].metric(cur, money(rate, 4),
                          delta="✓" if status == "ok" else f"⚠ {status}")

    st.markdown("---")

    # ── 各平台群組 ──
    for platform in OVERVIEW_ORDER:
        p_rows = enriched[enriched["platform"] == platform].copy().reset_index(drop=True)
        if p_rows.empty:
            continue
        render_platform_group(platform, p_rows)


# ════════════════════════════════════════════════════════════════════════════
# 以下原版完全不變
# ════════════════════════════════════════════════════════════════════════════

def render_fx_overview_cards() -> None:
    st.markdown("### 💱 匯率總覽")
    fx_cols = st.columns(len(CURRENCIES))
    for i, cur in enumerate(CURRENCIES):
        rate, status = fetch_fx(cur)
        with fx_cols[i]:
            st.metric(cur, money(rate, 4), delta="ok" if status == "ok" else status)


def price_test_section() -> None:
    st.subheader("抓價測試")
    st.caption("用這裡確認美股 ticker、基金代碼與匯率是否能抓到。")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 美股 / 台股")
        ticker = st.text_input("Ticker", value="PYPL", key="test_ticker")
        if st.button("測試股票價格", key="test_yahoo_price"):
            normalized = normalize_ticker(ticker)
            y_price, y_status = fetch_yahoo_price(normalized)
            g_price, g_status = fetch_google_finance_price(normalized, US_STOCK_EXCHANGES.get(normalized))
            final_price, final_status = fetch_stock_price(normalized, "美股")
            st.write({"ticker": normalized, "exchange": US_STOCK_EXCHANGES.get(normalized, "NASDAQ"),
                      "yahoo_price": y_price, "yahoo_status": y_status,
                      "google_price": g_price, "google_status": g_status,
                      "final_price": final_price, "final_status": final_status})
    with c2:
        st.markdown("#### 基金")
        fund_code_test = st.text_input("MoneyDJ 代號", value="acft94", key="test_fund_code")
        if st.button("測試基金淨值（所有來源）", key="test_fund_nav"):
            cnyes_id = FUND_CNYES_IDS.get(fund_code_test, "")
            pattern = FUND_PRESETS.get(fund_code_test, ("", "yp010000", "", ""))[1]
            results = {}
            nav0, st0 = fetch_gas_fund_nav(fund_code_test)
            results["GAS中繼（MoneyDJ→鉅亨）"] = {"nav": nav0, "status": st0}
            nav2, st2 = fetch_moneydj_nav(fund_code_test, pattern)
            results[f"MoneyDJ直連({pattern})"] = {"nav": nav2, "status": st2}
            if cnyes_id:
                nav1, st1 = fetch_cnyes_fund_nav(cnyes_id)
                results[f"鉅亨API直連({cnyes_id})"] = {"nav": nav1, "status": st1}
            nav_f, st_f = fetch_fund_nav(fund_code_test, pattern)
            results["✅ 最終結果"] = {"nav": nav_f, "status": st_f}
            st.write(results)
            if nav0:
                st.success(f"GAS 成功抓到：{nav0}（來源：{st0}）")
            else:
                st.warning(f"GAS 失敗：{st0}")
        st.markdown("---")
        st.markdown("**所有基金鉅亨 ID 對照：**")
        cnyes_rows = [{"MoneyDJ代號": k, "鉅亨ID": v, "名稱": FUND_PRESETS.get(k, ("?",))[0]}
                      for k, v in FUND_CNYES_IDS.items()]
        st.dataframe(pd.DataFrame(cnyes_rows), use_container_width=True, hide_index=True)
    st.markdown("#### 匯率")
    fx_rows = []
    for cur in ["USD", "ZAR", "CNY", "JPY", "TWD"]:
        rate, status = fetch_fx(cur)
        fx_rows.append({"currency": cur, "rate": rate, "status": status})
    st.dataframe(right_align_numbers(pd.DataFrame(fx_rows)), use_container_width=True, hide_index=True)


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
        asset_type = "美股"; ticker = clean_name.upper(); fund_code = ""; fund_pattern = ""; currency = "USD"; name_out = clean_name.upper()
    else:
        asset_type = "基金" if platform in ["基富通", "渣打基金", "台新基金"] else "台股"
        ticker = ""; fund_code = ""; fund_pattern = ""
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
            fund_code, fund_pattern = "pizm9", "yp010001"; currency = "ZAR"
        elif "高盛新興市場債券基金Y股美元" in clean_name:
            fund_code, fund_pattern = "anzb6", "yp010001"
        elif "高盛新興市場債券基金Ｙ" in clean_name and "南非幣" in clean_name:
            fund_code, fund_pattern = "ANZH2", "yp010001"; currency = "ZAR"
        name_out = clean_name
    return {"platform": platform, "asset_type": asset_type, "name": name_out, "ticker": ticker,
            "fund_code": fund_code, "fund_pattern": fund_pattern, "currency": currency,
            "original_units": 0, "units": 0, "corporate_action": "", "avg_cost": 0,
            "total_cost_input": 0, "monthly_dividend_per_unit": 0, "purchase_ym": "",
            "dividend_received_total": 0, "dividend_note": "",
            "note": f"依原始清單重建：{raw_platform} / {raw_currency}"}


def build_reset_seed_df_from_pasted(pasted_text: str) -> pd.DataFrame:
    targets = parse_pasted_order_text(pasted_text)
    rows = []
    for t in targets:
        row = infer_asset_from_pasted(t["raw_platform"], t["raw_currency"], t["name"])
        row["sort_order"] = t["target_order"]; row["原始平台"] = t["raw_platform"]; row["原始幣別"] = t["raw_currency"]
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    cols = ["sort_order", "原始平台", "原始幣別", "platform", "asset_type", "name", "ticker", "fund_code",
            "fund_pattern", "currency", "total_cost_input", "original_units", "units", "avg_cost",
            "monthly_dividend_per_unit", "purchase_ym", "dividend_received_total", "dividend_note", "corporate_action", "note"]
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
    insert_cols = ["sort_order", "platform", "asset_type", "name", "ticker", "fund_code", "fund_pattern",
                   "currency", "original_units", "units", "corporate_action", "avg_cost", "total_cost_input",
                   "monthly_dividend_per_unit", "purchase_ym", "dividend_received_total", "dividend_note", "note"]
    sb = supabase_client()
    count = 0
    for _, r in seed_df.iterrows():
        payload = {col: r.get(col) for col in insert_cols}
        payload = normalize_payload(payload)
        sb.table("positions").insert(payload).execute()
        count += 1
    return count


def force_zero_all_positions() -> int:
    current = load_positions()
    if current.empty:
        return 0
    sb = supabase_client()
    count = 0
    zero_payload = {"original_units": 0, "units": 0, "avg_cost": 0, "total_cost_input": 0,
                    "monthly_dividend_per_unit": 0, "dividend_received_total": 0, "dividend_note": "", "corporate_action": ""}
    for _, r in current.iterrows():
        rid = r.get("id")
        if pd.isna(rid):
            continue
        sb.table("positions").update(zero_payload).eq("id", int(float(rid))).execute()
        count += 1
    return count


def full_reset_rebuild_section(current_positions: pd.DataFrame) -> None:
    st.markdown("#### 🧨 全部歸零並依原始清單重建")
    st.error("這會刪除 positions 全部資料，重新建立成本、股數、配息皆為 0 的乾淨清單。請務必先下載備份。")
    backup = ensure_columns(current_positions).sort_values(["sort_order", "id"], na_position="last")
    st.download_button("⬇️ 下載目前資料備份 CSV", data=backup.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"), file_name="positions_backup_before_FULL_RESET.csv", mime="text/csv", key="download_backup_before_full_reset", disabled=backup.empty)
    pasted = st.text_area("貼上你的原始三欄清單", height=360, key="full_reset_pasted_order_text")
    seed_df = build_reset_seed_df_from_pasted(pasted)
    if pasted and seed_df.empty:
        st.warning("沒有解析到資料。請確認每列至少有：平台、幣別/類別、名稱。"); return
    if not seed_df.empty:
        st.success(f"已解析 {len(seed_df)} 筆，將以這些資料重建。")
        st.dataframe(right_align_numbers(seed_df), use_container_width=True, hide_index=True, height=520)
        st.download_button("⬇️ 下載即將重建的乾淨清單 CSV", data=seed_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"), file_name="positions_clean_rebuild_preview.csv", mime="text/csv", key="download_clean_rebuild_preview")
    typed = st.text_input("若確認要全部刪除並重建，請輸入 RESET", key="full_reset_confirm_text")
    confirm_backup = st.checkbox("我已下載備份，確認要全部歸零重建", key="full_reset_confirm_backup")
    st.markdown("#### 只歸零目前資料")
    st.caption("如果你不想刪除重建，只想把現有所有成本、股數、配息歸零，可用這個。")
    zero_only_confirm = st.checkbox("我確認只把目前資料全部歸零，不刪除列", key="zero_only_confirm")
    if st.button("🧹 只歸零目前所有資料", key="zero_only_button", disabled=not zero_only_confirm):
        zeroed = force_zero_all_positions()
        st.success(f"已強制歸零 {zeroed} 筆資料。"); st.cache_data.clear(); st.rerun()
    disabled = not (typed == "RESET" and confirm_backup and not seed_df.empty)
    if st.button("🧨 刪除全部 positions 並重建", key="run_full_reset_rebuild", disabled=disabled):
        deleted = delete_all_positions()
        inserted = rebuild_positions_from_seed_df(seed_df)
        zeroed = force_zero_all_positions()
        st.success(f"完成：已刪除 {deleted} 筆，重建 {inserted} 筆，強制歸零 {zeroed} 筆。")
        st.cache_data.clear(); st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# APP 主體（標題移到 hero 區塊外，避免被蓋住）
# ════════════════════════════════════════════════════════════════════════════

st.title("📈 Jenny 投資即時市值系統")
st.caption(f"版本：{APP_VERSION}｜Supabase 永久資料庫")

with st.expander("資料庫欄位提醒：第一次使用 v15 請先確認 Supabase 欄位"):
    st.code("""
alter table positions add column if not exists purchase_ym text default '';
alter table positions add column if not exists dividend_received_total numeric default 0;
alter table positions add column if not exists dividend_note text default '';
""", language="sql")

try:
    positions = load_positions()
except Exception as e:
    st.error(f"Supabase 讀取失敗：{e}"); st.stop()

enriched = enrich(positions)

total_value = enriched["台幣市值"].dropna().sum() if not enriched.empty and "台幣市值" in enriched else 0
total_cost  = enriched["台幣成本"].dropna().sum() if not enriched.empty and "台幣成本" in enriched else 0
total_pnl   = enriched["損益"].dropna().sum()     if not enriched.empty and "損益"     in enriched else 0
total_div   = enriched["每月配息"].dropna().sum()  if not enriched.empty and "每月配息" in enriched else 0
total_rate  = total_pnl / total_cost if total_cost else None

# Hero bar（不再 sticky，標題不被蓋）
with st.container():
    st.markdown('<div class="fixed-top"><div class="hero">', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("總台幣市值",   money(total_value), delta=f"含息損益 {signed_money(total_pnl)} / {pct(total_rate)}")
    c2.metric("總台幣成本",   money(total_cost))
    c3.metric("預估每月配息", money(total_div))
    c4.metric("投資筆數",     f"{len(positions):,}")
    if c5.button("🔄 更新即時價"):
        st.cache_data.clear(); st.rerun()
    st.markdown("</div></div>", unsafe_allow_html=True)

tabs = st.tabs(["總覽", "台股", "美股", "基富通", "渣打基金", "台新基金", "匯率", "批次更新", "資料安全", "修復排序", "貼上清單修復", "全部歸零重建", "抓價測試"])

show_cols = ["sort_order", "platform", "asset_type", "name", "ticker", "fund_code", "currency",
             "total_cost_input", "original_units", "units", "市值股數", "avg_cost", "purchase_ym",
             "即時價格/淨值", "匯率", "成本原幣", "市值原幣", "台幣成本", "台幣市值",
             "價差損益", "價差損益率", "累計已領配息", "含息總損益", "含息總損益率", "每月配息",
             "dividend_note", "corporate_action", "狀態"]

# ── ★ 改寫後的總覽 tab ──────────────────────────────────────────────────────
with tabs[0]:
    render_channel_overview_cards(enriched)
    render_fx_overview_cards()
    st.markdown("### 📈 資產配置圖")
    if not enriched.empty:
        chart_summary = enriched.groupby("platform", dropna=False).agg(台幣市值=("台幣市值", "sum")).reset_index()
        st.bar_chart(chart_summary.set_index("platform")[["台幣市值"]], height=280)

# ── 其餘 tab 原版完全不變 ────────────────────────────────────────────────────
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
            m3.metric("損益",     signed_money(view["損益"].dropna().sum()))
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
        rows.append({"幣別": cur, "對台幣匯率": money(rate, 4), "狀態": "✓" if status == "ok" else f"⚠ {status}"})
    st.dataframe(right_align_numbers(pd.DataFrame(rows)), use_container_width=True, hide_index=True)

with tabs[7]:
    upload_batch_section(positions)

with tabs[8]:
    st.subheader("資料安全")
    st.error("安全版 v7：不會自動建立預設資料，也不會自動清空資料。")
    st.markdown("#### 目前 Supabase 資料匯出")
    if positions.empty:
        st.warning("目前 positions 是空的。")
    else:
        export_df = ensure_columns(positions).sort_values(["sort_order", "id"], na_position="last")
        st.download_button("⬇️ 下載目前 Supabase positions 備份 CSV", data=export_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"), file_name="positions_backup_before_update.csv", mime="text/csv", key="download_positions_backup_safe")
        st.dataframe(right_align_numbers(export_df.head(100)), use_container_width=True, hide_index=True)
    st.markdown("#### 手動建立預設清單")
    st.caption("只有在 positions 完全空白，而且你確定要重建預設清單時才按。")
    confirm_seed = st.checkbox("我確認 positions 是空的，且我要建立預設清單", key="confirm_manual_seed")
    if st.button("手動建立預設清單", key="manual_seed_button", disabled=not confirm_seed):
        latest = load_positions()
        if not latest.empty:
            st.error("positions 不是空的，已取消建立。")
        else:
            seed_presets(); st.success("已手動建立預設清單。"); st.rerun()

with tabs[9]:
    st.subheader("修復排序")
    sort_repair_section(positions)

with tabs[10]:
    st.subheader("貼上清單修復")
    pasted_order_repair_section(positions)

with tabs[11]:
    st.subheader("全部歸零重建")
    full_reset_rebuild_section(positions)

with tabs[12]:
    price_test_section()
