"""
Jenny All｜投資系統 — 清新版本
================================
- 純白底 + 薄荷綠強調色，中文小字也看得清楚
- 強化資料來源切換：Google Sheet / 本機快取 / 手動上傳 xlsx
- 讀不到資料時會給出具體診斷（缺哪個工作表、Google Sheet 是否回傳 HTML、找到哪些列標籤）
- 同一檔案即可上線 Streamlit Community Cloud，本機執行也支援
"""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st

# ─── Config ──────────────────────────────────────────────────────────────
PRIMARY_SPREADSHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"
MARKET_SPREADSHEET_ID = "17HPytZKOPR_9Od_wor-xEx9kpccJlPS2v6B0Dz6MRYc"
BASE_DIR = Path(__file__).resolve().parent
PRIMARY_LOCAL = BASE_DIR / "inputs" / "investment-system-source.xlsx"
MARKET_LOCAL = BASE_DIR / "inputs" / "market-value-source.xlsx"
SUMMARY_JSON = BASE_DIR / "outputs" / "workbook_structure_summary.json"

MARKET_SHEETS = [
    "總覽", "台股", "「台股」的副本", "渣打-美股",
    "基富通-台", "基富通-人民幣", "基富通-日幣",
    "渣打-美金", "渣打-南非", "台新-美金", "台新-南非",
]

# Theme palette — 清新薄荷綠
INK = "#1f2937"          # 主文字
INK_SOFT = "#4b5563"     # 次要文字
MUTED = "#9ca3af"        # 灰色說明
BORDER = "#e5e7eb"       # 卡片邊線
SURFACE = "#ffffff"      # 卡片底色
PAGE = "#f7faf9"         # 頁面底色（極淺薄荷）
MINT = "#10b981"         # 主強調（薄荷綠）
MINT_SOFT = "#ecfdf5"    # 淺薄荷
MINT_INK = "#047857"     # 深薄荷（文字用）
ROSE = "#ef4444"         # 負值
ROSE_SOFT = "#fef2f2"
AMBER = "#f59e0b"
SKY = "#0ea5e9"

st.set_page_config(
    page_title="Jenny All｜投資系統",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── CSS ─────────────────────────────────────────────────────────────────
st.markdown(
    f"""
<style>
/* hide sidebar — keep top bar only */
[data-testid="stSidebar"], [data-testid="collapsedControl"],
section[data-testid="stSidebarNav"], button[kind="header"] {{
    display: none !important;
}}

/* base */
html, body, [class*="css"] {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                 "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif;
}}
.stApp {{ background: {PAGE}; color: {INK}; }}
.block-container {{ padding: 0 !important; max-width: 100% !important; }}

/* ── top nav ────────────────────────────────────────────────────────── */
.jenny-topbar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: {SURFACE};
    border-bottom: 1px solid {BORDER};
    padding: 0 28px;
    height: 56px;
    position: sticky; top: 0; z-index: 999;
}}
.jenny-topbar .logo {{
    font-size: 15px; font-weight: 700; color: {INK};
    display: flex; align-items: center; gap: 8px;
}}
.jenny-topbar .logo .dot {{
    width: 10px; height: 10px; border-radius: 50%;
    background: {MINT};
    box-shadow: 0 0 0 4px {MINT_SOFT};
    display: inline-block;
}}
.jenny-topbar .meta {{
    font-size: 12px; color: {MUTED};
}}

/* ── controls strip ─────────────────────────────────────────────────── */
.jenny-controls {{ padding: 14px 28px 0; }}

/* ── tabs ───────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {{
    background: {SURFACE};
    border-bottom: 1px solid {BORDER};
    padding: 0 28px;
    gap: 4px;
}}
.stTabs [data-baseweb="tab"] {{
    color: {INK_SOFT} !important;
    font-size: 14px;
    padding: 14px 16px;
    border-bottom: 2px solid transparent !important;
    background: transparent !important;
    font-weight: 500;
}}
.stTabs [data-baseweb="tab"]:hover {{ color: {MINT_INK} !important; }}
.stTabs [aria-selected="true"] {{
    color: {MINT_INK} !important;
    border-bottom-color: {MINT} !important;
    font-weight: 600 !important;
}}
.stTabs [data-baseweb="tab-panel"] {{
    background: {PAGE};
    padding: 22px 28px 40px;
}}

/* ── metric cards ───────────────────────────────────────────────────── */
[data-testid="stMetric"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 14px 18px !important;
    box-shadow: 0 1px 2px rgba(16,24,40,.04);
}}
[data-testid="stMetricLabel"] {{
    font-size: 12px !important;
    color: {MUTED} !important;
    font-weight: 500;
    letter-spacing: 0;
    text-transform: none;
}}
[data-testid="stMetricLabel"] p {{
    font-size: 12px !important;
    color: {MUTED} !important;
}}
[data-testid="stMetricValue"] {{
    font-size: 22px !important;
    font-weight: 700 !important;
    color: {INK} !important;
    line-height: 1.3;
}}
[data-testid="stMetricDelta"] {{ font-size: 12px !important; }}

/* ── dataframe ──────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {{
    border: 1px solid {BORDER} !important;
    border-radius: 10px !important;
    overflow: hidden;
    background: {SURFACE};
}}

/* ── radio (source selector) ────────────────────────────────────────── */
[data-testid="stRadio"] > div {{
    display: flex; flex-direction: row; gap: 8px; flex-wrap: wrap;
}}
[data-testid="stRadio"] label {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 13px;
    color: {INK_SOFT} !important;
    cursor: pointer;
    transition: all .15s ease;
}}
[data-testid="stRadio"] label:hover {{
    border-color: {MINT};
    color: {MINT_INK} !important;
}}
[data-testid="stRadio"] label:has(input:checked) {{
    background: {MINT_SOFT};
    border-color: {MINT};
    color: {MINT_INK} !important;
    font-weight: 600;
}}
[data-testid="stRadio"] label > div:first-child {{ display: none; }}

/* ── selectbox / file uploader ──────────────────────────────────────── */
[data-baseweb="select"] > div {{
    background: {SURFACE} !important;
    border-color: {BORDER} !important;
    color: {INK} !important;
    border-radius: 8px !important;
    font-size: 14px;
}}
[data-testid="stFileUploader"] section {{
    background: {SURFACE};
    border: 1px dashed {BORDER};
    border-radius: 10px;
}}

/* ── primary button ─────────────────────────────────────────────────── */
.stButton > button {{
    background: {MINT_SOFT};
    color: {MINT_INK};
    border: 1px solid {MINT};
    border-radius: 8px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 600;
    transition: all .15s ease;
}}
.stButton > button:hover {{
    background: {MINT};
    color: white;
}}

/* ── card ───────────────────────────────────────────────────────────── */
.j-card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 18px 22px;
    margin-bottom: 16px;
    box-shadow: 0 1px 2px rgba(16,24,40,.04);
}}
.j-card-title {{
    font-size: 13px; color: {INK};
    font-weight: 600;
    margin-bottom: 12px; padding-bottom: 10px;
    border-bottom: 1px solid {BORDER};
    display: flex; align-items: center; justify-content: space-between;
}}
.j-card-title .hint {{
    font-size: 11px; color: {MUTED}; font-weight: 400;
}}

/* ── page heading ───────────────────────────────────────────────────── */
.j-page-title {{
    font-size: 22px; font-weight: 700; color: {INK};
    margin: 4px 0 2px;
    display: flex; align-items: center; gap: 10px;
}}
.j-page-sub {{
    font-size: 13px; color: {INK_SOFT}; margin-bottom: 18px;
}}

/* ── status pill ────────────────────────────────────────────────────── */
.pill {{
    display:inline-block; padding:3px 10px; border-radius:999px;
    font-size:11px; font-weight:600; letter-spacing:.2px;
}}
.pill-ok   {{ background:{MINT_SOFT}; color:{MINT_INK}; }}
.pill-warn {{ background:#fff7ed; color:#c2410c; }}
.pill-err  {{ background:{ROSE_SOFT}; color:{ROSE}; }}
.pill-info {{ background:#eff6ff; color:#1d4ed8; }}

/* ── colored numbers ────────────────────────────────────────────────── */
.j-pos {{ color: {MINT_INK}; font-weight: 600; }}
.j-neg {{ color: {ROSE}; font-weight: 600; }}
.j-muted {{ color: {MUTED}; }}

/* ── info / warn / error banners (Streamlit) ───────────────────────── */
[data-testid="stAlert"] {{
    border-radius: 10px;
    border: 1px solid {BORDER};
}}

/* chart container */
[data-testid="stVegaLiteChart"], [data-testid="stChart"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px;
}}
</style>
""",
    unsafe_allow_html=True,
)

# ─── Helpers ─────────────────────────────────────────────────────────────
def google_export_url(sid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx"


@st.cache_data(ttl=600, show_spinner=False)
def download_xlsx(sid: str) -> bytes:
    """Download xlsx export, raising informative errors if Google returns HTML."""
    url = google_export_url(sid)
    r = requests.get(url, timeout=60, allow_redirects=True)
    r.raise_for_status()
    ct = r.headers.get("content-type", "")
    body = r.content
    # Detect HTML login / permission page disguised as 200
    if "text/html" in ct or body[:6].lower().startswith(b"<!doct") or body[:5].lower().startswith(b"<html"):
        raise RuntimeError(
            f"Google Sheet 沒回傳 xlsx，而是 HTML（content-type={ct or 'n/a'}）。"
            f"請打開 https://docs.google.com/spreadsheets/d/{sid}/edit，"
            f"確認分享設定為「知道連結的任何人可檢視」。"
        )
    if not body[:2] == b"PK":  # xlsx is a zip starting with PK
        raise RuntimeError(
            f"回傳內容不是 xlsx 檔（開頭非 PK）。content-type={ct}, 長度={len(body)}。"
        )
    return body


@st.cache_data(ttl=600, show_spinner=False)
def load_local(path: str) -> bytes:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"本機快取檔不存在：{path}")
    return p.read_bytes()


def load_uploaded(uploaded) -> bytes:
    return uploaded.getvalue()


@st.cache_data(ttl=600, show_spinner=False)
def list_sheets(xlsx: bytes) -> list[str]:
    return pd.ExcelFile(BytesIO(xlsx), engine="openpyxl").sheet_names


@st.cache_data(ttl=600, show_spinner=False)
def read_sheet(xlsx: bytes, sheet: str) -> pd.DataFrame:
    return pd.read_excel(BytesIO(xlsx), sheet_name=sheet, header=None, engine="openpyxl")


def find_sheet(xlsx: bytes, target: str) -> str | None:
    """Find the actual sheet name matching `target` (exact, then fuzzy)."""
    names = list_sheets(xlsx)
    if target in names:
        return target
    norm_t = target.replace(" ", "").replace("　", "").lower()
    for n in names:
        if n.replace(" ", "").replace("　", "").lower() == norm_t:
            return n
    # contains
    for n in names:
        if target in n or n in target:
            return n
    return None


def num(v: Any) -> float | None:
    try:
        return None if v is None or pd.isna(v) else float(v)
    except Exception:
        return None


def money(v: Any) -> str:
    n = num(v)
    if n is None:
        return "—"
    abs_n = abs(n)
    if abs_n >= 1e8:
        return f"{n / 1e8:,.2f} 億"
    if abs_n >= 1e4:
        return f"{n / 1e4:,.1f} 萬"
    return f"{n:,.0f}"


def pct(v: Any) -> str:
    n = num(v)
    return "—" if n is None else f"{n:.2%}"


def cleaned(df: pd.DataFrame, rows: int = 120, cols: int = 40) -> pd.DataFrame:
    t = df.dropna(how="all").dropna(axis=1, how="all")
    t = t.iloc[:rows, :cols].copy()
    t.columns = [str(c) for c in t.columns]
    return t


def row_label(df: pd.DataFrame, label: str) -> pd.Series | None:
    """Find a row whose first column matches `label` (exact, then fuzzy contains)."""
    lbs = df.iloc[:, 0].astype(str).str.strip()
    m = df.loc[lbs == label]
    if not m.empty:
        return m.iloc[0]
    # Try contains
    m2 = df.loc[lbs.str.contains(label, na=False, regex=False)]
    return None if m2.empty else m2.iloc[0]


def metric_ov(df: pd.DataFrame, label: str, col: int = 1) -> str:
    row = row_label(df, label)
    return money(row.iloc[col]) if row is not None and len(row) > col else "—"


def section_from_header(df: pd.DataFrame, sc: int, ec: int, rows: int = 80) -> pd.DataFrame:
    s = df.iloc[:rows, sc:ec].dropna(how="all").copy()
    if s.empty:
        return s
    hdr = s.iloc[0].fillna("")
    s = s.iloc[1:].copy()
    s.columns = [str(v).strip() or f"col_{i+1}" for i, v in enumerate(hdr)]
    return s.dropna(how="all")


def get_sheet_safely(xlsx: bytes, target: str) -> tuple[pd.DataFrame | None, str | None, str | None]:
    """Return (df, actual_sheet_name, error_message). One of df / error will be set."""
    try:
        actual = find_sheet(xlsx, target)
        if actual is None:
            available = ", ".join(list_sheets(xlsx)[:20])
            return None, None, f"找不到工作表「{target}」。可用的工作表：{available}…"
        return read_sheet(xlsx, actual), actual, None
    except Exception as e:
        return None, None, f"讀取「{target}」失敗：{e}"


# ─── Top bar ─────────────────────────────────────────────────────────────
st.markdown(
    """
<div class="jenny-topbar">
    <div class="logo"><span class="dot"></span> Jenny All｜投資系統</div>
    <div class="meta">資料每 10 分鐘自動快取・薄荷清新版</div>
</div>
""",
    unsafe_allow_html=True,
)

# ─── Source toggle ───────────────────────────────────────────────────────
st.markdown('<div class="jenny-controls">', unsafe_allow_html=True)
col_src, col_refresh, col_status = st.columns([3, 1, 6])
with col_src:
    source_mode = st.radio(
        "資料來源",
        ["Google Sheet", "本機快取", "上傳檔案"],
        horizontal=True,
        label_visibility="collapsed",
    )
with col_refresh:
    if st.button("🔄 重新整理"):
        st.cache_data.clear()
        st.rerun()

uploaded_primary = None
uploaded_market = None
if source_mode == "上傳檔案":
    up1, up2 = st.columns(2)
    with up1:
        uploaded_primary = st.file_uploader(
            "主帳本 xlsx（含 每月收入 / 2026細帳）", type=["xlsx"], key="up_primary"
        )
    with up2:
        uploaded_market = st.file_uploader(
            "市值來源 xlsx（含 總覽 / 各平台）", type=["xlsx"], key="up_market"
        )
st.markdown("</div>", unsafe_allow_html=True)


# ─── Load data ───────────────────────────────────────────────────────────
def load_workbook(which: str) -> tuple[bytes | None, str | None]:
    """Return (bytes, error). which ∈ {'primary','market'}."""
    try:
        if source_mode == "Google Sheet":
            sid = PRIMARY_SPREADSHEET_ID if which == "primary" else MARKET_SPREADSHEET_ID
            return download_xlsx(sid), None
        if source_mode == "本機快取":
            path = PRIMARY_LOCAL if which == "primary" else MARKET_LOCAL
            return load_local(str(path)), None
        # 上傳檔案
        up = uploaded_primary if which == "primary" else uploaded_market
        if up is None:
            return None, "請先上傳檔案"
        return load_uploaded(up), None
    except Exception as e:
        return None, str(e)


with st.spinner("讀取試算表中…"):
    pri, pri_err = load_workbook("primary")
    mkt, mkt_err = load_workbook("market")

# Status pills
status_bits = []
if pri_err:
    status_bits.append(f'<span class="pill pill-err">主帳本：{pri_err[:60]}</span>')
elif pri is not None:
    status_bits.append(
        f'<span class="pill pill-ok">主帳本 OK · {len(list_sheets(pri))} 個工作表</span>'
    )
if mkt_err:
    status_bits.append(f'<span class="pill pill-err">市值來源：{mkt_err[:60]}</span>')
elif mkt is not None:
    status_bits.append(
        f'<span class="pill pill-ok">市值來源 OK · {len(list_sheets(mkt))} 個工作表</span>'
    )

st.markdown(
    f'<div style="padding:10px 28px 0; display:flex; gap:8px; flex-wrap:wrap;">{" ".join(status_bits)}</div>',
    unsafe_allow_html=True,
)

if pri is None and mkt is None:
    st.markdown('<div style="padding: 20px 28px">', unsafe_allow_html=True)
    st.error("兩份試算表都讀不到。請檢查上方的錯誤訊息，或切換「資料來源」試試看。")
    if source_mode == "Google Sheet":
        st.info(
            "**Google Sheet 讀不到時最常見的原因**：\n\n"
            "1. 分享設定不是「知道連結的任何人可檢視」\n"
            "2. 試算表 ID 換了（請對照程式碼開頭的 `PRIMARY_SPREADSHEET_ID` / `MARKET_SPREADSHEET_ID`）\n"
            "3. Streamlit Cloud 暫時連不上 Google\n\n"
            "建議先用「上傳檔案」直接拖兩個 xlsx 上來看資料是否正常。"
        )
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# ─── Tabs ────────────────────────────────────────────────────────────────
tabs = st.tabs(["總覽", "每月收入", "2026 細帳", "市值來源", "資料健康"])

# ══════════════════════════════════════════════════════════════════════════
# TAB 1 — 總覽
# ══════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.markdown('<div class="j-page-title">🏠 總覽</div>', unsafe_allow_html=True)
    st.markdown('<div class="j-page-sub">所有帳戶資產彙整</div>', unsafe_allow_html=True)

    if mkt is None:
        st.warning(f"市值來源讀不到：{mkt_err}")
    else:
        ov, ov_name, ov_err = get_sheet_safely(mkt, "總覽")
        if ov_err:
            st.warning(ov_err)
        else:
            # KPI row
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("總資產", metric_ov(ov, "加總Total"))
            c2.metric("台股", metric_ov(ov, "台股total"))
            c3.metric("銀行", metric_ov(ov, "銀行total"))
            c4.metric("保險", metric_ov(ov, "保險total"))
            c5.metric("Uncle 待還", metric_ov(ov, "uncle待還"))

            # If every KPI is "—", show a diagnostic
            if all(
                metric_ov(ov, lbl) == "—"
                for lbl in ["加總Total", "台股total", "銀行total", "保險total", "uncle待還"]
            ):
                with st.expander("⚠️ KPI 全部顯示 — 點開看診斷"):
                    st.write("找到的工作表 A 欄前 20 列：")
                    st.dataframe(
                        ov.iloc[:20, :2].rename(columns={0: "A欄標籤", 1: "B欄值"}),
                        hide_index=True,
                        use_container_width=True,
                    )
                    st.caption(
                        "如果 A 欄標籤跟程式碼裡的 `加總Total / 台股total / 銀行total / 保險total / uncle待還` 不一致，"
                        "請改名其中之一就會對上。"
                    )

            st.markdown("<br>", unsafe_allow_html=True)

            left, right = st.columns([1, 1.5])
            with left:
                st.markdown(
                    '<div class="j-card"><div class="j-card-title">彙總摘要 <span class="hint">前 18 列</span></div>',
                    unsafe_allow_html=True,
                )
                summary = ov.iloc[:18, :5].copy()
                summary.columns = ["項目", "現值", "損益", "收入/配息", "合計"]
                st.dataframe(summary, use_container_width=True, hide_index=True, height=320)
                st.markdown("</div>", unsafe_allow_html=True)

            with right:
                st.markdown(
                    '<div class="j-card"><div class="j-card-title">投資明細 <span class="hint">F–R 欄</span></div>',
                    unsafe_allow_html=True,
                )
                inv = section_from_header(ov, 5, 18, 90)
                show = [
                    c
                    for c in [
                        "投資分類", "日期", "現值", "損益",
                        "台幣成本", "台幣市值", "累積配息", "台幣配息",
                        "配息率", "損益率",
                    ]
                    if c in inv.columns
                ]
                st.dataframe(
                    inv[show] if show else inv,
                    use_container_width=True,
                    hide_index=True,
                    height=320,
                )
                st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
# TAB 2 — 每月收入
# ══════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.markdown('<div class="j-page-title">💰 每月收入</div>', unsafe_allow_html=True)
    st.markdown('<div class="j-page-sub">配息・股利・利息月走勢</div>', unsafe_allow_html=True)

    if pri is None:
        st.warning(f"主帳本讀不到：{pri_err}")
    else:
        monthly, m_name, m_err = get_sheet_safely(pri, "每月收入")
        if m_err:
            st.warning(m_err)
        else:
            hdr = monthly.iloc[0]
            total_row = row_label(monthly, "合計")
            records = []
            if total_row is not None:
                for ci, hv in enumerate(hdr):
                    dt = pd.to_datetime(hv, errors="coerce")
                    amt = num(total_row.iloc[ci])
                    if pd.notna(dt) and amt is not None:
                        records.append({"月份": dt, "收入": amt})

            if records:
                trend = pd.DataFrame(records).set_index("月份")
                st.markdown(
                    '<div class="j-card"><div class="j-card-title">月收入走勢 '
                    f'<span class="hint">{len(records)} 個月</span></div>',
                    unsafe_allow_html=True,
                )
                st.bar_chart(trend, height=240, color=MINT)
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("找不到「合計」這列、或合計列裡沒有可解析的數字。請檢查工作表結構。")

            st.markdown(
                '<div class="j-card"><div class="j-card-title">明細資料 '
                '<span class="hint">前 22 列 × 46 欄</span></div>',
                unsafe_allow_html=True,
            )
            tbl = monthly.iloc[:22, :46].dropna(axis=1, how="all")
            tbl.columns = [str(c) for c in tbl.columns]
            st.dataframe(tbl, use_container_width=True, hide_index=True, height=340)
            st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
# TAB 3 — 2026 細帳
# ══════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.markdown('<div class="j-page-title">📒 2026 細帳</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="j-page-sub">全年進出帳記錄・帳戶移轉・配息・支出</div>',
        unsafe_allow_html=True,
    )

    if pri is None:
        st.warning(f"主帳本讀不到：{pri_err}")
    else:
        ledger, l_name, l_err = get_sheet_safely(pri, "2026細帳")
        if l_err:
            st.warning(l_err)
        else:
            months = ledger.iloc[0, 1:14]
            rows_data = []
            for ri in range(1, min(len(ledger), 160)):
                cat = ledger.iloc[ri, 0]
                if cat is None or pd.isna(cat):
                    continue
                for offset, mv in enumerate(months, start=1):
                    amt = num(ledger.iloc[ri, offset])
                    if amt is None or amt == 0:
                        continue
                    rows_data.append({"月份": str(mv), "項目": str(cat), "金額": amt})

            if rows_data:
                long = pd.DataFrame(rows_data)

                # summary metrics
                total_in = long[long["金額"] > 0]["金額"].sum()
                total_out = long[long["金額"] < 0]["金額"].sum()
                m1, m2, m3 = st.columns(3)
                m1.metric("收入合計", money(total_in))
                m2.metric("支出合計", money(abs(total_out)))
                m3.metric("淨收支", money(total_in + total_out))

                col_f, _ = st.columns([3, 9])
                with col_f:
                    cats = ["全部"] + sorted(long["項目"].unique().tolist())
                    sel = st.selectbox("篩選項目", cats, label_visibility="collapsed")
                view = long if sel == "全部" else long[long["項目"] == sel]

                st.markdown(
                    '<div class="j-card"><div class="j-card-title">篩選結果 '
                    f'<span class="hint">{len(view)} 筆</span></div>',
                    unsafe_allow_html=True,
                )
                st.dataframe(view, use_container_width=True, hide_index=True, height=320)
                st.markdown("</div>", unsafe_allow_html=True)

                with st.expander("查看原始寬表（前 140 列）"):
                    raw = ledger.iloc[:140, :16].copy()
                    raw.columns = [str(c) for c in raw.columns]
                    st.dataframe(raw, use_container_width=True, hide_index=True, height=340)
            else:
                st.info("這份工作表的格子全是空的或全為 0，沒有可顯示的明細。")

# ══════════════════════════════════════════════════════════════════════════
# TAB 4 — 市值來源
# ══════════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.markdown('<div class="j-page-title">📊 市值來源</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="j-page-sub">各平台基金・台股・外幣市值</div>',
        unsafe_allow_html=True,
    )

    if mkt is None:
        st.warning(f"市值來源讀不到：{mkt_err}")
    else:
        all_sheets = list_sheets(mkt)
        default_list = [s for s in MARKET_SHEETS if s in all_sheets] or all_sheets
        sel_sheet = st.selectbox("選擇工作表", default_list)

        sheet_df, actual_name, err = get_sheet_safely(mkt, sel_sheet)
        if err:
            st.warning(err)
        else:
            if sel_sheet not in {"總覽", "台股", "「台股」的副本", "渣打-美股"}:
                r = sheet_df.iloc[1] if len(sheet_df) > 1 else pd.Series(dtype=object)

                def mval(col: int) -> str:
                    return money(r.iloc[col]) if len(r) > col else "—"

                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("投資成本", mval(9))
                mc2.metric("總市值", mval(10))
                mc3.metric("損益", mval(12))
                mc4.metric("月配息", mval(14))

            st.markdown(
                '<div class="j-card"><div class="j-card-title">工作表資料 '
                f'<span class="hint">{actual_name or sel_sheet}</span></div>',
                unsafe_allow_html=True,
            )
            tbl = cleaned(sheet_df)
            st.dataframe(tbl, use_container_width=True, hide_index=True, height=480)
            st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
# TAB 5 — 資料健康
# ══════════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown('<div class="j-page-title">🔍 資料健康</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="j-page-sub">工作表結構・公式統計・錯誤偵測</div>',
        unsafe_allow_html=True,
    )

    # Live health: count NaN / errors in each loaded workbook
    def workbook_health(xlsx: bytes, name: str) -> pd.DataFrame:
        rows = []
        for sh in list_sheets(xlsx):
            try:
                df = read_sheet(xlsx, sh)
                nonempty = int(df.notna().sum().sum())
                errors = int(
                    df.astype(str)
                    .apply(lambda s: s.str.contains(r"#REF!|#N/A|#DIV/0!|#VALUE!|#NAME\?", na=False))
                    .sum()
                    .sum()
                )
                rows.append(
                    {
                        "workbook": name,
                        "sheet": sh,
                        "rows": int(df.shape[0]),
                        "cols": int(df.shape[1]),
                        "nonempty_cells": nonempty,
                        "error_cells": errors,
                    }
                )
            except Exception as e:
                rows.append(
                    {
                        "workbook": name,
                        "sheet": sh,
                        "rows": 0,
                        "cols": 0,
                        "nonempty_cells": 0,
                        "error_cells": -1,
                    }
                )
        return pd.DataFrame(rows)

    health_frames = []
    if pri is not None:
        health_frames.append(workbook_health(pri, "主帳本"))
    if mkt is not None:
        health_frames.append(workbook_health(mkt, "市值來源"))

    if health_frames:
        all_health = pd.concat(health_frames, ignore_index=True)
        err_total = int(all_health["error_cells"].clip(lower=0).sum())
        sh_total = len(all_health)
        h1, h2, h3 = st.columns(3)
        h1.metric("工作表總數", f"{sh_total}")
        h2.metric("非空儲存格", f"{int(all_health['nonempty_cells'].sum()):,}")
        h3.metric("錯誤儲存格", f"{err_total}")

        st.markdown(
            '<div class="j-card"><div class="j-card-title">工作表健康總覽</div>',
            unsafe_allow_html=True,
        )
        st.dataframe(
            all_health.sort_values(["workbook", "error_cells"], ascending=[True, False]),
            use_container_width=True,
            hide_index=True,
            height=420,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    # Also support the cached JSON summary from the analysis script
    if SUMMARY_JSON.exists():
        try:
            summaries = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
            for book in summaries:
                fname = Path(book["file"]).name
                st.markdown(
                    f'<div class="j-card"><div class="j-card-title">{fname} '
                    '<span class="hint">workbook_structure_summary.json</span></div>',
                    unsafe_allow_html=True,
                )
                bm1, bm2, bm3 = st.columns(3)
                bm1.metric("檔案大小 MB", book.get("size_mb", "—"))
                bm2.metric("工作表數", book.get("sheet_count", "—"))
                bm3.metric("公式種類", len(book.get("workbook_functions", {})))

                if "sheets" in book:
                    heavy = (
                        pd.DataFrame(book["sheets"])
                        .sort_values("formulas", ascending=False)[
                            ["sheet", "class", "rows", "cols", "nonempty", "formulas", "literal_errors"]
                        ]
                        .head(12)
                    )
                    st.dataframe(heavy, use_container_width=True, hide_index=True)

                if book.get("workbook_functions"):
                    funcs = pd.DataFrame(
                        [{"公式": k, "次數": v} for k, v in book["workbook_functions"].items()]
                    )
                    st.dataframe(funcs, use_container_width=True, hide_index=True)
                st.markdown("</div>", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"讀取 workbook_structure_summary.json 失敗：{e}")
    else:
        st.caption(
            "💡 若要看完整公式統計，可在本機跑分析腳本產出 `outputs/workbook_structure_summary.json`，"
            "此頁會自動顯示。"
        )
