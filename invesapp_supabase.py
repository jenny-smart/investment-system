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


APP_VERSION = "2026-05-17-supabase-v2-platform-edit"

DEFAULT_SUPABASE_URL = "https://qrvdztqyzxlsfskdgiqp.supabase.co"

PLATFORMS = ["台股", "美股", "基富通", "渣打基金", "台新基金"]
ASSET_TYPES = ["台股", "美股", "基金"]
CURRENCIES = ["TWD", "USD", "CNY", "JPY", "ZAR"]
FX_PAIRS = {"TWD": None, "USD": "USDTWD=X", "CNY": "CNYTWD=X", "JPY": "JPYTWD=X", "ZAR": "ZARTWD=X"}

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
    "shzx0":   ("貝萊德全球智慧數據股票入息A6日圓", "yp010001", "JPY", "基富通"),
    "TLZO3":   ("安聯收益成長AMgi月收（日圓避險）", "yp010001", "JPY", "基富通"),
    "acob36":  ("大華銀新加坡房地產收益基金-美元月配", "yp010000", "USD", "渣打基金"),
    "pizn8":   ("東方匯理新興市場債券A美元（月配）", "yp010001", "USD", "渣打基金"),
    "pizo1":   ("東方匯理新興市場債券U美元（月配）", "yp010001", "USD", "渣打基金"),
    "pizm9":   ("東方匯理新興市場債券U南非幣（月配）", "yp010001", "ZAR", "台新基金"),
    "anzb6":   ("高盛新興市場債券Y股美元", "yp010001", "USD", "渣打基金"),
    "ANZH2":   ("高盛新興市場債券Y南非幣對沖（月配）", "yp010001", "ZAR", "台新基金"),
}


st.set_page_config(page_title="Jenny 投資系統 Supabase", page_icon="📈", layout="wide")

st.markdown("""
<style>
.stApp { background:#f7faf9; color:#0f2b20; }
.block-container { padding-top:0.8rem; max-width:1600px; }
.fixed-top { position:sticky; top:0; z-index:999; background:#f7faf9; padding:8px 0 12px 0; border-bottom:1px solid #e4ece8; }
.hero { background:#fff; border:1px solid #e5eae8; border-radius:16px; padding:16px 20px; box-shadow:0 1px 6px rgba(0,0,0,.05); }
[data-testid="stMetric"] { background:#fff!important; border:1px solid #e5eae8!important; border-radius:14px!important; padding:18px 20px!important; box-shadow:0 1px 4px rgba(0,0,0,.04)!important; }
[data-testid="stDataFrame"] { background:#fff!important; border:1px solid #e5eae8!important; border-radius:14px!important; overflow:hidden!important; box-shadow:0 1px 4px rgba(0,0,0,.04)!important; }
.stButton > button { background:#10b981!important; color:#fff!important; border:0!important; border-radius:10px!important; font-weight:700!important; }
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
        st.error("缺少 SUPABASE_ANON_KEY。請到 Streamlit Cloud → Settings → Secrets 加入 SUPABASE_URL 與 SUPABASE_ANON_KEY。")
        st.stop()
    return create_client(url, key)


def load_positions() -> pd.DataFrame:
    sb = supabase_client()
    res = sb.table("positions").select("*").order("platform").order("id").execute()
    return pd.DataFrame(res.data or [])


def add_position(row: dict[str, Any]) -> None:
    sb = supabase_client()
    sb.table("positions").insert(row).execute()


def update_positions(df: pd.DataFrame) -> None:
    sb = supabase_client()
    for _, r in df.iterrows():
        rid = r.get("id", None)
        is_new = pd.isna(rid) or str(rid).strip() == ""

        payload = {
            "platform": str(r.get("platform", "台股") or "台股"),
            "asset_type": str(r.get("asset_type", "台股") or "台股"),
            "name": str(r.get("name", "") or "").strip(),
            "ticker": str(r.get("ticker", "") or "").strip(),
            "fund_code": str(r.get("fund_code", "") or "").strip(),
            "fund_pattern": str(r.get("fund_pattern", "") or "").strip(),
            "currency": str(r.get("currency", "TWD") or "TWD"),
            "units": float(r.get("units", 0) or 0),
            "avg_cost": float(r.get("avg_cost", 0) or 0),
            "monthly_dividend_per_unit": float(r.get("monthly_dividend_per_unit", 0) or 0),
            "note": str(r.get("note", "") or ""),
        }

        if not payload["name"] and not payload["ticker"] and not payload["fund_code"]:
            continue

        if is_new:
            sb.table("positions").insert(payload).execute()
        else:
            sb.table("positions").update(payload).eq("id", int(rid)).execute()


def delete_position(position_id: int) -> None:
    supabase_client().table("positions").delete().eq("id", int(position_id)).execute()


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
                    return float(cells[1].get_text(strip=True).replace(",", "")), "ok"
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
        units = float(r.get("units") or 0)
        avg_cost = float(r.get("avg_cost") or 0)

        if r.get("asset_type") in {"台股", "美股"}:
            price, p_status = fetch_yahoo_price(str(r.get("ticker") or ""))
        else:
            price, p_status = fetch_fund_nav(str(r.get("fund_code") or ""), str(r.get("fund_pattern") or ""))

        fx, fx_status = fetch_fx(currency)
        original_cost = units * avg_cost
        original_value = units * price if price is not None else None
        twd_cost = original_cost * fx if fx is not None else None
        twd_value = original_value * fx if original_value is not None and fx is not None else None
        pnl = twd_value - twd_cost if twd_value is not None and twd_cost is not None else None
        pnl_rate = pnl / twd_cost if pnl is not None and twd_cost else None
        monthly_div = units * float(r.get("monthly_dividend_per_unit") or 0)
        monthly_div_twd = monthly_div * fx if fx is not None else None

        out = dict(r)
        out.update({
            "即時價格/淨值": price,
            "匯率": fx,
            "台幣成本": twd_cost,
            "台幣市值": twd_value,
            "損益": pnl,
            "損益率": pnl_rate,
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
    for c in ["台幣成本", "台幣市值", "損益", "每月配息"]:
        if c in out:
            out[c] = out[c].apply(money)
    if "損益率" in out:
        out["損益率"] = out["損益率"].apply(pct)
    return out


def editable_platform_table(platform_name: str, current_positions: pd.DataFrame, editor_key: str) -> None:
    st.markdown("#### ✏️ 編輯 / 新增")
    st.caption("在這裡 key 單位數、平均成本、股票代碼或基金代號。新增列請拉到表格最下方直接輸入；按儲存後會寫入 Supabase。")

    cols = [
        "id", "platform", "asset_type", "name", "ticker", "fund_code", "fund_pattern",
        "currency", "units", "avg_cost", "monthly_dividend_per_unit", "note"
    ]

    base = current_positions[current_positions["platform"] == platform_name][cols].copy() if not current_positions.empty else pd.DataFrame(columns=cols)

    blank = {
        "id": None,
        "platform": platform_name,
        "asset_type": "基金" if platform_name in ["基富通", "渣打基金", "台新基金"] else platform_name,
        "name": "",
        "ticker": "",
        "fund_code": "",
        "fund_pattern": "yp010001" if platform_name in ["基富通", "渣打基金", "台新基金"] else "",
        "currency": "TWD" if platform_name in ["台股", "基富通"] else "USD",
        "units": 0.0,
        "avg_cost": 0.0,
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
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "platform": st.column_config.SelectboxColumn("平台", options=PLATFORMS, required=True),
            "asset_type": st.column_config.SelectboxColumn("類型", options=ASSET_TYPES, required=True),
            "currency": st.column_config.SelectboxColumn("幣別", options=CURRENCIES, required=True),
            "units": st.column_config.NumberColumn("單位數 / 股數", min_value=0, step=1.0, format="%.4f"),
            "avg_cost": st.column_config.NumberColumn("平均成本（原幣）", min_value=0, step=0.01, format="%.4f"),
            "monthly_dividend_per_unit": st.column_config.NumberColumn("每單位月配息", min_value=0, step=0.0001, format="%.4f"),
            "ticker": st.column_config.TextColumn("股票代碼"),
            "fund_code": st.column_config.TextColumn("基金代號"),
            "fund_pattern": st.column_config.TextColumn("基金 pattern"),
            "name": st.column_config.TextColumn("產品名稱"),
            "note": st.column_config.TextColumn("備註"),
        },
        key=editor_key,
    )

    c1, c2, c3 = st.columns([1, 1, 2])
    if c1.button("💾 儲存此頁變更", key=f"save_{editor_key}"):
        update_positions(edited)
        st.success("已儲存")
        st.rerun()

    copy_id = c2.number_input("複製 ID", value=0, step=1, key=f"copy_{editor_key}")
    if c2.button("📋 複製", key=f"copybtn_{editor_key}") and copy_id:
        row = current_positions[current_positions["id"] == int(copy_id)]
        if row.empty:
            st.error("找不到此 ID")
        else:
            r = row.iloc[0].to_dict()
            r.pop("id", None)
            r["name"] = str(r.get("name", "")) + "（複製）"
            add_position(r)
            st.success("已複製")
            st.rerun()

    delete_id = c3.number_input("刪除 ID", value=0, step=1, key=f"delete_{editor_key}")
    if c3.button("🗑️ 刪除", key=f"deletebtn_{editor_key}") and delete_id:
        delete_position(int(delete_id))
        st.success(f"已刪除 ID {delete_id}")
        st.rerun()


def seed_presets() -> None:
    existing = load_positions()
    if not existing.empty:
        return

    for name, ticker in TW_PRESETS.items():
        add_position({
            "platform": "台股", "asset_type": "台股", "name": name, "ticker": ticker,
            "fund_code": "", "fund_pattern": "", "currency": "TWD", "units": 0,
            "avg_cost": 0, "monthly_dividend_per_unit": 0, "note": "預設台股清單",
        })

    for ticker, name in [("PYPL", "PayPal"), ("XYZ", "Block / XYZ")]:
        add_position({
            "platform": "美股", "asset_type": "美股", "name": name, "ticker": ticker,
            "fund_code": "", "fund_pattern": "", "currency": "USD", "units": 0,
            "avg_cost": 0, "monthly_dividend_per_unit": 0, "note": "預設美股清單",
        })

    for code, (name, pattern, currency, platform) in FUND_PRESETS.items():
        add_position({
            "platform": platform, "asset_type": "基金", "name": name, "ticker": "",
            "fund_code": code, "fund_pattern": pattern, "currency": currency, "units": 0,
            "avg_cost": 0, "monthly_dividend_per_unit": 0, "note": "預設基金清單",
        })


st.title("📈 Jenny 投資即時市值系統")
st.caption(f"版本：{APP_VERSION}｜Supabase 永久資料庫")

try:
    seed_presets()
except Exception as e:
    st.error(f"Supabase 初始化失敗：{e}")
    st.stop()

positions = load_positions()
enriched = enrich(positions)

total_value = enriched["台幣市值"].dropna().sum() if not enriched.empty else 0
total_cost = enriched["台幣成本"].dropna().sum() if not enriched.empty else 0
total_pnl = enriched["損益"].dropna().sum() if not enriched.empty else 0
total_div = enriched["每月配息"].dropna().sum() if not enriched.empty else 0
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

tabs = st.tabs(["總覽", "台股", "美股", "基富通", "渣打基金", "台新基金", "匯率", "新增 / 編輯"])

show_cols = [
    "id", "platform", "asset_type", "name", "ticker", "fund_code", "currency",
    "units", "avg_cost", "即時價格/淨值", "匯率", "台幣成本", "台幣市值", "損益", "損益率", "每月配息", "狀態"
]

with tabs[0]:
    st.subheader("資產配置")
    if not enriched.empty:
        summary = enriched.groupby("platform", dropna=False).agg(
            台幣成本=("台幣成本", "sum"),
            台幣市值=("台幣市值", "sum"),
            損益=("損益", "sum"),
            每月配息=("每月配息", "sum"),
            筆數=("id", "count"),
        ).reset_index()
        summary["損益率"] = summary.apply(lambda r: r["損益"] / r["台幣成本"] if r["台幣成本"] else None, axis=1)
        left, right = st.columns([1, 1.7])
        with left:
            st.bar_chart(summary.set_index("platform")[["台幣市值"]], height=330)
        with right:
            st.dataframe(format_df(summary), use_container_width=True, hide_index=True, height=330)
        st.subheader("全部投資產品")
        st.dataframe(format_df(enriched[show_cols]), use_container_width=True, hide_index=True, height=520)

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
            st.caption("此表為即時計算結果，不在這裡 key。市值 = 單位數 × 即時價格/淨值 × 匯率。")
            st.dataframe(format_df(view[show_cols]), use_container_width=True, hide_index=True, height=330)

        editable_platform_table(platform, positions, f"editor_{platform}")

with tabs[6]:
    st.subheader("匯率")
    rows = []
    for cur in CURRENCIES:
        rate, status = fetch_fx(cur)
        rows.append({"幣別": cur, "對台幣匯率": money(rate, 4), "狀態": "✓" if status == "ok" else f"⚠ {status}"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with tabs[7]:
    st.subheader("新增 / 編輯投資產品")
    st.info("請在這裡 key 資料：單位數、平均成本、每單位月配息、股票代碼或基金代號。上面各平台頁是即時計算結果，不能直接編輯。")

    with st.expander("➕ 新增單筆投資產品", expanded=True):
        with st.form("add", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            platform = c1.selectbox("平台", PLATFORMS)
            asset_type = c2.selectbox("類型", ASSET_TYPES)
            currency = c3.selectbox("幣別", CURRENCIES)

            name = st.text_input("產品名稱")
            c4, c5, c6 = st.columns(3)
            ticker = c4.text_input("股票 Yahoo 代碼（台股例：1476.TW，美股例：PYPL）")
            fund_code = c5.text_input("基金 MoneyDJ 代號（例：acft94）")
            fund_pattern = c6.text_input("基金 pattern（yp010000 或 yp010001）")

            c7, c8, c9 = st.columns(3)
            units = c7.number_input("單位數 / 股數", value=0.0, step=1.0)
            avg_cost = c8.number_input("平均成本（原幣）", value=0.0, step=0.01)
            md = c9.number_input("每單位月配息（原幣）", value=0.0, step=0.0001, format="%.4f")

            note = st.text_input("備註")
            submitted = st.form_submit_button("新增")

        if submitted:
            if not name:
                st.error("請輸入產品名稱")
            else:
                add_position({
                    "platform": platform, "asset_type": asset_type, "name": name,
                    "ticker": ticker, "fund_code": fund_code, "fund_pattern": fund_pattern,
                    "currency": currency, "units": units, "avg_cost": avg_cost,
                    "monthly_dividend_per_unit": md, "note": note,
                })
                st.success("已新增")
                st.rerun()

    cols = ["id", "platform", "asset_type", "name", "ticker", "fund_code", "fund_pattern", "currency", "units", "avg_cost", "monthly_dividend_per_unit", "note"]
    base = positions[cols].copy() if not positions.empty else pd.DataFrame(columns=cols)

    edited = st.data_editor(
        base,
        use_container_width=True,
        hide_index=True,
        height=560,
        num_rows="dynamic",
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "platform": st.column_config.SelectboxColumn("平台", options=PLATFORMS, required=True),
            "asset_type": st.column_config.SelectboxColumn("類型", options=ASSET_TYPES, required=True),
            "currency": st.column_config.SelectboxColumn("幣別", options=CURRENCIES, required=True),
            "units": st.column_config.NumberColumn("單位數 / 股數", min_value=0, step=1.0, format="%.4f"),
            "avg_cost": st.column_config.NumberColumn("平均成本（原幣）", min_value=0, step=0.01, format="%.4f"),
            "monthly_dividend_per_unit": st.column_config.NumberColumn("每單位月配息", min_value=0, step=0.0001, format="%.4f"),
        },
        key="editor",
    )

    c10, c11, c12 = st.columns([1, 1, 2])
    if c10.button("💾 儲存表格變更"):
        update_positions(edited)
        st.success("已儲存")
        st.rerun()

    copy_id = c11.number_input("複製 ID", value=0, step=1)
    if c11.button("📋 複製此 ID") and copy_id:
        row = positions[positions["id"] == int(copy_id)]
        if row.empty:
            st.error("找不到此 ID")
        else:
            r = row.iloc[0].to_dict()
            r.pop("id", None)
            r["name"] = str(r.get("name", "")) + "（複製）"
            add_position(r)
            st.success("已複製")
            st.rerun()

    pid = c12.number_input("刪除 ID", value=0, step=1)
    if c12.button("🗑️ 刪除指定 ID") and pid:
        delete_position(int(pid))
        st.success(f"已刪除 ID {pid}")
        st.rerun()
