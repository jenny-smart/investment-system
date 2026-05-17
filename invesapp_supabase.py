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

APP_VERSION = "2026-05-17-v4"
DEFAULT_SUPABASE_URL = "https://qrvdztqyzxlsfskdgiqp.supabase.co"
PLATFORMS   = ["台股", "美股", "基富通", "渣打基金", "台新基金"]
ASSET_TYPES = ["台股", "美股", "基金"]
CURRENCIES  = ["TWD", "USD", "CNY", "JPY", "ZAR"]
FX_PAIRS    = {"TWD": None, "USD": "USDTWD=X", "CNY": "CNYTWD=X", "JPY": "JPYTWD=X", "ZAR": "ZARTWD=X"}
SORT_OPTIONS = {
    "名稱 A→Z":  ("name", True),
    "名稱 Z→A":  ("name", False),
    "代碼 A→Z":  ("ticker_or_code", True),
    "市值 高→低": ("台幣市值_raw", False),
    "市值 低→高": ("台幣市值_raw", True),
    "損益 高→低": ("損益_raw", False),
    "損益率 高→低":("損益率_raw", False),
    "配息 高→低": ("每月配息_raw", False),
}

TW_PRESETS = {
    "儒鴻":"1476.TW","大魯閣":"1432.TW","中砂":"1560.TW","中鴻":"2014.TW",
    "凱美":"2375.TW","華碩":"2357.TW","日勝生":"2547.TW","晶華":"2707.TW",
    "中壽":"2823.TW","凱基金":"2883.TW","凱基金乙特":"2883B.TW","聯陽":"3014.TW",
    "景碩":"3189.TW","緯創":"3231.TW","東隆興":"4401.TWO","和碩":"4938.TW",
    "松翰":"5471.TWO","智冠":"5478.TWO","久元":"6261.TWO","台塑化":"6505.TW",
    "上銀":"2049.TW","元大高股息":"0056.TW","元大台灣50":"0050.TW",
    "泰碩":"3338.TW","尼得科超眾":"6230.TW","立積":"4968.TW","鈺齊-KY":"9802.TW",
    "東陽":"1319.TW","華邦電":"2344.TW","元大金":"2885.TW","鴻海":"2317.TW",
    "長榮":"2603.TW","長華*":"8070.TW","群創":"3481.TW","集盛":"1455.TW",
    "華新":"1605.TW","第一銅":"2009.TW","大聯大":"3702.TW",
    "富邦特選高股息30":"00900.TW","群益台灣精選高息":"00919.TW",
    "富邦全球投等債":"00740B.TW","群益半導體收益":"00927.TW","華泰":"2329.TW",
    "圓剛":"2417.TW","楠梓電":"2316.TW","富邦台50":"006208.TW",
    "南亞科":"2408.TW","欣興":"3037.TW","京元電子":"2449.TW","國巨":"2327.TW",
}
FUND_PRESETS = {
    "acft94":  ("富蘭克林華美新興國家固定收益B-新臺幣","yp010000","TWD","基富通"),
    "acai222": ("柏瑞新興邊境非投資等級債券基金-B類型","yp010000","TWD","基富通"),
    "acft99":  ("富蘭克林華美新興國家固定收益B-人民幣","yp010000","CNY","基富通"),
    "shzx0":   ("貝萊德全球智慧數據股票入息A6日圓","yp010001","JPY","基富通"),
    "TLZO3":   ("安聯收益成長AMgi月收（日圓避險）","yp010001","JPY","基富通"),
    "acob36":  ("大華銀新加坡房地產收益基金-美元月配","yp010000","USD","渣打基金"),
    "pizn8":   ("東方匯理新興市場債券A美元（月配）","yp010001","USD","渣打基金"),
    "pizo1":   ("東方匯理新興市場債券U美元（月配）","yp010001","USD","渣打基金"),
    "pizm9":   ("東方匯理新興市場債券U南非幣（月配）","yp010001","ZAR","台新基金"),
    "anzb6":   ("高盛新興市場債券Y股美元","yp010001","USD","渣打基金"),
    "ANZH2":   ("高盛新興市場債券Y南非幣對沖（月配）","yp010001","ZAR","台新基金"),
}

# ── 頁面設定 ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Jenny 投資系統", page_icon="◈", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', 'PingFang TC', 'Noto Sans TC', sans-serif !important;
}
.stApp { background: #f4f7f5 !important; color: #0f2b20 !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }
[data-testid="stSidebar"], [data-testid="collapsedControl"],
button[kind="header"] { display: none !important; }

/* ── 頂部導覽列 ── */
.j-topbar {
    background: #0f2b20;
    padding: 0 28px;
    display: flex;
    align-items: center;
    gap: 16px;
    height: 60px;
    position: sticky; top: 0; z-index: 1000;
}
.j-logo {
    width: 34px; height: 34px;
    background: linear-gradient(135deg, #10b981, #34d399);
    border-radius: 9px;
    display: flex; align-items: center; justify-content: center;
    font-size: 17px; font-weight: 900; color: #fff;
    box-shadow: 0 2px 12px rgba(16,185,129,.4);
    flex-shrink: 0;
}
.j-app-name { font-size: 15px; font-weight: 700; color: #fff; letter-spacing: -.2px; }
.j-app-sub  { font-size: 11px; color: rgba(255,255,255,.45); margin-top: 1px; }
.j-spacer   { flex: 1; }
.j-ver-tag  {
    font-size: 10px; font-weight: 600;
    color: rgba(255,255,255,.5);
    font-family: 'JetBrains Mono', monospace;
    background: rgba(255,255,255,.07);
    border: 1px solid rgba(255,255,255,.12);
    border-radius: 12px; padding: 3px 10px;
}

/* ── 工具列（排序 + 更新）── */
.j-toolbar {
    background: #fff;
    border-bottom: 1px solid #e2ebe6;
    padding: 10px 28px;
    display: flex; align-items: center; gap: 16px;
}
.j-toolbar-label {
    font-size: 10px; font-weight: 700; color: #7b9188;
    text-transform: uppercase; letter-spacing: 1px;
    white-space: nowrap;
}

/* ── 指標列 ── */
.j-kpi-bar {
    background: #fff;
    border-bottom: 1px solid #e2ebe6;
    padding: 16px 28px;
    display: flex; gap: 1px;
}
.j-kpi {
    flex: 1; padding: 14px 18px;
    background: #f9fbfa;
    border-radius: 0;
}
.j-kpi:first-child { border-radius: 10px 0 0 10px; }
.j-kpi:last-child  { border-radius: 0 10px 10px 0; }
.j-kpi-label {
    font-size: 10px; font-weight: 700; color: #7b9188;
    text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px;
}
.j-kpi-val {
    font-size: 21px; font-weight: 800; color: #0f2b20;
    font-family: 'JetBrains Mono', monospace; letter-spacing: -.5px;
}
.j-kpi-sub { font-size: 11px; color: #9aafa8; margin-top: 3px; }
.j-kpi-sub.pos { color: #059669; font-weight: 600; }
.j-kpi-sub.neg { color: #dc2626; font-weight: 600; }

/* ── Tab ── */
.stTabs [data-baseweb="tab-list"] {
    background: #fff !important;
    border-bottom: 2px solid #e2ebe6 !important;
    padding: 0 28px !important; gap: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    color: #6b8a7a !important; font-size: 13px !important;
    font-weight: 500 !important; padding: 13px 20px !important;
    border-bottom: 2.5px solid transparent !important;
    background: transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #0f2b20 !important;
    border-bottom-color: #10b981 !important;
    font-weight: 700 !important;
}
.stTabs [data-baseweb="tab-panel"] {
    background: #f4f7f5; padding: 24px 28px;
}

/* ── 卡片 ── */
.j-card {
    background: #fff;
    border: 1px solid #e2ebe6;
    border-radius: 12px;
    padding: 18px 20px;
    margin-bottom: 14px;
    box-shadow: 0 1px 3px rgba(0,0,0,.04);
}
.j-card-title {
    font-size: 10px; font-weight: 700; color: #7b9188;
    text-transform: uppercase; letter-spacing: 1px;
    margin-bottom: 14px; padding-bottom: 10px;
    border-bottom: 1px solid #f0f5f3;
}
.j-pg-title { font-size: 18px; font-weight: 800; color: #0f2b20; margin-bottom: 3px; }
.j-pg-sub   { font-size: 12px; color: #9aafa8; margin-bottom: 18px; }

/* ── Streamlit Metric 卡片 ── */
[data-testid="stMetric"] {
    background: #fff !important;
    border: 1px solid #e2ebe6 !important;
    border-radius: 12px !important;
    padding: 16px 18px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,.04) !important;
}
[data-testid="stMetricLabel"] p {
    font-size: 10px !important; font-weight: 700 !important;
    color: #7b9188 !important; text-transform: uppercase !important;
    letter-spacing: 1px !important;
}
[data-testid="stMetricValue"] {
    font-size: 20px !important; font-weight: 800 !important;
    color: #0f2b20 !important;
    font-family: 'JetBrains Mono', monospace !important;
}

/* ── 資料表格 ── */
[data-testid="stDataFrame"] {
    background: #fff !important;
    border: 1px solid #e2ebe6 !important;
    border-radius: 12px !important;
    overflow: hidden !important;
    box-shadow: 0 1px 3px rgba(0,0,0,.04) !important;
}

/* ── 按鈕 ── */
.stButton > button {
    background: #10b981 !important; color: #fff !important;
    border: none !important; border-radius: 8px !important;
    font-weight: 600 !important; font-size: 13px !important;
    padding: 7px 18px !important;
    box-shadow: 0 2px 8px rgba(16,185,129,.25) !important;
}
.stButton > button:hover { background: #059669 !important; }

/* ── Selectbox ── */
[data-baseweb="select"] > div {
    background: #f4f7f5 !important; border-color: #d5e3de !important;
    border-radius: 8px !important; color: #0f2b20 !important;
    font-size: 13px !important;
}

/* ── 基金淨值列表 ── */
.j-fund-item {
    display: flex; align-items: center;
    padding: 9px 0; border-bottom: 1px solid #f0f5f3;
    font-size: 13px; gap: 12px;
}
.j-fund-item:last-child { border-bottom: none; }
.j-fn  { flex: 1; color: #0f2b20; font-weight: 500; }
.j-fc  { width: 64px; color: #7b9188; font-family: 'JetBrains Mono', monospace; font-size: 11px; }
.j-fcur{ width: 40px; color: #9aafa8; font-size: 11px; text-align: center; }
.j-nav { width: 80px; text-align: right; font-family: 'JetBrains Mono', monospace; color: #0f2b20; }
.j-twd { width: 90px; text-align: right; font-family: 'JetBrains Mono', monospace; color: #059669; font-weight: 700; }
.j-st  { width: 28px; text-align: center; }
</style>
""", unsafe_allow_html=True)


# ── 工具函式 ──────────────────────────────────────────────────────────────
def get_secret(name: str, default: str = "") -> str:
    try: return st.secrets.get(name, default)
    except Exception: return os.environ.get(name, default)

def to_float(v: Any) -> float | None:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)): return None
        if isinstance(v, str):
            v = v.replace(",","").replace("$","").strip()
            if v in {"","-","—"}: return None
        return float(v)
    except Exception: return None

def money(v: Any, d: int = 0) -> str:
    n = to_float(v); return "-" if n is None else f"{n:,.{d}f}"

def signed_money(v: Any) -> str:
    n = to_float(v); return "-" if n is None else f"{n:+,.0f}"

def pct(v: Any, signed: bool = False) -> str:
    n = to_float(v)
    if n is None: return "-"
    return (f"{n:+.2%}" if signed else f"{n:.2%}")


# ── Supabase ──────────────────────────────────────────────────────────────
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

def add_position(row: dict) -> None:
    supabase_client().table("positions").insert(row).execute()

def update_positions(df: pd.DataFrame) -> None:
    sb = supabase_client()
    for _, r in df.iterrows():
        rid = r.get("id", None)
        try:    is_new = pd.isna(float(str(rid)))
        except: is_new = str(rid).strip() in {"","None","nan"}
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
        if not any([payload["name"], payload["ticker"], payload["fund_code"]]): continue
        if is_new: sb.table("positions").insert(payload).execute()
        else:      sb.table("positions").update(payload).eq("id", int(rid)).execute()

def delete_position(pid: int) -> None:
    supabase_client().table("positions").delete().eq("id", pid).execute()


# ── 即時報價 ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def fetch_yahoo_price(ticker: str) -> tuple[float | None, str]:
    if not ticker: return None, "無代碼"
    if not HAS_YF: return None, "缺少yfinance"
    try:
        t = yf.Ticker(ticker)
        price = getattr(t.fast_info, "last_price", None)
        if price is None:
            h = t.history(period="5d")
            if not h.empty: price = float(h["Close"].dropna().iloc[-1])
        return (float(price), "ok") if price is not None else (None, "無價格")
    except Exception as e: return None, str(e)[:40]

@st.cache_data(ttl=300, show_spinner=False)
def fetch_fund_nav(code: str, pattern: str) -> tuple[float | None, str]:
    if not code or not pattern: return None, "無代碼"
    if not HAS_BS4: return None, "缺少bs4"
    try:
        url = f"https://www.moneydj.com/funddj/ya/{pattern}.djhtm?a={code}"
        r = requests.get(url, timeout=20, headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        tbl = soup.select_one("#article form table")
        if tbl:
            rows = tbl.find_all("tr")
            if len(rows) >= 2:
                cells = rows[1].find_all("td")
                if len(cells) >= 2:
                    return float(cells[1].get_text(strip=True).replace(",","")), "ok"
        return None, "找不到淨值"
    except Exception as e: return None, str(e)[:40]

@st.cache_data(ttl=300, show_spinner=False)
def fetch_fx(currency: str) -> tuple[float | None, str]:
    if currency == "TWD": return 1.0, "ok"
    pair = FX_PAIRS.get(currency)
    if not pair: return None, "未知幣別"
    return fetch_yahoo_price(pair)


# ── 計算市值（保留原始數值欄供排序用）────────────────────────────────────
def enrich(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    fx_cache: dict[str, tuple] = {}
    rows = []
    for _, r in df.iterrows():
        currency = str(r.get("currency") or "TWD")
        units    = float(r.get("units") or 0)
        avg_cost = float(r.get("avg_cost") or 0)

        if r.get("asset_type") in {"台股","美股"}:
            price, ps = fetch_yahoo_price(str(r.get("ticker") or ""))
        else:
            price, ps = fetch_fund_nav(str(r.get("fund_code") or ""), str(r.get("fund_pattern") or ""))

        if currency not in fx_cache: fx_cache[currency] = fetch_fx(currency)
        fx, fxs = fx_cache[currency]

        oc   = units * avg_cost
        ov   = units * price if price is not None else None
        tc   = oc * fx if fx else None
        tv   = ov * fx if ov is not None and fx else None
        pnl  = tv - tc if tv is not None and tc is not None else None
        rate = pnl / tc if pnl is not None and tc else None
        md   = units * float(r.get("monthly_dividend_per_unit") or 0) * (fx or 1)
        code = str(r.get("ticker") or r.get("fund_code") or "")

        out = dict(r)
        out.update({
            "ticker_or_code": code,
            # 顯示用
            "即時價格": money(price, 4) if price is not None else "-",
            "匯率":    money(fx, 4)   if fx   is not None else "-",
            "台幣成本": money(tc),
            "台幣市值": money(tv),
            "損益":    signed_money(pnl),
            "損益率":  pct(rate, signed=True),
            "每月配息": money(md) if md else "-",
            "狀態":    "✓" if ps == "ok" and fxs == "ok" else f"⚠{ps}",
            # 原始數值（供排序）
            "台幣市值_raw": tv or 0,
            "損益_raw":    pnl or 0,
            "損益率_raw":  rate or 0,
            "每月配息_raw": md or 0,
        })
        rows.append(out)
    return pd.DataFrame(rows)

def sort_df(df: pd.DataFrame, sort_key: str) -> pd.DataFrame:
    col, asc = SORT_OPTIONS.get(sort_key, ("name", True))
    if col in df.columns:
        return df.sort_values(col, ascending=asc, na_position="last").reset_index(drop=True)
    return df

# 顯示用欄位（不含 _raw 欄）
SHOW = ["id","platform","name","ticker","fund_code","currency",
        "units","avg_cost","即時價格","匯率","台幣成本","台幣市值",
        "損益","損益率","每月配息","狀態"]


# ── Seed ──────────────────────────────────────────────────────────────────
def seed_presets() -> None:
    if not load_positions().empty: return
    for name, ticker in TW_PRESETS.items():
        add_position({"platform":"台股","asset_type":"台股","name":name,"ticker":ticker,
                      "fund_code":"","fund_pattern":"","currency":"TWD","units":0,
                      "avg_cost":0,"monthly_dividend_per_unit":0,"note":"預設"})
    for ticker, name in [("PYPL","PayPal"),("XYZ","Block")]:
        add_position({"platform":"美股","asset_type":"美股","name":name,"ticker":ticker,
                      "fund_code":"","fund_pattern":"","currency":"USD","units":0,
                      "avg_cost":0,"monthly_dividend_per_unit":0,"note":"預設"})
    for code,(name,pattern,currency,platform) in FUND_PRESETS.items():
        add_position({"platform":platform,"asset_type":"基金","name":name,"ticker":"",
                      "fund_code":code,"fund_pattern":pattern,"currency":currency,"units":0,
                      "avg_cost":0,"monthly_dividend_per_unit":0,"note":"預設"})


# ── 編輯器元件 ────────────────────────────────────────────────────────────
def editable_table(platform_name: str, current: pd.DataFrame, ekey: str) -> None:
    st.markdown("---")
    st.markdown("**✏️ 編輯 / 新增持倉**")
    st.caption("直接在表格輸入，按儲存後寫入 Supabase。")
    cols = ["id","platform","asset_type","name","ticker","fund_code","fund_pattern",
            "currency","units","avg_cost","monthly_dividend_per_unit","note"]
    base = current[current["platform"] == platform_name][cols].copy() \
           if not current.empty else pd.DataFrame(columns=cols)
    blank = {"id":None,"platform":platform_name,
             "asset_type":"基金" if platform_name in ["基富通","渣打基金","台新基金"] else platform_name,
             "name":"","ticker":"","fund_code":"",
             "fund_pattern":"yp010001" if platform_name in ["基富通","渣打基金","台新基金"] else "",
             "currency":"TWD" if platform_name in ["台股","基富通"] else "USD",
             "units":0.0,"avg_cost":0.0,"monthly_dividend_per_unit":0.0,"note":""}
    base = pd.concat([base, pd.DataFrame([blank])], ignore_index=True)
    edited = st.data_editor(
        base, use_container_width=True, hide_index=True, height=300, num_rows="dynamic",
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "platform": st.column_config.SelectboxColumn("平台", options=PLATFORMS, required=True),
            "asset_type": st.column_config.SelectboxColumn("類型", options=ASSET_TYPES, required=True),
            "currency": st.column_config.SelectboxColumn("幣別", options=CURRENCIES, required=True),
            "units": st.column_config.NumberColumn("單位數/股數", min_value=0, step=1.0, format="%.4f"),
            "avg_cost": st.column_config.NumberColumn("平均成本", min_value=0, step=0.01, format="%.4f"),
            "monthly_dividend_per_unit": st.column_config.NumberColumn("每單位月配息", min_value=0, step=0.0001, format="%.4f"),
        }, key=ekey,
    )
    c1, c2, c3 = st.columns([1,1,2])
    if c1.button("💾 儲存", key=f"sv_{ekey}"):
        update_positions(edited); st.success("已儲存"); st.rerun()
    cp = c2.number_input("複製 ID", value=0, step=1, key=f"cp_{ekey}")
    if c2.button("📋", key=f"cpb_{ekey}") and cp:
        row = current[current["id"]==int(cp)]
        if not row.empty:
            r = row.iloc[0].to_dict(); r.pop("id",None)
            r["name"] = str(r.get("name","")) + "（複製）"
            add_position(r); st.success("已複製"); st.rerun()
    dl = c3.number_input("刪除 ID", value=0, step=1, key=f"dl_{ekey}")
    if c3.button("🗑️ 刪除", key=f"dlb_{ekey}") and dl:
        delete_position(int(dl)); st.success(f"已刪除 {dl}"); st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# APP
# ════════════════════════════════════════════════════════════════════════════

# ── 頂部導覽列 ──
st.markdown(f"""
<div class="j-topbar">
  <div class="j-logo">◈</div>
  <div>
    <div class="j-app-name">Jenny 投資系統</div>
    <div class="j-app-sub">即時市值 · Supabase</div>
  </div>
  <div class="j-spacer"></div>
  <div class="j-ver-tag">{APP_VERSION}</div>
</div>
""", unsafe_allow_html=True)

# ── 初始化 ──
try:
    seed_presets()
except Exception as e:
    st.error(f"Supabase 初始化失敗：{e}"); st.stop()

positions = load_positions()

# ── 工具列（排序 + 更新，同一排）──
tb1, tb2, tb3 = st.columns([1, 3, 1])
with tb1:
    st.markdown('<div style="padding:8px 0 0 0;font-size:10px;font-weight:700;color:#7b9188;text-transform:uppercase;letter-spacing:1px;">排序方式</div>', unsafe_allow_html=True)
with tb2:
    sort_key = st.selectbox("排序", list(SORT_OPTIONS.keys()), index=3, label_visibility="collapsed")
with tb3:
    if st.button("🔄 更新即時價格", use_container_width=True):
        st.cache_data.clear(); st.rerun()

# ── 計算 ──
with st.spinner("抓取即時價格…"):
    enriched = enrich(positions)

def safe_sum(col): return to_float(enriched[col].sum()) if not enriched.empty and col in enriched.columns else 0

tv   = safe_sum("台幣市值_raw")
tc   = safe_sum("台幣成本")   # tc 是字串了，改用 _raw
# 重新用 raw 計算 total
if not enriched.empty:
    tv   = float(enriched["台幣市值_raw"].fillna(0).sum())
    tc_r = enriched.get("台幣成本", pd.Series(dtype=float))
    # avg_cost * units * fx = twd_cost, 沒有 raw 版，從字串反算
    # 直接用 損益_raw + 台幣市值_raw 推
    pnl_r= float(enriched["損益_raw"].fillna(0).sum())
    tc   = tv - pnl_r if tv and pnl_r else 0
    div_r= float(enriched["每月配息_raw"].fillna(0).sum())
    rate_r = pnl_r / tc if tc else None
else:
    tv = tc = pnl_r = div_r = 0; rate_r = None

delta_cls = "pos" if pnl_r >= 0 else "neg"

# ── 指標列 ──
st.markdown(f"""
<div class="j-kpi-bar">
  <div class="j-kpi">
    <div class="j-kpi-label">總台幣市值</div>
    <div class="j-kpi-val">{money(tv)}</div>
    <div class="j-kpi-sub {delta_cls}">{signed_money(pnl_r)}&nbsp;·&nbsp;{pct(rate_r,True)}</div>
  </div>
  <div class="j-kpi">
    <div class="j-kpi-label">總台幣成本</div>
    <div class="j-kpi-val">{money(tc)}</div>
    <div class="j-kpi-sub">投入成本</div>
  </div>
  <div class="j-kpi">
    <div class="j-kpi-label">每月配息</div>
    <div class="j-kpi-val">{money(div_r)}</div>
    <div class="j-kpi-sub">台幣 / 月</div>
  </div>
  <div class="j-kpi">
    <div class="j-kpi-label">持倉產品</div>
    <div class="j-kpi-val">{len(positions):,}</div>
    <div class="j-kpi-sub">筆</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Tabs ──
tabs = st.tabs(["◈ 總覽","📈 台股","🇺🇸 美股","🟧 基富通","💹 渣打基金","🟥 台新基金","💱 匯率","📡 基金市值","✏️ 編輯"])

def show_platform_df(view: pd.DataFrame, sort_k: str) -> None:
    """排序後顯示明細表"""
    if view.empty:
        st.info("尚無資料"); return
    sv = sort_df(view, sort_k)
    valid = [c for c in SHOW if c in sv.columns]
    st.dataframe(sv[valid], use_container_width=True, hide_index=True, height=380)

# ── TAB 0 總覽 ──
with tabs[0]:
    st.markdown('<div class="j-pg-title">資產配置總覽</div>', unsafe_allow_html=True)
    st.markdown('<div class="j-pg-sub">所有平台即時計算結果</div>', unsafe_allow_html=True)
    if not enriched.empty:
        summary = enriched.groupby("platform", dropna=False).agg(
            台幣市值=("台幣市值_raw","sum"),
            損益=("損益_raw","sum"),
            每月配息=("每月配息_raw","sum"),
            筆數=("id","count"),
        ).reset_index()
        summary.insert(2,"台幣成本", summary["台幣市值"] - summary["損益"])
        summary["損益率"] = summary.apply(
            lambda r: r["損益"]/r["台幣成本"] if r["台幣成本"] else None, axis=1)

        left, right = st.columns([1, 1.6])
        with left:
            st.markdown('<div class="j-card"><div class="j-card-title">平台市值分布</div>', unsafe_allow_html=True)
            chart = summary.set_index("platform")[["台幣市值"]]
            st.bar_chart(chart, height=260, color="#10b981")
            st.markdown("</div>", unsafe_allow_html=True)
        with right:
            st.markdown('<div class="j-card"><div class="j-card-title">平台彙總</div>', unsafe_allow_html=True)
            disp = summary.copy()
            for c in ["台幣市值","台幣成本","損益","每月配息"]:
                if c == "損益": disp[c] = disp[c].apply(signed_money)
                else: disp[c] = disp[c].apply(money)
            disp["損益率"] = disp["損益率"].apply(lambda x: pct(x, True))
            st.dataframe(disp, use_container_width=True, hide_index=True, height=260)
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="j-card"><div class="j-card-title">全部持倉明細</div>', unsafe_allow_html=True)
        show_platform_df(enriched, sort_key)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("尚無持倉資料，請到「✏️ 編輯」頁新增。")

# ── TAB 1-5 各平台 ──
for idx, platform in enumerate(PLATFORMS, start=1):
    with tabs[idx]:
        st.markdown(f'<div class="j-pg-title">{platform}</div>', unsafe_allow_html=True)
        view = enriched[enriched["platform"] == platform].copy() if not enriched.empty else pd.DataFrame()

        if not view.empty:
            pv  = float(view["台幣市值_raw"].fillna(0).sum())
            pp  = float(view["損益_raw"].fillna(0).sum())
            pd_ = float(view["每月配息_raw"].fillna(0).sum())
            pc  = pv - pp
            pr  = pp / pc if pc else None
            m1,m2,m3,m4 = st.columns(4)
            m1.metric("台幣市值", money(pv))
            m2.metric("台幣成本", money(pc))
            m3.metric("損益", signed_money(pp), delta=pct(pr, True))
            m4.metric("每月配息", money(pd_))

        st.markdown('<div class="j-card"><div class="j-card-title">即時計算結果</div>', unsafe_allow_html=True)
        show_platform_df(view, sort_key)
        st.markdown("</div>", unsafe_allow_html=True)

        editable_table(platform, positions, f"ed_{platform}")

# ── TAB 6 匯率 ──
with tabs[6]:
    st.markdown('<div class="j-pg-title">即時匯率</div>', unsafe_allow_html=True)
    st.markdown('<div class="j-pg-sub">Yahoo Finance · 5 分鐘快取</div>', unsafe_allow_html=True)
    fc = st.columns(len(CURRENCIES))
    for i, cur in enumerate(CURRENCIES):
        rate, status = fetch_fx(cur)
        fc[i].metric(f"1 {cur} → TWD", money(rate, 4),
                     delta="即時 ✓" if status == "ok" else f"⚠ {status}")

# ── TAB 7 基金市值 ──
with tabs[7]:
    st.markdown('<div class="j-pg-title">基金最新淨值</div>', unsafe_allow_html=True)
    st.markdown('<div class="j-pg-sub">MoneyDJ 即時 NAV · 自動換算台幣 · 5 分鐘快取</div>', unsafe_allow_html=True)

    prog = st.progress(0, text="抓取中…")
    fx_c: dict = {}
    fund_rows = []
    codes = list(FUND_PRESETS.items())
    for i, (code,(name,pattern,currency,platform)) in enumerate(codes):
        nav, ns = fetch_fund_nav(code, pattern)
        if currency not in fx_c: fx_c[currency] = fetch_fx(currency)
        fx, fxs = fx_c[currency]
        twd = nav * fx if nav is not None and fx else None
        fund_rows.append({
            "平台":platform,"基金名稱":name,"代號":code,"幣別":currency,
            "最新淨值":money(nav,4),"匯率":money(fx,4),"台幣換算":money(twd,2),
            "狀態":"✓" if ns=="ok" and fxs=="ok" else f"⚠{ns}",
            "_twd": twd or 0,
        })
        prog.progress((i+1)/len(codes), text=f"{i+1}/{len(codes)}  {name[:14]}")
    prog.empty()

    fund_df = pd.DataFrame(fund_rows)

    # 平台分組卡片
    for plat in ["基富通","渣打基金","台新基金"]:
        pf = fund_df[fund_df["平台"]==plat]
        if pf.empty: continue
        ptwd = pf["_twd"].sum()
        st.markdown(f'<div class="j-card"><div class="j-card-title">{plat} — 台幣換算合計 {money(ptwd,2)}</div>', unsafe_allow_html=True)
        dcols = ["基金名稱","代號","幣別","最新淨值","匯率","台幣換算","狀態"]
        st.dataframe(pf[dcols], use_container_width=True, hide_index=True, height=min(200, 60+40*len(pf)))
        st.markdown("</div>", unsafe_allow_html=True)

    # 全部合計
    all_twd = fund_df["_twd"].sum()
    st.metric("全部基金台幣淨值合計（1單位基準）", money(all_twd, 2))

    if not HAS_BS4:
        st.warning("請安裝 beautifulsoup4 與 lxml：`pip install beautifulsoup4 lxml`")

# ── TAB 8 編輯 ──
with tabs[8]:
    st.markdown('<div class="j-pg-title">新增 / 編輯持倉</div>', unsafe_allow_html=True)
    st.markdown('<div class="j-pg-sub">在此輸入單位數、成本、代碼等。各平台頁是即時計算結果。</div>', unsafe_allow_html=True)

    with st.expander("➕ 快速新增單筆", expanded=False):
        with st.form("add_one", clear_on_submit=True):
            c1,c2,c3 = st.columns(3)
            pl_ = c1.selectbox("平台", PLATFORMS)
            at_ = c2.selectbox("類型", ASSET_TYPES)
            cu_ = c3.selectbox("幣別", CURRENCIES)
            nm_ = st.text_input("產品名稱")
            c4,c5,c6 = st.columns(3)
            tk_  = c4.text_input("股票代碼（例：1476.TW）")
            fcd_ = c5.text_input("基金代號（例：acft94）")
            fpt_ = c6.text_input("基金 pattern")
            c7,c8,c9 = st.columns(3)
            un_ = c7.number_input("單位數/股數", value=0.0, step=1.0)
            ac_ = c8.number_input("平均成本（原幣）", value=0.0, step=0.01)
            md_ = c9.number_input("每單位月配息", value=0.0, step=0.0001, format="%.4f")
            nt_ = st.text_input("備註")
            if st.form_submit_button("新增"):
                if not nm_: st.error("請輸入產品名稱")
                else:
                    add_position({"platform":pl_,"asset_type":at_,"name":nm_,"ticker":tk_,
                                  "fund_code":fcd_,"fund_pattern":fpt_,"currency":cu_,
                                  "units":un_,"avg_cost":ac_,"monthly_dividend_per_unit":md_,"note":nt_})
                    st.success("已新增"); st.rerun()

    st.markdown("**全部持倉管理表**")
    c_ = ["id","platform","asset_type","name","ticker","fund_code","fund_pattern",
          "currency","units","avg_cost","monthly_dividend_per_unit","note"]
    base_ = positions[c_].copy() if not positions.empty else pd.DataFrame(columns=c_)
    edited_ = st.data_editor(
        base_, use_container_width=True, hide_index=True, height=520, num_rows="dynamic",
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "platform": st.column_config.SelectboxColumn("平台", options=PLATFORMS, required=True),
            "asset_type": st.column_config.SelectboxColumn("類型", options=ASSET_TYPES, required=True),
            "currency": st.column_config.SelectboxColumn("幣別", options=CURRENCIES, required=True),
            "units": st.column_config.NumberColumn("單位數/股數", min_value=0, step=1.0, format="%.4f"),
            "avg_cost": st.column_config.NumberColumn("平均成本", min_value=0, step=0.01, format="%.4f"),
            "monthly_dividend_per_unit": st.column_config.NumberColumn("每單位月配息", min_value=0, step=0.0001, format="%.4f"),
        }, key="ed_all",
    )
    ca,cb,cc = st.columns([1,1,2])
    if ca.button("💾 儲存"):
        update_positions(edited_); st.success("已儲存"); st.rerun()
    cp2 = cb.number_input("複製 ID", value=0, step=1, key="cp2")
    if cb.button("📋 複製", key="cpb2") and cp2:
        row = positions[positions["id"]==int(cp2)]
        if not row.empty:
            r=row.iloc[0].to_dict(); r.pop("id",None)
            r["name"]=str(r.get("name",""))+"（複製）"
            add_position(r); st.success("已複製"); st.rerun()
    dl2 = cc.number_input("刪除 ID", value=0, step=1, key="dl2")
    if cc.button("🗑️ 刪除", key="dlb2") and dl2:
        delete_position(int(dl2)); st.success(f"已刪除 {dl2}"); st.rerun()
