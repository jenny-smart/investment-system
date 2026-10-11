"""共用基礎：設定常數、Supabase、持倉讀寫、報價／基金淨值／匯率、enrich 計算、總帳試算表讀取。"""
from __future__ import annotations

import os
import io
import re
import html as html_lib
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

from asset_summary import sheet_other_assets


APP_VERSION = "2026-10-11-v75-dividend-diff"


GAS_FUND_NAV_URL = "https://script.google.com/macros/s/AKfycbx2tregTV1NlYpUkOvy9UpRu3YDMP5r9wQEQuiB7qj_Y9HGa8yON4isAUIke30XF23p/exec"


MAIN_GOOGLE_SHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"


ONLINE_SHEET_SOURCES = {
    "2026細帳": "1862868285",
    "每月收入": "1804324921",
    "資產總覽": "151289982",
}


OVERVIEW_SHEET_GID = "1120619093"  # 總帳「總覽」分頁（每月加總）


DEFAULT_SUPABASE_URL = "https://qrvdztqyzxlsfskdgiqp.supabase.co"


PLATFORMS = ["台股", "美股", "基富通", "渣打基金", "台新基金"]


ASSET_TYPES = ["台股", "美股", "基金"]


CURRENCIES = ["TWD", "USD", "CNY", "JPY", "ZAR"]


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


TW_DELISTED_TICKERS = {
    "2823.TW",   # 中壽，已下市
}


TW_DELISTED_NAMES = {
    "中壽",
}


GAS_REQUEST_TIMEOUT_SECONDS = 6


PRICE_REQUEST_TIMEOUT_SECONDS = 8


FX_FALLBACK_URL = "https://open.er-api.com/v6/latest/{currency}"


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
        "dividend_received_original_base": 0.0,
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


def normalize_ticker(ticker: str) -> str:
    t = normalize_text(ticker).strip()
    if not t:
        return ""
    return t.replace(" ", "").upper()


def is_delisted_tw_stock(ticker: str = "", name: str = "") -> bool:
    ticker = normalize_ticker(ticker)
    name = normalize_text(name)
    preset_ticker = normalize_ticker(TW_PRESETS.get(name, ""))
    return (
        ticker in TW_DELISTED_TICKERS
        or preset_ticker in TW_DELISTED_TICKERS
        or name in TW_DELISTED_NAMES
    )


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
        r = requests.get(url, timeout=PRICE_REQUEST_TIMEOUT_SECONDS, headers={
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


@st.cache_data(ttl=120, show_spinner=False)
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
        r = requests.get(url, params=params, timeout=PRICE_REQUEST_TIMEOUT_SECONDS, headers=headers)
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


@st.cache_data(ttl=300, show_spinner=False)
def fetch_stock_price(ticker: str, asset_type: str = "") -> tuple[float | None, str]:
    ticker = normalize_ticker(ticker)
    if ticker in TW_DELISTED_TICKERS:
        return None, "已下市"

    is_tw = asset_type == "台股" or is_tw_stock_ticker(ticker)

    if is_tw:
        # 台股優先走 TWSE，避免 Yahoo Finance 短時間大量查詢被 429 限流。
        tw_quote = fetch_twse_realtime_quote(ticker)
        if tw_quote.get("price") is not None:
            return float(tw_quote["price"]), normalize_text(tw_quote.get("status", "TWSE即時"))

        y_price, y_status = fetch_yahoo_price(ticker)
        if y_price is not None:
            return y_price, "Yahoo"

        # Google 台股只在前兩者都失敗時才試，且僅限有明確 exchange 的
        g_price, g_status = fetch_google_finance_price(ticker, TW_STOCK_EXCHANGES.get(ticker))
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
                timeout=GAS_REQUEST_TIMEOUT_SECONDS,
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
            r = requests.get(url, timeout=PRICE_REQUEST_TIMEOUT_SECONDS, headers=headers)
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
        r = requests.get(url, timeout=PRICE_REQUEST_TIMEOUT_SECONDS, headers={
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


def _decode_moneydj_content(content: bytes) -> str:
    for encoding in ("big5", "cp950", "utf-8"):
        try:
            return content.decode(encoding)
        except Exception:
            continue
    return content.decode("utf-8", errors="ignore")


def _moneydj_text_from_html(html: str) -> str:
    if HAS_BS4:
        try:
            return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        except Exception:
            pass
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return html_lib.unescape(re.sub(r"\s+", " ", text)).strip()


def parse_moneydj_fund_quote(html: str) -> dict[str, Any]:
    text = _moneydj_text_from_html(html).replace(",", "")
    patterns = [
        r"淨值日期\s+最新淨值\s+每日變化\s+最高淨值\(年\)\s+最低淨值\(年\)\s+"
        r"(20\d{2}/\d{1,2}/\d{1,2})\s+([0-9]+(?:\.[0-9]+)?)",
        r"淨值日期\s+最新淨值.*?(20\d{2}/\d{1,2}/\d{1,2})\s+([0-9]+(?:\.[0-9]+)?)",
        r"(20\d{2}/\d{1,2}/\d{1,2})\s+([0-9]+(?:\.[0-9]+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.S)
        if not match:
            continue
        raw_date = _format_dividend_date(match.group(1))
        nav = to_float(match.group(2))
        if nav is not None and 0 < nav < 10000:
            return {
                "nav": float(nav),
                "date": _parse_date_str(raw_date),
                "raw_date": raw_date,
                "status": "MoneyDJ直連✓",
            }

    nums = re.findall(r"(?<!\d)([0-9]+\.[0-9]{2,6})(?!\d)", text)
    for n in nums:
        nav = to_float(n)
        if nav is not None and 0 < nav < 10000:
            return {"nav": float(nav), "date": "—", "raw_date": "", "status": "MoneyDJ直連✓"}
    return {"nav": None, "date": "—", "raw_date": "", "status": "MoneyDJ 找不到淨值"}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_moneydj_fund_quote(code: str, pattern: str) -> dict[str, Any]:
    if not code or not pattern:
        return {"nav": None, "date": "—", "raw_date": "", "status": "無 fund_code/fund_pattern"}
    try:
        url = f"https://www.moneydj.com/funddj/ya/{pattern}.djhtm?a={code}"
        r = requests.get(url, timeout=PRICE_REQUEST_TIMEOUT_SECONDS, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            "Referer": "https://www.moneydj.com/",
        })
        r.raise_for_status()
        quote = parse_moneydj_fund_quote(_decode_moneydj_content(r.content))
        if quote.get("nav") is not None:
            return quote
        quote["status"] = f"{quote.get('status', 'MoneyDJ 找不到淨值')}:{code}"
        return quote
    except Exception as e:
        return {"nav": None, "date": "—", "raw_date": "", "status": f"MoneyDJ 錯誤:{str(e)[:40]}"}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_moneydj_nav(code: str, pattern: str) -> tuple[float | None, str]:
    quote = fetch_moneydj_fund_quote(code, pattern)
    nav = quote.get("nav")
    return (float(nav), normalize_text(quote.get("status", "MoneyDJ直連✓"))) if nav is not None else (None, normalize_text(quote.get("status", "MoneyDJ 找不到淨值")))


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_gas_div_for_enrich(fund_code: str) -> float | None:
    if not fund_code:
        return None
    value = _get_gas_data(fund_code).get("monthly_div")
    return float(value) if value else None


@st.cache_data(ttl=300, show_spinner=False)
def fetch_fund_quote(code: str, pattern: str) -> dict[str, Any]:
    code = normalize_text(code)
    pattern = normalize_text(pattern)
    empty = {"nav": None, "date": "—", "raw_date": "", "status": "基金代碼空白"}
    if not code:
        return empty
    if re.fullmatch(r"[A-Z]\d{5}", code.upper()):
        nav, status = fetch_anue_fund_nav(code)
        if nav:
            return {"nav": nav, "date": "—", "raw_date": "", "status": status}
        nav, status = fetch_gas_fund_nav(code)
        if nav:
            gas = _get_gas_data(code)
            return {"nav": nav, "date": gas.get("date", "—"), "raw_date": normalize_text(gas.get("date", "")), "status": status}
        return {"nav": None, "date": "—", "raw_date": "", "status": status}
    statuses: list[str] = []
    if pattern and pattern.lower() != "anue":
        quote = fetch_moneydj_fund_quote(code, pattern)
        nav = quote.get("nav")
        if nav is not None:
            return quote
        statuses.append(normalize_text(quote.get("status", "")))
    cnyes_id = FUND_CNYES_IDS.get(code, "")
    if cnyes_id:
        nav, status = fetch_cnyes_fund_nav(cnyes_id)
        if nav:
            return {"nav": nav, "date": "—", "raw_date": "", "status": f"鉅亨直連✓({cnyes_id})"}
        statuses.append(status)
    anue_id = FUND_ANUE_IDS.get(code.lower(), "")
    if anue_id:
        nav, status = fetch_anue_fund_nav(anue_id)
        if nav:
            return {"nav": nav, "date": "—", "raw_date": "", "status": f"鉅亨舊✓({anue_id})"}
        statuses.append(status)
    nav, status = fetch_gas_fund_nav(code)
    if nav:
        gas = _get_gas_data(code)
        return {"nav": nav, "date": gas.get("date", "—"), "raw_date": normalize_text(gas.get("date", "")), "status": status}
    statuses.append(status)
    detail = "；".join(s for s in statuses if s)
    return {"nav": None, "date": "—", "raw_date": "", "status": f"所有來源失敗:{code} {detail[:120]}"}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_fund_nav(code: str, pattern: str) -> tuple[float | None, str]:
    quote = fetch_fund_quote(code, pattern)
    nav = quote.get("nav")
    return (float(nav), normalize_text(quote.get("status", "ok"))) if nav is not None else (None, normalize_text(quote.get("status", "所有來源失敗")))


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fx_fallback(currency: str) -> tuple[float | None, str]:
    currency = normalize_text(currency, "TWD").upper()
    if currency == "TWD":
        return 1.0, "ok"
    try:
        r = requests.get(
            FX_FALLBACK_URL.format(currency=currency),
            timeout=PRICE_REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        r.raise_for_status()
        data = r.json()
        if data.get("result") != "success":
            return None, f"備援匯率失敗:{currency}"
        twd = to_float((data.get("rates") or {}).get("TWD"))
        if twd and twd > 0:
            return float(twd), "ER-API"
    except Exception as e:
        return None, f"備援匯率錯誤:{str(e)[:40]}"
    return None, f"備援匯率無TWD:{currency}"


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
        fallback, fallback_status = fetch_fx_fallback(currency)
        if fallback is not None:
            return fallback, fallback_status
        return None, f"匯率抓取失敗:{currency}; {status}; {fallback_status}"
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
    dividend_received_total = dividend_received_original_total * fx if fx is not None else 0
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


def effective_position_currency(r: pd.Series | dict[str, Any]) -> str:
    name = normalize_text(r.get("name", ""))
    currency = normalize_text(r.get("currency", "TWD")).upper()
    if "南非幣" in name:
        return "ZAR"
    if "美元" in name or "美金" in name or normalize_text(r.get("asset_type")) == "美股":
        return "USD"
    if "人民幣" in name:
        return "CNY"
    if "日圓" in name or "日幣" in name:
        return "JPY"
    return currency


def effective_fund_fields(r: pd.Series | dict[str, Any]) -> tuple[str, str]:
    return infer_fund_fields(
        normalize_text(r.get("name", "")),
        normalize_text(r.get("fund_code", "")),
        normalize_text(r.get("fund_pattern", "")),
    )


def dividend_group_key(row: pd.Series, asset_type: str, fund_code: str = "", currency: str = "") -> tuple[str, str, str, str] | None:
    if normalize_text(asset_type) != "基金":
        return None
    platform = normalize_text(row.get("platform", ""))
    currency = normalize_text(currency or row.get("currency", ""))
    key_code = normalize_text(fund_code or row.get("fund_code", "")) or normalize_match_name(row.get("name", ""))
    if not key_code:
        return None
    return (platform, currency, key_code.lower(), "基金")


def fund_dividend_original_totals(df: pd.DataFrame) -> dict[tuple[str, str, str, str], float]:
    totals: dict[tuple[str, str, str, str], float] = {}
    primary_totals: dict[tuple[str, str, str, str], float] = {}
    source = ensure_columns(df)
    for _, row in source.iterrows():
        if normalize_text(row.get("asset_type", "")) != "基金":
            continue
        currency = effective_position_currency(row)
        fund_code, _ = effective_fund_fields(row)
        key = dividend_group_key(row, "基金", fund_code, currency)
        if key is None:
            continue
        original_total = normalize_number(row.get("dividend_received_original_total", 0), 0)
        totals[key] = totals.get(key, 0) + original_total
        if key not in primary_totals:
            primary_totals[key] = original_total
    return {
        key: primary_totals.get(key, 0) if primary_totals.get(key, 0) > 0 else total
        for key, total in totals.items()
    }


def _prefetch_quotes(df: pd.DataFrame) -> None:
    """平行預先抓報價、基金淨值、匯率、GAS 配息，填好快取。

    enrich 逐筆依序抓時，冷啟動（重開機、快取過期）要好幾十秒，超過
    Streamlit Cloud 的 60 秒健康檢查就會一直轉圈；平行抓完後 enrich 都直接讀快取。
    """
    from concurrent.futures import ThreadPoolExecutor
    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

    jobs: set[tuple] = set()
    for _, r in df.iterrows():
        name = normalize_text(r.get("name", ""))
        asset_type = normalize_text(r.get("asset_type", ""))
        jobs.add((fetch_fx, effective_position_currency(r)))
        if asset_type in {"台股", "美股"}:
            ticker = normalize_text(r.get("ticker", ""))
            if asset_type == "台股" and not ticker and name in TW_PRESETS:
                ticker = TW_PRESETS.get(name, "")
            elif not ticker and name:
                ticker = name.upper()
            if not (asset_type == "台股" and is_delisted_tw_stock(ticker, name)):
                jobs.add((fetch_stock_price, ticker, asset_type))
        else:
            fund_code, fund_pattern = effective_fund_fields(r)
            jobs.add((fetch_fund_quote, fund_code, fund_pattern))
            fc = normalize_text(r.get("fund_code", "")) or infer_fund_fields(
                name, normalize_text(r.get("fund_code", "")), normalize_text(r.get("fund_pattern", "")))[0]
            if fc and normalize_number(r.get("monthly_dividend_per_unit", 0), 0) <= 0:
                jobs.add((_fetch_gas_div_for_enrich, fc))
    ctx = get_script_run_ctx()

    def run(job):
        if ctx is not None:
            add_script_run_ctx(ctx=ctx)
        try:
            job[0](*job[1:])
        except Exception:
            pass  # 失敗留給 enrich 照原本流程處理

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(run, jobs))


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = ensure_columns(df)
    if df.empty:
        return df
    _prefetch_quotes(df)
    rows = []
    dividend_primary_seen: set[tuple[str, str, str, str]] = set()
    dividend_original_totals = fund_dividend_original_totals(df)
    for _, r in df.iterrows():
        name = normalize_text(r.get("name", ""))
        currency = effective_position_currency(r)
        fund_nav_date = "—"
        asset_type = normalize_text(r.get("asset_type", ""))
        if asset_type in {"台股", "美股"}:
            ticker = normalize_text(r.get("ticker", ""))
            if asset_type == "台股" and not ticker and name in TW_PRESETS:
                ticker = TW_PRESETS.get(name, "")
            elif not ticker and name:
                ticker = name.upper()
            if asset_type == "台股" and is_delisted_tw_stock(ticker, name):
                price, p_status = None, "已下市"
            else:
                price, p_status = fetch_stock_price(ticker, asset_type)
        else:
            fund_code, fund_pattern = effective_fund_fields(r)
            fund_quote = fetch_fund_quote(fund_code, fund_pattern)
            price = to_float(fund_quote.get("nav"))
            p_status = normalize_text(fund_quote.get("status", "所有來源失敗"))
            fund_nav_date = normalize_text(fund_quote.get("date", "—"), "—")
        fx, fx_status = fetch_fx(currency)
        calc_row = r.copy()
        is_dividend_primary = True
        if asset_type == "基金":
            group_key = dividend_group_key(r, asset_type, fund_code, currency)
            if group_key is not None:
                is_dividend_primary = group_key not in dividend_primary_seen
                dividend_primary_seen.add(group_key)
            if is_dividend_primary:
                calc_row["dividend_received_original_total"] = dividend_original_totals.get(
                    group_key,
                    normalize_number(r.get("dividend_received_original_total", 0), 0),
                )
                calc_row["dividend_received_total"] = 0
            else:
                calc_row["dividend_received_original_total"] = 0
                calc_row["dividend_received_total"] = 0
        calc = calculate_cost_and_value(calc_row, price, fx)
        units = normalize_number(calc.get("市值股數", r.get("units", 0)), 0)
        if asset_type == "基金":
            _fc = normalize_text(r.get("fund_code", "")) or infer_fund_fields(normalize_text(r.get("name","")),normalize_text(r.get("fund_code","")),normalize_text(r.get("fund_pattern","")))[0]
            manual_div = normalize_number(r.get("monthly_dividend_per_unit", 0), 0)
            _gas_div = _fetch_gas_div_for_enrich(_fc) if _fc and manual_div <= 0 else None
            div_per_unit = manual_div or _gas_div or 0
            div_source = "手動" if manual_div else "GAS"
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
            "基金淨值日期": fund_nav_date,
            "匯率": fx,
            "累積配息主列": is_dividend_primary,
            "每單位月配息估算": div_per_unit,
            "每月配息": monthly_div_twd,
            "月配息來源": div_source if div_per_unit else "",
            "狀態": "✓" if price is not None and fx is not None else f"價格:{p_status} 匯率:{fx_status}",
        })
        rows.append(out)
    return pd.DataFrame(rows)


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


def online_sheet_url(gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{MAIN_GOOGLE_SHEET_ID}/export?format=csv&gid={gid}"


@st.cache_data(ttl=600, show_spinner=False)
def load_sheet_grid(gid: str) -> list[list[str]]:
    """整張分頁原樣讀成二維陣列（保留欄列位置，供依日期 / 名稱定位）。"""
    response = requests.get(online_sheet_url(gid), timeout=30)
    response.raise_for_status()
    if "<html" in response.text[:200].lower():
        raise RuntimeError("Google Sheet CSV 下載失敗，請確認分享權限或部署端可讀取。")
    import csv
    return [row for row in csv.reader(io.StringIO(response.text))]


def load_other_assets() -> dict[str, Any] | None:
    """總帳 Jennyall 本月的銀行 / 保險 / 懷思投資 / uncle待還 / 外幣 / 待還；讀不到回傳 None。"""
    try:
        return sheet_other_assets(load_sheet_grid(ONLINE_SHEET_SOURCES["資產總覽"]), today=tw_now().date())
    except Exception as exc:
        st.session_state["other_assets_error"] = str(exc)
        return None


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
                             timeout=GAS_REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": "Mozilla/5.0"})
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


def _format_dividend_date(value: Any) -> str:
    parsed = _parse_dividend_date(value)
    if parsed is None:
        return normalize_text(value, "—") or "—"
    return parsed.strftime("%Y/%m/%d")


def html_table(df: pd.DataFrame, number_cols: list[str] | tuple[str, ...] = (), max_height: int | None = None) -> str:
    """精簡 HTML 表格：欄寬依內容、數字靠右、沒有資料的格子空白（st.dataframe 一律顯示 None）。"""
    def cell(col: str, value: Any) -> str:
        if col in number_cols:
            n = to_float(value)
            text = "" if n is None else f"{n:,.0f}"
            return f'<td style="text-align:right;font-family:monospace">{text}</td>'
        text = "" if value is None or (isinstance(value, float) and pd.isna(value)) else html_lib.escape(str(value))
        return f"<td>{text}</td>"

    head = "".join(f'<th style="text-align:{"right" if c in number_cols else "left"}">{html_lib.escape(str(c))}</th>'
                   for c in df.columns)
    body = "".join("<tr>" + "".join(cell(c, row[c]) for c in df.columns) + "</tr>"
                   for _, row in df.iterrows())
    height = f"max-height:{max_height}px;" if max_height else ""
    return f"""
<div style="overflow:auto;{height}border:1px solid #e5e7eb;border-radius:8px;background:#fff;margin:2px 0 10px 0">
<table class="jt-table" style="border-collapse:collapse;font-size:13px;white-space:nowrap">
<thead><tr style="position:sticky;top:0;background:#f8fafc">{head}</tr></thead>
<tbody>{body}</tbody></table></div>
<style>
.jt-table th, .jt-table td {{ padding:5px 12px; border-bottom:1px solid #f1f5f9; }}
.jt-table th {{ color:#6b7280; font-weight:600; }}
</style>"""
