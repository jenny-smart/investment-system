from __future__ import annotations

from typing import Any

import pandas as pd
import requests
import streamlit as st

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


st.set_page_config(
    page_title="投資即時市值表",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.stApp { background:#f7faf9; color:#0f2b20; }
.block-container { padding-top: 1.2rem; max-width: 1500px; }
[data-testid="stMetric"] {
    background:#fff; border:1px solid #e5eae8; border-radius:14px;
    padding:18px 20px; box-shadow:0 1px 4px rgba(0,0,0,.04);
}
[data-testid="stDataFrame"] {
    background:#fff; border:1px solid #e5eae8; border-radius:14px;
    overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,.04);
}
h1, h2, h3 { color:#0f2b20; }
.small { color:#7b9188; font-size:13px; }
</style>
""", unsafe_allow_html=True)

st.title("📈 投資即時市值表與匯率")
st.markdown(
    '<div class="small">台股 / 美股使用 Yahoo Finance；基金淨值使用 MoneyDJ；匯率使用 Yahoo Finance。台股清單保留重複項目，不去重。</div>',
    unsafe_allow_html=True,
)


TW_STOCK_NAMES = [
    "儒鴻", "儒鴻", "大魯閣", "中砂", "中砂", "中鴻", "凱美", "華碩", "日勝生", "日勝生",
    "晶華", "晶華", "中壽", "中壽", "凱基金", "凱基金乙特", "聯陽", "景碩", "景碩", "景碩",
    "緯創", "緯創", "緯創", "緯創", "緯創", "緯創", "緯創", "東隆興", "東隆興", "和碩",
    "松翰", "松翰", "智冠", "久元", "久元", "久元", "台塑化", "台塑化", "上銀", "元大高股息",
    "元大台灣50", "泰碩", "尼得科超眾", "立積", "立積", "鈺齊-KY", "東陽", "東陽", "東陽", "東陽",
    "中砂", "中砂", "中砂", "中砂", "中砂", "中砂", "中砂", "中砂", "華邦電", "華邦電",
    "元大金", "元大金", "元大金", "元大金", "元大金", "元大金", "元大金", "元大金", "鴻海", "長榮",
    "長華*", "群創", "集盛", "華新", "第一銅", "大聯大", "富邦特選高股息30", "富邦特選高股息30",
    "群益台灣精選高息", "群益台灣精選高息", "富邦全球投等債", "群益半導體收益", "華泰", "圓剛", "圓剛",
    "中鴻", "楠梓電", "富邦台50", "南亞科", "欣興", "京元電子", "國巨",
]

TW_STOCK_CODE_MAP = {
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

US_STOCKS = [
    {"name": "PayPal", "ticker": "PYPL", "currency": "USD"},
    {"name": "Block / XYZ", "ticker": "XYZ", "currency": "USD"},
]

FUNDS = [
    {"name": "富蘭克林華美新興國家固定收益基金B-新臺幣", "code": "acft94", "pattern": "yp010000", "currency": "TWD"},
    {"name": "柏瑞新興邊境非投資等級債券基金-B類型", "code": "acai222", "pattern": "yp010000", "currency": "TWD"},
    {"name": "富蘭克林華美新興國家固定收益基金B-人民幣", "code": "acft99", "pattern": "yp010000", "currency": "CNY"},
    {"name": "貝萊德全球智慧數據股票入息 Hedged A6 日圓穩定配息", "code": "shzx0", "pattern": "yp010001", "currency": "JPY"},
    {"name": "安聯收益成長基金-AMgi月收總收益類股（日圓避險）", "code": "TLZO3", "pattern": "yp010001", "currency": "JPY"},
    {"name": "大華銀新加坡房地產收益基金-美元月配（後收）", "code": "acob36", "pattern": "yp010000", "currency": "USD"},
    {"name": "東方匯理基金新興市場債券A美元（穩定月配息）", "code": "pizn8", "pattern": "yp010001", "currency": "USD"},
    {"name": "東方匯理基金新興市場債券U南非幣（穩定月配息）", "code": "pizm9", "pattern": "yp010001", "currency": "ZAR"},
    {"name": "高盛新興市場債券基金Y股美元", "code": "anzb6", "pattern": "yp010001", "currency": "USD"},
    {"name": "東方匯理基金新興市場債券U美元（穩定月配息）", "code": "pizo1", "pattern": "yp010001", "currency": "USD"},
    {"name": "高盛新興市場債券基金Y南非幣對沖（月配息）", "code": "ANZH2", "pattern": "yp010001", "currency": "ZAR"},
    {"name": "東方匯理基金新興市場債券U南非幣（穩定月配息）", "code": "pizm9", "pattern": "yp010001", "currency": "ZAR"},
]

FX_PAIRS = {
    "USD": "USDTWD=X",
    "CNY": "CNYTWD=X",
    "JPY": "JPYTWD=X",
    "ZAR": "ZARTWD=X",
    "TWD": None,
}


def to_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        if isinstance(value, str):
            value = value.replace(",", "").replace("$", "").strip()
            if value in {"", "-", "—"}:
                return None
        return float(value)
    except Exception:
        return None


def money(v: Any, decimals: int = 2) -> str:
    n = to_float(v)
    if n is None:
        return "-"
    return f"{n:,.{decimals}f}"


def money0(v: Any) -> str:
    n = to_float(v)
    if n is None:
        return "-"
    return f"{n:,.0f}"


@st.cache_data(ttl=300, show_spinner=False)
def fetch_yahoo_price(ticker: str) -> tuple[float | None, str]:
    if not HAS_YF:
        return None, "缺少 yfinance"
    try:
        t = yf.Ticker(ticker)
        price = getattr(t.fast_info, "last_price", None)
        if price is None:
            hist = t.history(period="5d")
            if not hist.empty:
                price = hist["Close"].dropna().iloc[-1]
        return (float(price), "ok") if price is not None else (None, "無價格")
    except Exception as e:
        return None, str(e)[:60]


@st.cache_data(ttl=300, show_spinner=False)
def fetch_fx_rate(currency: str) -> tuple[float | None, str]:
    if currency == "TWD":
        return 1.0, "ok"
    pair = FX_PAIRS.get(currency)
    if pair is None:
        return None, "未知幣別"
    return fetch_yahoo_price(pair)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_fund_nav(code: str, pattern: str) -> tuple[float | None, str]:
    if not HAS_BS4:
        return None, "缺少 beautifulsoup4"
    url = f"https://www.moneydj.com/funddj/ya/{pattern}.djhtm?a={code}"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=20)
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
        return None, "找不到淨值欄位"
    except Exception as e:
        return None, str(e)[:60]


def clear_cache_button() -> None:
    if st.button("🔄 重新抓取即時資料"):
        st.cache_data.clear()
        st.rerun()


def build_fx_table() -> pd.DataFrame:
    rows = []
    for cur in ["USD", "CNY", "JPY", "ZAR", "TWD"]:
        rate, status = fetch_fx_rate(cur)
        rows.append({"幣別": cur, "對台幣匯率": rate, "狀態": "✓" if status == "ok" else f"⚠ {status}"})
    return pd.DataFrame(rows)


def build_tw_table(shares_map: dict[str, float] | None = None) -> pd.DataFrame:
    shares_map = shares_map or {}
    rows = []
    for i, name in enumerate(TW_STOCK_NAMES, start=1):
        ticker = TW_STOCK_CODE_MAP.get(name, "")
        price, status = fetch_yahoo_price(ticker) if ticker else (None, "未設定代碼")
        shares = shares_map.get(str(i), 0.0)
        market_value = price * shares if price is not None and shares else None
        rows.append({
            "序號": i,
            "股票名稱": name,
            "Yahoo代碼": ticker,
            "即時股價": price,
            "持股數": shares,
            "台幣市值": market_value,
            "狀態": "✓" if status == "ok" else f"⚠ {status}",
        })
    return pd.DataFrame(rows)


def build_us_table(shares_map: dict[str, float] | None = None) -> pd.DataFrame:
    shares_map = shares_map or {}
    rows = []
    usd_rate, _ = fetch_fx_rate("USD")
    for s in US_STOCKS:
        price, status = fetch_yahoo_price(s["ticker"])
        shares = shares_map.get(s["ticker"], 0.0)
        usd_value = price * shares if price is not None and shares else None
        twd_value = usd_value * usd_rate if usd_value is not None and usd_rate is not None else None
        rows.append({
            "名稱": s["name"],
            "代號": s["ticker"],
            "幣別": s["currency"],
            "即時股價": price,
            "持股數": shares,
            "原幣市值": usd_value,
            "台幣市值": twd_value,
            "USD/TWD": usd_rate,
            "狀態": "✓" if status == "ok" else f"⚠ {status}",
        })
    return pd.DataFrame(rows)


def build_fund_table(units_map: dict[str, float] | None = None) -> pd.DataFrame:
    units_map = units_map or {}
    rows = []
    for f in FUNDS:
        nav, status = fetch_fund_nav(f["code"], f["pattern"])
        fx_rate, fx_status = fetch_fx_rate(f["currency"])
        units = units_map.get(f["code"], 0.0)
        original_value = nav * units if nav is not None and units else None
        twd_nav = nav * fx_rate if nav is not None and fx_rate is not None else None
        twd_value = original_value * fx_rate if original_value is not None and fx_rate is not None else None
        rows.append({
            "基金名稱": f["name"],
            "MoneyDJ代號": f["code"],
            "幣別": f["currency"],
            "最新淨值": nav,
            "匯率": fx_rate,
            "台幣淨值": twd_nav,
            "單位數": units,
            "原幣市值": original_value,
            "台幣市值": twd_value,
            "狀態": "✓" if status == "ok" and fx_status == "ok" else f"⚠ NAV:{status} FX:{fx_status}",
        })
    return pd.DataFrame(rows)


def format_numeric_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if col in {"即時股價", "最新淨值", "匯率", "台幣淨值", "原幣市值", "USD/TWD", "對台幣匯率"}:
            out[col] = out[col].apply(lambda x: money(x, 4))
        elif col in {"台幣市值"}:
            out[col] = out[col].apply(money0)
    return out


def parse_uploaded_positions(file) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    tw, us, funds = {}, {}, {}
    if file is None:
        return tw, us, funds
    df = pd.read_csv(file)
    if not {"類別", "識別", "數量"}.issubset(set(df.columns)):
        st.warning("匯入 CSV 需要欄位：類別, 識別, 數量")
        return tw, us, funds
    for _, r in df.iterrows():
        typ, key, qty = str(r["類別"]).strip(), str(r["識別"]).strip(), to_float(r["數量"]) or 0
        if typ == "台股":
            tw[key] = qty
        elif typ == "美股":
            us[key] = qty
        elif typ == "基金":
            funds[key] = qty
    return tw, us, funds


top1, top2 = st.columns([1, 4])
with top1:
    clear_cache_button()
with top2:
    uploaded = st.file_uploader(
        "可選：匯入持有數量 CSV（欄位：類別, 識別, 數量）。台股識別用序號；美股用 PYPL/XYZ；基金用 MoneyDJ 代號。",
        type=["csv"],
    )

tw_shares, us_shares, fund_units = parse_uploaded_positions(uploaded)

fx_df = build_fx_table()
m1, m2, m3, m4 = st.columns(4)
for metric_col, cur in zip([m1, m2, m3, m4], ["USD", "CNY", "JPY", "ZAR"]):
    rate = fx_df.loc[fx_df["幣別"] == cur, "對台幣匯率"].iloc[0]
    metric_col.metric(f"{cur}/TWD", money(rate, 4))

tabs = st.tabs(["匯率", "台股即時表", "美股即時表", "基金即時表", "總表"])

with tabs[0]:
    st.subheader("💱 匯率")
    st.dataframe(format_numeric_df(fx_df), use_container_width=True, hide_index=True)

with tabs[1]:
    st.subheader("🇹🇼 台股即時價格 / 市值表")
    tw_df = build_tw_table(tw_shares)
    st.caption("清單保留重複項目，不去重。若未匯入持股數，台幣市值會是空白。")
    st.dataframe(format_numeric_df(tw_df), use_container_width=True, hide_index=True, height=650)
    st.metric("台股台幣市值合計", money0(tw_df["台幣市值"].dropna().sum()))

with tabs[2]:
    st.subheader("🇺🇸 美股即時價格 / 市值表")
    us_df = build_us_table(us_shares)
    st.dataframe(format_numeric_df(us_df), use_container_width=True, hide_index=True)
    st.metric("美股台幣市值合計", money0(us_df["台幣市值"].dropna().sum()))

with tabs[3]:
    st.subheader("🏦 基金最新淨值 / 台幣淨值 / 市值表")
    fund_df = build_fund_table(fund_units)
    st.dataframe(format_numeric_df(fund_df), use_container_width=True, hide_index=True, height=520)
    st.metric("基金台幣市值合計", money0(fund_df["台幣市值"].dropna().sum()))

with tabs[4]:
    st.subheader("📊 總表")
    tw_df = build_tw_table(tw_shares)
    us_df = build_us_table(us_shares)
    fund_df = build_fund_table(fund_units)

    summary = pd.DataFrame([
        {"類別": "台股", "筆數": len(tw_df), "台幣市值": tw_df["台幣市值"].dropna().sum()},
        {"類別": "美股", "筆數": len(us_df), "台幣市值": us_df["台幣市值"].dropna().sum()},
        {"類別": "基金", "筆數": len(fund_df), "台幣市值": fund_df["台幣市值"].dropna().sum()},
    ])
    summary["台幣市值"] = summary["台幣市值"].apply(money0)
    st.dataframe(summary, use_container_width=True, hide_index=True)
