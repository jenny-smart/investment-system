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


APP_VERSION = "2026-05-17-supabase-v3"

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
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "富蘭克林華美新興國家固定收益基金B-新臺幣", "", "acft94", "yp010000"),
    ("基富通", "TWD", "基金", "柏瑞新興邊境非投資等級債券證券投資信託基金-B類型", "", "acai222", "yp010000"),
    ("基富通", "TWD", "基金", "柏瑞新興邊境非投資等級債券證券投資信託基金-B類型", "", "acai222", "yp010000"),
    ("基富通", "TWD", "基金", "柏瑞新興邊境非投資等級債券證券投資信託基金-B類型", "", "acai222", "yp010000"),
    ("基富通", "TWD", "基金", "柏瑞新興邊境非投資等級債券證券投資信託基金-B類型", "", "acai222", "yp010000"),
    ("基富通", "TWD", "基金", "柏瑞新興邊境非投資等級債券證券投資信託基金-B類型", "", "acai222", "yp010000"),
    ("基富通", "TWD", "基金", "柏瑞新興邊境非投資等級債券證券投資信託基金-B類型", "", "acai222", "yp010000"),
    ("基富通", "TWD", "基金", "柏瑞新興邊境非投資等級債券證券投資信託基金-B類型", "", "acai222", "yp010000"),
    ("基富通", "TWD", "基金", "柏瑞新興邊境非投資等級債券證券投資信託基金-B類型", "", "acai222", "yp010000"),
    ("基富通", "TWD", "基金", "柏瑞新興邊境非投資等級債券證券投資信託基金-B類型", "", "acai222", "yp010000"),
    ("基富通", "TWD", "基金", "柏瑞新興邊境非投資等級債券證券投資信託基金-B類型", "", "acai222", "yp010000"),
    ("基富通", "TWD", "基金", "柏瑞新興邊境非投資等級債券證券投資信託基金-B類型", "", "acai222", "yp010000"),
    ("基富通", "TWD", "基金", "柏瑞新興邊境非投資等級債券證券投資信託基金-B類型", "", "acai222", "yp010000"),
    ("基富通", "TWD", "基金", "柏瑞新興邊境非投資等級債券證券投資信託基金-B類型", "", "acai222", "yp010000"),
    ("基富通", "TWD", "基金", "柏瑞新興邊境非投資等級債券證券投資信託基金-B類型", "", "acai222", "yp010000"),
    ("基富通", "TWD", "基金", "柏瑞新興邊境非投資等級債券證券投資信託基金-B類型", "", "acai222", "yp010000"),
    ("基富通", "CNY", "基金", "富蘭克林華美新興國家固定收益證劵投資信託基金B-人民幣", "", "acft99", "yp010000"),
    ("基富通", "CNY", "基金", "富蘭克林華美新興國家固定收益證劵投資信託基金B-人民幣", "", "acft99", "yp010000"),
    ("基富通", "JPY", "基金", "貝萊德全球智慧數據股票入息Hedged A6日圓穩定配息", "", "shzx0", "yp010001"),
    ("基富通", "JPY", "基金", "貝萊德全球智慧數據股票入息Hedged A6日圓穩定配息", "", "shzx0", "yp010001"),
    ("基富通", "JPY", "基金", "安聯收益成長基金-AMgi月收總收益類股(日圓避險", "", "TLZO3", "yp010001"),
    ("基富通", "JPY", "基金", "安聯收益成長基金-AMgi月收總收益類股(日圓避險", "", "TLZO3", "yp010001"),
    ("基富通", "JPY", "基金", "安聯收益成長基金-AMgi月收總收益類股(日圓避險", "", "TLZO3", "yp010001"),

    ("美股", "USD", "美股", "PYPL", "PYPL", "", ""),
    ("美股", "USD", "美股", "PYPL", "PYPL", "", ""),
    ("美股", "USD", "美股", "PYPL", "PYPL", "", ""),
    ("美股", "USD", "美股", "XYZ", "XYZ", "", ""),

    ("渣打基金", "USD", "基金", "大華銀新加坡房地產收益基金-美元月配(後收)", "", "acob36", "yp010000"),
    ("渣打基金", "USD", "基金", "東方匯理基金新興市場債券A美元(穩定月配息)", "", "pizn8", "yp010001"),
    ("渣打基金", "USD", "基金", "東方匯理基金新興市場債券A美元(穩定月配息)", "", "pizn8", "yp010001"),
    ("渣打基金", "USD", "基金", "東方匯理基金新興市場債券A美元(穩定月配息)", "", "pizn8", "yp010001"),
    ("渣打基金", "USD", "基金", "東方匯理基金新興市場債券A美元(穩定月配息)", "", "pizn8", "yp010001"),
    ("渣打基金", "ZAR", "基金", "東方匯理基金新興市場債券U 南非幣(穩定月配息)", "", "pizm9", "yp010001"),

    ("台新基金", "USD", "基金", "高盛新興市場債券基金Y股美元", "", "anzb6", "yp010001"),
    ("台新基金", "USD", "基金", "東方匯理基金新興市場債券U 美元(穩定月配息)", "", "pizo1", "yp010001"),
    ("台新基金", "ZAR", "基金", "高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)", "", "ANZH2", "yp010001"),
    ("台新基金", "ZAR", "基金", "高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)", "", "ANZH2", "yp010001"),
    ("台新基金", "ZAR", "基金", "高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)", "", "ANZH2", "yp010001"),
    ("台新基金", "ZAR", "基金", "高盛新興市場債券基金Ｙ(南非幣對沖)(月配息)", "", "ANZH2", "yp010001"),
    ("台新基金", "ZAR", "基金", "東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)", "", "pizm9", "yp010001"),
    ("台新基金", "ZAR", "基金", "東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)", "", "pizm9", "yp010001"),
    ("台新基金", "ZAR", "基金", "東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)", "", "pizm9", "yp010001"),
    ("台新基金", "ZAR", "基金", "東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)", "", "pizm9", "yp010001"),
    ("台新基金", "ZAR", "基金", "東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)", "", "pizm9", "yp010001"),
    ("台新基金", "ZAR", "基金", "東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)", "", "pizm9", "yp010001"),
    ("台新基金", "ZAR", "基金", "東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)", "", "pizm9", "yp010001"),
    ("台新基金", "ZAR", "基金", "東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)", "", "pizm9", "yp010001"),
    ("台新基金", "ZAR", "基金", "東方匯理基金新興市場債券Ｕ(南非幣)(穩定月配息)", "", "pizm9", "yp010001"),
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


def load_positions() -> pd.DataFrame:
    sb = supabase_client()

    result = (
        sb.table("positions")
        .select("*")
        .order("platform")
        .order("sort_order")
        .order("id")
        .execute()
    )

    return pd.DataFrame(result.data or [])


def add_position(row: dict[str, Any]) -> None:
    sb = supabase_client()
    sb.table("positions").insert(row).execute()


def update_positions(df: pd.DataFrame) -> None:
    sb = supabase_client()

    for _, r in df.iterrows():

        rid = r.get("id", None)

        is_new = pd.isna(rid) or str(rid).strip() == ""

        payload = {
            "platform": str(r.get("platform", "台股")),
            "asset_type": str(r.get("asset_type", "台股")),
            "name": str(r.get("name", "")).strip(),
            "ticker": str(r.get("ticker", "")).strip(),
            "fund_code": str(r.get("fund_code", "")).strip(),
            "fund_pattern": str(r.get("fund_pattern", "")).strip(),
            "currency": str(r.get("currency", "TWD")),
            "original_units": float(
                r.get("original_units", 0) or 0
            ),

            "units": float(
                r.get("units", 0) or 0
            ),

            "corporate_action": str(
                r.get("corporate_action", "")
            ),
            "avg_cost": float(r.get("avg_cost", 0) or 0),
            "total_cost_input": float(
                r.get("total_cost_input", 0) or 0
            ),
            "monthly_dividend_per_unit": float(
                r.get("monthly_dividend_per_unit", 0) or 0
            ),
            "note": str(r.get("note", "")),
        }

        if not payload["name"]:
            continue

        if is_new:
            sb.table("positions").insert(payload).execute()
        else:
            (
                sb.table("positions")
                .update(payload)
                .eq("id", int(rid))
                .execute()
            )


def delete_position(position_id: int) -> None:
    (
        supabase_client()
        .table("positions")
        .delete()
        .eq("id", int(position_id))
        .execute()
    )


def mark_position_sold(position_id: int) -> None:

    (
        supabase_client()
        .table("positions")
        .update({
            "units": 0,
            "note": "已賣出 / 已結清"
        })
        .eq("id", int(position_id))
        .execute()
    )


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

        url = (
            f"https://www.moneydj.com/funddj/ya/"
            f"{pattern}.djhtm?a={code}"
        )

        r = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        r.raise_for_status()

        soup = BeautifulSoup(r.text, "lxml")

        table = soup.select_one("#article form table")

        if table:

            rows = table.find_all("tr")

            if len(rows) >= 2:

                cells = rows[1].find_all("td")

                if len(cells) >= 2:

                    nav = (
                        cells[1]
                        .get_text(strip=True)
                        .replace(",", "")
                    )

                    return float(nav), "ok"

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


def enrich(df: pd.DataFrame) -> pd.DataFrame:

    if df.empty:
        return df

    rows = []

    for _, r in df.iterrows():

        currency = r.get("currency", "TWD")

        original_units = float(
            r.get("original_units")
            or r.get("units")
            or 0
        )

        units = float(
            r.get("units")
            or 0
        )

        avg_cost = float(
            r.get("avg_cost")
            or 0
        )

        total_cost_input = float(
            r.get("total_cost_input")
            or 0
        )

        # 如果沒填單位數，自動由總成本反推
        if units == 0 and total_cost_input > 0 and avg_cost > 0:
            units = total_cost_input / avg_cost

        if original_units == 0 and total_cost_input > 0 and avg_cost > 0:
            original_units = total_cost_input / avg_cost

        if r.get("asset_type") in {"台股", "美股"}:

            price, p_status = fetch_yahoo_price(
                str(r.get("ticker") or "")
            )

        else:

            price, p_status = fetch_fund_nav(
                str(r.get("fund_code") or ""),
                str(r.get("fund_pattern") or "")
            )

        fx, fx_status = fetch_fx(currency)

        original_cost = (
            total_cost_input
            if total_cost_input > 0
            else original_units * avg_cost
        )

        original_value = (
            units * price
            if price is not None
            else None
        )

        twd_cost = (
            original_cost * fx
            if fx is not None
            else None
        )

        twd_value = (
            original_value * fx
            if original_value is not None and fx is not None
            else None
        )

        pnl = (
            twd_value - twd_cost
            if twd_value is not None and twd_cost is not None
            else None
        )

        pnl_rate = (
            pnl / twd_cost
            if pnl is not None and twd_cost
            else None
        )

        monthly_div = (
            units
            * float(r.get("monthly_dividend_per_unit") or 0)
        )

        monthly_div_twd = (
            monthly_div * fx
            if fx is not None
            else None
        )

        out = dict(r)

        out.update({
            "即時價格/淨值": price,
            "匯率": fx,
            "台幣成本": twd_cost,
            "台幣市值": twd_value,
            "損益": pnl,
            "損益率": pnl_rate,
            "每月配息": monthly_div_twd,
            "狀態":
                "✓"
                if p_status == "ok" and fx_status == "ok"
                else f"價格:{p_status} 匯率:{fx_status}"
        })

        rows.append(out)

    return pd.DataFrame(rows)


def format_df(df: pd.DataFrame) -> pd.DataFrame:

    out = df.copy()

    for c in ["即時價格/淨值", "匯率"]:

        if c in out:
            out[c] = out[c].apply(
                lambda x: money(x, 4)
            )

    for c in ["台幣成本", "台幣市值", "損益", "每月配息"]:

        if c in out:
            out[c] = out[c].apply(money)

    if "損益率" in out:
        out["損益率"] = out["損益率"].apply(pct)

    rename_map = {
        "sort_order": "排序",
        "original_units": "成本股數",
        "units": "現在股數",
        "avg_cost": "平均成本",
        "total_cost_input": "投入總成本",
        "corporate_action": "股數調整備註",
    }

    out = out.rename(columns=rename_map)

    return out

def seed_presets() -> None:

    existing = load_positions()

    existing_names = set(
        existing["name"].astype(str).tolist()
    ) if not existing.empty else set()

    for seq, name in enumerate(TW_STOCK_NAMES_DUPLICATE, start=1):

        ticker = TW_PRESETS.get(name, "")
        
    if name not in existing_names:
        add_position({
            "platform": "台股",
            "asset_type": "台股",
            "name": f"{name} #{seq:03d}",
            "ticker": ticker,
            "fund_code": "",
            "fund_pattern": "",
            "currency": "TWD",
            "units": 0,
            "avg_cost": 0,
            "monthly_dividend_per_unit": 0,
            "note": f"預設台股清單：{name}",
        })

    for seq, (
        platform,
        currency,
        asset_type,
        name,
        ticker,
        fund_code,
        fund_pattern,
    ) in enumerate(INVESTMENT_ITEMS_DUPLICATE, start=1):

        add_position({
            "platform": platform,
            "asset_type": asset_type,
            "name": f"{name} #{seq:03d}",
            "ticker": ticker,
            "fund_code": fund_code,
            "fund_pattern": fund_pattern,
            "currency": currency,
            "original_units": 0,
            "units": 0,
            "avg_cost": 0,
            "total_cost_input": 0,
            "monthly_dividend_per_unit": 0,
            "corporate_action": "",
            "note": "預設投資清單",
        })


def editable_platform_table(
    platform_name: str,
    current_positions: pd.DataFrame,
    editor_key: str
) -> None:

    st.markdown("#### ✏️ 編輯 / 新增")
    st.caption(
        "在這裡 key 成本股數、市值股數、平均成本、股票代碼或基金代號。"
        "新增列請拉到表格最下方直接輸入；按儲存後會寫入 Supabase。"
    )

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

    if current_positions.empty:
        base = pd.DataFrame(columns=cols)
    else:
        base = (
            current_positions[
                current_positions["platform"] == platform_name
            ][cols]
            .sort_values(["sort_order", "id"], na_position="last")
            .copy()
        )

    blank = {
        "id": None,
        "platform": platform_name,
        "asset_type": (
            "基金"
            if platform_name in ["基富通", "渣打基金", "台新基金"]
            else platform_name
        ),
        "name": "",
        "ticker": "",
        "fund_code": "",
        "fund_pattern": (
            "yp010001"
            if platform_name in ["基富通", "渣打基金", "台新基金"]
            else ""
        ),
        "currency": (
            "TWD"
            if platform_name in ["台股", "基富通"]
            else "USD"
        ),
        "original_units": 0.0,
        "units": 0.0,
        "corporate_action": "",
        "avg_cost": 0.0,
        "total_cost_input": 0.0,
        "monthly_dividend_per_unit": 0.0,
        "note": "",
    }

    base = pd.concat(
        [base, pd.DataFrame([blank])],
        ignore_index=True
    )

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
            "currency",
            "original_units",
            "units",
            "avg_cost",
            "monthly_dividend_per_unit",
            "corporate_action",
            "note",
        ],

        column_config={

            "sort_order": st.column_config.NumberColumn(
                "排序",
                step=1,
            ),

            "platform": st.column_config.SelectboxColumn(
                "平台",
                options=PLATFORMS,
               required=True,
            ),

            "asset_type": st.column_config.SelectboxColumn(
                "類型",
                options=ASSET_TYPES,
                required=True,
            ),
        },

        key=editor_key,
    )


    c1, c2, c3, c4 = st.columns([1, 1.4, 1.4, 1.4])

    if c1.button(
        "💾 儲存此頁變更",
        key=f"save_{editor_key}"
    ):

        update_positions(edited)

        st.success("已儲存")

        st.rerun()

    platform_rows = current_positions[
        current_positions["platform"] == platform_name
    ].copy()

    if not platform_rows.empty:

        platform_rows["選項"] = (
            platform_rows["name"].astype(str)
            + "｜"
            + platform_rows["ticker"].fillna("").astype(str)
            + platform_rows["fund_code"].fillna("").astype(str)
            + "｜ID "
            + platform_rows["id"].astype(str)
        )

        options = [""] + platform_rows["選項"].tolist()

    else:
        options = [""]

    copy_choice = c2.selectbox(
        "複製股票/基金名稱",
        options,
        key=f"copy_name_{editor_key}"
    )

    if c2.button(
        "📋 複製選取品項",
        key=f"copybtn_{editor_key}"
    ) and copy_choice:

        row = platform_rows[
            platform_rows["選項"] == copy_choice
        ]

        if row.empty:
            st.error("找不到此品項")

        else:

            r = row.iloc[0].to_dict()

            r.pop("id", None)

            r.pop("選項", None)

            r["name"] = str(r.get("name", "")) + "（複製）"

            add_position(r)

            st.success("已複製")

            st.rerun()

    sold_choice = c3.selectbox(
        "賣出 / 結清品項",
        options,
        key=f"sold_name_{editor_key}"
    )

    if c3.button(
        "✅ 標記賣出 / 結清",
        key=f"soldbtn_{editor_key}"
    ) and sold_choice:

        row = platform_rows[
            platform_rows["選項"] == sold_choice
        ]

        if row.empty:
            st.error("找不到此品項")

        else:

            mark_position_sold(
                int(row.iloc[0]["id"])
            )

            st.success(
                f"已標記賣出 / 結清：{row.iloc[0]['name']}"
            )

            st.rerun()

    delete_choice = c4.selectbox(
        "刪除股票/基金名稱",
        options,
        key=f"delete_name_{editor_key}"
    )

    if c4.button(
        "🗑️ 刪除選取品項",
        key=f"deletebtn_{editor_key}"
    ) and delete_choice:

        row = platform_rows[
            platform_rows["選項"] == delete_choice
        ]

        if row.empty:
            st.error("找不到此品項")

        else:

            delete_position(
                int(row.iloc[0]["id"])
            )

            st.success(
                f"已刪除：{row.iloc[0]['name']}"
            )

            st.rerun()


st.title("📈 Jenny 投資即時市值系統")

st.caption(
    f"版本：{APP_VERSION}｜Supabase 永久資料庫"
)

try:

    seed_presets()

except Exception as e:

    st.error(f"Supabase 初始化失敗：{e}")

    st.stop()


positions = load_positions()

enriched = enrich(positions)


total_value = (
    enriched["台幣市值"].dropna().sum()
    if not enriched.empty
    else 0
)

total_cost = (
    enriched["台幣成本"].dropna().sum()
    if not enriched.empty
    else 0
)

total_pnl = (
    enriched["損益"].dropna().sum()
    if not enriched.empty
    else 0
)

total_div = (
    enriched["每月配息"].dropna().sum()
    if not enriched.empty
    else 0
)

total_rate = (
    total_pnl / total_cost
    if total_cost
    else None
)


with st.container():

    st.markdown(
        '<div class="fixed-top"><div class="hero">',
        unsafe_allow_html=True
    )

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric(
        "總台幣市值",
        money(total_value),
        delta=f"{signed_money(total_pnl)} / {pct(total_rate)}"
    )

    c2.metric(
        "總台幣成本",
        money(total_cost)
    )

    c3.metric(
        "每月配息",
        money(total_div)
    )

    c4.metric(
        "投資筆數",
        f"{len(positions):,}"
    )

    if c5.button("🔄 更新即時價"):

        st.cache_data.clear()

        st.rerun()

    st.markdown(
        "</div></div>",
        unsafe_allow_html=True
    )

tabs = st.tabs([
    "總覽",
    "台股",
    "美股",
    "基富通",
    "渣打基金",
    "台新基金",
    "匯率",
])


show_cols = [
    "id",
    "platform",
    "asset_type",
    "name",
    "ticker",
    "fund_code",
    "currency",
    "original_units",
    "units",
    "avg_cost",
    "即時價格/淨值",
    "匯率",
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
            lambda r:
                r["損益"] / r["台幣成本"]
                if r["台幣成本"]
                else None,
            axis=1,
        )

        left, right = st.columns([1, 1.7])

        with left:

            st.bar_chart(
                summary.set_index("platform")[["台幣市值"]],
                height=330,
            )

        with right:

            st.dataframe(
                format_df(summary),
                use_container_width=True,
                hide_index=True,
                height=330,
            )

        st.subheader("全部投資產品")

        st.dataframe(
            format_df(enriched[show_cols]),
            use_container_width=True,
            hide_index=True,
            height=560,
        )


for idx, platform in enumerate(PLATFORMS, start=1):

    with tabs[idx]:

        st.subheader(platform)

        view = (
            enriched[
                enriched["platform"] == platform
            ].copy()
            if not enriched.empty
            else pd.DataFrame()
        )

        if view.empty:

            st.info(f"尚無 {platform} 資料")

        else:

            m1, m2, m3, m4 = st.columns(4)

            m1.metric(
                "台幣市值",
                money(view["台幣市值"].dropna().sum())
            )

            m2.metric(
                "台幣成本",
                money(view["台幣成本"].dropna().sum())
            )

            m3.metric(
                "損益",
                signed_money(view["損益"].dropna().sum())
            )

            m4.metric(
                "每月配息",
                money(view["每月配息"].dropna().sum())
            )

            st.markdown("#### 即時計算結果")

            st.caption(
                "市值 = 單位數 × 即時價格/淨值 × 匯率"
            )

            st.dataframe(
                format_df(view[show_cols]),
                use_container_width=True,
                hide_index=True,
                height=360,
            )

        editable_platform_table(
            platform,
            positions,
            f"editor_{platform}"
        )


with tabs[6]:

    st.subheader("匯率")

    rows = []

    for cur in CURRENCIES:

        rate, status = fetch_fx(cur)

        rows.append({
            "幣別": cur,
            "對台幣匯率": money(rate, 4),
            "狀態":
                "✓"
                if status == "ok"
                else f"⚠ {status}",
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
    )

