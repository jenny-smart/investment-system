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


APP_VERSION = "2026-05-20-supabase-v19-fund-nav-fallback"

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
