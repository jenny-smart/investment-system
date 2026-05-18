from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
PRIMARY_SPREADSHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"
MARKET_SPREADSHEET_ID = "17HPytZKOPR_9Od_wor-xEx9kpccJlPS2v6B0Dz6MRYc"
PRIMARY_LOCAL = PROJECT_DIR / "inputs" / "investment-system-source.xlsx"
MARKET_LOCAL = PROJECT_DIR / "inputs" / "market-value-source.xlsx"
SUMMARY_JSON = PROJECT_DIR / "outputs" / "workbook_structure_summary.json"

MARKET_SHEETS = [
    "總覽",
    "台股",
    "「台股」的副本",
    "渣打-美股",
    "基富通-台",
    "基富通-人民幣",
    "基富通-日幣",
    "渣打-美金",
    "渣打-南非",
    "台新-美金",
    "台新-南非",
]


st.set_page_config(
    page_title="投資系統",
    layout="wide",
)


def google_export_url(spreadsheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=xlsx"


@st.cache_data(ttl=600, show_spinner=False)
def download_xlsx(spreadsheet_id: str) -> bytes:
    response = requests.get(google_export_url(spreadsheet_id), timeout=60)
    response.raise_for_status()
    return response.content


@st.cache_data(ttl=600, show_spinner=False)
def load_local_xlsx(path: str) -> bytes:
    return Path(path).read_bytes()


@st.cache_data(ttl=600, show_spinner=False)
def read_sheet(xlsx_bytes: bytes, sheet_name: str) -> pd.DataFrame:
    return pd.read_excel(
        BytesIO(xlsx_bytes),
        sheet_name=sheet_name,
        header=None,
        engine="openpyxl",
    )


def workbook_bytes(source_mode: str, workbook: str) -> bytes:
    if workbook == "primary":
        return (
            load_local_xlsx(str(PRIMARY_LOCAL))
            if source_mode == "本機快取"
            else download_xlsx(PRIMARY_SPREADSHEET_ID)
        )
    return (
        load_local_xlsx(str(MARKET_LOCAL))
        if source_mode == "本機快取"
        else download_xlsx(MARKET_SPREADSHEET_ID)
    )


def numeric(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def money(value: Any) -> str:
    number = numeric(value)
    if number is None:
        return "-"
    return f"{number:,.0f}"


def percent(value: Any) -> str:
    number = numeric(value)
    if number is None:
        return "-"
    return f"{number:.2%}"


def cleaned_table(df: pd.DataFrame, max_rows: int = 120, max_cols: int = 40) -> pd.DataFrame:
    table = df.dropna(how="all").dropna(axis=1, how="all")
    table = table.iloc[:max_rows, :max_cols].copy()
    table.columns = [str(col) for col in table.columns]
    return table


def row_by_label(df: pd.DataFrame, label: str) -> pd.Series | None:
    labels = df.iloc[:, 0].astype(str).str.strip()
    matches = df.loc[labels == label]
    if matches.empty:
        return None
    return matches.iloc[0]


def metric_from_overview(df: pd.DataFrame, label: str, col: int = 1) -> str:
    row = row_by_label(df, label)
    return money(row.iloc[col]) if row is not None and len(row) > col else "-"


def make_section_from_header(df: pd.DataFrame, start_col: int, end_col: int, max_rows: int = 80) -> pd.DataFrame:
    section = df.iloc[:max_rows, start_col:end_col].dropna(how="all").copy()
    if section.empty:
        return section
    header = section.iloc[0].fillna("")
    section = section.iloc[1:].copy()
    section.columns = [str(value).strip() or f"col_{idx + 1}" for idx, value in enumerate(header)]
    return section.dropna(how="all")


def render_overview(market_bytes: bytes) -> None:
    overview = read_sheet(market_bytes, "總覽")

    st.subheader("總覽")
    cols = st.columns(5)
    cols[0].metric("總資產", metric_from_overview(overview, "加總Total", 1))
    cols[1].metric("台股", metric_from_overview(overview, "台股total", 1))
    cols[2].metric("銀行", metric_from_overview(overview, "銀行total", 1))
    cols[3].metric("保險", metric_from_overview(overview, "保險total", 1))
    cols[4].metric("Uncle 待還", metric_from_overview(overview, "uncle待還", 1))

    left, right = st.columns([0.85, 1.4])
    with left:
        summary = overview.iloc[:18, :5].copy()
        summary.columns = ["項目", "現值", "損益", "收入/配息", "合計"]
        st.dataframe(summary, use_container_width=True, hide_index=True)

    with right:
        investments = make_section_from_header(overview, 5, 18, 90)
        visible_cols = [
            col
            for col in ["投資分類", "日期", "現值", "損益", "台幣成本", "台幣市值", "累積配息", "台幣配息", "配息率", "損益率"]
            if col in investments.columns
        ]
        st.dataframe(investments[visible_cols], use_container_width=True, hide_index=True)


def monthly_income_trend(monthly_df: pd.DataFrame) -> pd.DataFrame:
    header = monthly_df.iloc[0]
    total_row = row_by_label(monthly_df, "合計")
    if total_row is None:
        return pd.DataFrame(columns=["月份", "收入"])

    records: list[dict[str, Any]] = []
    for col_idx, header_value in enumerate(header):
        date_value = pd.to_datetime(header_value, errors="coerce")
        amount = numeric(total_row.iloc[col_idx])
        if pd.notna(date_value) and amount is not None:
            records.append({"月份": date_value, "收入": amount})
    return pd.DataFrame(records)


def render_income(primary_bytes: bytes) -> None:
    monthly = read_sheet(primary_bytes, "每月收入")
    st.subheader("每月收入")

    trend = monthly_income_trend(monthly)
    if not trend.empty:
        chart_data = trend.set_index("月份")
        st.bar_chart(chart_data, height=260)

    table = monthly.iloc[:22, :46].copy()
    table = table.dropna(axis=1, how="all")
    table.columns = [str(col) for col in table.columns]
    st.dataframe(table, use_container_width=True, hide_index=True)


def ledger_long_table(ledger: pd.DataFrame) -> pd.DataFrame:
    months = ledger.iloc[0, 1:14]
    records: list[dict[str, Any]] = []
    for row_idx in range(1, min(len(ledger), 160)):
        category = ledger.iloc[row_idx, 0]
        if category is None or pd.isna(category):
            continue
        for offset, month_value in enumerate(months, start=1):
            amount = numeric(ledger.iloc[row_idx, offset])
            if amount is None or amount == 0:
                continue
            records.append(
                {
                    "月份": str(month_value),
                    "項目": str(category),
                    "金額": amount,
                    "來源列": row_idx + 1,
                }
            )
    return pd.DataFrame(records)


def render_ledger(primary_bytes: bytes) -> None:
    ledger = read_sheet(primary_bytes, "2026細帳")
    st.subheader("2026 細帳")

    long_df = ledger_long_table(ledger)
    if not long_df.empty:
        categories = ["全部"] + sorted(long_df["項目"].unique().tolist())
        selected = st.selectbox("項目", categories)
        view = long_df if selected == "全部" else long_df[long_df["項目"] == selected]
        st.dataframe(view, use_container_width=True, hide_index=True)

    raw = ledger.iloc[:140, :16].copy()
    raw.columns = [str(col) for col in raw.columns]
    st.dataframe(raw, use_container_width=True, hide_index=True)


def fund_sheet_metrics(df: pd.DataFrame) -> dict[str, str]:
    row = df.iloc[1] if len(df) > 1 else pd.Series(dtype=object)
    return {
        "投資成本": money(row.iloc[9]) if len(row) > 9 else "-",
        "總市值": money(row.iloc[10]) if len(row) > 10 else "-",
        "損益": money(row.iloc[12]) if len(row) > 12 else "-",
        "月配息": money(row.iloc[14]) if len(row) > 14 else "-",
    }


def render_market_source(market_bytes: bytes) -> None:
    st.subheader("市值來源")
    selected_sheet = st.selectbox("工作表", MARKET_SHEETS)
    sheet = read_sheet(market_bytes, selected_sheet)

    if selected_sheet not in {"總覽", "台股", "「台股」的副本", "渣打-美股"}:
        metrics = fund_sheet_metrics(sheet)
        cols = st.columns(4)
        for col, (label, value) in zip(cols, metrics.items()):
            col.metric(label, value)

    table = cleaned_table(sheet)
    st.dataframe(table, use_container_width=True, hide_index=True)


def load_health_summary() -> list[dict[str, Any]]:
    if not SUMMARY_JSON.exists():
        return []
    return json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))


def render_health() -> None:
    st.subheader("資料健康")
    summaries = load_health_summary()
    if not summaries:
        st.info("尚未產生 workbook_structure_summary.json")
        return

    for book in summaries:
        st.markdown(f"**{Path(book['file']).name}**")
        cols = st.columns(3)
        cols[0].metric("檔案大小 MB", book["size_mb"])
        cols[1].metric("工作表數", book["sheet_count"])
        cols[2].metric("公式種類", len(book["workbook_functions"]))

        heavy = pd.DataFrame(book["sheets"]).sort_values("formulas", ascending=False)
        visible = heavy[["sheet", "class", "rows", "cols", "nonempty", "formulas", "literal_errors"]].head(12)
        st.dataframe(visible, use_container_width=True, hide_index=True)

        functions = pd.DataFrame(
            [{"公式": key, "次數": value} for key, value in book["workbook_functions"].items()]
        )
        st.dataframe(functions, use_container_width=True, hide_index=True)


def main() -> None:
    st.title("投資系統")

    with st.sidebar:
        source_mode = st.radio("資料來源", ["本機快取", "Google Sheet"], horizontal=False)
        st.caption("本機快取適合開發，Google Sheet 適合部署後讀最新資料。")

    try:
        primary_bytes = workbook_bytes(source_mode, "primary")
        market_bytes = workbook_bytes(source_mode, "market")
    except Exception as exc:
        st.error(f"讀取資料失敗：{exc}")
        return

    tabs = st.tabs(["總覽", "每月收入", "2026細帳", "市值來源", "資料健康"])
    with tabs[0]:
        render_overview(market_bytes)
    with tabs[1]:
        render_income(primary_bytes)
    with tabs[2]:
        render_ledger(primary_bytes)
    with tabs[3]:
        render_market_source(market_bytes)
    with tabs[4]:
        render_health()


if __name__ == "__main__":
    main()
