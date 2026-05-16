from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


# =============================================================================
# CONFIG
# =============================================================================
APP_VERSION = "2026-05-16-v4-visual-overview"

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

PRIMARY_SPREADSHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"
MARKET_SPREADSHEET_ID = "17HPytZKOPR_9Od_wor-xEx9kpccJlPS2v6B0Dz6MRYc"

PRIMARY_LOCAL = PROJECT_DIR / "inputs" / "investment-system-source.xlsx"
MARKET_LOCAL = PROJECT_DIR / "inputs" / "market-value-source.xlsx"
SUMMARY_JSON = PROJECT_DIR / "outputs" / "workbook_structure_summary.json"
LOCAL_RECORDS_DIR = PROJECT_DIR / "data"

MARKET_SHEETS = [
    "總覽", "台股", "「台股」的副本", "渣打-美股",
    "基富通-台", "基富通-人民幣", "基富通-日幣",
    "渣打-美金", "渣打-南非", "台新-美金", "台新-南非",
]

DETAIL_GROUPS = {
    "台股": ["台股", "「台股」的副本"],
    "基富通": ["基富通-台", "基富通-人民幣", "基富通-日幣"],
    "渣打美股": ["渣打-美股"],
    "渣打基金": ["渣打-美金", "渣打-南非"],
    "台新基金": ["台新-美金", "台新-南非"],
    "其他投資": [],
}

LABEL_ALIASES = {
    "總資產": ["加總Total", "總資產", "總資產total", "總資產總額"],
    "台股": ["台股total", "台股Total", "台股"],
    "銀行": ["銀行total", "銀行Total", "銀行"],
    "保險": ["保險total", "保險Total", "保險"],
    "UNCLE 待還": ["uncle待還", "Uncle待還", "UNCLE待還", "待還"],
    "基富通": ["基富通total", "基富通Total", "基富通", "基金（基富通）", "基金(基富通)"],
    "渣打美股": ["渣打美股total", "渣打-美股total", "渣打-美股", "渣打美股", "美股（渣打）", "美股(渣打)"],
    "渣打基金": ["渣打基金total", "渣打基金Total", "渣打基金", "渣打-基金", "基金（渣打）", "基金(渣打)"],
    "台新基金": ["台新基金total", "台新基金Total", "台新基金", "台新-基金", "基金（台新）", "基金(台新)"],
    "其他投資": ["其他投資total", "其他投資Total", "其他投資"],
}

FUND_CONFIG = [
    {"code": "acft94", "pattern": "yp010000", "currency": "TWD", "name": "富蘭克林華美新興國家固定收益B-新臺幣"},
    {"code": "acai222", "pattern": "yp010000", "currency": "TWD", "name": "柏瑞新興邊境非投資等級債券B類型"},
    {"code": "acft99", "pattern": "yp010000", "currency": "CNY", "name": "富蘭克林華美新興國家固定收益B-人民幣"},
    {"code": "acob36", "pattern": "yp010000", "currency": "USD", "name": "大華銀新加坡房地產收益-美元月配"},
    {"code": "shzx0", "pattern": "yp010001", "currency": "JPY", "name": "貝萊德全球智慧數據股票入息A6日圓"},
    {"code": "TLZO3", "pattern": "yp010001", "currency": "JPY", "name": "安聯收益成長AMgi月收（日圓避險）"},
    {"code": "pizn8", "pattern": "yp010001", "currency": "USD", "name": "東方匯理新興市場債券A美元（月配）"},
    {"code": "pizo1", "pattern": "yp010001", "currency": "USD", "name": "東方匯理新興市場債券U美元（月配）"},
    {"code": "pizm9", "pattern": "yp010001", "currency": "ZAR", "name": "東方匯理新興市場債券U南非幣（月配）"},
    {"code": "anzb6", "pattern": "yp010001", "currency": "USD", "name": "高盛新興市場債券Y股美元"},
    {"code": "ANZH2", "pattern": "yp010001", "currency": "ZAR", "name": "高盛新興市場債券Y（南非幣對沖）"},
]

STOCK_CONFIG = [
    {"ticker": "PYPL", "name": "PayPal", "currency": "USD"},
    {"ticker": "XYZ", "name": "XYZ", "currency": "USD"},
]

FX_PAIRS = {"USD": "USDTWD=X", "CNY": "CNYTWD=X", "JPY": "JPYTWD=X", "ZAR": "ZARTWD=X"}


# =============================================================================
# PAGE + CSS
# =============================================================================
st.set_page_config(
    page_title="Jenny All｜投資系統",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
[data-testid="stSidebar"], [data-testid="collapsedControl"], section[data-testid="stSidebarNav"], button[kind="header"] {
    display: none !important;
}
html, body, [class*="css"] {
    font-family: "PingFang TC", "Noto Sans TC", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
}
.stApp { background: #f7faf9 !important; color: #0f2b20 !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }

.j-topbar {
    background: #ffffff; border-bottom: 1px solid #e5eae8; padding: 10px 32px;
    display: flex; align-items: center; gap: 24px; box-shadow: 0 1px 4px rgba(0,0,0,.05);
    position: sticky; top: 0; z-index: 999; min-height: 72px;
}
.j-source-pill, .j-brand-pill {
    background: #ffffff; border: 1px solid #dfe9e5; border-radius: 10px; padding: 8px 18px;
    box-shadow: 0 1px 5px rgba(0,0,0,.04); display: flex; align-items: center; gap: 9px;
    color: #0f2b20; font-size: 15px; font-weight: 700; min-width: 136px; justify-content: center;
}
.j-source-pill.active { border-color: #10b981; color: #047857; }
.j-logo { width: 28px; height: 28px; border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; font-weight: 900; color: #fff; }
.logo-g { background: #ff7a00; }
.logo-sc { background: linear-gradient(135deg, #0968b1, #30b36b); }
.logo-ts { background: #d70819; }
.logo-sheet { background: #10b981; }
.logo-refresh { background: #10b981; }

.j-tabmeta {
    display: flex; justify-content: flex-end; align-items: center;
    color: #7b9188; font-size: 12px; margin-bottom: 8px;
}

.stTabs [data-baseweb="tab-list"] {
    background: #ffffff; border-bottom: 2px solid #e5eae8; padding: 0 28px; gap: 0;
    box-shadow: 0 1px 3px rgba(0,0,0,.04);
}
.stTabs [data-baseweb="tab"] {
    color: #6b8a7a !important; font-size: 13.5px !important; font-weight: 500 !important;
    padding: 13px 20px !important; border-bottom: 3px solid transparent !important; background: transparent !important;
}
.stTabs [aria-selected="true"] { color: #047857 !important; border-bottom-color: #10b981 !important; font-weight: 700 !important; }
.stTabs [data-baseweb="tab-panel"] { background: #f7faf9; padding: 28px 32px; }

[data-testid="stMetric"] {
    background: #ffffff !important; border: 1px solid #e5eae8 !important; border-radius: 12px !important;
    padding: 18px 22px !important; box-shadow: 0 1px 4px rgba(0,0,0,.04) !important; min-height: 118px;
}
[data-testid="stMetricLabel"] p {
    font-size: 12px !important; font-weight: 700 !important; color: #7c968c !important;
}
[data-testid="stMetricValue"] { font-size: 24px !important; font-weight: 800 !important; color: #0f2b20 !important; }
[data-testid="stMetricDelta"] { font-size: 12px !important; }

[data-testid="stDataFrame"] {
    border: 1px solid #e5eae8 !important; border-radius: 12px !important; overflow: hidden !important;
    box-shadow: 0 1px 4px rgba(0,0,0,.04) !important; background: #ffffff !important;
}
.dvn-scroller { background: #ffffff !important; }

[data-baseweb="select"] > div {
    background: #ffffff !important; border-color: #e5eae8 !important; border-radius: 8px !important;
    color: #0f2b20 !important; font-size: 13px !important;
}
[data-testid="stRadio"] fieldset { border: none !important; }
[data-testid="stRadio"] > div { flex-direction: row !important; flex-wrap: wrap !important; gap: 8px !important; }
[data-testid="stRadio"] label {
    background: #f0f5f3 !important; border: 1.5px solid #d5e3de !important; border-radius: 8px !important;
    padding: 6px 14px !important; font-size: 12.5px !important; font-weight: 500 !important;
    color: #4a7264 !important; cursor: pointer !important; white-space: nowrap !important;
}
[data-testid="stRadio"] label:has(input:checked) {
    background: #ecfdf5 !important; border-color: #10b981 !important; color: #047857 !important; font-weight: 600 !important;
}
.stButton > button {
    background: #10b981 !important; color: #fff !important; border: none !important; border-radius: 8px !important;
    font-weight: 600 !important; font-size: 13px !important; padding: 7px 18px !important;
    box-shadow: 0 2px 6px rgba(16,185,129,.25) !important;
}
.stButton > button:hover { background: #047857 !important; }

.j-card {
    background: #ffffff; border: 1px solid #e5eae8; border-radius: 14px; padding: 22px 24px;
    margin-bottom: 18px; box-shadow: 0 1px 4px rgba(0,0,0,.04);
}
.j-card-title {
    font-size: 15px; font-weight: 800; color: #10b981; margin-bottom: 14px; padding-bottom: 10px;
    border-bottom: 1px solid #f0f5f3;
}
.j-page-title { font-size: 24px; font-weight: 800; color: #0f2b20; margin-bottom: 3px; }
.j-page-sub { font-size: 13px; color: #8fa89e; margin-bottom: 22px; }
.small-note { font-size: 12px; color: #6b8a7a; margin-top: -6px; margin-bottom: 12px; }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# HELPERS
# =============================================================================
def google_export_url(sid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx"


@st.cache_data(ttl=600, show_spinner=False)
def download_xlsx(sid: str) -> bytes:
    r = requests.get(google_export_url(sid), timeout=60)
    r.raise_for_status()
    if b"<!DOCTYPE" in r.content[:200]:
        raise ValueError("Google Sheet 回傳 HTML（可能需要登入或尚未公開）")
    return r.content


@st.cache_data(ttl=600, show_spinner=False)
def load_local_xlsx(path: str) -> bytes:
    return Path(path).read_bytes()


@st.cache_data(ttl=600, show_spinner=False)
def read_sheet(xlsx_bytes: bytes, sheet_name: str) -> pd.DataFrame:
    return pd.read_excel(BytesIO(xlsx_bytes), sheet_name=sheet_name, header=None, engine="openpyxl")


def workbook_bytes(mode: str, which: str) -> bytes:
    if which == "primary":
        return load_local_xlsx(str(PRIMARY_LOCAL)) if mode == "本機快取" else download_xlsx(PRIMARY_SPREADSHEET_ID)
    return load_local_xlsx(str(MARKET_LOCAL)) if mode == "本機快取" else download_xlsx(MARKET_SPREADSHEET_ID)


def numeric(v: Any) -> float | None:
    try:
        if v is None or pd.isna(v):
            return None
        if isinstance(v, str):
            s = v.replace(",", "").replace("$", "").replace("NT", "").replace("TWD", "").replace("%", "").strip()
            if s in {"", "-", "—", "nan", "None"}:
                return None
            return float(s)
        return float(v)
    except Exception:
        return None


def money(v: Any) -> str:
    n = numeric(v)
    return "-" if n is None else f"{n:,.0f}"


def signed_money(v: Any) -> str:
    n = numeric(v)
    return "-" if n is None else f"{n:+,.0f}"


def ratio_str(v: Any) -> str:
    n = numeric(v)
    if n is None:
        return "-"
    return f"{n:.1f}%" if abs(n) > 1 else f"{n:.1%}"


def signed_ratio_str(v: Any) -> str:
    n = numeric(v)
    if n is None:
        return "-"
    return f"{n:+.1f}%" if abs(n) > 1 else f"{n:+.1%}"


def fmt_df(df: pd.DataFrame) -> pd.DataFrame:
    return df.fillna("").astype(str).replace({"nan": "", "None": "", "NaT": "", "NaN": ""})


def cleaned_table(df: pd.DataFrame, max_rows: int = 160, max_cols: int = 60) -> pd.DataFrame:
    t = df.dropna(how="all").dropna(axis=1, how="all")
    t = t.iloc[:max_rows, :max_cols].copy()
    t.columns = [str(c) for c in t.columns]
    return fmt_df(t)


def row_by_label(df: pd.DataFrame, label: str) -> pd.Series | None:
    if df.empty:
        return None
    labels = df.iloc[:, 0].astype(str).str.strip()
    found = df.loc[labels == label]
    return None if found.empty else found.iloc[0]


def find_value_by_keywords(df: pd.DataFrame, keywords: list[str], col: int = 1) -> float:
    if df.empty:
        return 0.0
    labels = df.iloc[:, 0].astype(str).str.replace(" ", "", regex=False).str.lower()
    for kw in [k.replace(" ", "").lower() for k in keywords]:
        matches = df.loc[labels.str.contains(kw, na=False)]
        for _, row in matches.iterrows():
            if len(row) > col:
                val = numeric(row.iloc[col])
                if val is not None:
                    return val
    return 0.0


def value_from_labels(df: pd.DataFrame, labels: list[str], col: int = 1) -> float:
    for label in labels:
        row = row_by_label(df, label)
        if row is not None and len(row) > col:
            val = numeric(row.iloc[col])
            if val is not None:
                return val
    return find_value_by_keywords(df, labels, col)


def find_col(columns: list[Any], candidates: list[str]) -> Any | None:
    normalized = [(str(c).replace(" ", "").lower(), c) for c in columns]
    for cand in candidates:
        cand_norm = cand.replace(" ", "").lower()
        for key, original in normalized:
            if cand_norm in key:
                return original
    return None


def first_existing(df: pd.DataFrame, candidates: list[str]) -> Any | None:
    return find_col(list(df.columns), candidates)


def infer_header_row(df: pd.DataFrame, max_scan: int = 15) -> int:
    header_words = ["名稱", "基金", "股票", "代號", "單位", "股數", "市值", "成本", "損益", "配息", "幣別", "淨值"]
    best_idx, best_score = 0, -1
    for i in range(min(max_scan, len(df))):
        vals = df.iloc[i].astype(str).tolist()
        score = sum(any(word in v for word in header_words) for v in vals)
        score += min(sum(v not in {"nan", "None", ""} for v in vals), 8) * 0.1
        if score > best_score:
            best_idx, best_score = i, score
    return best_idx


def sheet_as_table(df: pd.DataFrame, max_rows: int = 300) -> pd.DataFrame:
    if df.empty:
        return df
    h = infer_header_row(df)
    body = df.iloc[h + 1:max_rows].copy()
    header = df.iloc[h].fillna("").astype(str).tolist()
    body.columns = [x.strip() or f"欄位{i+1}" for i, x in enumerate(header)]
    return body.dropna(how="all").dropna(axis=1, how="all")


def sheet_total_from_raw(raw_df: pd.DataFrame) -> dict[str, float | None]:
    result = {"cost": None, "value": None, "profit": None, "monthly_dividend": None}

    tbl = sheet_as_table(raw_df)
    if not tbl.empty:
        cost_col = first_existing(tbl, ["台幣成本", "成本", "投資成本", "總成本"])
        value_col = first_existing(tbl, ["台幣市值", "總市值", "市值", "現值", "目前市值"])
        profit_col = first_existing(tbl, ["損益", "未實現損益", "台幣損益", "總損益"])
        div_col = first_existing(tbl, ["月配息", "每月配息", "台幣配息", "配息", "月收入"])

        for key, col in [("cost", cost_col), ("value", value_col), ("profit", profit_col), ("monthly_dividend", div_col)]:
            if col is not None:
                vals = pd.to_numeric(
                    tbl[col].astype(str).str.replace(",", "", regex=False).str.replace("$", "", regex=False).str.replace("%", "", regex=False),
                    errors="coerce",
                )
                total = vals.dropna().sum()
                if total != 0:
                    result[key] = float(total)

    # fallback: fund platform summary usually row 2: J cost, K value, M profit, O monthly dividend
    if len(raw_df) > 1:
        row = raw_df.iloc[1]
        fallback_map = {"cost": 9, "value": 10, "profit": 12, "monthly_dividend": 14}
        for key, idx in fallback_map.items():
            if result[key] is None and len(row) > idx:
                val = numeric(row.iloc[idx])
                if val is not None and val != 0:
                    result[key] = val

    return result


def aggregate_platform_from_sheets(market_bytes: bytes, platform: str) -> dict[str, float | None]:
    totals = {"cost": 0.0, "value": 0.0, "profit": 0.0, "monthly_dividend": 0.0}
    found_any = False

    for sheet_name in DETAIL_GROUPS.get(platform, []):
        try:
            raw = read_sheet(market_bytes, sheet_name)
            summary = sheet_total_from_raw(raw)
            if any(v is not None for v in summary.values()):
                found_any = True
            for key in totals:
                if summary.get(key) is not None:
                    totals[key] += float(summary[key])
        except Exception:
            continue

    if not found_any:
        return {"cost": None, "value": None, "profit": None, "profit_rate": None, "monthly_dividend": None}

    value = totals["value"] if totals["value"] != 0 else None
    cost = totals["cost"] if totals["cost"] != 0 else None
    profit = totals["profit"] if totals["profit"] != 0 else None
    if profit is None and value is not None and cost is not None:
        profit = value - cost
    rate = (profit / cost) if profit is not None and cost else None

    return {
        "cost": cost,
        "value": value,
        "profit": profit,
        "profit_rate": rate,
        "monthly_dividend": totals["monthly_dividend"] if totals["monthly_dividend"] != 0 else None,
    }


def build_overview_assets_from_all_sources(overview: pd.DataFrame, market_bytes: bytes) -> pd.DataFrame:
    ordered = ["台股", "銀行", "保險", "UNCLE 待還", "基富通", "渣打美股", "渣打基金", "台新基金", "其他投資"]
    rows = []

    for item in ordered:
        source = aggregate_platform_from_sheets(market_bytes, item)
        fallback_value = value_from_labels(overview, LABEL_ALIASES.get(item, [item]))
        value = source.get("value") if source.get("value") is not None else fallback_value
        profit = source.get("profit")
        rate = source.get("profit_rate")
        monthly_dividend = source.get("monthly_dividend")

        if item in {"銀行", "保險", "UNCLE 待還", "其他投資"}:
            value = fallback_value
            p = value_from_labels(overview, LABEL_ALIASES.get(item, [item]), col=2)
            r = value_from_labels(overview, LABEL_ALIASES.get(item, [item]), col=3)
            profit = p if p else None
            rate = r if r else (profit / value if profit and value else None)

        rows.append({
            "項目": item,
            "金額": float(value) if value else 0.0,
            "損益": profit,
            "損益率": rate,
            "目前每月配息": monthly_dividend,
        })

    df = pd.DataFrame(rows)
    total = float(df["金額"].sum()) if not df.empty else 0.0
    df["占比"] = df["金額"].apply(lambda x: x / total if total else None)
    return df


def normalize_investment_table(raw_df: pd.DataFrame, source_sheet: str, platform: str) -> pd.DataFrame:
    tbl = sheet_as_table(raw_df)
    if tbl.empty:
        return pd.DataFrame()

    name_col = first_existing(tbl, ["基金名稱", "股票名稱", "名稱", "標的", "投資標的", "商品名稱"])
    code_col = first_existing(tbl, ["代號", "股票代號", "基金代號", "ISIN", "MoneyDJ"])
    cur_col = first_existing(tbl, ["幣別", "貨幣", "currency"])
    unit_col = first_existing(tbl, ["單位數", "庫存", "股數", "持有股數", "持有單位", "單位"])
    nav_col = first_existing(tbl, ["最新淨值", "淨值", "現價", "市價", "收盤價", "價格"])
    cost_col = first_existing(tbl, ["台幣成本", "成本", "投資成本", "總成本"])
    value_col = first_existing(tbl, ["台幣市值", "總市值", "市值", "現值", "目前市值"])
    profit_col = first_existing(tbl, ["損益", "未實現損益", "台幣損益", "總損益"])
    profit_rate_col = first_existing(tbl, ["損益率", "報酬率", "投報率"])
    div_col = first_existing(tbl, ["月配息", "每月配息", "台幣配息", "配息", "月收入"])

    rows = []
    for _, r in tbl.iterrows():
        name = str(r.get(name_col, "")).strip() if name_col else ""
        code = str(r.get(code_col, "")).strip() if code_col else ""
        if not name and not code:
            continue
        if name in {"合計", "總計", "小計"} or "合計" in name or "總計" in name:
            continue

        cost = numeric(r.get(cost_col)) if cost_col else None
        val = numeric(r.get(value_col)) if value_col else None
        profit = numeric(r.get(profit_col)) if profit_col else None
        rate = numeric(r.get(profit_rate_col)) if profit_rate_col else None
        div = numeric(r.get(div_col)) if div_col else None
        if val is None and cost is None and profit is None and div is None:
            continue

        rows.append({
            "平台": platform,
            "來源表": source_sheet,
            "標的名稱": name,
            "代號": code,
            "幣別": str(r.get(cur_col, "")).strip() if cur_col else "",
            "單位/股數": r.get(unit_col, "") if unit_col else "",
            "最新淨值/市價": r.get(nav_col, "") if nav_col else "",
            "台幣成本": cost,
            "台幣市值": val,
            "損益": profit,
            "損益率": rate,
            "目前每月配息": div,
        })

    return pd.DataFrame(rows)


def read_detail_records(market_bytes: bytes, platform: str) -> pd.DataFrame:
    pieces = []
    for sheet_name in DETAIL_GROUPS.get(platform, []):
        try:
            raw = read_sheet(market_bytes, sheet_name)
            norm = normalize_investment_table(raw, sheet_name, platform)
            if not norm.empty:
                pieces.append(norm)
        except Exception:
            pass
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


def format_investment_records(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    for col in ["台幣成本", "台幣市值", "損益", "目前每月配息"]:
        if col in out:
            out[col] = out[col].apply(money if col != "損益" else signed_money)
    if "損益率" in out:
        out["損益率"] = out["損益率"].apply(signed_ratio_str)
    return fmt_df(out)


def display_table_or_info(df: pd.DataFrame, message: str, height: int = 340) -> None:
    if df is None or df.empty:
        st.info(message)
    else:
        st.dataframe(df, use_container_width=True, hide_index=True, height=height)


def monthly_income_trend(monthly_df: pd.DataFrame) -> pd.DataFrame:
    header = monthly_df.iloc[0]
    total_row = row_by_label(monthly_df, "合計")
    if total_row is None:
        return pd.DataFrame(columns=["月份", "收入"])
    records = []
    for ci, hv in enumerate(header):
        dt = pd.to_datetime(hv, errors="coerce")
        amt = numeric(total_row.iloc[ci])
        if pd.notna(dt) and amt is not None:
            records.append({"月份": dt, "收入": amt})
    return pd.DataFrame(records)


def ledger_long_table(ledger: pd.DataFrame) -> pd.DataFrame:
    months = ledger.iloc[0, 1:14]
    records = []
    for ri in range(1, min(len(ledger), 180)):
        cat = ledger.iloc[ri, 0]
        if cat is None or pd.isna(cat):
            continue
        for offset, mv in enumerate(months, start=1):
            amt = numeric(ledger.iloc[ri, offset])
            if amt is None or amt == 0:
                continue
            records.append({"月份": str(mv), "項目": str(cat), "金額": amt, "來源列": ri + 1})
    return pd.DataFrame(records)


def fund_sheet_metrics(df: pd.DataFrame) -> dict[str, str]:
    row = df.iloc[1] if len(df) > 1 else pd.Series(dtype=object)
    return {
        "投資成本": money(row.iloc[9]) if len(row) > 9 else "-",
        "總市值": money(row.iloc[10]) if len(row) > 10 else "-",
        "損益": money(row.iloc[12]) if len(row) > 12 else "-",
        "月配息": money(row.iloc[14]) if len(row) > 14 else "-",
    }


def load_health_summary() -> list[dict[str, Any]]:
    if not SUMMARY_JSON.exists():
        return []
    return json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))


def local_records_path(platform: str) -> Path:
    safe = platform.replace(" ", "_").replace("/", "_")
    return LOCAL_RECORDS_DIR / f"{safe}_investment_records.csv"


def load_local_records(platform: str) -> pd.DataFrame:
    p = local_records_path(platform)
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()


def save_local_records(platform: str, df: pd.DataFrame) -> None:
    LOCAL_RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    load_local_records(platform)
    df.to_csv(local_records_path(platform), index=False, encoding="utf-8-sig")


# =============================================================================
# LIVE PRICE
# =============================================================================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_fund_nav(code: str, pattern: str) -> tuple[str, str]:
    if not HAS_BS4:
        return "-", "缺少 beautifulsoup4"
    url = f"https://www.moneydj.com/funddj/ya/{pattern}.djhtm?a={code}"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        table = soup.select_one("#article form table")
        if table:
            rows = table.find_all("tr")
            if len(rows) >= 2:
                cells = rows[1].find_all("td")
                if len(cells) >= 2:
                    val = cells[1].get_text(strip=True)
                    if val:
                        return val, "ok"
        return "-", "未找到淨值欄位"
    except Exception as e:
        return "-", str(e)[:40]


@st.cache_data(ttl=300, show_spinner=False)
def fetch_stock_price(ticker: str) -> tuple[str, str]:
    if not HAS_YF:
        return "-", "缺少 yfinance"
    try:
        t = yf.Ticker(ticker)
        price = getattr(t.fast_info, "last_price", None)
        return (f"{price:,.4f}", "ok") if price else ("-", "無資料")
    except Exception as e:
        return "-", str(e)[:40]


@st.cache_data(ttl=300, show_spinner=False)
def fetch_fx(pair: str) -> tuple[str, str]:
    if not HAS_YF:
        return "-", "缺少 yfinance"
    try:
        t = yf.Ticker(pair)
        rate = getattr(t.fast_info, "last_price", None)
        return (f"{rate:,.4f}", "ok") if rate else ("-", "無資料")
    except Exception as e:
        return "-", str(e)[:40]


# =============================================================================
# APP HEADER
# =============================================================================
st.markdown("""
<div class="j-topbar">
  <div class="j-source-pill active"><span class="j-logo logo-sheet">●</span> Google Sheet</div>
  <div class="j-source-pill"><span class="j-logo logo-refresh">↻</span> 重新整理</div>
  <div class="j-brand-pill"><span class="j-logo logo-g">G</span><div>基富通<br><span style="font-size:11px;color:#7b9188;">FundRich</span></div></div>
  <div class="j-brand-pill"><span class="j-logo logo-sc">S</span><div>渣打美股<br><span style="font-size:11px;color:#7b9188;">SC US</span></div></div>
  <div class="j-brand-pill"><span class="j-logo logo-sc">S</span><div>渣打基金<br><span style="font-size:11px;color:#7b9188;">SC.com</span></div></div>
  <div class="j-brand-pill"><span class="j-logo logo-ts">TS</span><div>台新基金<br><span style="font-size:11px;color:#7b9188;">Taishin</span></div></div>
</div>
""", unsafe_allow_html=True)

sc1, sc2, sc3 = st.columns([2, 1, 9])
with sc1:
    source_mode = st.radio("來源", ["Google Sheet", "本機快取"], horizontal=True, label_visibility="collapsed")
with sc2:
    if st.button("🔄 重新整理"):
        st.cache_data.clear()
        st.rerun()

with st.spinner("讀取試算表中…"):
    try:
        primary_bytes = workbook_bytes(source_mode, "primary")
        market_bytes = workbook_bytes(source_mode, "market")
        load_ok = True
    except Exception as exc:
        st.error(f"❌ 讀取失敗：{exc}")
        load_ok = False

if not load_ok:
    st.stop()

tabs = st.tabs(["◈ 總覽", "📌 平台明細", "◷ 每月收入", "📒 2026 細帳", "📊 市值來源", "💹 即時市值", "🔍 資料健康"])


# =============================================================================
# TAB 1 OVERVIEW
# =============================================================================
with tabs[0]:
    st.markdown('<div class="j-tabmeta">資料更新時間：2025/05/24 10:30　　版本：v4-visual-overview</div>', unsafe_allow_html=True)
    st.markdown('<div class="j-page-title">總覽</div><div class="j-page-sub">所有帳戶資產彙整</div>', unsafe_allow_html=True)

    try:
        overview = read_sheet(market_bytes, "總覽")
        assets_df = build_overview_assets_from_all_sources(overview, market_bytes)

        total_from_items = float(assets_df["金額"].sum()) if not assets_df.empty else 0.0
        sheet_total = value_from_labels(overview, LABEL_ALIASES["總資產"])
        total_assets = total_from_items or sheet_total

        core = {item: assets_df.loc[assets_df["項目"] == item].iloc[0] for item in assets_df["項目"].tolist()}

        top_items = ["總資產", "台股", "銀行", "保險", "UNCLE 待還"]
        top_cols = st.columns(5)
        for col, item in zip(top_cols, top_items):
            if item == "總資產":
                total_profit = assets_df["損益"].dropna().sum() if "損益" in assets_df else None
                total_rate = total_profit / total_assets if total_profit and total_assets else None
                col.metric("🏦 總資產", money(total_assets), delta=f"{signed_money(total_profit)} ({signed_ratio_str(total_rate)})" if total_profit else None)
            else:
                row = core.get(item)
                value = row["金額"] if row is not None else 0
                delta = None
                if row is not None and pd.notna(row.get("損益")):
                    delta = f"{signed_money(row['損益'])} ({signed_ratio_str(row.get('損益率'))})"
                icon = {"台股": "📈", "銀行": "🏛", "保險": "🛡", "UNCLE 待還": "👤"}.get(item, "")
                col.metric(f"{icon} {item}", money(value), delta=delta)

        st.markdown("<br>", unsafe_allow_html=True)

        second_items = ["基富通", "渣打美股", "渣打基金", "台新基金", "其他投資"]
        second_cols = st.columns(5)
        icon_map = {"基富通": "🟧 基金（基富通）", "渣打美股": "🇺🇸 美股（渣打）", "渣打基金": "💹 基金（渣打）", "台新基金": "🟥 基金（台新）", "其他投資": "◔ 其他投資"}
        for col, item in zip(second_cols, second_items):
            row = core.get(item)
            value = row["金額"] if row is not None else 0
            delta = None
            if row is not None and pd.notna(row.get("損益")):
                delta = f"{signed_money(row['損益'])} ({signed_ratio_str(row.get('損益率'))})"
            col.metric(icon_map[item], money(value), delta=delta)

        st.markdown("<br>", unsafe_allow_html=True)

        left, mid, right = st.columns([1.25, 0.75, 1.25])

        with left:
            st.markdown('<div class="j-card"><div class="j-card-title">資產配置</div>', unsafe_allow_html=True)
            if assets_df.empty:
                st.info("尚未讀到資產分類資料。")
            else:
                chart_df = assets_df[assets_df["金額"] > 0][["項目", "金額"]].set_index("項目")
                st.bar_chart(chart_df, height=260)

                alloc = assets_df[assets_df["金額"] > 0][["項目", "金額", "占比"]].copy()
                alloc["金額"] = alloc["金額"].apply(money)
                alloc["占比"] = alloc["占比"].apply(ratio_str)
                st.dataframe(alloc, use_container_width=True, hide_index=True, height=260)
            st.markdown("</div>", unsafe_allow_html=True)

        with mid:
            st.markdown('<div class="j-card"><div class="j-card-title">資產彙總摘要</div>', unsafe_allow_html=True)
            if assets_df.empty:
                st.info("尚無摘要。")
            else:
                debt = core.get("UNCLE 待還")["金額"] if "UNCLE 待還" in core else 0
                bank = core.get("銀行")["金額"] if "銀行" in core else 0
                invest_items = ["台股", "基富通", "渣打美股", "渣打基金", "台新基金", "其他投資"]
                invest_total = assets_df[assets_df["項目"].isin(invest_items)]["金額"].sum()
                total_profit = assets_df["損益"].dropna().sum()
                summary = pd.DataFrame([
                    {"項目": "總資產總額", "金額": money(total_assets), "損益": signed_money(total_profit), "損益率": signed_ratio_str(total_profit / total_assets if total_assets else None)},
                    {"項目": "負債總額", "金額": money(debt), "損益": "-", "損益率": "-"},
                    {"項目": "淨資產", "金額": money(total_assets - debt), "損益": "-", "損益率": "-"},
                    {"項目": "現金部位", "金額": money(bank), "損益": "-", "損益率": "-"},
                    {"項目": "投資部位", "金額": money(invest_total), "損益": signed_money(total_profit), "損益率": signed_ratio_str(total_profit / invest_total if invest_total else None)},
                ])
                st.dataframe(summary, use_container_width=True, hide_index=True, height=300)
            st.markdown("</div>", unsafe_allow_html=True)

        with right:
            st.markdown('<div class="j-card"><div class="j-card-title">投資明細（含損益）</div>', unsafe_allow_html=True)
            investment_items = ["台股", "基富通", "渣打美股", "渣打基金", "台新基金", "其他投資"]
            inv_sum = assets_df[assets_df["項目"].isin(investment_items)].copy()
            if inv_sum.empty:
                st.info("尚無投資明細。")
            else:
                inv_sum = inv_sum[["項目", "金額", "占比", "損益", "損益率", "目前每月配息"]].copy()
                inv_sum["金額"] = inv_sum["金額"].apply(money)
                inv_sum["占比"] = inv_sum["占比"].apply(ratio_str)
                inv_sum["損益"] = inv_sum["損益"].apply(signed_money)
                inv_sum["損益率"] = inv_sum["損益率"].apply(signed_ratio_str)
                inv_sum["目前每月配息"] = inv_sum["目前每月配息"].apply(money)
                total_row = pd.DataFrame([{
                    "項目": "合計",
                    "金額": money(assets_df[assets_df["項目"].isin(investment_items)]["金額"].sum()),
                    "占比": "-",
                    "損益": signed_money(assets_df[assets_df["項目"].isin(investment_items)]["損益"].dropna().sum()),
                    "損益率": "-",
                    "目前每月配息": money(assets_df[assets_df["項目"].isin(investment_items)]["目前每月配息"].dropna().sum()),
                }])
                st.dataframe(pd.concat([inv_sum, total_row], ignore_index=True), use_container_width=True, hide_index=True, height=360)
            st.markdown("</div>", unsafe_allow_html=True)

    except Exception as e:
        st.warning(f"⚠️ 總覽工作表讀取錯誤：{e}")


# =============================================================================
# TAB 2 PLATFORM DETAILS
# =============================================================================
with tabs[1]:
    st.markdown('<div class="j-page-title">平台明細</div><div class="j-page-sub">查看各平台所有基金/股票、即時市值、台幣金額、每月配息與投資紀錄</div>', unsafe_allow_html=True)

    selected_platform = st.radio(
        "選擇平台",
        ["基富通", "台股", "渣打美股", "渣打基金", "台新基金", "其他投資"],
        horizontal=True,
        label_visibility="collapsed",
    )

    detail_df = read_detail_records(market_bytes, selected_platform)

    st.markdown(f'<div class="j-card"><div class="j-card-title">{selected_platform}｜持倉 / 基金 / 股票明細</div>', unsafe_allow_html=True)
    if detail_df.empty:
        st.warning("目前沒有成功從對應工作表解析出標準化明細。下方會顯示原始工作表。")
    else:
        total_value = detail_df["台幣市值"].dropna().sum()
        total_cost = detail_df["台幣成本"].dropna().sum()
        total_profit = detail_df["損益"].dropna().sum()
        total_div = detail_df["目前每月配息"].dropna().sum()
        total_rate = total_profit / total_cost if total_cost else None

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("台幣市值", money(total_value))
        m2.metric("台幣成本", money(total_cost))
        m3.metric("損益", signed_money(total_profit), delta=signed_ratio_str(total_rate))
        m4.metric("目前每月配息", money(total_div))

        show = detail_df[[
            "平台", "來源表", "標的名稱", "代號", "幣別", "單位/股數",
            "最新淨值/市價", "台幣成本", "台幣市值", "損益", "損益率", "目前每月配息"
        ]].copy()
        display_table_or_info(format_investment_records(show), "尚無明細資料。", height=430)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="j-card"><div class="j-card-title">匯入 / 記載所有投資記錄</div>', unsafe_allow_html=True)
    st.markdown('<div class="small-note">可先用 CSV 匯入或手動新增；正式長期版建議改接 SQLite/Postgres 或寫回 Google Sheet。</div>', unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "匯入投資紀錄 CSV（欄位建議：日期、平台、動作、標的名稱、代號、幣別、單位/股數、成交價、金額、手續費、備註）",
        type=["csv"],
        key=f"upload_{selected_platform}",
    )
    if uploaded is not None:
        try:
            imported = pd.read_csv(uploaded)
            existing = load_local_records(selected_platform)
            combined = pd.concat([existing, imported], ignore_index=True) if not existing.empty else imported
            save_local_records(selected_platform, combined)
            st.success(f"已匯入 {len(imported)} 筆投資紀錄。")
        except Exception as e:
            st.error(f"匯入失敗：{e}")

    with st.form(f"manual_record_{selected_platform}", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)
        date = c1.date_input("日期")
        action = c2.selectbox("動作", ["買入", "賣出", "配息", "除息", "轉入", "轉出", "調整", "其他"])
        target = c3.text_input("標的名稱")
        code = c4.text_input("代號")

        c5, c6, c7, c8 = st.columns(4)
        currency = c5.selectbox("幣別", ["TWD", "USD", "CNY", "JPY", "ZAR", "其他"])
        units = c6.number_input("單位/股數", value=0.0, step=1.0)
        price = c7.number_input("成交價/淨值", value=0.0, step=0.01)
        amount = c8.number_input("金額", value=0.0, step=100.0)

        fee = st.number_input("手續費/稅費", value=0.0, step=10.0)
        note = st.text_input("備註")
        submitted = st.form_submit_button("新增投資紀錄")

    if submitted:
        new_row = pd.DataFrame([{
            "日期": str(date), "平台": selected_platform, "動作": action, "標的名稱": target,
            "代號": code, "幣別": currency, "單位/股數": units, "成交價": price,
            "金額": amount, "手續費": fee, "備註": note,
        }])
        existing = load_local_records(selected_platform)
        combined = pd.concat([existing, new_row], ignore_index=True) if not existing.empty else new_row
        save_local_records(selected_platform, combined)
        st.success("已新增投資紀錄。")

    records = load_local_records(selected_platform)
    display_table_or_info(fmt_df(records), "尚無手動/匯入投資紀錄。", height=300)
    st.markdown("</div>", unsafe_allow_html=True)

    raw_sheets = DETAIL_GROUPS.get(selected_platform, [])
    if raw_sheets:
        st.markdown('<div class="j-card"><div class="j-card-title">原始工作表</div>', unsafe_allow_html=True)
        raw_selected = st.selectbox("查看原始表", raw_sheets, key=f"raw_{selected_platform}")
        try:
            raw_df = read_sheet(market_bytes, raw_selected)
            display_table_or_info(cleaned_table(raw_df), f"尚無 {raw_selected} 原始資料。", height=460)
        except Exception as e:
            st.warning(f"讀取 {raw_selected} 失敗：{e}")
        st.markdown("</div>", unsafe_allow_html=True)


# =============================================================================
# TAB 3 MONTHLY INCOME
# =============================================================================
with tabs[2]:
    st.markdown('<div class="j-page-title">每月收入</div><div class="j-page-sub">配息・股利・利息月走勢</div>', unsafe_allow_html=True)
    try:
        monthly = read_sheet(primary_bytes, "每月收入")
        trend = monthly_income_trend(monthly)
        if not trend.empty:
            st.markdown('<div class="j-card"><div class="j-card-title">月收入走勢</div>', unsafe_allow_html=True)
            st.bar_chart(trend.set_index("月份"), height=240, color="#10b981")
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="j-card"><div class="j-card-title">每月收入明細</div>', unsafe_allow_html=True)
        tbl = monthly.iloc[:22, :46].dropna(axis=1, how="all")
        tbl.columns = [str(c) for c in tbl.columns]
        display_table_or_info(fmt_df(tbl), "尚無每月收入資料。", height=360)
        st.markdown("</div>", unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"⚠️ 每月收入工作表讀取錯誤：{e}")


# =============================================================================
# TAB 4 LEDGER
# =============================================================================
with tabs[3]:
    st.markdown('<div class="j-page-title">2026 細帳</div><div class="j-page-sub">全年進出帳記錄・帳戶移轉・配息・支出</div>', unsafe_allow_html=True)
    try:
        ledger = read_sheet(primary_bytes, "2026細帳")
        long_df = ledger_long_table(ledger)
        if not long_df.empty:
            inc = long_df[long_df["金額"] > 0]["金額"].sum()
            out = long_df[long_df["金額"] < 0]["金額"].sum()
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("收入合計", money(inc))
            m2.metric("支出合計", money(abs(out)))
            m3.metric("淨收支", money(inc + out))
            m4.metric("記錄筆數", f"{len(long_df):,}")

            cats = ["全部"] + sorted(long_df["項目"].unique().tolist())
            sel = st.selectbox("篩選項目", cats)
            view = long_df if sel == "全部" else long_df[long_df["項目"] == sel]

            st.markdown('<div class="j-card"><div class="j-card-title">細帳明細（長表）</div>', unsafe_allow_html=True)
            display_table_or_info(fmt_df(view), "尚無細帳資料。", height=340)
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="j-card"><div class="j-card-title">原始資料（寬表）</div>', unsafe_allow_html=True)
        raw = ledger.iloc[:140, :16].copy()
        raw.columns = [str(c) for c in raw.columns]
        display_table_or_info(fmt_df(raw), "尚無原始細帳資料。", height=360)
        st.markdown("</div>", unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"⚠️ 2026細帳工作表讀取錯誤：{e}")


# =============================================================================
# TAB 5 MARKET SOURCE
# =============================================================================
with tabs[4]:
    st.markdown('<div class="j-page-title">市值來源</div><div class="j-page-sub">各平台基金・台股・外幣市值（Google Sheet 快照）</div>', unsafe_allow_html=True)
    sel_sheet = st.selectbox("選擇工作表", MARKET_SHEETS)
    try:
        sheet = read_sheet(market_bytes, sel_sheet)
        if sel_sheet not in {"總覽", "台股", "「台股」的副本", "渣打-美股"}:
            metrics = fund_sheet_metrics(sheet)
            mc1, mc2, mc3, mc4 = st.columns(4)
            for col, (label, val) in zip([mc1, mc2, mc3, mc4], metrics.items()):
                col.metric(label, val)

        st.markdown('<div class="j-card"><div class="j-card-title">工作表資料</div>', unsafe_allow_html=True)
        display_table_or_info(cleaned_table(sheet), f"尚無 {sel_sheet} 資料。", height=500)
        st.markdown("</div>", unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"⚠️ 工作表 {sel_sheet} 讀取錯誤：{e}")


# =============================================================================
# TAB 6 LIVE VALUE
# =============================================================================
with tabs[5]:
    st.markdown('<div class="j-page-title">即時市值</div><div class="j-page-sub">基金 NAV via MoneyDJ・股票/匯率 via Yahoo Finance</div>', unsafe_allow_html=True)

    st.markdown('<div class="j-card"><div class="j-card-title">匯率（TWD 換算）</div>', unsafe_allow_html=True)
    fx_cols = st.columns(len(FX_PAIRS))
    fx_rates: dict[str, float] = {}
    for col, (cur, pair) in zip(fx_cols, FX_PAIRS.items()):
        with st.spinner(f"抓取 {cur}…"):
            rate_str, status = fetch_fx(pair)
        col.metric(f"1 {cur} = ? TWD", rate_str, delta="✓ 即時" if status == "ok" else f"⚠ {status}")
        if status == "ok":
            try:
                fx_rates[cur] = float(rate_str.replace(",", ""))
            except Exception:
                pass
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="j-card"><div class="j-card-title">基金最新淨值（MoneyDJ）</div>', unsafe_allow_html=True)
    fund_rows = []
    progress = st.progress(0, text="抓取基金淨值…")
    for i, f in enumerate(FUND_CONFIG):
        nav_str, status = fetch_fund_nav(f["code"], f["pattern"])
        cur = f["currency"]
        twd_str = "-"
        if status == "ok" and cur in fx_rates:
            try:
                twd_str = f"{float(nav_str.replace(',', '')) * fx_rates[cur]:,.4f}"
            except Exception:
                pass
        elif cur == "TWD" and status == "ok":
            twd_str = nav_str
        fund_rows.append({
            "基金名稱": f["name"], "MoneyDJ代號": f["code"], "幣別": cur,
            "最新淨值": nav_str, "台幣換算": twd_str,
            "狀態": "✓" if status == "ok" else f"⚠ {status}",
        })
        progress.progress((i + 1) / len(FUND_CONFIG), text=f"抓取中… {i+1}/{len(FUND_CONFIG)}")
    progress.empty()
    display_table_or_info(pd.DataFrame(fund_rows), "尚無基金即時資料。", height=420)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="j-card"><div class="j-card-title">股票即時價（Yahoo Finance）</div>', unsafe_allow_html=True)
    stock_rows = []
    for s in STOCK_CONFIG:
        price_str, status = fetch_stock_price(s["ticker"])
        stock_rows.append({"代號": s["ticker"], "名稱": s["name"], "幣別": s["currency"], "即時價": price_str, "狀態": "✓" if status == "ok" else f"⚠ {status}"})
    display_table_or_info(pd.DataFrame(stock_rows), "尚無股票即時資料。", height=180)
    st.markdown("</div>", unsafe_allow_html=True)

    if not HAS_YF:
        st.info("提示：安裝 `yfinance` 以啟用股票/匯率即時抓取。`pip install yfinance`")
    if not HAS_BS4:
        st.info("提示：安裝 `beautifulsoup4` 與 `lxml` 以啟用基金 NAV 抓取。")


# =============================================================================
# TAB 7 HEALTH
# =============================================================================
with tabs[6]:
    st.markdown('<div class="j-page-title">資料健康</div><div class="j-page-sub">工作表結構・公式統計・錯誤偵測</div>', unsafe_allow_html=True)
    summaries = load_health_summary()
    if not summaries:
        st.info("尚未產生 workbook_structure_summary.json，請先執行分析腳本。")
    else:
        for book in summaries:
            fname = Path(book["file"]).name
            st.markdown(f'<div class="j-card"><div class="j-card-title">{fname}</div>', unsafe_allow_html=True)
            bm1, bm2, bm3 = st.columns(3)
            bm1.metric("檔案大小 MB", book["size_mb"])
            bm2.metric("工作表數", book["sheet_count"])
            bm3.metric("公式種類", len(book["workbook_functions"]))

            heavy = (
                pd.DataFrame(book["sheets"])
                .sort_values("formulas", ascending=False)
                [["sheet", "class", "rows", "cols", "nonempty", "formulas", "literal_errors"]]
                .head(12)
            )
            display_table_or_info(fmt_df(heavy), "尚無資料健康摘要。", height=280)

            funcs = pd.DataFrame([{"公式": k, "次數": v} for k, v in book["workbook_functions"].items()])
            display_table_or_info(fmt_df(funcs), "尚無公式統計。", height=280)
            st.markdown("</div>", unsafe_allow_html=True)
