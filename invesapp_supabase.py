from __future__ import annotations

import os
import io
import re
from datetime import datetime, timedelta, timezone
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

APP_VERSION = "2026-06-06-v37-dividend-current-total-fix"

GAS_FUND_NAV_URL = "https://script.google.com/macros/s/AKfycbx2tregTV1NlYpUkOvy9UpRu3YDMP5r9wQEQuiB7qj_Y9HGa8yON4isAUIke30XF23p/exec"

MAIN_GOOGLE_SHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"
ONLINE_SHEET_SOURCES = {
    "2026細帳": "1862868285",
    "每月收入": "1804324921",
    "資產總覽": "151289982",
}

DEFAULT_SUPABASE_URL = "https://qrvdztqyzxlsfskdgiqp.supabase.co"

PLATFORMS = ["台股", "美股", "基富通", "渣打基金", "台新基金"]
ASSET_TYPES = ["台股", "美股", "基金"]
CURRENCIES = ["TWD", "USD", "CNY", "JPY", "ZAR"]
CASH_CURRENCIES = ["TWD", "USD", "JPY", "KRW", "CNY", "HKD", "THB", "EUR", "ZAR"]

FX_PAIRS = {
    "TWD": None,
    "USD": "USDTWD=X",
    "CNY": "CNYTWD=X",
    "JPY": "JPYTWD=X",
    "KRW": "KRWTWD=X",
    "HKD": "HKDTWD=X",
    "THB": "THBTWD=X",
    "EUR": "EURTWD=X",
    "ZAR": "ZARTWD=X",
}

US_STOCK_EXCHANGES = {
    "PYPL": "NASDAQ",
    "XYZ": "NYSE",
}

# 台股 Google Finance 交易所對照
# TPE = 上市（TWSE）, TAI = 上櫃（OTC/TWO）
TW_STOCK_EXCHANGES = {
    "5471.TW":   "TAI",    # 松翰（上櫃）
    "00740B.TWO":  "TPE",    # 富邦全球投等債 ETF
    "4401.TWO":   "TAI",    # 東隆興
    "5478.TWO":   "TAI",    # 智冠
    "6261.TWO":   "TAI",    # 久元
    "9802.TW":    "TPE",    # 鈺齊-KY
}

TW_PRESETS = {
    "儒鴻": "1476.TW", "大魯閣": "1432.TW", "中砂": "1560.TW", "中鴻": "2014.TW",
    "凱美": "2375.TW", "華碩": "2357.TW", "日勝生": "2547.TW", "晶華": "2707.TW",
    "中壽": "2823.TW", "凱基金": "2883.TW", "凱基金乙特": "2883B.TW", "聯陽": "3014.TW",
    "景碩": "3189.TW", "緯創": "3231.TW", "東隆興": "4401.TWO", "和碩": "4938.TW",
    "松翰": "5471.TW", "智冠": "5478.TWO", "久元": "6261.TWO", "台塑化": "6505.TW",
    "上銀": "2049.TW", "元大高股息": "0056.TW", "元大台灣50": "0050.TW",
    "泰碩": "3338.TW", "尼得科超眾": "6230.TW", "立積": "4968.TW", "鈺齊-KY": "9802.TW",
    "東陽": "1319.TW", "華邦電": "2344.TW", "元大金": "2885.TW", "鴻海": "2317.TW",
    "長榮": "2603.TW", "長華*": "8070.TW", "群創": "3481.TW", "集盛": "1455.TW",
    "華新": "1605.TW", "第一銅": "2009.TW", "大聯大": "3702.TW",
    "富邦特選高股息30": "00900.TW", "群益台灣精選高息": "00919.TW",
    "富邦全球投等債": "00740B.TWO", "群益半導體收益": "00927.TW", "華泰": "2329.TW",
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


def gas_fund_code_candidates(code: Any) -> list[str]:
    raw = normalize_text(code)
    if not raw:
        return []
    candidates = [raw]
    for preset_code in FUND_PRESETS:
        if preset_code.lower() == raw.lower():
            candidates.append(preset_code)
            break
    candidates.extend([raw.upper(), raw.lower()])
    deduped: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped

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
h1 { font-size: 1.4rem !important; font-weight: 700 !important; }
h2, h3, h4 { font-size: 1rem !important; font-weight: 600 !important; }
.stApp { background:#f8fafc; color:#1e293b; }
.block-container { padding-top:2.5rem; max-width:1600px; }
.app-page-title {
    display: block !important;
    margin: 0.2rem 0 0.35rem 0 !important;
    color: #1e293b !important;
    font-size: 30px !important;
    line-height: 1.5 !important;
    font-weight: 800 !important;
    letter-spacing: 0 !important;
}
@media (max-width: 640px) {
    .app-page-title { font-size: 24px !important; }
}
.hero { background:#fff; border:1px solid #e2e8f0; border-radius:16px; padding:16px 20px; box-shadow:0 1px 4px rgba(0,0,0,.06); }
[data-testid="stMetric"] { background:#fff !important; border:1px solid #e2e8f0 !important; border-radius:12px !important; padding:16px 18px !important; box-shadow:0 1px 4px rgba(0,0,0,.05) !important; }
[data-testid="stMetricValue"] { font-size:1.35rem !important; font-weight:700 !important; }
[data-testid="stDataFrame"] { background:#fff !important; border:1px solid #e2e8f0 !important; border-radius:10px !important; }
.stButton > button { background:#10b981 !important; color:#fff !important; border-radius:10px !important; border:0 !important; font-weight:600 !important; }
.stButton > button:hover { background:#059669 !important; }
.stTabs [data-baseweb="tab"] { font-size:13px !important; font-weight:500 !important; color:#64748b !important; }
.stTabs [aria-selected="true"] { color:#10b981 !important; font-weight:700 !important; border-bottom-color:#10b981 !important; }
.stAlert { border-radius:10px !important; }
/* ── Tab 質感升級 ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: #f1f5f9;
    padding: 6px 8px;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
}
.stTabs [data-baseweb="tab"] {
    height: 36px;
    padding: 0 16px;
    border-radius: 8px;
    font-size: 13px !important;
    font-weight: 500 !important;
    color: #64748b !important;
    background: transparent;
    border: none;
    white-space: nowrap;
}
.stTabs [data-baseweb="tab"]:hover {
    background: #e2e8f0 !important;
    color: #334155 !important;
}
.stTabs [aria-selected="true"] {
    background: #fff !important;
    color: #10b981 !important;
    font-weight: 700 !important;
    box-shadow: 0 1px 4px rgba(0,0,0,.1);
    border-bottom: none !important;
}
.stTabs [data-baseweb="tab-highlight"] {
    display: none;
}
.stTabs [data-baseweb="tab-border"] {
    display: none;
}
</style>
""", unsafe_allow_html=True)


_original_st_dataframe = st.dataframe


def _localized_number_config(config: Any) -> Any:
    if not isinstance(config, dict):
        return config
    out = dict(config)
    type_config = out.get("type_config")
    if isinstance(type_config, dict) and type_config.get("type") == "number":
        new_type_config = dict(type_config)
        new_type_config["format"] = "localized"
        out["type_config"] = new_type_config
    return out


def _dataframe_with_localized_numbers(data: Any = None, *args: Any, **kwargs: Any) -> Any:
    df = getattr(data, "data", data)
    if isinstance(df, pd.DataFrame):
        column_config = dict(kwargs.get("column_config") or {})
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                existing = column_config.get(col)
                column_config[col] = (
                    st.column_config.NumberColumn(str(col), format="localized")
                    if existing is None
                    else _localized_number_config(existing)
                )
        if column_config:
            kwargs["column_config"] = column_config
    return _original_st_dataframe(data, *args, **kwargs)


st.dataframe = _dataframe_with_localized_numbers


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


def normalize_bool(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    try:
        if pd.isna(v):
            return default
    except Exception:
        pass
    if isinstance(v, str):
        text = v.strip().lower()
        if text in {"true", "1", "yes", "y", "是"}:
            return True
        if text in {"false", "0", "no", "n", "否", ""}:
            return False
    return bool(v)


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    defaults = {
        "id": None, "sort_order": 0, "platform": "台股", "asset_type": "台股",
        "name": "", "ticker": "", "fund_code": "", "fund_pattern": "", "currency": "TWD",
        "original_units": 0.0, "units": 0.0, "corporate_action": "",
        "avg_cost": 0.0, "total_cost_input": 0.0, "monthly_dividend_per_unit": 0.0,
        "purchase_ym": "", "dividend_received_original_total": 0.0,
        "dividend_received_total": 0.0, "dividend_note": "", "note": "",
        "is_reinvest": False,
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
        "dividend_received_original_total": normalize_number(r.get("dividend_received_original_total", 0), 0),
        "dividend_received_total": normalize_number(r.get("dividend_received_total", 0), 0),
        "dividend_note": normalize_text(r.get("dividend_note", ""), ""),
        "note": normalize_text(r.get("note", ""), ""),
        "is_reinvest": normalize_bool(r.get("is_reinvest", False), False),
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


def money_short(v: Any) -> str:
    n = to_float(v)
    if n is None: return "-"
    a = abs(n)
    if a >= 100_000_000: return f"{n/100_000_000:.2f}億"
    if a >= 10_000: return f"{n/10_000:,.1f}萬"
    return f"{n:,.0f}"


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
    # 優先用傳入的 exchange，其次查台股對照，再次查美股對照，最後預設 TPE
    if not exchange:
        if ticker in TW_STOCK_EXCHANGES:
            exchange = TW_STOCK_EXCHANGES[ticker]
        elif ticker in US_STOCK_EXCHANGES:
            exchange = US_STOCK_EXCHANGES[ticker]
        elif ticker.endswith(".TW") or ticker.endswith(".TWO"):
            exchange = "TAI" if ticker.endswith(".TWO") else "TPE"
        else:
            exchange = "NASDAQ"
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


def is_tw_stock_ticker(ticker: str) -> bool:
    """判斷是否為台股 / 台股 ETF ticker。"""
    ticker = normalize_ticker(ticker)
    return ticker.endswith(".TW") or ticker.endswith(".TWO") or ticker in TW_STOCK_EXCHANGES


def tw_now() -> datetime:
    """台灣時間。Streamlit Cloud / GitHub Actions 常是 UTC，這裡固定轉 UTC+8。"""
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))


def fmt_md(dt: datetime) -> str:
    """顯示 M/DD。"""
    return f"{dt.month}/{dt.day:02d}"


def is_tw_market_session(dt: datetime | None = None) -> bool:
    """台股一般交易時段附近：週一到週五 09:00 後到 13:40。"""
    dt = dt or tw_now()
    if dt.weekday() >= 5:
        return False
    minutes = dt.hour * 60 + dt.minute
    return 9 * 60 <= minutes <= 13 * 60 + 40


def tw_stock_market_prefix(ticker: str) -> str:
    """TWSE MIS API 的交易所代碼：上市 tse，上櫃 otc。"""
    ticker = normalize_ticker(ticker)
    exchange = TW_STOCK_EXCHANGES.get(ticker, "")
    if ticker.endswith(".TWO") or exchange == "TAI":
        return "otc"
    return "tse"


def tw_stock_plain_code(ticker: str) -> str:
    """把 2330.TW / 5478.TWO 轉成 TWSE MIS 使用的 2330 / 5478。"""
    ticker = normalize_ticker(ticker)
    return ticker.replace(".TW", "").replace(".TWO", "")


@st.cache_data(ttl=20, show_spinner=False)
def fetch_twse_realtime_quote(ticker: str) -> dict[str, Any]:
    """
    台股即時報價：優先使用證交所 MIS API。
    回傳欄位：price, date, time, status。
    
    說明：
    - z = 最新成交價；若 z 為 '-'，用 b/a 或昨日收盤 y 備援，但會標示非最新成交。
    - d = YYYYMMDD，t = HH:MM:SS。
    - 這比 yfinance history 更適合盤中即時報價。
    """
    ticker = normalize_ticker(ticker)
    code = tw_stock_plain_code(ticker)
    if not code:
        return {"price": None, "date": "—", "time": "—", "status": "台股無代碼"}

    prefix = tw_stock_market_prefix(ticker)
    ex_ch = f"{prefix}_{code}.tw"
    url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
    params = {"ex_ch": ex_ch, "json": "1", "delay": "0", "_": str(int(tw_now().timestamp() * 1000))}
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Referer": "https://mis.twse.com.tw/stock/fibest.jsp",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }

    try:
        r = requests.get(url, params=params, timeout=10, headers=headers)
        r.raise_for_status()
        data = r.json()
        items = data.get("msgArray") or []
        if not items:
            return {"price": None, "date": "—", "time": "—", "status": f"TWSE無資料:{ex_ch}"}
        q = items[0]

        def pick_number(*keys: str) -> float | None:
            for key in keys:
                raw = normalize_text(q.get(key, ""))
                if not raw or raw == "-":
                    continue
                # b / a 可能是 '12.30_'，取第一個價位
                raw = raw.split("_")[0].replace(",", "")
                val = to_float(raw)
                if val is not None and 0 < val < 100000:
                    return float(val)
            return None

        price = pick_number("z")
        source_note = "TWSE即時"
        if price is None:
            price = pick_number("b", "a")
            source_note = "TWSE買賣價備援"
        if price is None:
            price = pick_number("y")
            source_note = "TWSE昨收備援"

        raw_date = normalize_text(q.get("d", ""))
        raw_time = normalize_text(q.get("t", ""))
        date_str = "—"
        if len(raw_date) == 8 and raw_date.isdigit():
            date_str = f"{int(raw_date[4:6])}/{int(raw_date[6:8]):02d}"

        if price is None:
            return {"price": None, "date": date_str, "time": raw_time or "—", "status": f"TWSE無價格:{ex_ch}"}

        return {"price": price, "date": date_str, "time": raw_time or "—", "status": source_note}
    except Exception as e:
        return {"price": None, "date": "—", "time": "—", "status": f"TWSE錯誤:{str(e)[:40]}"}


@st.cache_data(ttl=20, show_spinner=False)
def fetch_stock_price(ticker: str, asset_type: str = "") -> tuple[float | None, str]:
    ticker = normalize_ticker(ticker)
    is_tw = asset_type == "台股" or is_tw_stock_ticker(ticker)

    if is_tw:
        # 台股：先試 Yahoo（最準），再試 TWSE MIS，最後才 Google
        y_price, y_status = fetch_yahoo_price(ticker)
        if y_price is not None:
            return y_price, "Yahoo"

        tw_quote = fetch_twse_realtime_quote(ticker)
        if tw_quote.get("price") is not None:
            return float(tw_quote["price"]), normalize_text(tw_quote.get("status", "TWSE即時"))

        # Google 台股只在前兩者都失敗時才試，且僅限有明確 exchange 的
        if ticker in TW_STOCK_EXCHANGES:
            g_price, g_status = fetch_google_finance_price(ticker, TW_STOCK_EXCHANGES[ticker])
            if g_price is not None:
                return g_price, "Google備援"

        return None, f"Yahoo:{y_status}; TWSE:{tw_quote.get('status')}"

    price, status = fetch_yahoo_price(ticker)
    if price is not None:
        return price, "Yahoo"
    g_price, g_status = fetch_google_finance_price(ticker, None)
    if g_price is not None:
        return g_price, "Google"
    return None, f"{status}; {g_status}"


@st.cache_data(ttl=300, show_spinner=False)
def fetch_gas_fund_nav(code: str) -> tuple[float | None, str]:
    if not GAS_FUND_NAV_URL or not code:
        return None, "GAS未設定"
    last_status = "GAS無可用代碼"
    for query_code in gas_fund_code_candidates(code):
        try:
            r = requests.get(
                GAS_FUND_NAV_URL,
                params={"code": query_code},
                timeout=30,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if r.status_code != 200:
                last_status = f"GAS HTTP {r.status_code}:{query_code}"
                continue
            data = r.json()
            if data.get("ok") and data.get("nav") is not None:
                nav = to_float(data["nav"])
                source = data.get("source", "GAS")
                if nav and nav > 0:
                    return nav, f"GAS({source})✓"
            last_status = f"GAS回傳無淨值:{data.get('error','')}:{query_code}"
        except Exception as e:
            last_status = f"GAS錯誤:{str(e)[:40]}"
    return None, last_status


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
def _fetch_gas_div_for_enrich(fund_code: str) -> float | None:
    if not fund_code:
        return None
    value = _get_gas_data(fund_code).get("monthly_div")
    return float(value) if value else None

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
        "韓幣": "KRW", "韓元": "KRW", "港幣": "HKD",
        "泰幣": "THB", "歐元": "EUR",
    }
    currency = alias.get(currency, currency)
    if currency == "TWD":
        return 1.0, "ok"
    direct_pairs = {
        "USD": "USDTWD=X", "CNY": "CNYTWD=X", "JPY": "JPYTWD=X",
        "KRW": "KRWTWD=X", "HKD": "HKDTWD=X", "THB": "THBTWD=X",
        "EUR": "EURTWD=X", "ZAR": "ZARTWD=X",
    }
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
    dividend_received_original_total = normalize_number(r.get("dividend_received_original_total", 0), 0)
    legacy_dividend_received_total = normalize_number(r.get("dividend_received_total", 0), 0)
    dividend_received_total = (
        dividend_received_original_total * fx
        if dividend_received_original_total > 0 and fx is not None
        else legacy_dividend_received_total
    )
    total_pnl_with_dividend = pnl + dividend_received_total if pnl is not None else None
    total_pnl_rate_with_dividend = total_pnl_with_dividend / twd_cost if total_pnl_with_dividend is not None and twd_cost else None
    is_reinvest = bool(r.get("is_reinvest", False))
    return {
        "成本原幣": cost_original_currency, "市值原幣": value_original_currency,
        "台幣成本": twd_cost, "台幣市值": twd_value,
        "價差損益": pnl, "價差損益率": pnl_rate,
        "累計配息原幣": dividend_received_original_total,
        "累計已領配息": dividend_received_total,
        "含息總損益": total_pnl_with_dividend,
        "含息總損益率": total_pnl_rate_with_dividend,
        "市值股數": market_units,
        "損益": total_pnl_with_dividend,
        "損益率": total_pnl_rate_with_dividend,
    }


def dividend_group_key(row: pd.Series, asset_type: str, fund_code: str = "", currency: str = "") -> tuple[str, str, str, str] | None:
    if normalize_text(asset_type) != "基金":
        return None
    platform = normalize_text(row.get("platform", ""))
    currency = normalize_text(currency or row.get("currency", ""))
    key_code = normalize_text(fund_code or row.get("fund_code", "")) or normalize_match_name(row.get("name", ""))
    if not key_code:
        return None
    return (platform, currency, key_code.lower(), "基金")


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_columns(df)
    if df.empty:
        return df
    rows = []
    dividend_primary_seen: set[tuple[str, str, str, str]] = set()
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
        calc_row = r.copy()
        is_dividend_primary = True
        if asset_type == "基金":
            group_key = dividend_group_key(r, asset_type, fund_code, currency)
            if group_key is not None:
                is_dividend_primary = group_key not in dividend_primary_seen
                dividend_primary_seen.add(group_key)
            if not is_dividend_primary:
                calc_row["dividend_received_original_total"] = 0
                calc_row["dividend_received_total"] = 0
        calc = calculate_cost_and_value(calc_row, price, fx)
        units = normalize_number(calc.get("市值股數", r.get("units", 0)), 0)
        if asset_type == "基金":
            _fc = normalize_text(r.get("fund_code", "")) or infer_fund_fields(normalize_text(r.get("name","")),normalize_text(r.get("fund_code","")),normalize_text(r.get("fund_pattern","")))[0]
            _gas_div = _fetch_gas_div_for_enrich(_fc) if _fc else None
            div_per_unit = _gas_div or normalize_number(r.get("monthly_dividend_per_unit", 0), 0)
            div_source = "GAS" if _gas_div else "手動"
        else:
            div_per_unit = normalize_number(r.get("monthly_dividend_per_unit", 0), 0)
            div_source = "手動"
        monthly_div = units * div_per_unit
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
            "累積配息主列": is_dividend_primary,
            "每單位月配息估算": div_per_unit,
            "每月配息": monthly_div_twd,
            "月配息來源": div_source if div_per_unit else "",
            "狀態": "✓" if price is not None and fx is not None else f"價格:{p_status} 匯率:{fx_status}",
        })
        rows.append(out)
    return pd.DataFrame(rows)


def format_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "sort_order" in out:
        out["sort_order"] = out["sort_order"].apply(lambda x: "" if pd.isna(x) else str(int(float(x))))
    for c in ["即時價格/淨值", "匯率"]:
        if c in out:
            out[c] = out[c].apply(lambda x: money(x, 4))
    for c in ["成本原幣", "市值原幣", "台幣成本", "台幣市值", "價差損益", "累計配息原幣", "累計已領配息", "含息總損益", "損益", "每月配息"]:
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
        "purchase_ym": "購買年月",
        "dividend_received_original_total": "累計配息原幣輸入",
        "dividend_received_total": "累計已領配息台幣舊欄",
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


def parse_sheet_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "—", "nan", "None", "FALSE", "TRUE"}:
        return None
    if text.startswith("#"):
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace(",", "").replace("$", "").replace("NT", "").strip()
    is_percent = text.endswith("%")
    text = text[:-1].strip() if is_percent else text
    try:
        number = float(text)
    except Exception:
        return None
    if negative:
        number = -number
    return number / 100 if is_percent else number


def normalize_sheet_month_label(label: Any) -> str:
    text = str(label).strip()
    match = re.fullmatch(r"(20\d{2})-/(?:[-/]\d{1,2})?", text)
    if not match:
        return ""
    return f"{match.group(1)}-{int(match.group(2)):02d}"


def online_sheet_url(gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{MAIN_GOOGLE_SHEET_ID}/export?format=csv&gid={gid}"


@st.cache_data(ttl=600, show_spinner=False)
def load_online_sheet_csv(gid: str) -> pd.DataFrame:
    response = requests.get(online_sheet_url(gid), timeout=30)
    response.raise_for_status()
    if "<html" in response.text[:200].lower():
        raise RuntimeError("Google Sheet CSV 下載失敗，請確認分享權限或部署端可讀取。")
    df = pd.read_csv(io.StringIO(response.text), dtype=str, keep_default_na=False)
    df = df.dropna(axis=1, how="all")
    empty_cols = [c for c in df.columns if str(c).startswith("Unnamed") and df[c].astype(str).str.strip().eq("").all()]
    if empty_cols:
        df = df.drop(columns=empty_cols)
    return df


def month_columns(df: pd.DataFrame) -> list[str]:
    return [col for col in df.columns if normalize_sheet_month_label(col)]


def extract_monthly_total(df: pd.DataFrame, row_label: str = "合計") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["月份", "金額"])
    label_col = df.columns[0]
    target = df[df[label_col].astype(str).str.strip() == row_label]
    if target.empty:
        target = df.head(1)
    row = target.iloc[0]
    records = []
    for col in month_columns(df):
        month = normalize_sheet_month_label(col)
        amount = parse_sheet_number(row.get(col))
        if amount is None:
            continue
        records.append({"月份": month, "金額": amount})
    return pd.DataFrame(records)


def build_monthly_long_entries(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["月份", "原始項目", "項目", "金額"])
    label_col = df.columns[0]
    records = []
    occurrence_counts: dict[str, int] = {}
    for _, row in df.iterrows():
        raw_item = normalize_text(row.get(label_col, ""))
        if not raw_item or raw_item in {"合計", "總計"}:
            continue
        item = canonical_cash_subject(raw_item, occurrence_counts)
        for col in month_columns(df):
            amount = parse_sheet_number(row.get(col))
            if amount is None or amount == 0:
                continue
            records.append({
                "月份": normalize_sheet_month_label(col),
                "原始項目": raw_item,
                "項目": item,
                "金額": amount,
            })
    return pd.DataFrame(records)


def _cash_subject_record(
    subjects: list[str],
    category: str,
    subcategory: str,
    role: str,
    target_table: str,
    cashflow_type: str,
    note: str = "",
) -> list[dict[str, str]]:
    return [
        {
            "科目": subject,
            "大類": category,
            "子類": subcategory,
            "資料角色": role,
            "建議線上表": target_table,
            "收支屬性": cashflow_type,
            "備註": note,
        }
        for subject in subjects
    ]


CASH_SUBJECT_RULES: list[dict[str, str]] = (
    _cash_subject_record(
        [
            "零用金-餐費", "零用金-食材", "零用金-衣飾", "零用金-頭髮",
            "零用金-化妝保養＋按摩", "零用金-交通1", "零用金-交通2",
            "零用金-書", "零用金-用品", "零用金-電話", "零用金-電影",
            "零用金-命理", "零用金-醫療", "零用金-拜拜", "零用金-其他",
            "零用金-旅行", "零用金-朋友", "零用金-家用",
        ],
        "支出",
        "零用金生活支出",
        "expense",
        "cash_ledger_entries",
        "支出",
    )
    + _cash_subject_record(
        ["零用金-公司", "零用金-公司內勤", "零用金-公司代墊", "零用金-代墊"],
        "支出/代墊",
        "零用金代墊",
        "advance_expense",
        "cash_ledger_entries",
        "代墊",
        "後續可用公司代墊款入帳沖銷。",
    )
    + _cash_subject_record(
        ["零用金", "零用金--總支出", "零用金-支出", "零用金-淨值", "月支出"],
        "彙總",
        "零用金彙總",
        "summary",
        "cash_monthly_snapshots",
        "彙總",
        "這類通常是公式結果，不應當作單筆交易重複入帳。",
    )
    + _cash_subject_record(
        ["薪資入帳", "公司代墊款入帳"],
        "收入",
        "薪資/代墊款入帳",
        "income",
        "cash_ledger_entries",
        "收入",
    )
    + _cash_subject_record(
        [
            "富邦銀行", "元大銀行", "郵局", "台新銀行-建北", "台新銀行-信義",
            "台新銀行-Richard", "台新銀行-子帳戶", "台新銀行-內湖新轉",
            "連線銀行", "將來銀行", "渣打銀行", "中國信託", "樂天銀行",
            "悠遊付", "一卡通",
        ],
        "現金/銀行",
        "台幣帳戶",
        "account_balance",
        "cash_accounts",
        "餘額",
        "轉線上時做帳戶餘額或月份快照，不當作收入或支出。",
    )
    + _cash_subject_record(
        [
            "富邦銀行-銀行利息", "元大bank-銀行利息", "台新bank-銀行利息",
            "連線bank-銀行利息", "將來bank-銀行利息", "樂天bank-銀行利息",
        ],
        "收入",
        "銀行利息",
        "interest_income",
        "cash_ledger_entries",
        "收入",
    )
    + _cash_subject_record(
        ["台銀人壽", "國泰人壽", "新光人壽", "保誠人壽"],
        "保險",
        "保單/保險資產",
        "insurance_balance",
        "insurance_accounts",
        "餘額",
    )
    + _cash_subject_record(
        ["保費支出"],
        "支出",
        "保費支出",
        "insurance_expense",
        "cash_ledger_entries",
        "支出",
    )
    + _cash_subject_record(
        ["保險回饋金"],
        "收入",
        "保險回饋",
        "insurance_rebate",
        "cash_ledger_entries",
        "收入",
    )
    + _cash_subject_record(
        ["台幣換外幣"],
        "轉帳/換匯",
        "台幣換外幣",
        "fx_transfer",
        "cash_transfers",
        "轉帳",
    )
    + _cash_subject_record(
        ["美金", "日幣", "韓幣", "人民幣", "港幣", "泰幣", "歐元"],
        "現金/銀行",
        "外幣現金",
        "foreign_cash_balance",
        "cash_accounts",
        "餘額",
    )
    + _cash_subject_record(
        ["渣打美金", "渣打南非", "台新美金", "台新日幣", "台新南非"],
        "現金/銀行",
        "外幣銀行帳戶",
        "foreign_account_balance",
        "cash_accounts",
        "餘額",
    )
    + _cash_subject_record(
        ["借入"],
        "借款",
        "借入",
        "loan_payable",
        "loan_entries",
        "借入",
    )
    + _cash_subject_record(
        ["借出+投資"],
        "借款/投資",
        "借出與投資",
        "loan_or_investment_outflow",
        "loan_entries",
        "借出/投資",
    )
    + _cash_subject_record(
        ["借出+代墊+借入小計"],
        "彙總",
        "借款代墊小計",
        "summary",
        "cash_monthly_snapshots",
        "彙總",
    )
    + _cash_subject_record(
        [
            "台股-舊資金", "台股-新資金", "台股", "富邦奈米投",
            "基富通-台", "基富通-人", "基富通-日", "渣打-美金",
            "渣打-南非", "台新-美金", "台新-南非",
            "懷思投資", "懷思新增投資", "notyetincome",
        ],
        "投資",
        "投資資金/帳戶",
        "investment_transfer_or_balance",
        "investment_cash_links",
        "投資/轉帳",
    )
    + _cash_subject_record(
        ["懷思投資total"],
        "彙總",
        "懷思投資彙總",
        "summary",
        "investment_snapshots",
        "彙總",
    )
    + _cash_subject_record(
        ["懷思投資報酬", "基金配息", "j渣打-大華"],
        "收入",
        "投資收入",
        "investment_income",
        "cash_ledger_entries",
        "收入",
    )
    + _cash_subject_record(
        [
            "信用卡-渣打 14", "信用卡-富邦 19", "信用卡-聯邦",
            "信用卡-星展 08", "信用卡-台新 18", "信用卡-國泰世華 24",
        ],
        "支出",
        "信用卡消費",
        "credit_card_expense",
        "cash_ledger_entries",
        "支出",
        "信用卡消費只記分類，不建立互轉帳戶。",
    )
)


CASH_SUBJECT_LOOKUP: dict[str, dict[str, str]] = {
    normalize_text(row["科目"]): row for row in CASH_SUBJECT_RULES
}


def classify_cash_subject(subject: Any) -> dict[str, str]:
    item = normalize_text(subject)
    if item in CASH_SUBJECT_LOOKUP:
        return CASH_SUBJECT_LOOKUP[item]
    if not item:
        return {"科目": item, "大類": "未分類", "子類": "空白", "資料角色": "unknown", "建議線上表": "", "收支屬性": "未分類", "備註": ""}
    if "銀行利息" in item or "bank-銀行利息" in item:
        return {"科目": item, "大類": "收入", "子類": "銀行利息", "資料角色": "interest_income", "建議線上表": "cash_ledger_entries", "收支屬性": "收入", "備註": "依名稱自動判斷"}
    if item.startswith("零用金-") or item.startswith("零用金--"):
        return {"科目": item, "大類": "支出", "子類": "零用金待確認", "資料角色": "expense", "建議線上表": "cash_ledger_entries", "收支屬性": "支出", "備註": "依零用金前綴自動判斷"}
    if item.startswith("信用卡-"):
        return {"科目": item, "大類": "支出", "子類": "信用卡消費", "資料角色": "credit_card_expense", "建議線上表": "cash_ledger_entries", "收支屬性": "支出", "備註": "信用卡消費只記分類，不建立互轉帳戶"}
    if item.endswith("人壽"):
        return {"科目": item, "大類": "保險", "子類": "保單/保險資產", "資料角色": "insurance_balance", "建議線上表": "insurance_accounts", "收支屬性": "餘額", "備註": "依人壽名稱自動判斷"}
    if item.startswith("j-") or item.startswith("j"):
        return {"科目": item, "大類": "收入", "子類": "投資收入", "資料角色": "investment_income", "建議線上表": "cash_ledger_entries", "收支屬性": "收入", "備註": "依 j 配息前綴自動判斷"}
    if "配息" in item or "股利" in item or "投資報酬" in item:
        return {"科目": item, "大類": "收入", "子類": "投資收入", "資料角色": "investment_income", "建議線上表": "cash_ledger_entries", "收支屬性": "收入", "備註": "依名稱自動判斷"}
    if "銀行" in item or item in {"郵局", "中國信託", "悠遊付", "一卡通"}:
        return {"科目": item, "大類": "現金/銀行", "子類": "帳戶待確認", "資料角色": "account_balance", "建議線上表": "cash_accounts", "收支屬性": "餘額", "備註": "依帳戶名稱自動判斷"}
    return {"科目": item, "大類": "未分類", "子類": "待確認", "資料角色": "unknown", "建議線上表": "", "收支屬性": "未分類", "備註": "需人工確認"}


def cash_subject_catalog_df() -> pd.DataFrame:
    return pd.DataFrame(CASH_SUBJECT_RULES).drop_duplicates(subset=["科目"], keep="first")


def enrich_cash_ledger_entries(long_entries: pd.DataFrame) -> pd.DataFrame:
    if long_entries.empty:
        return pd.DataFrame(columns=["月份", "原始項目", "項目", "金額", "大類", "子類", "資料角色", "建議線上表", "收支屬性", "備註"])
    rows = []
    for _, row in long_entries.iterrows():
        raw_item = normalize_text(row.get("原始項目", row.get("項目", "")))
        item = normalize_text(row.get("項目", "")) or canonical_cash_subject(raw_item)
        rule = classify_cash_subject(item)
        rows.append({
            "月份": row.get("月份", ""),
            "原始項目": raw_item,
            "項目": item,
            "金額": row.get("金額", 0),
            "大類": rule.get("大類", ""),
            "子類": rule.get("子類", ""),
            "資料角色": rule.get("資料角色", ""),
            "建議線上表": rule.get("建議線上表", ""),
            "收支屬性": rule.get("收支屬性", ""),
            "備註": rule.get("備註", ""),
        })
    return pd.DataFrame(rows)


def sheet_health_rows(loaded: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    error_pattern = re.compile(r"#(?:REF!|DIV/0!|N/A|VALUE!|NAME\\?|ERROR!)")
    for name, df in loaded.items():
        values = df.astype(str)
        error_count = int(values.apply(lambda col: col.str.contains(error_pattern, regex=True, na=False)).sum().sum())
        non_empty = int(values.apply(lambda col: col.str.strip().ne("")).sum().sum())
        rows.append({
            "資料表": name,
            "列數": len(df),
            "欄數": len(df.columns),
            "非空白儲存格": non_empty,
            "公式錯誤格": error_count,
            "CSV": online_sheet_url(ONLINE_SHEET_SOURCES[name]),
        })
    return pd.DataFrame(rows)


def render_online_sheets_tab() -> None:
    st.subheader("📒 線上總表")

    loaded: dict[str, pd.DataFrame] = {}
    failures: list[dict[str, str]] = []
    for name, gid in ONLINE_SHEET_SOURCES.items():
        try:
            loaded[name] = load_online_sheet_csv(gid)
        except Exception as exc:
            failures.append({"資料表": name, "狀態": str(exc)})

    if failures:
        st.error("部分 Google Sheet 無法讀取。")
        st.dataframe(pd.DataFrame(failures), use_container_width=True, hide_index=True)

    if not loaded:
        return

    sheet_tabs = st.tabs(["每月收入", "2026細帳", "現金科目", "資產總覽", "資料健康"])

    with sheet_tabs[0]:
        income = loaded.get("每月收入", pd.DataFrame())
        monthly = extract_monthly_total(income, "合計")
        if monthly.empty:
            st.info("沒有讀到每月收入合計列。")
        else:
            current_year = monthly[monthly["月份"].astype(str).str.startswith("2026-")]
            nonzero = current_year[current_year["金額"] != 0]
            latest = nonzero.iloc[-1] if not nonzero.empty else current_year.iloc[-1] if not current_year.empty else monthly.iloc[-1]
            c1, c2, c3 = st.columns(3)
            c1.metric("2026 已估/已入帳收入", money(current_year["金額"].sum()))
            c2.metric("最近月份", latest["月份"])
            c3.metric("最近月份金額", money(latest["金額"]))
            st.dataframe(
                monthly,
                use_container_width=True,
                hide_index=True,
                column_config={"金額": st.column_config.NumberColumn("金額", format="%.0f")},
            )

    with sheet_tabs[1]:
        ledger = loaded.get("2026細帳", pd.DataFrame())
        long_entries = build_monthly_long_entries(ledger)
        if long_entries.empty:
            st.info("沒有讀到 2026 細帳月份資料。")
        else:
            monthly_sum = long_entries.groupby("月份", as_index=False)["金額"].sum()
            category_sum = (
                long_entries.groupby("項目", as_index=False)["金額"]
                .sum()
                .assign(abs_sum=lambda d: d["金額"].abs())
                .sort_values("abs_sum", ascending=False)
                .drop(columns=["abs_sum"])
                .head(30)
            )
            c1, c2, c3 = st.columns(3)
            c1.metric("線上細帳筆數", f"{len(long_entries):,}")
            c2.metric("月份數", f"{long_entries['月份'].nunique():,}")
            c3.metric("非零項目數", f"{long_entries['項目'].nunique():,}")
            st.markdown("#### 月份合計")
            st.dataframe(
                monthly_sum,
                use_container_width=True,
                hide_index=True,
                column_config={"金額": st.column_config.NumberColumn("金額", format="%.0f")},
            )
            st.markdown("#### 金額最大的項目")
            st.dataframe(
                category_sum,
                use_container_width=True,
                hide_index=True,
                column_config={"金額": st.column_config.NumberColumn("金額", format="%.0f")},
            )
            st.markdown("#### 明細")
            st.dataframe(
                long_entries.sort_values(["月份", "項目"]),
                use_container_width=True,
                hide_index=True,
                height=520,
                column_config={"金額": st.column_config.NumberColumn("金額", format="%.0f")},
            )

    with sheet_tabs[2]:
        ledger = loaded.get("2026細帳", pd.DataFrame())
        long_entries = build_monthly_long_entries(ledger)
        catalog = cash_subject_catalog_df()
        st.markdown("#### 科目字典")
        st.caption("這裡先把你提供的科目轉成線上規則：支出、收入、銀行帳戶、利息、換匯、投資、借款、配息、信用卡與彙總列。")
        c1, c2, c3 = st.columns(3)
        c1.metric("已定義科目", f"{len(catalog):,}")
        c2.metric("大類數", f"{catalog['大類'].nunique():,}")
        c3.metric("建議線上表", f"{catalog['建議線上表'].nunique():,}")

        if long_entries.empty:
            st.info("沒有讀到 2026 細帳月份資料，先顯示科目字典。")
        else:
            classified = enrich_cash_ledger_entries(long_entries)
            unknown = (
                classified[classified["大類"] == "未分類"]
                .groupby("項目", as_index=False)["金額"]
                .sum()
                .assign(abs_sum=lambda d: d["金額"].abs())
                .sort_values("abs_sum", ascending=False)
                .drop(columns=["abs_sum"])
            )
            summary = (
                classified.groupby(["大類", "子類", "資料角色", "建議線上表", "收支屬性"], as_index=False)["金額"]
                .sum()
                .assign(abs_sum=lambda d: d["金額"].abs())
                .sort_values(["大類", "abs_sum"], ascending=[True, False])
                .drop(columns=["abs_sum"])
            )
            month_summary = (
                classified.groupby(["月份", "大類"], as_index=False)["金額"]
                .sum()
                .pivot(index="月份", columns="大類", values="金額")
                .fillna(0)
                .reset_index()
            )
            k1, k2, k3 = st.columns(3)
            k1.metric("已轉換明細", f"{len(classified):,}")
            k2.metric("已分類項目", f"{classified[classified['大類'] != '未分類']['項目'].nunique():,}")
            k3.metric("未分類項目", f"{unknown['項目'].nunique():,}")

            st.markdown("#### 線上轉換摘要")
            st.dataframe(
                summary,
                use_container_width=True,
                hide_index=True,
                height=min(42 * len(summary) + 44, 420),
                column_config={"金額": st.column_config.NumberColumn("金額", format="%.0f")},
            )
            st.markdown("#### 月份 × 大類")
            st.dataframe(
                month_summary,
                use_container_width=True,
                hide_index=True,
                height=min(42 * len(month_summary) + 44, 360),
            )
            if not unknown.empty:
                st.warning("仍有未分類科目，這些需要再補規則。")
                st.dataframe(
                    unknown,
                    use_container_width=True,
                    hide_index=True,
                    height=min(42 * len(unknown) + 44, 280),
                    column_config={"金額": st.column_config.NumberColumn("金額", format="%.0f")},
                )
            st.markdown("#### 轉換後明細")
            st.dataframe(
                classified.sort_values(["月份", "大類", "項目"]),
                use_container_width=True,
                hide_index=True,
                height=520,
                column_config={"金額": st.column_config.NumberColumn("金額", format="%.0f")},
            )

        st.markdown("#### 科目字典明細")
        st.dataframe(
            catalog.sort_values(["大類", "子類", "科目"]),
            use_container_width=True,
            hide_index=True,
            height=520,
        )

    with sheet_tabs[3]:
        overview = loaded.get("資產總覽", pd.DataFrame())
        if overview.empty:
            st.info("沒有讀到資產總覽資料。")
        else:
            st.dataframe(overview.head(80), use_container_width=True, hide_index=True, height=560)

    with sheet_tabs[4]:
        health = sheet_health_rows(loaded)
        st.dataframe(
            health,
            use_container_width=True,
            hide_index=True,
            column_config={
                "非空白儲存格": st.column_config.NumberColumn("非空白儲存格", format="%.0f"),
                "公式錯誤格": st.column_config.NumberColumn("公式錯誤格", format="%.0f"),
                "CSV": st.column_config.LinkColumn("CSV"),
            },
        )


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
            "units", "monthly_dividend_per_unit", "purchase_ym", "dividend_received_original_total",
            "dividend_received_total",
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
    "韓幣": "KRW", "韓元": "KRW", "KRW": "KRW",
    "港幣": "HKD", "HKD": "HKD",
    "泰幣": "THB", "THB": "THB",
    "歐元": "EUR", "EUR": "EUR",
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
            "monthly_dividend_per_unit", "purchase_ym", "dividend_received_original_total",
            "dividend_received_total", "dividend_note", "note", "is_reinvest"]
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
             "dividend_received_original_total": 0.0, "dividend_received_total": 0.0,
             "dividend_note": "", "note": "", "is_reinvest": False}
    base = pd.concat([base, pd.DataFrame([blank])], ignore_index=True)
    edited = st.data_editor(
        base, use_container_width=True, hide_index=True, height=360, num_rows="dynamic",
        column_order=["sort_order", "platform", "asset_type", "name", "ticker", "fund_code", "fund_pattern",
                      "currency", "original_units", "units", "avg_cost", "total_cost_input", "purchase_ym",
                      "dividend_received_original_total", "dividend_received_total",
                      "monthly_dividend_per_unit", "dividend_note", "corporate_action", "note", "is_reinvest"],
        column_config={
            "sort_order": st.column_config.NumberColumn("排序", step=1),
            "platform": st.column_config.SelectboxColumn("平台", options=PLATFORMS, required=True),
            "asset_type": st.column_config.SelectboxColumn("類型", options=ASSET_TYPES, required=True),
            "currency": st.column_config.SelectboxColumn("幣別", options=CURRENCIES, required=True),
            "dividend_received_original_total": st.column_config.NumberColumn("累計配息原幣", format="localized"),
            "dividend_received_total": st.column_config.NumberColumn("累計配息台幣舊欄", format="localized"),
            "is_reinvest": st.column_config.CheckboxColumn("配息再投入"),
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
# 順序：台股 → 美股 → 基富通 → 渣打基金 → 台新基金
# 修正：xyz 消失 / 台股 TypeError / 日期顯示 / 欄位對齊
# ════════════════════════════════════════════════════════════════════════════

OVERVIEW_ORDER = ["台股", "美股", "基富通", "渣打基金", "台新基金"]
PLATFORM_ICONS = {"台股": "📈", "美股": "🇺🇸", "基富通": "🟧", "渣打基金": "🏦", "台新基金": "🟥"}

# 子平台群組定義（sub_label, currency_filter）
SUB_GROUPS: dict[str, list[tuple[str, str]]] = {
    "基富通":  [("基富通-台", "TWD"), ("基富通-人民幣", "CNY"), ("基富通-日", "JPY")],
    "渣打基金":[("渣打-美金",  "USD"), ("渣打-南非",    "ZAR")],
    "台新基金":[("台新-美金",  "USD"), ("台新-南非",    "ZAR")],
    "美股":    [("美股",       "USD")],
    "台股":    [("台股",       "TWD")],
}

# GAS 快取（同 session 只抓一次）
# 結構：{fund_code: {"date":"5/19","monthly_div":0.044,"ex_date":"2026/05/05","pay_date":"2026/05/13"}}
_gas_cache: dict[str, dict] = {}

GAS_FUND_NAV_URL_V3 = GAS_FUND_NAV_URL


def _parse_date_str(raw: str) -> str:
    """YYYY/MM/DD → M/DD，供顯示用"""
    parts = raw.split("/")
    return f"{int(parts[1])}/{int(parts[2]):02d}" if len(parts) == 3 else "—"


def _get_gas_data(fund_code: str) -> dict:
    """
    從 GAS v3 取得基金完整資料：
    {"date":"5/19","monthly_div":0.044,"ex_date":"2026/05/05","pay_date":"2026/05/13"}
    同 session 快取，避免重複 HTTP。
    """
    global _gas_cache
    fund_code = normalize_text(fund_code)
    if fund_code in _gas_cache:
        return _gas_cache[fund_code]

    gas_url = GAS_FUND_NAV_URL_V3
    empty = {"date": "—", "monthly_div": None, "ex_date": None, "pay_date": None}
    if not gas_url or not fund_code:
        _gas_cache[fund_code] = empty
        return empty

    candidates = gas_fund_code_candidates(fund_code)
    result = empty
    for query_code in candidates:
        try:
            r = requests.get(gas_url, params={"code": query_code},
                             timeout=25, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                continue
            data = r.json()
            if data.get("ok"):
                result = {
                    "date":        _parse_date_str(data.get("date", "")),
                    "monthly_div": float(data["monthly_div"]) if data.get("monthly_div") else None,
                    "ex_date":     data.get("ex_date"),    # YYYY/MM/DD
                    "pay_date":    data.get("pay_date"),   # YYYY/MM/DD
                }
                break
        except Exception:
            continue

    for candidate in candidates:
        _gas_cache[candidate] = result
    _gas_cache[fund_code] = result
    return result


def _get_gas_date(fund_code: str) -> str:
    return _get_gas_data(fund_code).get("date", "—")


def _get_gas_monthly_div(fund_code: str) -> float | None:
    return _get_gas_data(fund_code).get("monthly_div")


def _get_gas_ex_date(fund_code: str) -> str | None:
    """除息日 YYYY/MM/DD，用於單位數快照判斷"""
    return _get_gas_data(fund_code).get("ex_date")


def _get_gas_pay_date(fund_code: str) -> str | None:
    """發放日 YYYY/MM/DD，用於累計配息認列"""
    return _get_gas_data(fund_code).get("pay_date")


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

    sum_cols   = ["台幣成本", "台幣市值", "含息總損益", "累計配息原幣", "累計已領配息", "每月配息",
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

    nav_pnl_sub   = total_val - total_cost if total_val and total_cost else 0
    total_pnl_sub = nav_pnl_sub + total_div
    nav_color  = "#6ee7b7" if nav_pnl_sub >= 0 else "#fca5a5"
    tot_color  = "#6ee7b7" if total_pnl_sub >= 0 else "#fca5a5"

    st.markdown(f"""
<div style="background:#f0fdf4;color:#1a2e22;padding:8px 16px;border-radius:8px;
            display:flex;flex-wrap:wrap;align-items:center;gap:14px;
            margin:6px 0 1px 20px;font-size:12px;font-weight:600;
            border:1px solid #bbf7d0;border-left:3px solid #10b981;">
  <span style="font-size:12px;font-family:sans-serif;min-width:90px;font-weight:800;color:#065f46">{sub_label}</span>
  <span style="min-width:100px;font-family:monospace">
    <span style="color:#9ca3af;font-size:10px">成本 </span>{money(total_cost)}</span>
  <span style="min-width:100px;font-family:monospace">
    <span style="color:#9ca3af;font-size:10px">市值 </span>{money(total_val)}</span>
  <span style="min-width:110px;font-family:monospace">
    <span style="color:#9ca3af;font-size:10px">市值損益 </span>
    <span style="color:{'#059669' if nav_pnl_sub>=0 else '#dc2626'};font-weight:700">{signed_money(nav_pnl_sub)}</span></span>
  <span style="min-width:90px;font-family:monospace">
    <span style="color:#9ca3af;font-size:10px">配息 </span>
    <span style="color:#0284c7">{money(total_div)}</span></span>
  <span style="min-width:110px;font-family:monospace">
    <span style="color:#9ca3af;font-size:10px">總損益 </span>
    <span style="color:{'#059669' if total_pnl_sub>=0 else '#dc2626'};font-weight:800">{signed_money(total_pnl_sub)}</span></span>
  <span style="min-width:80px;font-family:monospace">
    <span style="color:#9ca3af;font-size:10px">月配息 </span>
    <span style="color:#7c3aed">{money(total_mdiv)}</span></span>
</div>
""", unsafe_allow_html=True)

    rows_disp = []
    for _, pr in sub_rows.iterrows():
        atype     = normalize_text(pr.get("asset_type", ""))
        price_val = to_float(pr.get("即時價格/淨值"))
        cost_val  = to_float(pr.get("台幣成本")) or 0.0
        mval      = to_float(pr.get("台幣市值")) or 0.0
        pnl_val   = to_float(pr.get("含息總損益"))
        div_original = to_float(pr.get("累計配息原幣")) or 0.0
        div_val   = to_float(pr.get("累計已領配息")) or 0.0
        mdiv      = to_float(pr.get("每月配息")) or 0.0
        rate_val  = to_float(pr.get("含息總損益率"))
        ann_rate  = (mdiv * 12 / cost_val) if cost_val and mdiv else None

        # 取報價日期
        if atype in {"台股", "美股"}:
            date_str = fmt_md(tw_now())
        else:
            fc       = normalize_text(pr.get("fund_code", ""))
            date_str = _get_gas_date(fc) if fc else "—"

        if price_val is None:
            date_str = "❌"

        # 市值損益 = 台幣市值 - 台幣成本（不含配息）
        nav_pnl = (mval - cost_val) if mval and cost_val else None
        nav_pnl_rate = (nav_pnl / cost_val * 100) if nav_pnl is not None and cost_val else None
        total_pnl_val = (nav_pnl + div_val) if nav_pnl is not None else None
        total_pnl_rate = (total_pnl_val / cost_val * 100) if total_pnl_val is not None and cost_val else None

        rows_disp.append({
            "名稱":     normalize_text(pr.get("name", "")),
            "日期":     date_str,
            "現值":     round(price_val, 2)      if price_val is not None else None,
            "台幣成本": round(cost_val, 0)        if cost_val else None,
            "台幣市值": round(mval, 0)            if mval     else None,
            "市值損益": round(nav_pnl, 0)         if nav_pnl  is not None else None,
            "累積配息原幣": round(div_original, 2) if div_original else None,
            "累積配息": round(div_val, 0)         if div_val  else None,
            "總損益":   round(total_pnl_val, 0)   if total_pnl_val is not None else None,
            "市值損益率%": round(nav_pnl_rate, 2) if nav_pnl_rate is not None else None,
            "總損益率%":  round(total_pnl_rate, 2) if total_pnl_rate is not None else None,
            "月配息":   round(mdiv, 0)            if mdiv     else None,
            "配息率%":  round(ann_rate * 100, 2)  if ann_rate else None,
        })

    if rows_disp:
        df_disp = pd.DataFrame(rows_disp)
        col_cfg = {
            "名稱":       st.column_config.TextColumn("名稱",       width="large"),
            "日期":       st.column_config.TextColumn("日期",       width="small"),
            "現值":       st.column_config.NumberColumn("現值",     width="small",  format="%.2f"),
            "台幣成本":   st.column_config.NumberColumn("台幣成本", width="medium", format="%.0f"),
            "台幣市值":   st.column_config.NumberColumn("台幣市值", width="medium", format="%.0f"),
            "市值損益":   st.column_config.NumberColumn("市值損益", width="medium", format="%.0f"),
            "累積配息原幣": st.column_config.NumberColumn("累積配息原幣", width="medium", format="%.2f"),
            "累積配息":   st.column_config.NumberColumn("累積配息", width="medium", format="%.0f"),
            "總損益":     st.column_config.NumberColumn("總損益",   width="medium", format="%.0f"),
            "市值損益率%":st.column_config.NumberColumn("市值損益率%", width="small", format="%.2f"),
            "總損益率%":  st.column_config.NumberColumn("總損益率%",  width="small", format="%.2f"),
            "月配息":     st.column_config.NumberColumn("月配息",   width="small",  format="%.0f"),
            "配息率%":    st.column_config.NumberColumn("配息率%",  width="small",  format="%.2f"),
        }
        # 台股/美股列數多，固定2列高度可上下滾動；基金類自適應
        if sub_label in {"台股", "美股"}:
            tbl_height = 42 * 2 + 44
        else:
            tbl_height = min(42 * len(df_disp) + 44, 480)
        st.dataframe(df_disp, use_container_width=True, hide_index=True,
                     height=tbl_height,
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

    nav_pnl_plt   = total_val - total_cost if total_val and total_cost else 0
    total_pnl_plt = nav_pnl_plt + total_div
    nav_color_plt = "#6ee7b7" if nav_pnl_plt >= 0 else "#fca5a5"
    tot_color_plt = "#6ee7b7" if total_pnl_plt >= 0 else "#fca5a5"
    tot_rate_plt  = total_pnl_plt / total_cost if total_cost else None

    st.markdown(f"""
<div style="background:#fff;color:#1a2e22;padding:14px 20px;border-radius:12px;
            display:flex;flex-wrap:wrap;align-items:center;gap:18px;
            margin:24px 0 4px 0;font-size:13px;font-weight:700;
            border:1.5px solid #d1e8dc;border-left:5px solid #10b981;
            box-shadow:0 2px 10px rgba(16,185,129,.08);">
  <span style="font-size:16px;font-family:sans-serif;min-width:90px;font-weight:800;color:#10b981">{icon} {platform}</span>
  <span style="min-width:120px;font-family:monospace">
    <div style="font-size:10px;color:#6b7280;font-family:sans-serif">成本</div>
    <div style="font-size:14px;font-weight:700">{money(total_cost)}</div>
  </span>
  <span style="min-width:120px;font-family:monospace">
    <div style="font-size:10px;color:#6b7280;font-family:sans-serif">市值</div>
    <div style="font-size:14px;font-weight:700">{money(total_val)}</div>
  </span>
  <span style="min-width:130px;font-family:monospace">
    <div style="font-size:10px;color:#6b7280;font-family:sans-serif">市值損益</div>
    <div style="font-size:14px;font-weight:700;color:{'#059669' if nav_pnl_plt>=0 else '#dc2626'}">{signed_money(nav_pnl_plt)}</div>
  </span>
  <span style="min-width:110px;font-family:monospace">
    <div style="font-size:10px;color:#6b7280;font-family:sans-serif">累積配息</div>
    <div style="font-size:14px;font-weight:700;color:#0284c7">{money(total_div)}</div>
  </span>
  <span style="min-width:140px;font-family:monospace">
    <div style="font-size:10px;color:#6b7280;font-family:sans-serif">總損益</div>
    <div style="font-size:14px;font-weight:800;color:{'#059669' if total_pnl_plt>=0 else '#dc2626'}">{signed_money(total_pnl_plt)} <span style="font-size:11px">({pct(tot_rate_plt)})</span></div>
  </span>
  <span style="min-width:90px;font-family:monospace">
    <div style="font-size:10px;color:#6b7280;font-family:sans-serif">月配息</div>
    <div style="font-size:14px;font-weight:700;color:#7c3aed">{money(total_mdiv)}</div>
  </span>
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
                    ca.markdown(f"**{row['name']}**　{code}　幣別：{row.get('currency','')}")
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


# ════════════════════════════════════════════════════════════════════════════
# ★ 配息自動化：快照單位數 + 認列累計配息
# ════════════════════════════════════════════════════════════════════════════

def _date_diff_days(date_str: str) -> int | None:
    """YYYY/MM/DD 距今幾天（負=過去，正=未來）"""
    try:
        from datetime import date
        parts = date_str.split("/")
        d = date(int(parts[0]), int(parts[1]), int(parts[2]))
        return (d - date.today()).days
    except Exception:
        return None


def _parse_dividend_date(value: Any):
    text = normalize_text(value)
    if not text:
        return None
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y/%m", "%Y-%m"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.date()
        except Exception:
            continue
    return None


def _position_counts_on_ex_date(row: pd.Series, ex_date: str | None) -> bool:
    if not ex_date:
        return True
    purchase_date = _parse_dividend_date(row.get("purchase_ym", ""))
    ex_dt = _parse_dividend_date(ex_date)
    if purchase_date is None or ex_dt is None:
        return True
    return purchase_date <= ex_dt


def _position_dividend_units(row: pd.Series) -> float:
    units = normalize_number(row.get("units", 0), 0)
    original_units = normalize_number(row.get("original_units", 0), 0)
    note = normalize_text(row.get("note", ""))
    is_closed = any(term in note for term in ["已賣出", "已結清", "結清", "賣出"])
    return units if units > 0 or is_closed else original_units


def _fund_name_from_rows(rows: list[pd.Series]) -> str:
    names: list[str] = []
    for row in rows:
        name = normalize_text(row.get("name", ""))
        if name and name not in names:
            names.append(name)
    return " / ".join(names[:2])


def auto_dividend_update(positions: pd.DataFrame) -> int:
    """
    手動執行配息候選更新：
    - 只看當月除息日，不再依發放日自動認列。
    - 配息單位數 = 目前單位數 - 當月購買單位數。
    - 僅寫入/更新未確認的 fund_dividends 候選；實際入帳由使用者在配息記錄表勾選。
    回傳：更新筆數
    """
    positions = ensure_columns(pd.DataFrame(positions))
    if positions.empty:
        return 0

    sb = supabase_client()
    updated = 0

    try:
        existing_rows = sb.table("fund_dividends").select(
            "fund_code,fund_name,platform,currency,ex_date,pay_date,is_paid,units_at_ex,div_amount,actual_div_amount,fx_rate,twd_total,id"
        ).execute()
        existing = {
            (r["fund_code"], r["platform"], r["currency"], _dividend_key_date(r.get("ex_date", ""))): r
            for r in (existing_rows.data or [])
        }
    except Exception:
        existing = {}

    fund_groups: dict[tuple, list[pd.Series]] = {}
    for _, r in positions.iterrows():
        if normalize_text(r.get("asset_type", "")) != "基金":
            continue
        fc = normalize_text(r.get("fund_code", ""))
        plt = normalize_text(r.get("platform", ""))
        cur = normalize_text(r.get("currency", "TWD"))
        if not fc:
            continue
        fund_groups.setdefault((fc, plt, cur), []).append(r)

    for (fc, plt, cur), rows in fund_groups.items():
        gas = _get_gas_data(fc)
        ex_date = gas.get("ex_date")
        div_amt = gas.get("monthly_div")
        if not ex_date or not div_amt or not _is_current_month_date(ex_date):
            continue

        fx_val, _ = fetch_fx(cur)
        fx_val = fx_val or 1.0
        exist_key = (fc, plt, cur, _dividend_key_date(ex_date))
        exist_row = existing.get(exist_key)

        current_units = sum(_position_dividend_units(r) for r in rows)
        month_purchase_units = sum(
            _position_dividend_units(r)
            for r in rows
            if _same_month(r.get("purchase_ym", ""), ex_date)
        )
        total_units = max(0.0, current_units - month_purchase_units)
        if current_units <= 0:
            continue

        payload = {
            "fund_code": fc,
            "fund_name": _fund_name_from_rows(rows),
            "platform": plt,
            "currency": cur,
            "ex_date": ex_date,
            "pay_date": "",
            "div_amount": float(div_amt),
            "actual_div_amount": 0,
            "units_at_ex": float(total_units),
            "fx_rate": float(fx_val),
            "twd_total": 0,
            "is_paid": False,
            "note": f"當月除息候選：目前 {current_units:.4f} - 當月買入 {month_purchase_units:.4f}",
        }
        try:
            if not exist_row:
                sb.table("fund_dividends").insert(payload).execute()
                updated += 1
            elif not normalize_bool(exist_row.get("is_paid", False), False):
                row_id = exist_row.get("id")
                if row_id:
                    update_payload = dict(payload)
                    update_payload["updated_at"] = "now()"
                    sb.table("fund_dividends").update(update_payload).eq("id", int(row_id)).execute()
                    updated += 1
        except Exception:
            pass

    return updated

def render_channel_overview_cards(enriched: pd.DataFrame) -> None:
    """總覽主函式：KPI + 匯率 + 各平台群組（美股→基富通→渣打→台新→台股）"""
    st.markdown("### 💎 所有投資管道總覽")
    if enriched.empty:
        st.info("目前沒有資料。")
        return

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

# ════════════════════════════════════════════════════════════════════════════
# ★ 歷史記錄 Tab
# ════════════════════════════════════════════════════════════════════════════

def _take_snapshot_now(trigger: str = "manual") -> dict:
    """直接使用已計算好的全域 enriched 數值，與總覽 hero bar 保持一致"""
    global enriched, total_value, total_cost, total_pnl_all, total_div_received

    if enriched is None or enriched.empty:
        return {}

    platform_val: dict[str, float] = {
        "台股": 0, "美股": 0, "基富通": 0, "渣打基金": 0, "台新基金": 0
    }

    for _, r in enriched.iterrows():
        plt = normalize_text(r.get("platform", ""))
        val = to_float(r.get("台幣市值"))
        if plt in platform_val and val:
            platform_val[plt] += val

    from datetime import datetime, timezone, timedelta
    tw_now_dt = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))

    return {
        "total_twd":           round(total_value, 0),
        "tw_stock":            round(platform_val["台股"], 0),
        "us_stock":            round(platform_val["美股"], 0),
        "kifutong":            round(platform_val["基富通"], 0),
        "scb":                 round(platform_val["渣打基金"], 0),
        "taishin":             round(platform_val["台新基金"], 0),
        "total_cost":          round(total_cost, 0),
        "total_pnl":           round(total_value - total_cost, 0),
        "cumulative_dividend": round(total_div_received, 0),
        "trigger":             trigger,
        "note":                f"手動快照 {tw_now_dt.strftime('%Y-%m-%d %H:%M')}",
    }


# ════════════════════════════════════════════════════════════════════════════
# ★ 歷史記錄 Tab
# ════════════════════════════════════════════════════════════════════════════

def _take_snapshot_now(trigger: str = "manual") -> dict:
    """即時抓取各平台市值並回傳 dict（供手動記錄用）"""
    if enriched is None or enriched.empty:
        return {}

    platform_val: dict[str, float] = {
        "台股": 0, "美股": 0, "基富通": 0, "渣打基金": 0, "台新基金": 0
    }
    total_cost_sum = 0.0
    total_div_sum  = 0.0

    for _, r in enriched.iterrows():
        plt = normalize_text(r.get("platform", ""))
        val = to_float(r.get("台幣市值"))
        cost= to_float(r.get("台幣成本"))
        div = to_float(r.get("累計已領配息"))
        if plt in platform_val and val:
            platform_val[plt] += val
        if cost: total_cost_sum += cost
        if div:  total_div_sum  += div

    total = sum(platform_val.values())
    from datetime import datetime, timezone, timedelta
    tw_now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))

    return {
        "total_twd":           round(total, 0),
        "tw_stock":            round(platform_val["台股"], 0),
        "us_stock":            round(platform_val["美股"], 0),
        "kifutong":            round(platform_val["基富通"], 0),
        "scb":                 round(platform_val["渣打基金"], 0),
        "taishin":             round(platform_val["台新基金"], 0),
        "total_cost":          round(total_cost_sum, 0),
        "total_pnl":           round(total - total_cost_sum, 0),
        "cumulative_dividend": round(total_div_sum, 0),
        "trigger":             trigger,
        "note":                f"手動快照 {tw_now.strftime('%Y-%m-%d %H:%M')}",
    }


def render_history_tab() -> None:
    """📊 歷史市值"""
    st.subheader("📊 歷史市值走勢")

    # ── 手動記錄按鈕 ──
    col_btn, col_info = st.columns([1, 4])
    if col_btn.button("📸 立即記錄當下市值", key="manual_snapshot_btn"):
        try:
            data = _take_snapshot_now("manual")
            if data:
                supabase_client().table("portfolio_snapshots").insert(data).execute()
                st.success(f"✅ 已記錄！總市值：{money(data['total_twd'])}")
                st.rerun()
            else:
                st.error("無法取得市值，請先更新即時價。")
        except Exception as e:
            st.error(f"記錄失敗：{e}")
    col_info.caption("排程：每天 08:00 / 20:00 自動記錄。也可以手動點按鈕立即記錄。")

    # ── 讀取資料 ──
    try:
        rows = supabase_client().table("portfolio_snapshots") \
            .select("id,snapshot_at,total_twd,tw_stock,us_stock,kifutong,scb,taishin,total_cost,total_pnl,cumulative_dividend,trigger,note") \
            .order("snapshot_at", desc=True) \
            .execute().data or []
    except Exception as e:
        st.error(f"讀取失敗：{e}")
        return

    if not rows:
        st.info("還沒有記錄，點上方按鈕立即記錄一筆。")
        return

    df = pd.DataFrame(rows)
    df["snapshot_at"] = pd.to_datetime(df["snapshot_at"]).dt.tz_convert("Asia/Taipei")
    df = df.sort_values("snapshot_at", ascending=False).reset_index(drop=True)
    df["時間"] = df["snapshot_at"].dt.strftime("%m/%d %H:%M")

    # ── 明細表（愈新愈上）──
    df_show = df[[
        "時間", "total_twd", "tw_stock", "us_stock",
        "kifutong", "scb", "taishin",
        "total_cost", "total_pnl", "cumulative_dividend", "trigger", "note"
    ]].copy()
    df_show.columns = [
        "時間", "總市值", "台股", "美股",
        "基富通", "渣打", "台新",
        "總成本", "市值損益", "累計配息", "觸發方式", "備註"
    ]
    col_cfg = {
        "時間":     st.column_config.TextColumn("時間",       width="small"),
        "總市值":   st.column_config.NumberColumn("總市值",   format="%.0f", width="medium"),
        "台股":     st.column_config.NumberColumn("台股",     format="%.0f", width="medium"),
        "美股":     st.column_config.NumberColumn("美股",     format="%.0f", width="medium"),
        "基富通":   st.column_config.NumberColumn("基富通",   format="%.0f", width="medium"),
        "渣打":     st.column_config.NumberColumn("渣打",     format="%.0f", width="medium"),
        "台新":     st.column_config.NumberColumn("台新",     format="%.0f", width="medium"),
        "總成本":   st.column_config.NumberColumn("總成本",   format="%.0f", width="medium"),
        "市值損益": st.column_config.NumberColumn("市值損益", format="%.0f", width="medium"),
        "累計配息": st.column_config.NumberColumn("累計配息", format="%.0f", width="medium"),
        "觸發方式": st.column_config.TextColumn("觸發方式",   width="small"),
        "備註":     st.column_config.TextColumn("備註",       width="medium"),
    }
    st.dataframe(
        df_show, use_container_width=True, hide_index=True,
        height=min(42 * len(df_show) + 44, 600),
        column_config=col_cfg
    )

    # ── 刪除歷史記錄 ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🗑️ 刪除歷史記錄")

    # 重新讀取供刪除用（不受上方 df 篩選影響）
    try:
        del_rows = supabase_client().table("portfolio_snapshots") \
            .select("id,snapshot_at,total_twd,tw_stock,total_cost,cumulative_dividend,trigger,note") \
            .order("snapshot_at", desc=True) \
            .execute().data or []
    except Exception as e:
        st.error(f"讀取失敗：{e}")
        del_rows = []

    if del_rows:
        del_df = pd.DataFrame(del_rows)
        del_df["snapshot_at"] = pd.to_datetime(del_df["snapshot_at"]).dt.tz_convert("Asia/Taipei")
        del_df["選項"] = (
            del_df["snapshot_at"].dt.strftime("%m/%d %H:%M")
            + "｜" + del_df["trigger"].fillna("")
            + "｜總市值 " + del_df["total_twd"].apply(lambda x: f"{x:,.0f}")
            + "｜累計配息 " + del_df["cumulative_dividend"].apply(lambda x: f"{x:,.0f}")
        )

        col_a, col_b = st.columns([3, 1])
        selected = col_a.multiselect(
            "選擇要刪除的記錄（可多選）",
            options=del_df["選項"].tolist(),
            key="del_snapshot_select",
        )

        if selected:
            selected_ids = del_df[del_df["選項"].isin(selected)]["id"].tolist()
            st.warning(f"即將刪除 {len(selected_ids)} 筆記錄，請確認後按刪除。")
            if col_b.button("🗑️ 確認刪除", key="confirm_del_snapshots"):
                try:
                    for sid in selected_ids:
                        supabase_client().table("portfolio_snapshots") \
                            .delete().eq("id", int(sid)).execute()
                    st.success(f"已刪除 {len(selected_ids)} 筆。")
                    st.rerun()
                except Exception as e:
                    st.error(f"刪除失敗：{e}")

ESTIMATED_DIVIDEND_COLUMNS = [
    "平台",
    "基金名稱",
    "幣別",
    "目前單位數",
    "除息日期",
    "每單位配息",
    "預估配息原幣",
    "匯率",
    "預估配息台幣",
]

ACTUAL_DIVIDEND_COLUMNS = [
    "平台",
    "基金名稱",
    "幣別",
    "目前單位數",
    "當月購買單位數",
    "配息單位數",
    "除息日期",
    "每單位配息",
    "實際配息原幣",
    "匯率",
    "實際配息台幣",
    "確認入帳",
    "累計配息原幣",
    "累計配息台幣",
]

def _fund_name_lookup(enriched_df: pd.DataFrame) -> dict[tuple[str, str, str], str]:
    lookup: dict[tuple[str, str, str], str] = {}
    if enriched_df is None or enriched_df.empty:
        return lookup
    funds = enriched_df[enriched_df["asset_type"].astype(str) == "基金"].copy()
    for _, row in funds.iterrows():
        fc = normalize_text(row.get("fund_code", ""))
        platform = normalize_text(row.get("platform", ""))
        currency = normalize_text(row.get("currency", ""))
        name = normalize_text(row.get("name", ""))
        if not name:
            continue
        lookup[(fc, platform, currency)] = name
        lookup[(fc, "", currency)] = name
        lookup[(fc, "", "")] = name
    return lookup


def _first_positive(values: list[Any]) -> float:
    for value in values:
        number = normalize_number(value, 0)
        if number > 0:
            return number
    return 0.0


def _format_dividend_date(value: Any) -> str:
    parsed = _parse_dividend_date(value)
    if parsed is None:
        return normalize_text(value, "—") or "—"
    return parsed.strftime("%Y/%m/%d")

def _dividend_key_date(value: Any) -> str:
    parsed = _parse_dividend_date(value)
    if parsed is None:
        return normalize_text(value, "")
    return parsed.strftime("%Y/%m/%d")

def _latest_past_date(values: list[Any]) -> str:
    today = tw_now().date()
    parsed_dates = []
    for value in values:
        parsed = _parse_dividend_date(value)
        if parsed is not None and parsed < today:
            parsed_dates.append(parsed)
    if not parsed_dates:
        return "—"
    return max(parsed_dates).strftime("%Y/%m/%d")


def _combined_dividend_records() -> list[dict[str, Any]]:
    records = _fetch_dividend_rows("fund_dividends")
    log_records = _fetch_dividend_rows("dividend_log")
    existing_keys = {
        (
            normalize_text(r.get("fund_code", "")),
            normalize_text(r.get("platform", "")),
            normalize_text(r.get("currency", "")),
            _dividend_key_date(r.get("ex_date", "")),
        )
        for r in records
    }
    for record in log_records:
        key = (
            normalize_text(record.get("fund_code", "")),
            normalize_text(record.get("platform", "")),
            normalize_text(record.get("currency", "")),
            _dividend_key_date(record.get("ex_date", "")),
        )
        if key not in existing_keys:
            copy = dict(record)
            copy["_source_table"] = "dividend_log"
            records.append(copy)
    for record in records:
        record.setdefault("_source_table", "fund_dividends")
    return records


def _dividend_record_variants(fund_code: str, platform: str, currency: str) -> list[tuple[str, str, str]]:
    return [
        (fund_code, platform, currency),
        (fund_code, "", currency),
        (fund_code, platform, ""),
        (fund_code, "", ""),
    ]


def _dividend_history_index(records: list[dict[str, Any]]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        fund_code = normalize_text(record.get("fund_code", ""))
        platform = normalize_text(record.get("platform", ""))
        currency = normalize_text(record.get("currency", ""))
        for key in _dividend_record_variants(fund_code, platform, currency):
            index.setdefault(key, []).append(record)
    return index


def _history_records_for(
    index: dict[tuple[str, str, str], list[dict[str, Any]]],
    fund_code: str,
    platform: str,
    currency: str,
) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for key in _dividend_record_variants(fund_code, platform, currency):
        for record in index.get(key, []):
            marker = (normalize_text(record.get("_source_table", "")), normalize_text(record.get("id", "")))
            if marker in seen:
                continue
            seen.add(marker)
            rows.append(record)
    return rows


def _latest_past_record(records: list[dict[str, Any]], date_col: str) -> dict[str, Any] | None:
    today = tw_now().date()
    candidates: list[tuple[Any, dict[str, Any]]] = []
    for record in records:
        parsed = _parse_dividend_date(record.get(date_col, ""))
        if parsed is not None and parsed < today:
            candidates.append((parsed, record))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0], reverse=True)[0][1]

def _is_current_month_date(value: Any) -> bool:
    parsed = _parse_dividend_date(value)
    if parsed is None:
        return False
    today = tw_now().date()
    return parsed.year == today.year and parsed.month == today.month


def _same_month(left: Any, right: Any) -> bool:
    left_dt = _parse_dividend_date(left)
    right_dt = _parse_dividend_date(right)
    if left_dt is None or right_dt is None:
        return False
    return left_dt.year == right_dt.year and left_dt.month == right_dt.month


def _fund_group_key_from_row(row: pd.Series) -> tuple[str, str, str] | None:
    fund_code = normalize_text(row.get("fund_code", ""))
    platform = normalize_text(row.get("platform", ""))
    currency = normalize_text(row.get("currency", ""))
    if not fund_code:
        return None
    return (fund_code, platform, currency)


def _fund_group_rows(enriched_df: pd.DataFrame | None) -> dict[tuple[str, str, str], pd.DataFrame]:
    if enriched_df is None or enriched_df.empty:
        return {}
    funds = enriched_df[enriched_df["asset_type"].astype(str) == "基金"].copy()
    if funds.empty:
        return {}
    groups: dict[tuple[str, str, str], list[pd.Series]] = {}
    for _, row in funds.iterrows():
        key = _fund_group_key_from_row(row)
        if key is None:
            continue
        groups.setdefault(key, []).append(row)
    return {key: pd.DataFrame(rows) for key, rows in groups.items()}


def _find_fund_group(
    fund_groups: dict[tuple[str, str, str], pd.DataFrame],
    fund_code: str,
    platform: str,
    currency: str,
) -> pd.DataFrame | None:
    direct_key = (fund_code, platform, currency)
    if direct_key in fund_groups:
        return fund_groups[direct_key]

    target_code = normalize_text(fund_code).lower()
    target_platform = normalize_text(platform)
    target_currency = normalize_text(currency).upper()

    for (code, plt, cur), grp in fund_groups.items():
        if (
            normalize_text(code).lower() == target_code
            and normalize_text(plt) == target_platform
            and normalize_text(cur).upper() == target_currency
        ):
            return grp

    for (code, _, cur), grp in fund_groups.items():
        if normalize_text(code).lower() == target_code and normalize_text(cur).upper() == target_currency:
            return grp

    for (code, _, _), grp in fund_groups.items():
        if normalize_text(code).lower() == target_code:
            return grp

    return None


def _fund_current_month_dividend_units(grp: pd.DataFrame, ex_date: Any) -> tuple[float, float, float]:
    current_units = 0.0
    month_purchase_units = 0.0
    for _, row in grp.iterrows():
        row_units = _position_dividend_units(row)
        current_units += row_units
        if _same_month(row.get("purchase_ym", ""), ex_date):
            month_purchase_units += row_units
    dividend_units = max(0.0, current_units - month_purchase_units)
    return current_units, month_purchase_units, dividend_units


def _group_first_positive(grp: pd.DataFrame, column: str) -> float:
    if column not in grp:
        return 0.0
    return _first_positive(grp[column].tolist())


def _fund_current_dividend_totals(grp: pd.DataFrame, fx: float) -> tuple[float, float]:
    if grp is None or grp.empty:
        return 0.0, 0.0

    source = grp
    if "累積配息主列" in grp.columns:
        primary = grp[grp["累積配息主列"].apply(lambda value: normalize_bool(value, False))]
        if not primary.empty:
            source = primary

    original_total = 0.0
    twd_total = 0.0
    for _, row in source.iterrows():
        original = max(
            normalize_number(row.get("累計配息原幣", 0), 0),
            normalize_number(row.get("dividend_received_original_total", 0), 0),
        )
        twd = max(
            normalize_number(row.get("累計已領配息", 0), 0),
            normalize_number(row.get("dividend_received_total", 0), 0),
        )

        if twd <= 0 and original > 0 and fx > 0:
            twd = original * fx

        original_total += original
        twd_total += twd

    return original_total, twd_total


def _current_month_dividend_candidates(
    enriched_df: pd.DataFrame | None,
    existing_keys: set[tuple[str, str, str, str]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for (fund_code, platform, currency), grp in _fund_group_rows(enriched_df).items():
        gas = _get_gas_data(fund_code) if fund_code else {}
        ex_date = normalize_text(gas.get("ex_date", ""))
        if not ex_date or not _is_current_month_date(ex_date):
            continue
        key = (fund_code, platform, currency, _dividend_key_date(ex_date))
        if key in existing_keys:
            continue

        div_per_unit = _group_first_positive(grp, "每單位月配息估算")
        if div_per_unit <= 0:
            div_per_unit = _group_first_positive(grp, "monthly_dividend_per_unit")
        if div_per_unit <= 0:
            div_per_unit = normalize_number(gas.get("monthly_div"), 0)
        if div_per_unit <= 0:
            continue

        current_units, month_purchase_units, dividend_units = _fund_current_month_dividend_units(grp, ex_date)
        if current_units <= 0:
            continue

        fx = _group_first_positive(grp, "匯率")
        if fx <= 0:
            fx, _ = fetch_fx(currency)
            fx = fx or 1.0

        total_amount = dividend_units * div_per_unit
        candidates.append({
            "fund_code": fund_code,
            "fund_name": _fund_name_from_rows([r for _, r in grp.iterrows()]),
            "platform": platform,
            "currency": currency,
            "ex_date": ex_date,
            "pay_date": "",
            "div_amount": div_per_unit,
            "actual_div_amount": 0,
            "units_at_ex": dividend_units,
            "fx_rate": fx,
            "twd_total": total_amount * fx,
            "is_paid": False,
            "note": "當月除息候選",
            "_source_table": "dividend_log_candidate",
            "_current_units": current_units,
            "_month_purchase_units": month_purchase_units,
        })
    return candidates


def build_estimated_dividend_table(enriched_df: pd.DataFrame) -> pd.DataFrame:
    if enriched_df is None or enriched_df.empty:
        return pd.DataFrame(columns=ESTIMATED_DIVIDEND_COLUMNS + ["_預估配息台幣"])

    funds = enriched_df[enriched_df["asset_type"].astype(str) == "基金"].copy()
    if funds.empty:
        return pd.DataFrame(columns=ESTIMATED_DIVIDEND_COLUMNS + ["_預估配息台幣"])

    history_index = _dividend_history_index(_combined_dividend_records())

    funds["_dividend_key"] = funds.apply(
        lambda r: "|".join([
            normalize_text(r.get("platform", "")),
            normalize_text(r.get("fund_code", "")) or normalize_text(r.get("name", "")),
            normalize_text(r.get("currency", "")),
        ]),
        axis=1,
    )

    rows: list[dict[str, Any]] = []
    for _, grp in funds.groupby("_dividend_key", dropna=False):
        first = grp.iloc[0]
        platform = normalize_text(first.get("platform", ""))
        fund_code = normalize_text(first.get("fund_code", ""))
        currency = normalize_text(first.get("currency", ""))
        fund_name = normalize_text(first.get("name", ""))
        units = sum(normalize_number(r.get("市值股數", r.get("units", 0)), 0) for _, r in grp.iterrows())
        if units <= 0:
            continue

        history_rows = _history_records_for(history_index, fund_code, platform, currency)
        latest_history = _latest_past_record(history_rows, "ex_date")
        gas = _get_gas_data(fund_code) if fund_code else {}
        ex_date = _latest_past_date([gas.get("ex_date")] + [r.get("ex_date", "") for r in history_rows])

        div_per_unit = _first_positive(grp.get("每單位月配息估算", pd.Series(dtype=float)).tolist())
        if div_per_unit <= 0:
            div_per_unit = _first_positive(grp.get("monthly_dividend_per_unit", pd.Series(dtype=float)).tolist())
        if div_per_unit <= 0:
            div_per_unit = normalize_number(gas.get("monthly_div"), 0)
        if div_per_unit <= 0 and latest_history:
            div_per_unit = _first_positive([
                latest_history.get("actual_div_amount", 0),
                latest_history.get("div_amount", 0),
            ])
        fx = _first_positive(grp.get("匯率", pd.Series(dtype=float)).tolist())
        if fx <= 0:
            fx, _ = fetch_fx(currency)
            fx = fx or 1.0
        if div_per_unit <= 0 and units > 0 and fx > 0:
            monthly_div_twd = _first_positive(grp.get("每月配息", pd.Series(dtype=float)).tolist())
            if monthly_div_twd > 0:
                div_per_unit = monthly_div_twd / fx / units
        total_amount = units * div_per_unit
        rows.append({
            "平台": platform,
            "基金名稱": fund_name,
            "幣別": currency,
            "目前單位數": units,
            "除息日期": ex_date,
            "每單位配息": div_per_unit if div_per_unit > 0 else None,
            "預估配息原幣": total_amount if div_per_unit > 0 else None,
            "匯率": fx,
            "預估配息台幣": total_amount * fx if div_per_unit > 0 else None,
            "_預估配息台幣": total_amount * fx if div_per_unit > 0 else 0,
        })
    return pd.DataFrame(rows, columns=ESTIMATED_DIVIDEND_COLUMNS + ["_預估配息台幣"]).sort_values(["平台", "基金名稱"])


def _fetch_dividend_rows(table_name: str) -> list[dict[str, Any]]:
    try:
        return supabase_client().table(table_name).select("*").execute().data or []
    except Exception:
        return []


def build_actual_dividend_table(enriched_df: pd.DataFrame) -> pd.DataFrame:
    name_lookup = _fund_name_lookup(enriched_df)
    records = _combined_dividend_records()
    existing_keys = {
        (
            normalize_text(record.get("fund_code", "")),
            normalize_text(record.get("platform", "")),
            normalize_text(record.get("currency", "")),
            _dividend_key_date(record.get("ex_date", "")),
        )
        for record in records
    }
    records = records + _current_month_dividend_candidates(enriched_df, existing_keys)
    fund_groups = _fund_group_rows(enriched_df)

    rows: list[dict[str, Any]] = []
    for record in records:
        fund_code = normalize_text(record.get("fund_code", ""))
        platform = normalize_text(record.get("platform", ""))
        currency = normalize_text(record.get("currency", ""))
        ex_date = normalize_text(record.get("ex_date", ""))
        name = (
            normalize_text(record.get("fund_name", ""))
            or name_lookup.get((fund_code, platform, currency), "")
            or name_lookup.get((fund_code, "", currency), "")
            or name_lookup.get((fund_code, "", ""), "")
            or fund_code
        )

        units = normalize_number(record.get("units_at_ex", 0), 0)
        current_units = normalize_number(record.get("_current_units", None), None)
        month_purchase_units = normalize_number(record.get("_month_purchase_units", None), None)
        estimated_div = normalize_number(record.get("div_amount", 0), 0)
        is_paid = normalize_bool(record.get("is_paid", False), False)
        actual_div = normalize_number(record.get("actual_div_amount", 0), 0)
        fx = normalize_number(record.get("fx_rate", 1), 1)

        group = fund_groups.get((fund_code, platform, currency))
        current_acc_original = 0.0
        current_acc_twd = 0.0
        if group is not None:
            current_acc_original, current_acc_twd = _fund_current_dividend_totals(group, fx)

        if group is not None and _is_current_month_date(ex_date):
            calc_current_units, calc_month_purchase_units, calc_dividend_units = _fund_current_month_dividend_units(group, ex_date)
            current_units = calc_current_units
            month_purchase_units = calc_month_purchase_units
            if not is_paid:
                units = calc_dividend_units

        if is_paid and actual_div <= 0:
            actual_div = estimated_div
        display_div = actual_div if actual_div > 0 else estimated_div
        total_amount = units * display_div if units >= 0 and display_div > 0 else None

        twd_total = normalize_number(record.get("twd_total", 0), 0)
        if twd_total <= 0 and total_amount is not None:
            twd_total = total_amount * fx
        if total_amount is None and twd_total > 0 and fx > 0:
            total_amount = twd_total / fx

        rows.append({
            "平台": platform,
            "基金名稱": name,
            "幣別": currency,
            "目前單位數": current_units,
            "當月購買單位數": month_purchase_units,
            "配息單位數": units,
            "除息日期": _format_dividend_date(ex_date),
            "每單位配息": display_div if display_div > 0 else None,
            "實際配息原幣": total_amount if total_amount is not None else None,
            "匯率": fx,
            "實際配息台幣": twd_total if twd_total > 0 else None,
            "確認入帳": is_paid,
            "_確認前": is_paid,
            "_累計用配息金額": total_amount if is_paid and total_amount is not None else 0,
            "_累計用配息台幣": twd_total if is_paid else 0,
            "_實際配息台幣": twd_total,
            "_目前累計配息原幣": current_acc_original,
            "_目前累計配息台幣": current_acc_twd,
            "_fund_code": fund_code,
            "_platform": platform,
            "_currency": currency,
            "_id": record.get("id"),
            "_source_table": record.get("_source_table", "fund_dividends"),
            "_fx_rate": fx,
            "_ex_date": ex_date,
            "_fund_name": name,
            "_sort_date": _parse_dividend_date(ex_date),
        })

    internal_cols = [
        "_確認前", "_累計用配息金額", "_累計用配息台幣", "_實際配息台幣",
        "_目前累計配息原幣", "_目前累計配息台幣",
        "_fund_code", "_platform", "_currency", "_id", "_source_table",
        "_fx_rate", "_ex_date", "_fund_name", "_sort_date",
    ]
    columns = ACTUAL_DIVIDEND_COLUMNS + internal_cols
    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(rows)
    df["_sort_date"] = df["_sort_date"].apply(lambda d: pd.Timestamp(d) if d is not None else pd.Timestamp.min)
    df = df.sort_values(["平台", "基金名稱", "幣別", "_sort_date"], ascending=True).reset_index(drop=True)
    df["累計配息原幣"] = df["_目前累計配息原幣"].round(2)
    df["累計配息台幣"] = df["_目前累計配息台幣"].round(0)
    df = df.sort_values("_sort_date", ascending=False).reset_index(drop=True)
    return df[columns]

def render_estimated_dividend_table(df: pd.DataFrame, height_cap: int = 520) -> None:
    if df.empty:
        st.info("目前沒有資料。")
        return
    display_df = df[ESTIMATED_DIVIDEND_COLUMNS].copy()
    col_cfg = {
        "基金名稱": st.column_config.TextColumn("基金名稱", width="large"),
        "目前單位數": st.column_config.NumberColumn("目前單位數", format="%.4f"),
        "每單位配息": st.column_config.NumberColumn("每單位配息", format="%.6f"),
        "預估配息原幣": st.column_config.NumberColumn("預估配息原幣", format="localized"),
        "匯率": st.column_config.NumberColumn("匯率", format="%.4f"),
        "預估配息台幣": st.column_config.NumberColumn("預估配息台幣", format="localized"),
    }
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=min(42 * len(display_df) + 44, height_cap),
        column_config=col_cfg,
    )


def update_position_dividend_original_total(
    fund_code: str,
    platform: str,
    currency: str,
    delta_original: float,
) -> bool:
    delta_original = normalize_number(delta_original, 0)
    if not fund_code or delta_original == 0:
        return False
    try:
        rows = supabase_client().table("positions").select(
            "id,sort_order,fund_code,platform,currency,dividend_received_original_total"
        ).eq("platform", platform).eq("currency", currency).execute().data or []
    except Exception:
        rows = []
    matched = [
        row for row in rows
        if normalize_text(row.get("fund_code", "")).lower() == normalize_text(fund_code).lower()
    ]
    if not matched:
        return False
    matched = sorted(
        matched,
        key=lambda row: (
            normalize_number(row.get("sort_order", 999999), 999999),
            normalize_number(row.get("id", 999999), 999999),
        ),
    )
    primary = matched[0]
    primary_id = int(float(primary["id"]))
    current_total = normalize_number(primary.get("dividend_received_original_total", 0), 0)
    new_total = max(0, current_total + delta_original)
    supabase_client().table("positions").update({
        "dividend_received_original_total": new_total,
        "dividend_received_total": 0,
    }).eq("id", primary_id).execute()
    return True


def render_actual_dividend_table(df: pd.DataFrame, height_cap: int = 520) -> None:
    if df.empty:
        st.info("目前沒有實際配息記錄。")
        return
    display_df = df[ACTUAL_DIVIDEND_COLUMNS].copy()
    col_cfg = {
        "基金名稱": st.column_config.TextColumn("基金名稱", width="large"),
        "目前單位數": st.column_config.NumberColumn("目前單位數", format="localized"),
        "當月購買單位數": st.column_config.NumberColumn("當月購買單位數", format="localized"),
        "配息單位數": st.column_config.NumberColumn("配息單位數", format="localized"),
        "除息日期": st.column_config.TextColumn("除息日期"),
        "每單位配息": st.column_config.NumberColumn("每單位配息", format="%.6f"),
        "實際配息原幣": st.column_config.NumberColumn("實際配息原幣", format="localized"),
        "匯率": st.column_config.NumberColumn("匯率", format="%.4f"),
        "實際配息台幣": st.column_config.NumberColumn("實際配息台幣", format="localized"),
        "確認入帳": st.column_config.CheckboxColumn("確認入帳"),
        "累計配息原幣": st.column_config.NumberColumn("累計配息原幣", format="localized"),
        "累計配息台幣": st.column_config.NumberColumn("累計配息台幣", format="localized"),
    }
    edited = st.data_editor(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=min(42 * len(display_df) + 44, height_cap),
        column_config=col_cfg,
        disabled=[c for c in ACTUAL_DIVIDEND_COLUMNS if c != "確認入帳"],
        key="actual_dividend_editor",
    )
        if st.button("💾 儲存確認入帳", key="save_actual_dividend_confirm"):
        sb = supabase_client()
        updated = 0
        for pos, (_, row) in enumerate(edited.iterrows()):
            source_row = df.iloc[pos]
            old_confirmed = normalize_bool(source_row.get("_確認前", False), False)
            new_confirmed = normalize_bool(row.get("確認入帳", False), False)
            if old_confirmed == new_confirmed:
                continue

            row_id = source_row.get("_id")
            source_table = normalize_text(source_row.get("_source_table", "fund_dividends"), "fund_dividends")
            units = normalize_number(row.get("配息單位數", 0), 0)
            div_amount = normalize_number(row.get("每單位配息", 0), 0)
            total_amount = normalize_number(row.get("實際配息原幣", 0), 0)
            if total_amount <= 0 and units > 0 and div_amount > 0:
                total_amount = units * div_amount
            actual_div = total_amount / units if total_amount > 0 and units > 0 else div_amount
            fx = normalize_number(source_row.get("_fx_rate", 1), 1)

            payload = {
                "is_paid": new_confirmed,
                "actual_div_amount": actual_div,
                "twd_total": round(total_amount * fx, 0) if total_amount > 0 else 0,
            }

            row_id_text = normalize_text(row_id, "")
            has_row_id = row_id is not None and row_id_text not in {"", "nan", "None"}
            if source_table == "dividend_log_candidate":
                if not new_confirmed:
                    continue
                insert_payload = {
                    "fund_code": normalize_text(source_row.get("_fund_code", "")),
                    "fund_name": normalize_text(source_row.get("_fund_name", row.get("基金名稱", ""))),
                    "platform": normalize_text(source_row.get("_platform", "")),
                    "currency": normalize_text(source_row.get("_currency", "")),
                    "ex_date": normalize_text(source_row.get("_ex_date", row.get("除息日期", ""))),
                    "pay_date": "",
                    "div_amount": div_amount,
                    "actual_div_amount": actual_div,
                    "units_at_ex": units,
                    "fx_rate": fx,
                    "twd_total": round(total_amount * fx, 0) if total_amount > 0 else 0,
                    "is_paid": True,
                    "note": f"當月除息確認入帳 {tw_now().strftime('%Y/%m/%d')}",
                }
                sb.table("dividend_log").insert(insert_payload).execute()
            elif has_row_id:
                if source_table == "fund_dividends":
                    payload["updated_at"] = "now()"
                sb.table(source_table).update(payload).eq("id", int(float(row_id))).execute()
            else:
                continue

            if total_amount > 0:
                delta_original = total_amount if new_confirmed else -total_amount
                update_position_dividend_original_total(
                    normalize_text(source_row.get("_fund_code", "")),
                    normalize_text(source_row.get("_platform", "")),
                    normalize_text(source_row.get("_currency", "")),
                    delta_original,
                )
            updated += 1

        if updated:
            st.success(f"已更新 {updated} 筆確認狀態。")
            st.cache_data.clear()
            st.rerun()
        else:
            st.info("沒有勾選狀態需要更新。")

def render_dividend_log_tab(enriched_df: pd.DataFrame | None = None) -> None:
    """💰 配息記錄"""
    st.subheader("💰 配息記錄")

    # ── 配息操作按鈕 ──
    action_col1, action_col2 = st.columns([1, 1])
    if action_col1.button("💰 執行配息快照 / 認列", key="run_auto_dividend_update"):
        try:
            source_positions = globals().get("positions", pd.DataFrame())
            n = auto_dividend_update(source_positions)
            if n > 0:
                st.success(f"配息更新完成：{n} 筆")
                st.cache_data.clear()
            else:
                st.info("目前沒有需要認列或快照的配息。")
        except Exception as exc:
            st.warning(f"配息更新失敗：{exc}")

    if action_col2.button("同步基金每單位月配息", key="sync_fund_monthly_dividend"):
        source = enriched_df if enriched_df is not None else globals().get("enriched", pd.DataFrame())
        fund_rows = source[
            (source["asset_type"] == "基金") &
            (source["fund_code"].fillna("") != "") &
            (source["monthly_dividend_per_unit"].fillna(0) == 0)
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
                    sb.table("positions").update(
                        {"monthly_dividend_per_unit": mdiv}
                    ).eq("fund_code", fc).execute()
                    done_codes.add(fc)
                    updated += 1
            if updated:
                st.success(f"已更新 {updated} 檔基金每單位月配息。")
                st.cache_data.clear()
            else:
                st.info("沒有需要回填的基金每月配息。")
        else:
            st.info("沒有需要回填的基金每月配息。")

    source = enriched_df if enriched_df is not None else globals().get("enriched", pd.DataFrame())
    estimate_df = build_estimated_dividend_table(source)
    actual_df = build_actual_dividend_table(source)

    platforms = sorted(
        set(estimate_df.get("平台", pd.Series(dtype=str)).dropna().astype(str))
        | set(actual_df.get("平台", pd.Series(dtype=str)).dropna().astype(str))
    )
    selected_platform = st.selectbox("篩選平台", ["全部"] + platforms, key="div_record_platform")
    if selected_platform != "全部":
        estimate_df = estimate_df[estimate_df["平台"] == selected_platform].reset_index(drop=True)
        actual_df = actual_df[actual_df["平台"] == selected_platform].reset_index(drop=True)

    est_twd = estimate_df["_預估配息台幣"].fillna(0).sum() if "_預估配息台幣" in estimate_df else 0
    paid_df = actual_df[actual_df["確認入帳"] == True] if "確認入帳" in actual_df else pd.DataFrame()
    paid_twd = paid_df["_實際配息台幣"].fillna(0).sum() if not paid_df.empty and "_實際配息台幣" in paid_df else 0
    c1, c2, c3 = st.columns(3)
    c1.metric("預估配息折台幣", money(est_twd))
    c2.metric("已確認實際配息折台幣", money(paid_twd))
    c3.metric("配息記錄筆數", f"{len(actual_df):,}")

    st.markdown("#### 預估配息表")
    st.caption("目前單位數 × 最近一次每單位配息金額 = 預估配息原幣；再乘匯率得到預估配息台幣。除息日期取離今天最近且小於今天的日期。")
    render_estimated_dividend_table(estimate_df)

    st.markdown("#### 配息記錄表")
    st.caption("實際配息改依當月除息日列出；配息單位數 = 目前單位數 - 當月購買單位數。勾選確認入帳後，實際配息原幣會加入持倉累計配息。")
    render_actual_dividend_table(actual_df)

    st.markdown("---")

    with st.expander("➕ 手動新增配息記錄（補填歷史）"):
        st.caption("用於補填歷史配息；實際配息留 0 時，確認入帳記錄會用每單位配息 × 配息單位數代入。")
        with st.form("manual_div_log"):
            c1, c2, c3 = st.columns(3)
            m_platform  = c1.selectbox("平台", PLATFORMS[2:], key="mdl_platform")
            m_currency  = c2.selectbox("幣別", CURRENCIES[1:], key="mdl_currency")
            m_fund_code = c3.text_input("基金代號", key="mdl_fund_code")
            m_fund_name = st.text_input("基金名稱", key="mdl_fund_name")
            c4, c5 = st.columns(2)
            m_ex_date  = c4.text_input("除息日（YYYY/MM/DD）", key="mdl_ex_date")
            m_pay_date = c5.text_input("發放日（YYYY/MM/DD）", key="mdl_pay_date")
            c6, c7, c8, c9 = st.columns(4)
            m_div_amt = c6.number_input("每單位配息", value=0.0, format="%.6f", key="mdl_div_amt")
            m_units = c7.number_input("配息單位數", value=0.0, format="%.4f", key="mdl_units")
            m_actual_total = c8.number_input("實際配息原幣", value=0.0, format="%.2f", key="mdl_actual_total")
            m_fx = c9.number_input("匯率", value=1.0, format="%.4f", key="mdl_fx")
            m_total = m_actual_total if m_actual_total > 0 else m_units * m_div_amt
            st.caption(f"總配息原幣：**{money(m_total, 2)} {m_currency}**｜換算台幣：**{money(m_total * m_fx)}**")
            m_is_paid = st.checkbox("確認入帳（加入累計配息原幣）", key="mdl_is_paid")
            m_note = st.text_input("備註", key="mdl_note")

            if st.form_submit_button("💾 新增"):
                if not m_fund_code or not m_ex_date:
                    st.error("基金代號和除息日必填")
                else:
                    try:
                        actual_div = m_total / m_units if m_units > 0 and m_total > 0 else m_div_amt
                        twd_total = m_total * m_fx
                        payload = {
                            "fund_code": m_fund_code,
                            "fund_name": m_fund_name,
                            "platform": m_platform,
                            "currency": m_currency,
                            "ex_date": m_ex_date,
                            "pay_date": m_pay_date,
                            "div_amount": m_div_amt,
                            "actual_div_amount": actual_div if m_is_paid else 0,
                            "units_at_ex": m_units,
                            "fx_rate": m_fx,
                            "twd_total": round(twd_total, 0),
                            "is_paid": m_is_paid,
                            "note": m_note or "手動新增",
                        }
                        supabase_client().table("dividend_log").insert(payload).execute()
                        if m_is_paid and m_total > 0:
                            update_position_dividend_original_total(
                                m_fund_code,
                                m_platform,
                                m_currency,
                                m_total,
                            )
                        st.success("已新增！"); st.rerun()
                    except Exception as e:
                        st.error(f"新增失敗：{e}")
                        
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
            tw_quote = fetch_twse_realtime_quote(normalized) if is_tw_stock_ticker(normalized) else {}
            final_price, final_status = fetch_stock_price(normalized, "台股" if is_tw_stock_ticker(normalized) else "美股")
            st.write({"ticker": normalized, "exchange": US_STOCK_EXCHANGES.get(normalized, "NASDAQ"),
                      "twse_quote": tw_quote,
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
            "dividend_received_original_total": 0, "dividend_received_total": 0, "dividend_note": "",
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
            "monthly_dividend_per_unit", "purchase_ym", "dividend_received_original_total",
            "dividend_received_total", "dividend_note", "corporate_action", "note"]
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
                   "monthly_dividend_per_unit", "purchase_ym", "dividend_received_original_total",
                   "dividend_received_total", "dividend_note", "note"]
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
                    "monthly_dividend_per_unit": 0, "dividend_received_original_total": 0,
                    "dividend_received_total": 0, "dividend_note": "", "corporate_action": ""}
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
# ★ 現金流 Tab：帳戶、交易、科目字典
# ════════════════════════════════════════════════════════════════════════════

TXN_TYPES = ["轉帳", "收入", "支出", "利息收入", "利息支出", "信用卡消費", "投資買入", "投資賣出", "借入", "借出", "代墊"]
CASH_ACCOUNT_CATEGORIES = ["現金", "銀行", "外幣", "投資", "保險", "借款/代墊", "其他"]
NET_ASSET_CATEGORIES = ["現金", "銀行", "外幣", "投資", "保險"]
LIABILITY_CATEGORIES = ["借款/代墊"]
TRANSFER_ACCOUNT_CATEGORIES = {"銀行", "外幣", "投資", "保險", "借款/代墊", "其他"}
TRANSFER_ACCOUNT_ROLES = {
    "account_balance", "foreign_cash_balance", "foreign_account_balance",
    "insurance_balance", "investment_transfer_or_balance",
    "loan_payable", "loan_or_investment_outflow",
}

CASH_SUBJECT_ALIASES = {
    "food": "零用金-餐費",
    "clothes": "零用金-衣飾",
    "shoes": "零用金-衣飾",
    "hair": "零用金-頭髮",
    "makingup+按摩": "零用金-化妝保養＋按摩",
    "books": "零用金-書",
    "用品": "零用金-用品",
    "tel": "零用金-電話",
    "movie": "零用金-電影",
    "sing": "零用金-命理",
    "medicine": "零用金-醫療",
    "拜拜": "零用金-拜拜",
    "other": "零用金-其他",
    "company-檸檬早午餐": "零用金-公司",
    "company-檸檬內勤": "零用金-公司內勤",
    "company-檸檬代墊": "零用金-公司代墊",
    "travel": "零用金-旅行",
    "friends": "零用金-朋友",
    "home": "零用金-家用",
    "prettycash": "零用金",
    "總支出": "零用金--總支出",
    "支出": "零用金-支出",
    "netprettycash": "零用金-淨值",
    "salary": "薪資入帳",
    "台新基金": "台新基金",
    "日幣 suica": "日幣",
    "stock": "台股-舊資金",
    "new stock": "台股-新資金",
    "stock total": "台股",
    "j-基富通-台": "基金配息",
    "j-基富通-人": "基金配息",
    "j-基富通-日": "基金配息",
    "j-渣打-大華": "j渣打-大華",
    "j-渣打-美金": "基金配息",
    "j-渣打-南非": "基金配息",
    "j-台新-美金": "基金配息",
    "j-台新-南非": "基金配息",
    "credit渣打 14": "信用卡-渣打 14",
    "credit富邦 19": "信用卡-富邦 19",
    "credit聯邦": "信用卡-聯邦",
    "credit花旗 08": "信用卡-星展 08",
    "credit台新 18": "信用卡-台新 18",
    "credit國泰世華 24": "信用卡-國泰世華 24",
    "保費": "保費支出",
}

CASH_SUBJECT_OCCURRENCE_ALIASES = {
    ("traffic", 1): "零用金-交通1",
    ("traffic", 2): "零用金-交通2",
    ("代墊", 1): "零用金-代墊",
    ("代墊", 2): "公司代墊款入帳",
}


def canonical_cash_subject(subject: Any, occurrence_counts: dict[str, int] | None = None) -> str:
    item = normalize_text(subject)
    if not item:
        return ""
    if occurrence_counts is not None:
        occurrence_counts[item] = occurrence_counts.get(item, 0) + 1
        occurrence_alias = CASH_SUBJECT_OCCURRENCE_ALIASES.get((item, occurrence_counts[item]))
        if occurrence_alias:
            return occurrence_alias
    return CASH_SUBJECT_ALIASES.get(item, item)


def _is_transfer_account_rule(rule: dict[str, str]) -> bool:
    role = normalize_text(rule.get("資料角色", ""))
    return role in TRANSFER_ACCOUNT_ROLES


def _unique_keep_order(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = normalize_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def cash_subject_options() -> list[str]:
    return cash_subject_catalog_df()["科目"].dropna().astype(str).tolist()


def _cash_subject_currency(subject: str) -> str:
    subject = normalize_text(subject)
    if any(token in subject for token in ["美金", "美元"]):
        return "USD"
    if "日幣" in subject or "日圓" in subject or subject.endswith("-日") or "台新日幣" in subject:
        return "JPY"
    if "人民幣" in subject or subject.endswith("-人"):
        return "CNY"
    if "南非" in subject:
        return "ZAR"
    if "韓幣" in subject:
        return "KRW"
    if "港幣" in subject:
        return "HKD"
    if "泰幣" in subject:
        return "THB"
    if "歐元" in subject:
        return "EUR"
    return "TWD"


def _cash_account_category(rule: dict[str, str]) -> str:
    subject = normalize_text(rule.get("科目", ""))
    role = normalize_text(rule.get("資料角色", ""))
    category = normalize_text(rule.get("大類", ""))
    if subject == "零用金":
        return "現金"
    if role == "advance_expense":
        return "支出"
    if category.startswith("支出"):
        return "支出"
    if category == "收入":
        return "收入"
    if category == "轉帳/換匯":
        return "轉帳/換匯"
    if role in {"account_balance"}:
        return "銀行" if subject not in {"悠遊付", "一卡通"} else "現金"
    if role in {"foreign_cash_balance", "foreign_account_balance", "fx_transfer"}:
        return "外幣"
    if role == "insurance_balance" or category == "保險":
        return "保險"
    if role in {"investment_transfer_or_balance"} or category == "投資":
        return "投資"
    if role in {"credit_card_balance"} or category == "負債":
        return "信用卡"
    if role in {"loan_payable", "loan_or_investment_outflow"} or "借" in category:
        return "借款/代墊"
    return "其他"


def _cash_account_bank_name(subject: str, account_category: str) -> tuple[str, str]:
    subject = normalize_text(subject)
    if subject == "零用金":
        return "零用金", "主帳戶"
    if account_category in {"支出", "收入"}:
        if "-" in subject:
            bank, name = subject.split("-", 1)
            return bank, name or subject
        return account_category, subject
    if account_category == "信用卡" and subject.startswith("信用卡-"):
        return "信用卡", subject.replace("信用卡-", "", 1)
    if account_category == "外幣" and subject in {"美金", "日幣", "韓幣", "人民幣", "港幣", "泰幣", "歐元"}:
        return "外幣現金", subject
    if account_category == "保險":
        return subject, "保單"
    if "-" in subject:
        bank, name = subject.split("-", 1)
        return bank, name or subject
    if account_category == "投資":
        return subject, "投資帳戶"
    if account_category == "借款/代墊":
        return subject, "往來帳戶"
    return subject, "主帳戶"


def cash_account_preset_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, rule in cash_subject_catalog_df().iterrows():
        subject = normalize_text(rule.get("科目", ""))
        role = normalize_text(rule.get("資料角色", ""))
        rule_dict = rule.to_dict()
        if role == "summary" or not _is_transfer_account_rule(rule_dict):
            continue
        if subject in seen:
            continue
        seen.add(subject)
        category = _cash_account_category(rule_dict)
        bank, name = _cash_account_bank_name(subject, category)
        rows.append({
            "科目": subject,
            "category": category,
            "bank": bank,
            "name": name,
            "currency": _cash_subject_currency(subject),
            "note": f"預設科目：{subject}",
        })
    return rows


@st.cache_data(ttl=30, show_spinner=False)
def load_accounts() -> pd.DataFrame:
    cols = ["id", "sort_order", "category", "bank", "name", "currency", "balance", "note", "is_active"]
    try:
        try:
            rows = supabase_client().table("accounts").select("*").order("sort_order").execute().data or []
        except Exception:
            rows = supabase_client().table("accounts").select("*").execute().data or []
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=cols)
    except Exception as e:
        st.error(f"load_accounts 錯誤：{e}")
        return pd.DataFrame(columns=cols)


@st.cache_data(ttl=30, show_spinner=False)
def load_transactions(limit: int = 200) -> pd.DataFrame:
    try:
        rows = supabase_client().table("transactions").select(
            "id,txn_date,txn_type,from_account_id,to_account_id,amount,currency,fx_rate,twd_amount,description,category,note,created_at"
        ).order("txn_date", desc=True).order("id", desc=True).limit(limit).execute().data or []
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    except Exception as e:
        st.error(f"load_transactions 錯誤：{e}")
        return pd.DataFrame()


def _active_accounts(accts: pd.DataFrame) -> pd.DataFrame:
    if accts.empty:
        return accts
    if "is_active" not in accts.columns:
        return accts
    mask = accts["is_active"].apply(lambda x: normalize_bool(x, True))
    return accts[mask].copy()


def _account_category_series(accts: pd.DataFrame) -> pd.Series:
    if "category" in accts.columns:
        return accts["category"].fillna("其他").astype(str)
    return pd.Series(["其他"] * len(accts), index=accts.index)


def _transfer_accounts(accts: pd.DataFrame) -> pd.DataFrame:
    if accts.empty:
        return accts
    categories = _account_category_series(accts)
    return accts[categories.isin(TRANSFER_ACCOUNT_CATEGORIES)].copy()


def _acct_label(accts: pd.DataFrame, acct_id: Any) -> str:
    if acct_id is None or pd.isna(acct_id):
        return "—"
    try:
        row = accts[accts["id"] == int(float(acct_id))]
    except Exception:
        return str(acct_id)
    if row.empty:
        return str(acct_id)
    r = row.iloc[0]
    return f"{r.get('bank', '')} {r.get('name', '')}({r.get('currency', '')})"


def _acct_options(accts: pd.DataFrame) -> list[str]:
    opts: list[str] = []
    if accts.empty:
        return opts
    for _, r in _transfer_accounts(_active_accounts(accts)).iterrows():
        opts.append(f"{r.get('id')}｜{r.get('bank', '')} {r.get('name', '')}({r.get('currency', '')})")
    return opts


def _id_from_option(opt: str) -> int | None:
    if not opt or opt == "（無）":
        return None
    try:
        return int(str(opt).split("｜")[0])
    except Exception:
        return None


def _account_balance_twd(row: pd.Series) -> float:
    bal = normalize_number(row.get("balance", 0), 0)
    cur = normalize_text(row.get("currency", "TWD"), "TWD").upper()
    fx_val, _ = fetch_fx(cur)
    return bal * (fx_val or 1)


def _amount_in_account_currency(amount: float, txn_currency: str, account_currency: str, fx_rate: float) -> float:
    txn_currency = normalize_text(txn_currency, "TWD").upper()
    account_currency = normalize_text(account_currency, "TWD").upper()
    amount = normalize_number(amount, 0)
    fx_rate = normalize_number(fx_rate, 1)
    if txn_currency == account_currency:
        return amount
    twd_amount = amount if txn_currency == "TWD" else amount * fx_rate
    if account_currency == "TWD":
        return twd_amount
    account_fx, _ = fetch_fx(account_currency)
    account_fx = account_fx or 1.0
    return twd_amount / account_fx


def create_missing_cash_account_presets() -> int:
    presets = cash_account_preset_rows()
    current = load_accounts()
    existing: set[tuple[str, str, str, str]] = set()
    if not current.empty:
        for _, row in current.iterrows():
            existing.add((
                normalize_text(row.get("category", "")),
                normalize_text(row.get("bank", "")),
                normalize_text(row.get("name", "")),
                normalize_text(row.get("currency", "")),
            ))
    next_order = 1
    if not current.empty and "sort_order" in current.columns:
        next_order = int(normalize_number(current["sort_order"].max(), 0)) + 1
    sb = supabase_client()
    inserted = 0
    for preset in presets:
        key = (
            normalize_text(preset["category"]),
            normalize_text(preset["bank"]),
            normalize_text(preset["name"]),
            normalize_text(preset["currency"]),
        )
        if key in existing:
            continue
        payload = {
            "sort_order": next_order,
            "category": preset["category"],
            "bank": preset["bank"],
            "name": preset["name"],
            "currency": preset["currency"],
            "balance": 0,
            "note": preset["note"],
            "is_active": True,
        }
        sb.table("accounts").insert(payload).execute()
        existing.add(key)
        next_order += 1
        inserted += 1
    return inserted


def cash_import_month_options(ledger: pd.DataFrame) -> list[str]:
    return _unique_keep_order([normalize_sheet_month_label(col) for col in month_columns(ledger)])


def _cash_import_preview_columns() -> list[str]:
    return ["匯入", "可互轉", "月份", "原始科目", "科目", "類別", "銀行/平台", "帳戶名稱", "幣別", "餘額", "台幣換算", "資料角色", "略過原因", "備註"]


def _cash_subject_account_fields(subject: str) -> dict[str, str]:
    rule = classify_cash_subject(subject)
    category = _cash_account_category(rule)
    bank, name = _cash_account_bank_name(subject, category)
    is_account = _is_transfer_account_rule(rule)
    is_transfer_endpoint = is_account and category in TRANSFER_ACCOUNT_CATEGORIES
    return {
        "科目": subject,
        "類別": category,
        "銀行/平台": bank,
        "帳戶名稱": name,
        "幣別": _cash_subject_currency(subject),
        "資料角色": normalize_text(rule.get("資料角色", "")),
        "匯入帳戶": "是" if is_account else "否",
        "可互轉": "是" if is_transfer_endpoint else "否",
        "備註": normalize_text(rule.get("備註", "")),
    }


def build_cash_import_preview(ledger: pd.DataFrame, month_label: str) -> pd.DataFrame:
    if ledger.empty or not month_label:
        return pd.DataFrame(columns=_cash_import_preview_columns())
    label_col = ledger.columns[0]
    source_col = ""
    for col in month_columns(ledger):
        if normalize_sheet_month_label(col) == month_label:
            source_col = col
            break
    if not source_col:
        return pd.DataFrame(columns=_cash_import_preview_columns())

    rows: list[dict[str, Any]] = []
    occurrence_counts: dict[str, int] = {}
    for _, row in ledger.iterrows():
        raw_subject = normalize_text(row.get(label_col, ""))
        if not raw_subject or raw_subject in {"合計", "總計"}:
            continue
        subject = canonical_cash_subject(raw_subject, occurrence_counts)
        amount = parse_sheet_number(row.get(source_col))
        if amount is None:
            continue
        fields = _cash_subject_account_fields(subject)
        role = fields["資料角色"]
        should_import = fields["匯入帳戶"] == "是"
        fx_val, _ = fetch_fx(fields["幣別"])
        if role == "summary":
            skip_reason = "彙總/公式列，不匯入為帳戶"
        elif not should_import:
            skip_reason = "支出/收入分類，只留作交易分類，不建立帳戶"
        else:
            skip_reason = ""
        rows.append({
            "匯入": should_import,
            "可互轉": fields["可互轉"],
            "月份": month_label,
            "原始科目": raw_subject,
            "科目": subject,
            "類別": fields["類別"],
            "銀行/平台": fields["銀行/平台"],
            "帳戶名稱": fields["帳戶名稱"],
            "幣別": fields["幣別"],
            "餘額": amount,
            "台幣換算": amount * (fx_val or 1),
            "資料角色": role,
            "略過原因": skip_reason,
            "備註": fields["備註"],
        })

    if not rows:
        return pd.DataFrame(columns=_cash_import_preview_columns())

    df = pd.DataFrame(rows)
    importable = df[df["匯入"] == True].copy()
    skipped = df[df["匯入"] == False].copy()
    if not importable.empty:
        group_cols = ["匯入", "可互轉", "月份", "原始科目", "科目", "類別", "銀行/平台", "帳戶名稱", "幣別", "資料角色", "略過原因", "備註"]
        importable = importable.groupby(group_cols, as_index=False, dropna=False).agg({"餘額": "sum", "台幣換算": "sum"})
    out = pd.concat([importable, skipped], ignore_index=True)
    return out[_cash_import_preview_columns()].sort_values(["匯入", "類別", "科目"], ascending=[False, True, True])


def apply_cash_import_preview(preview: pd.DataFrame, update_existing: bool = True) -> tuple[int, int, int]:
    if preview.empty:
        return 0, 0, 0
    current = load_accounts()
    existing: dict[tuple[str, str, str, str], pd.Series] = {}
    if not current.empty:
        for _, row in current.iterrows():
            key = (
                normalize_text(row.get("category", "")),
                normalize_text(row.get("bank", "")),
                normalize_text(row.get("name", "")),
                normalize_text(row.get("currency", "")),
            )
            existing[key] = row

    next_order = 1
    if not current.empty and "sort_order" in current.columns:
        next_order = int(normalize_number(current["sort_order"].max(), 0)) + 1

    sb = supabase_client()
    inserted = 0
    updated = 0
    skipped = 0
    rows = preview[preview["匯入"] == True].copy()
    for _, row in rows.iterrows():
        category = normalize_text(row.get("類別", "其他"), "其他")
        bank = normalize_text(row.get("銀行/平台", ""))
        name = normalize_text(row.get("帳戶名稱", ""))
        currency = normalize_text(row.get("幣別", "TWD"), "TWD")
        if not bank or not name:
            skipped += 1
            continue
        key = (category, bank, name, currency)
        note = f"匯入 2026細帳 {normalize_text(row.get('月份', ''))}：{normalize_text(row.get('科目', ''))}"
        payload = {
            "category": category,
            "bank": bank,
            "name": name,
            "currency": currency,
            "balance": normalize_number(row.get("餘額", 0), 0),
            "note": note,
            "is_active": True,
        }
        old_row = existing.get(key)
        if old_row is not None:
            if update_existing:
                rid = old_row.get("id")
                if pd.isna(rid):
                    skipped += 1
                    continue
                sb.table("accounts").update(payload).eq("id", int(float(rid))).execute()
                updated += 1
            else:
                skipped += 1
            continue
        payload["sort_order"] = next_order
        sb.table("accounts").insert(payload).execute()
        existing[key] = pd.Series(payload)
        next_order += 1
        inserted += 1
    return inserted, updated, skipped


def render_cash_import_section() -> None:
    st.markdown("#### 📥 匯入目前資料")
    st.caption("從 2026細帳選一個月份匯入帳戶目前餘額；轉帳來源/目標只列銀行、外幣、保險、投資、借款/代墊。零用金明細、信用卡消費、收入與彙總列只保留為交易分類。")

    source_choice = st.radio("資料來源", ["線上 2026細帳", "上傳 CSV / Excel"], horizontal=True, key="cash_import_source")
    ledger = pd.DataFrame()
    if source_choice == "線上 2026細帳":
        if st.button("讀取線上 2026細帳", key="load_online_cash_ledger"):
            st.session_state["cash_import_load_online"] = True
        if st.session_state.get("cash_import_load_online", False):
            try:
                ledger = load_online_sheet_csv(ONLINE_SHEET_SOURCES["2026細帳"])
            except Exception as e:
                st.error(f"讀取 2026細帳失敗：{e}")
    else:
        uploaded = st.file_uploader("上傳 2026細帳 CSV / Excel", type=["csv", "xlsx", "xls"], key="cash_import_upload")
        if uploaded is not None:
            try:
                ledger = read_uploaded_table(uploaded)
            except Exception as e:
                st.error(f"讀取上傳檔案失敗：{e}")

    if ledger.empty:
        st.info("請先讀取線上 2026細帳或上傳檔案。")
        return

    months = cash_import_month_options(ledger)
    if not months:
        st.warning("找不到月份欄位，請確認欄名格式像 2026-01 或 2026/01。")
        return
    selected_month = st.selectbox("選擇要匯入的目前月份", months, index=len(months) - 1, key="cash_import_month")
    preview = build_cash_import_preview(ledger, selected_month)
    if preview.empty:
        st.info("這個月份沒有可匯入資料。")
        return

    importable = preview[preview["匯入"] == True]
    skipped = preview[preview["匯入"] == False]
    c1, c2, c3 = st.columns(3)
    c1.metric("可匯入科目", f"{len(importable):,}")
    c2.metric("分類/彙總不匯入", f"{len(skipped):,}")
    c3.metric("匯入台幣換算", money(importable["台幣換算"].fillna(0).sum() if not importable.empty else 0))

    edited_preview = st.data_editor(
        preview,
        use_container_width=True,
        hide_index=True,
        height=min(42 * len(preview) + 44, 620),
        disabled=[col for col in preview.columns if col != "匯入"],
        column_config={
            "匯入": st.column_config.CheckboxColumn("匯入"),
            "餘額": st.column_config.NumberColumn("餘額", format="%.4f"),
            "台幣換算": st.column_config.NumberColumn("台幣換算", format="%.0f"),
        },
        key="cash_import_preview_editor",
    )

    update_existing = st.checkbox("若科目已存在，更新目前餘額", value=True, key="cash_import_update_existing")
    confirm = st.checkbox("確認匯入/更新 accounts 科目餘額", key="cash_import_confirm")
    if st.button("匯入目前資料", disabled=not confirm, key="apply_cash_import"):
        try:
            inserted, updated, skipped_count = apply_cash_import_preview(edited_preview, update_existing=update_existing)
            st.success(f"匯入完成：新增 {inserted} 筆，更新 {updated} 筆，略過 {skipped_count} 筆。")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"匯入失敗：{e}")


def render_cashflow_tab() -> None:
    st.subheader("💵 現金流管理")

    accts = load_accounts()
    txns = load_transactions()
    active = _active_accounts(accts)

    if not active.empty:
        active_categories = _account_category_series(active)
        category_totals = {}
        for category in CASH_ACCOUNT_CATEGORIES:
            rows = active[active_categories == category]
            category_totals[category] = sum(_account_balance_twd(r) for _, r in rows.iterrows())
        asset_total = sum(category_totals.get(c, 0) for c in NET_ASSET_CATEGORIES)
        liability_total = sum(category_totals.get(c, 0) for c in LIABILITY_CATEGORIES)
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("淨資產（台幣）", money(asset_total - liability_total))
        k2.metric("現金/外幣", money(category_totals.get("現金", 0) + category_totals.get("外幣", 0)))
        k3.metric("銀行存款", money(category_totals.get("銀行", 0)))
        k4.metric("投資/保險", money(category_totals.get("投資", 0) + category_totals.get("保險", 0)))
        k5.metric("借款/代墊", money(liability_total), delta=f"-{money(liability_total)}" if liability_total else None)

    tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs(["📥 匯入目前資料", "📋 帳戶總覽", "➕ 新增交易", "📜 交易記錄", "⚙️ 帳戶管理", "📚 科目字典"])

    with tab0:
        render_cash_import_section()

    with tab1:
        if accts.empty:
            st.info("尚無帳戶，請先到「帳戶管理」新增，或一鍵建立預設科目帳戶。")
        else:
            account_categories = _account_category_series(accts)
            categories = _unique_keep_order(CASH_ACCOUNT_CATEGORIES + account_categories.dropna().astype(str).tolist())
            category_rows = []
            for cat in categories:
                grp = accts[account_categories == cat]
                if grp.empty:
                    continue
                category_rows.append({
                    "類別": cat,
                    "科目數": len(grp),
                    "台幣換算": round(sum(_account_balance_twd(r) for _, r in grp.iterrows()), 0),
                })
            if category_rows:
                st.markdown("#### 各類別餘額")
                st.dataframe(
                    pd.DataFrame(category_rows),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "科目數": st.column_config.NumberColumn("科目數", format="%.0f"),
                        "台幣換算": st.column_config.NumberColumn("台幣換算", format="%.0f"),
                    },
                )
            for cat in categories:
                grp = accts[account_categories == cat]
                if grp.empty:
                    continue
                st.markdown(f"#### {cat}")
                rows_disp = []
                for _, r in grp.iterrows():
                    bal = normalize_number(r.get("balance", 0), 0)
                    cur = normalize_text(r.get("currency", "TWD")).upper()
                    twd_val = _account_balance_twd(r)
                    rows_disp.append({
                        "銀行/平台": r.get("bank", ""),
                        "帳戶名稱": r.get("name", ""),
                        "幣別": cur,
                        "餘額": round(bal, 4),
                        "台幣換算": round(twd_val, 0),
                        "備註": r.get("note", ""),
                    })
                df_disp = pd.DataFrame(rows_disp)
                st.caption(f"小計：{money(df_disp['台幣換算'].sum())} 台幣")
                st.dataframe(
                    df_disp,
                    use_container_width=True,
                    hide_index=True,
                    height=min(42 * len(df_disp) + 44, 340),
                    column_config={
                        "餘額": st.column_config.NumberColumn("餘額", format="%.4f"),
                        "台幣換算": st.column_config.NumberColumn("台幣換算", format="%.0f"),
                    },
                )

    with tab2:
        st.markdown("#### ➕ 新增一筆交易")
        if accts.empty:
            st.warning("請先到「帳戶管理」建立帳戶。")
        else:
            acct_opts = ["（無）"] + _acct_options(accts)
            subject_opts = cash_subject_options()
            default_subject_idx = subject_opts.index("零用金-餐費") if "零用金-餐費" in subject_opts else 0
            st.caption("來源/目標是帳戶互轉；轉入零用金或信用卡時，請在「分類 / 支出項目」選對應科目，並可填轉帳註記。")
            with st.form("new_txn_form"):
                c1, c2, c3 = st.columns(3)
                txn_date = c1.date_input("日期", value=pd.Timestamp.today())
                txn_type = c2.selectbox("類型", TXN_TYPES)
                txn_subject = c3.selectbox("分類 / 支出項目", subject_opts, index=default_subject_idx)
                rule = classify_cash_subject(txn_subject)
                role = normalize_text(rule.get("資料角色", ""))
                st.caption(f"科目分類：{rule.get('大類', '')} / {rule.get('子類', '')}｜{rule.get('收支屬性', '')}")

                c4, c5 = st.columns(2)
                from_opt = c4.selectbox("來源科目（扣款方）", acct_opts, key="from_acct")
                to_opt = c5.selectbox("目標科目（入帳方）", acct_opts, key="to_acct")

                c6, c7, c8 = st.columns(3)
                amount = c6.number_input("金額（原幣）", value=0.0, format="%.2f", min_value=0.0)
                currency = c7.selectbox("幣別", CASH_CURRENCIES, index=0)
                default_fx, _ = fetch_fx(currency)
                fx_rate_input = c8.number_input("匯率（原幣→台幣）", value=float(default_fx or 1.0), format="%.4f", min_value=0.0)

                twd_est = amount * fx_rate_input
                st.caption(f"估算台幣金額：**{money(twd_est)}**")
                desc = st.text_input("說明", value=txn_subject)
                note = st.text_input("轉帳註記 / 備註")

                if st.form_submit_button("💾 新增交易"):
                    from_id = _id_from_option(from_opt)
                    to_id = _id_from_option(to_opt)
                    record_only_allowed = role in {"expense", "advance_expense", "credit_card_expense", "insurance_expense"}
                    if amount <= 0:
                        st.error("金額必須大於 0")
                    elif from_id is None and to_id is None and not record_only_allowed:
                        st.error("來源和目標科目至少填一個")
                    elif from_id is not None and to_id is not None and from_id == to_id:
                        st.error("來源和目標不能是同一個科目")
                    else:
                        try:
                            sb = supabase_client()
                            sb.table("transactions").insert({
                                "txn_date": str(txn_date),
                                "txn_type": txn_type,
                                "from_account_id": from_id,
                                "to_account_id": to_id,
                                "amount": amount,
                                "currency": currency,
                                "fx_rate": fx_rate_input,
                                "twd_amount": round(twd_est, 0),
                                "description": desc or txn_subject,
                                "category": txn_subject,
                                "note": note,
                            }).execute()

                            if from_id:
                                from_row = accts[accts["id"] == from_id].iloc[0]
                                from_amount = _amount_in_account_currency(
                                    amount, currency, normalize_text(from_row.get("currency", "TWD")), fx_rate_input
                                )
                                new_bal = normalize_number(from_row.get("balance", 0), 0) - from_amount
                                sb.table("accounts").update({"balance": new_bal}).eq("id", from_id).execute()
                            if to_id:
                                to_row = accts[accts["id"] == to_id].iloc[0]
                                to_amount = _amount_in_account_currency(
                                    amount, currency, normalize_text(to_row.get("currency", "TWD")), fx_rate_input
                                )
                                new_bal = normalize_number(to_row.get("balance", 0), 0) + to_amount
                                sb.table("accounts").update({"balance": new_bal}).eq("id", to_id).execute()

                            st.success("✅ 已新增！")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"新增失敗：{e}")

    with tab3:
        st.markdown("#### 📜 最近 200 筆交易")
        if txns.empty:
            st.info("還沒有交易記錄。")
        else:
            txns_disp = txns.copy()
            txns_disp["來源"] = txns_disp["from_account_id"].apply(lambda x: _acct_label(accts, x))
            txns_disp["目標"] = txns_disp["to_account_id"].apply(lambda x: _acct_label(accts, x))
            txns_disp["txn_date"] = pd.to_datetime(txns_disp["txn_date"]).dt.strftime("%Y/%m/%d")
            show = txns_disp[[
                "txn_date", "txn_type", "來源", "目標",
                "amount", "currency", "twd_amount", "description", "category", "note",
            ]].copy()
            show.columns = ["日期", "類型", "來源", "目標", "金額", "幣別", "台幣金額", "說明", "分類", "備註"]

            f1, f2 = st.columns(2)
            types = ["全部"] + sorted(show["類型"].dropna().unique().tolist())
            sel_type = f1.selectbox("篩選類型", types, key="txn_filter_type")
            subjects = ["全部"] + sorted(show["分類"].dropna().unique().tolist())
            sel_subject = f2.selectbox("篩選分類", subjects, key="txn_filter_subject")
            if sel_type != "全部":
                show = show[show["類型"] == sel_type]
            if sel_subject != "全部":
                show = show[show["分類"] == sel_subject]

            st.dataframe(
                show,
                use_container_width=True,
                hide_index=True,
                height=min(42 * len(show) + 44, 600),
                column_config={
                    "金額": st.column_config.NumberColumn("金額", format="%.2f"),
                    "台幣金額": st.column_config.NumberColumn("台幣金額", format="%.0f"),
                },
            )

            col_s1, col_s2, col_s3 = st.columns(3)
            income = show[show["類型"].isin(["收入", "利息收入", "投資賣出"])]["台幣金額"].fillna(0).sum()
            expense = show[show["類型"].isin(["支出", "信用卡消費", "利息支出", "投資買入"])]["台幣金額"].fillna(0).sum()
            transfer = show[show["類型"].isin(["轉帳", "借入", "借出", "代墊"])]["台幣金額"].fillna(0).sum()
            col_s1.metric("收入合計（台幣）", money(income))
            col_s2.metric("支出合計（台幣）", money(expense))
            col_s3.metric("轉帳/借貸合計（台幣）", money(transfer))

    with tab4:
        st.markdown("#### ⚙️ 帳戶餘額更新")
        if accts.empty:
            st.info("還沒有帳戶。")
        else:
            with st.form("update_balance_form"):
                updated_vals: dict[int, float] = {}
                account_categories = _account_category_series(accts)
                for cat in _unique_keep_order(CASH_ACCOUNT_CATEGORIES + account_categories.dropna().astype(str).tolist()):
                    grp = accts[account_categories == cat]
                    if grp.empty:
                        continue
                    st.markdown(f"**{cat}**")
                    cols = st.columns(min(len(grp), 4))
                    for i, (_, r) in enumerate(grp.iterrows()):
                        with cols[i % 4]:
                            label = f"{r.get('bank', '')} {r.get('name', '')}\n({r.get('currency', '')})"
                            updated_vals[int(r["id"])] = st.number_input(
                                label,
                                value=normalize_number(r.get("balance", 0), 0),
                                format="%.2f",
                                key=f"bal_{r['id']}",
                            )
                if st.form_submit_button("💾 更新所有餘額"):
                    sb = supabase_client()
                    for aid, bal in updated_vals.items():
                        sb.table("accounts").update({"balance": bal}).eq("id", aid).execute()
                    st.success("✅ 餘額已更新！")
                    st.cache_data.clear()
                    st.rerun()

        st.markdown("---")
        st.markdown("#### ➕ 新增帳戶 / 科目")
        preset_rows = cash_account_preset_rows()
        preset_labels = ["手動新增"] + [row["科目"] for row in preset_rows]
        with st.form("add_account_form"):
            preset_choice = st.selectbox("快速科目", preset_labels)
            if preset_choice == "手動新增":
                a1, a2, a3 = st.columns(3)
                a_cat = a1.selectbox("類別", CASH_ACCOUNT_CATEGORIES)
                a_bank = a2.text_input("銀行/平台名稱")
                a_name = a3.text_input("帳戶名稱")
                a4, a5, a6 = st.columns(3)
                a_cur = a4.selectbox("幣別", CASH_CURRENCIES)
                a_bal = a5.number_input("初始餘額", value=0.0, format="%.2f")
                a_note = a6.text_input("備註")
            else:
                preset = next(row for row in preset_rows if row["科目"] == preset_choice)
                a_cat = preset["category"]
                a_bank = preset["bank"]
                a_name = preset["name"]
                a_cur = preset["currency"]
                a_bal = st.number_input("初始餘額", value=0.0, format="%.2f")
                a_note = st.text_input("備註", value=preset["note"])
                st.caption(f"將建立：{a_cat}｜{a_bank} {a_name}｜{a_cur}")

            if st.form_submit_button("新增帳戶"):
                if not a_bank or not a_name:
                    st.error("銀行/平台和帳戶名稱必填")
                else:
                    try:
                        next_order = 1
                        if not accts.empty and "sort_order" in accts.columns:
                            next_order = int(normalize_number(accts["sort_order"].max(), 0)) + 1
                        supabase_client().table("accounts").insert({
                            "sort_order": next_order,
                            "category": a_cat,
                            "bank": a_bank,
                            "name": a_name,
                            "currency": a_cur,
                            "balance": a_bal,
                            "note": a_note,
                            "is_active": True,
                        }).execute()
                        st.success("✅ 已新增帳戶！")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"新增失敗：{e}")

        with st.expander("一鍵建立缺少的預設帳戶"):
            st.caption("會建立帳戶餘額科目；來源/目標互轉只列銀行、外幣、保險、投資、借款/代墊。現金類可做總覽但不列入互轉，支出/收入/信用卡消費只作分類；已存在者會略過。")
            st.dataframe(pd.DataFrame(preset_rows), use_container_width=True, hide_index=True, height=360)
            confirm_seed = st.checkbox("確認建立缺少的預設科目帳戶", key="confirm_seed_cash_accounts")
            if st.button("建立預設科目帳戶", disabled=not confirm_seed, key="seed_cash_accounts"):
                try:
                    count = create_missing_cash_account_presets()
                    st.success(f"已新增 {count} 個預設帳戶。")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"建立失敗：{e}")

    with tab5:
        catalog = cash_subject_catalog_df().sort_values(["大類", "子類", "科目"])
        st.markdown("#### 科目字典")
        c1, c2, c3 = st.columns(3)
        c1.metric("科目數", f"{len(catalog):,}")
        c2.metric("大類數", f"{catalog['大類'].nunique():,}")
        c3.metric("預設帳戶數", f"{len(cash_account_preset_rows()):,}")
        st.dataframe(catalog, use_container_width=True, hide_index=True, height=620)


# ════════════════════════════════════════════════════════════════════════════
# APP 主體（標題移到 hero 區塊外，避免被蓋住）
# ════════════════════════════════════════════════════════════════════════════

st.title("📈 Jenny 投資即時市值系統")
st.caption(f"版本：{APP_VERSION}｜Supabase 永久資料庫")

with st.expander("資料庫欄位提醒：請確認 Supabase 欄位"):
    st.code("""
alter table positions add column if not exists purchase_ym text default '';
alter table positions add column if not exists dividend_received_original_total numeric default 0;
alter table positions add column if not exists dividend_received_total numeric default 0;
alter table positions add column if not exists dividend_note text default '';
alter table positions add column if not exists dividend_pay_date text default '';
alter table positions add column if not exists is_reinvest boolean default false;

alter table fund_dividends add column if not exists fund_name text default '';
alter table fund_dividends add column if not exists actual_div_amount numeric default 0;
alter table dividend_log add column if not exists fund_name text default '';
alter table dividend_log add column if not exists actual_div_amount numeric default 0;

create table if not exists accounts (
    id bigserial primary key,
    sort_order numeric default 0,
    category text default '銀行',
    bank text default '',
    name text default '',
    currency text default 'TWD',
    balance numeric default 0,
    note text default '',
    is_active boolean default true,
    created_at timestamptz default now()
);
alter table accounts add column if not exists sort_order numeric default 0;
alter table accounts add column if not exists category text default '銀行';
alter table accounts add column if not exists bank text default '';
alter table accounts add column if not exists name text default '';
alter table accounts add column if not exists currency text default 'TWD';
alter table accounts add column if not exists balance numeric default 0;
alter table accounts add column if not exists note text default '';
alter table accounts add column if not exists is_active boolean default true;
alter table accounts add column if not exists created_at timestamptz default now();

create table if not exists transactions (
    id bigserial primary key,
    txn_date date default current_date,
    txn_type text default '',
    from_account_id bigint,
    to_account_id bigint,
    amount numeric default 0,
    currency text default 'TWD',
    fx_rate numeric default 1,
    twd_amount numeric default 0,
    description text default '',
    category text default '',
    note text default '',
    created_at timestamptz default now()
);
alter table transactions add column if not exists txn_date date default current_date;
alter table transactions add column if not exists txn_type text default '';
alter table transactions add column if not exists from_account_id bigint;
alter table transactions add column if not exists to_account_id bigint;
alter table transactions add column if not exists amount numeric default 0;
alter table transactions add column if not exists currency text default 'TWD';
alter table transactions add column if not exists fx_rate numeric default 1;
alter table transactions add column if not exists twd_amount numeric default 0;
alter table transactions add column if not exists description text default '';
alter table transactions add column if not exists category text default '';
alter table transactions add column if not exists note text default '';
alter table transactions add column if not exists created_at timestamptz default now();
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

# ── 寫入 latest_portfolio_values 供排程讀取 ──────────────────────────────
try:
    _platform_val = {}
    if not enriched.empty:
        for _plt in ["台股", "美股", "基富通", "渣打基金", "台新基金"]:
            _platform_val[_plt] = float(
                enriched[enriched["platform"] == _plt]["台幣市值"].fillna(0).sum()
            )
    total_pnl_all   = total_value - total_cost
    total_div_received = enriched["累計已領配息"].dropna().sum() if not enriched.empty and "累計已領配息" in enriched else 0
    _tw_now_str = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    supabase_client().table("latest_portfolio_values").upsert({
        "id":                  1,
        "total_twd":           round(total_value, 0),
        "tw_stock":            round(_platform_val.get("台股", 0), 0),
        "us_stock":            round(_platform_val.get("美股", 0), 0),
        "kifutong":            round(_platform_val.get("基富通", 0), 0),
        "scb":                 round(_platform_val.get("渣打基金", 0), 0),
        "taishin":             round(_platform_val.get("台新基金", 0), 0),
        "total_cost":          round(total_cost, 0),
        "cumulative_dividend": round(total_div_received, 0),
        "updated_at":          _tw_now_str,
    }, on_conflict="id").execute()
except Exception:
    pass

# Hero bar（不再 sticky，標題不被蓋）
with st.container():
    st.markdown('<div class="hero">', unsafe_allow_html=True)
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    tw_missing = []
    if not enriched.empty:
        tw_no_price = enriched[
            (enriched["platform"] == "台股") &
            (enriched["units"].fillna(0) > 0) &
            (enriched["即時價格/淨值"].isna())
        ]
        tw_missing = tw_no_price["name"].dropna().unique().tolist()
    if tw_missing:
        st.warning(f"⚠️ 台股缺報價：{'、'.join(tw_missing)}")
    pnl_delta = f"{total_pnl:+,.0f} / {pct(total_rate)}"
    c1.metric("總台幣市值", money(total_value), delta=pnl_delta)
    external_cost = enriched[enriched["is_reinvest"].fillna(False) == False]["台幣成本"].dropna().sum() if not enriched.empty else 0
    c2.metric("總台幣成本", money(total_cost),
              delta=f"外部投入 {money(external_cost)}" if external_cost != total_cost else None)
    total_pnl_all = total_value - total_cost
    total_div_received = enriched["累計已領配息"].dropna().sum() if not enriched.empty and "累計已領配息" in enriched else 0
    c3.metric("總損益（市值）", signed_money(total_pnl_all))
    c4.metric("累計配息", money(total_div_received))
    c5.metric("預估每月配息", money(total_div))
    
    if c6.button("🔄 更新即時價"):
        st.cache_data.clear(); st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

tabs = st.tabs(["總覽", "台股", "美股", "基富通", "渣打基金", "台新基金", "資料安全", "工具", "📊 歷史市值", "💰 配息記錄", "📒 線上總表", "💵 現金流"])

show_cols = ["sort_order", "platform", "asset_type", "name", "ticker", "fund_code", "currency",
             "total_cost_input", "original_units", "units", "市值股數", "avg_cost", "purchase_ym",
             "即時價格/淨值", "匯率", "成本原幣", "市值原幣", "台幣成本", "台幣市值",
             "價差損益", "價差損益率", "累計配息原幣", "累計已領配息", "含息總損益", "含息總損益率", "每月配息",
             "每單位月配息估算", "月配息來源", "dividend_note", "corporate_action", "狀態"]

# ── ★ 改寫後的總覽 tab ──────────────────────────────────────────────────────
with tabs[0]:
    render_channel_overview_cards(enriched)
    render_fx_overview_cards()
    st.markdown("### 📈 資產配置圖")
    if not enriched.empty:
        chart_summary = enriched.groupby("platform", dropna=False).agg(台幣市值=("台幣市值", "sum")).reset_index()
        chart_summary["占比"] = chart_summary["台幣市值"] / chart_summary["台幣市值"].sum() if chart_summary["台幣市值"].sum() else 0
        st.dataframe(
            chart_summary,
            use_container_width=True,
            hide_index=True,
            column_config={
                "台幣市值": st.column_config.NumberColumn("台幣市值", format="%.0f"),
                "占比": st.column_config.NumberColumn("占比", format="%.2f%%"),
            },
        )

# ── 其餘 tab 原版完全不變 ────────────────────────────────────────────────────
for idx, platform in enumerate(PLATFORMS, start=1):
    with tabs[idx]:
        st.subheader(platform)
        # ── 第一排：全局KPI ──
        g1, g2, g3, g4 = st.columns(4)
        g1.metric("總台幣市值", money(total_value), delta=f"{total_pnl:+,.0f} / {pct(total_rate)}")
        g2.metric("總台幣成本", money(total_cost))
        g3.metric("預估每月配息", money(total_div))
        if g4.button("🔄 更新即時價", key=f"refresh_{platform}"):
            st.cache_data.clear(); st.rerun()
        view = enriched[enriched["platform"] == platform].copy() if not enriched.empty else pd.DataFrame()
        if view.empty:
            st.info(f"尚無 {platform} 資料")
        else:
            # ── 第二排：平台KPI ──
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("台幣市值", money(view["台幣市值"].dropna().sum()))
            m2.metric("台幣成本", money(view["台幣成本"].dropna().sum()))
            m3.metric("損益",     signed_money(view["損益"].dropna().sum()))
            m4.metric("每月配息", money(view["每月配息"].dropna().sum()))
            st.markdown("#### 即時計算結果")
            # 數值欄位直接用原始數值 + NumberColumn，靠右對齊、可排序
            num_cols = {
                "total_cost_input": st.column_config.NumberColumn("總投入成本", format="%.0f"),
                "original_units":   st.column_config.NumberColumn("成本股數",   format="%.4f"),
                "units":            st.column_config.NumberColumn("現在股數",   format="%.4f"),
                "市值股數":         st.column_config.NumberColumn("市值股數",   format="%.4f"),
                "avg_cost":         st.column_config.NumberColumn("平均成本",   format="%.4f"),
                "即時價格/淨值":    st.column_config.NumberColumn("即時價格/淨值", format="%.4f"),
                "匯率":             st.column_config.NumberColumn("匯率",       format="%.4f"),
                "成本原幣":         st.column_config.NumberColumn("成本原幣",   format="%.0f"),
                "市值原幣":         st.column_config.NumberColumn("市值原幣",   format="%.0f"),
                "台幣成本":         st.column_config.NumberColumn("台幣成本",   format="%.0f"),
                "台幣市值":         st.column_config.NumberColumn("台幣市值",   format="%.0f"),
                "價差損益":         st.column_config.NumberColumn("市值損益",   format="%.0f"),
                "累計配息原幣":     st.column_config.NumberColumn("累積配息原幣", format="%.2f"),
                "累計已領配息":     st.column_config.NumberColumn("累積配息台幣", format="%.0f"),
                "含息總損益":       st.column_config.NumberColumn("總損益",     format="%.0f"),
                "每月配息":         st.column_config.NumberColumn("月配息",     format="%.0f"),
                "每單位月配息估算": st.column_config.NumberColumn("每單位月配息", format="%.4f"),
                "價差損益率":       st.column_config.NumberColumn("市值損益率", format="%.2f%%"),
                "含息總損益率":     st.column_config.NumberColumn("總損益率",   format="%.2f%%"),
            }
            view_disp = view[show_cols].copy()
            # 把百分比欄位從小數轉成百分比數值
            for col in ["價差損益率", "含息總損益率"]:
                if col in view_disp.columns:
                    view_disp[col] = view_disp[col].apply(lambda x: x * 100 if x is not None and str(x) not in ["-", "—", "nan"] else None)
            st.dataframe(
                view_disp,
                use_container_width=True,
                hide_index=True,
                height=400,
                column_config=num_cols,
            )
        editable_platform_table(platform, positions, f"editor_{platform}")

with tabs[6]:
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

with tabs[7]:
    st.subheader("工具")
    tool_choice = st.selectbox(
        "選擇工具",
        ["批次更新", "修復排序", "貼上清單修復", "全部歸零重建", "抓價測試"],
        key="tool_menu",
    )
    if tool_choice == "批次更新":
        upload_batch_section(positions)
    elif tool_choice == "修復排序":
        sort_repair_section(positions)
    elif tool_choice == "貼上清單修復":
        pasted_order_repair_section(positions)
    elif tool_choice == "全部歸零重建":
        full_reset_rebuild_section(positions)
    elif tool_choice == "抓價測試":
        price_test_section()

with tabs[8]:
    render_history_tab()

with tabs[9]:
    render_dividend_log_tab(enriched)

with tabs[10]:
    render_online_sheets_tab()

with tabs[11]:
    render_cashflow_tab()
