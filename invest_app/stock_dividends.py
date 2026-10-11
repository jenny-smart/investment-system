"""台股股利：股利候選掃描、手動／上傳、台股股利頁。"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pandas as pd
import requests
import streamlit as st
from invest_app.core import (
    PRICE_REQUEST_TIMEOUT_SECONDS,
    TW_PRESETS,
    TW_STOCK_EXCHANGES,
    _format_dividend_date,
    _parse_dividend_date,
    ensure_columns,
    is_delisted_tw_stock,
    load_positions,
    money,
    normalize_bool,
    normalize_number,
    normalize_payload,
    normalize_text,
    normalize_ticker,
    right_align_numbers,
    supabase_client,
    tw_now,
)
from invest_app.dividends import (
    _position_dividend_units,
)
from invest_app.positions_admin import (
    read_uploaded_table,
)


STOCK_DIVIDEND_COLUMNS = [
    "平台", "股票名稱", "股票代碼", "除權息日", "現金發放日", "股票發放日",
    "除權息股數", "每股現金股利", "預估現金股利", "實際現金股利", "確認現金入帳",
    "每股股票股利", "預估股票股數", "實際股票股數", "確認股票入帳", "備註",
]


STOCK_DIVIDEND_UPLOAD_COLUMNS = [
    "平台", "股票代碼", "股票名稱", "除權息日", "現金發放日", "股票發放日",
    "除權息股數", "每股現金股利", "實際現金股利",
    "每股股票股利", "實際股票股數",
    "確認現金入帳", "確認股票入帳", "備註",
]


def _plain_stock_code(ticker: Any) -> str:
    text = normalize_ticker(normalize_text(ticker))
    return text.replace(".TW", "").replace(".TWO", "")


def _format_tw_stock_ticker(code: Any, fallback_ticker: str = "") -> str:
    code_text = _plain_stock_code(code)
    if fallback_ticker:
        return normalize_ticker(fallback_ticker)
    if not code_text:
        return ""
    suffix = ".TWO" if f"{code_text}.TWO" in TW_STOCK_EXCHANGES else ".TW"
    return f"{code_text}{suffix}"


def _parse_stock_api_date(value: Any) -> str:
    text = normalize_text(value).replace("-", "/")
    if not text:
        return ""
    if re.fullmatch(r"\d{7}", text):
        return f"{int(text[:3]) + 1911}/{int(text[3:5]):02d}/{int(text[5:7]):02d}"
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}/{text[4:6]}/{text[6:8]}"
    if re.fullmatch(r"\d{3}/\d{1,2}/\d{1,2}", text):
        y, m, d = text.split("/")
        return f"{int(y) + 1911}/{int(m):02d}/{int(d):02d}"
    parsed = _parse_dividend_date(text)
    return parsed.strftime("%Y/%m/%d") if parsed else text


def _stock_year_from_record(row: pd.Series | dict[str, Any]) -> int | None:
    for col in ["cash_pay_date", "ex_date", "現金發放日", "除權息日"]:
        normalized = _parse_stock_api_date(row.get(col, ""))
        parsed = _parse_dividend_date(normalized)
        if parsed is not None:
            return parsed.year
    # 自動掃描的候選可能沒有除息日；確認入帳後以記錄建立年度認列。
    created_at = normalize_text(row.get("created_at", ""))
    if created_at:
        try:
            parsed_created = pd.to_datetime(created_at, errors="coerce")
            if not pd.isna(parsed_created):
                return int(parsed_created.year)
        except Exception:
            pass
    return None


def _stock_dividend_number(value: Any) -> float:
    return normalize_number(value, 0)


def _stock_bonus_per_share(value: Any) -> float:
    number = _stock_dividend_number(value)
    if number <= 0:
        return 0.0
    return number / 10 if number > 1 else number


def _stock_bonus_shares(shares_at_ex: float, stock_dividend_per_share: float) -> float:
    return max(0.0, shares_at_ex * stock_dividend_per_share / 10)


def _stock_groups_from_positions(current_positions: pd.DataFrame) -> dict[str, pd.DataFrame]:
    current = ensure_columns(current_positions).copy()
    stocks = current[current["asset_type"].astype(str).isin(["台股"])].copy()
    if stocks.empty:
        return {}
    stocks["_stock_key"] = stocks.apply(
        lambda r: _plain_stock_code(r.get("ticker", "")) or _plain_stock_code(TW_PRESETS.get(normalize_text(r.get("name", "")), "")),
        axis=1,
    )
    if not stocks.empty:
        active_mask = ~stocks.apply(
            lambda r: is_delisted_tw_stock(r.get("ticker", ""), r.get("name", "")),
            axis=1,
        )
        stocks = stocks.loc[active_mask].copy()
    return {
        key: grp.copy()
        for key, grp in stocks.groupby("_stock_key", dropna=False)
        if normalize_text(key)
    }


def _stock_group_current_units(grp: pd.DataFrame) -> float:
    return sum(_position_dividend_units(row) for _, row in grp.iterrows())


def _stock_group_primary_row(grp: pd.DataFrame) -> pd.Series:
    sorted_grp = grp.copy()
    sorted_grp["_sort_num"] = sorted_grp["sort_order"].apply(lambda v: normalize_number(v, 999999))
    sorted_grp["_id_num"] = sorted_grp["id"].apply(lambda v: normalize_number(v, 999999))
    return sorted_grp.sort_values(["_sort_num", "_id_num"]).iloc[0]


@st.cache_data(ttl=30, show_spinner=False)
def load_stock_dividend_log() -> pd.DataFrame:
    cols = [
        "id", "platform", "ticker", "name", "currency", "ex_date", "cash_pay_date", "stock_pay_date",
        "shares_at_ex", "cash_dividend_per_share", "estimated_cash_total", "actual_cash_total",
        "stock_dividend_per_share", "estimated_stock_shares", "actual_stock_shares",
        "is_cash_received", "is_stock_received", "source", "note", "created_at",
    ]
    try:
        rows = supabase_client().table("stock_dividend_log").select("*").order("ex_date", desc=True).order("id", desc=True).execute().data or []
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=cols)
    except Exception:
        return pd.DataFrame(columns=cols)


def stock_cash_dividend_total_for_year(year: int | None = None) -> float:
    year = year or tw_now().year
    df = load_stock_dividend_log()
    if df.empty:
        return 0.0
    total = 0.0
    for _, row in df.iterrows():
        if not normalize_bool(row.get("is_cash_received", False), False):
            continue
        if _stock_year_from_record(row) != year:
            continue
        actual = normalize_number(row.get("actual_cash_total", 0), 0)
        estimated = normalize_number(row.get("estimated_cash_total", 0), 0)
        total += actual if actual > 0 else estimated
    return total


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_twse_stock_dividend_announcements() -> list[dict[str, Any]]:
    url = "https://openapi.twse.com.tw/v1/opendata/t187ap45_L"
    try:
        response = requests.get(url, timeout=PRICE_REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        code = normalize_text(item.get("公司代號", ""))
        name = normalize_text(item.get("公司名稱", ""))
        cash = (
            _stock_dividend_number(item.get("股東配發-盈餘分配之現金股利(元/股)", 0))
            + _stock_dividend_number(item.get("股東配發-法定盈餘公積發放之現金(元/股)", 0))
            + _stock_dividend_number(item.get("股東配發-資本公積發放之現金(元/股)", 0))
        )
        stock_per_share = (
            _stock_dividend_number(item.get("股東配發-盈餘轉增資配股(元/股)", 0))
            + _stock_dividend_number(item.get("股東配發-法定盈餘公積轉增資配股(元/股)", 0))
            + _stock_dividend_number(item.get("股東配發-資本公積轉增資配股(元/股)", 0))
        )
        if not code or (cash <= 0 and stock_per_share <= 0):
            continue
        rows.append({
            "code": _plain_stock_code(code),
            "name": name,
            "ex_date": "",
            "cash_dividend_per_share": cash,
            "stock_dividend_per_share": stock_per_share,
            "source": "TWSE",
            "note": f"TWSE 股利分派候選；董事會日 {_parse_stock_api_date(item.get('董事會（擬議）股利分派日', ''))}",
        })
    return rows


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_tpex_stock_dividend_announcements() -> list[dict[str, Any]]:
    url = "https://www.tpex.org.tw/openapi/v1/tpex_exright_prepost"
    try:
        response = requests.get(url, timeout=PRICE_REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        code = normalize_text(item.get("SecuritiesCompanyCode", ""))
        cash = _stock_dividend_number(item.get("CashDividend", 0))
        stock_per_share = _stock_bonus_per_share(item.get("StockDividendRatio", 0))
        if not code or (cash <= 0 and stock_per_share <= 0):
            continue
        rows.append({
            "code": _plain_stock_code(code),
            "name": normalize_text(item.get("CompanyName", "")),
            "ex_date": _parse_stock_api_date(item.get("ExRrightsExDividendDate", "")),
            "cash_dividend_per_share": cash,
            "stock_dividend_per_share": stock_per_share,
            "source": "TPEx",
            "note": f"TPEx 除權除息預告：{normalize_text(item.get('ExRrightsExDividend', ''))}",
        })
    return rows


def scan_stock_dividend_candidates(current_positions: pd.DataFrame) -> int:
    stock_groups = _stock_groups_from_positions(current_positions)
    if not stock_groups:
        return 0
    existing = load_stock_dividend_log()
    existing_keys: set[tuple[str, str, str]] = set()
    if not existing.empty:
        for _, row in existing.iterrows():
            existing_keys.add((
                _plain_stock_code(row.get("ticker", "")),
                _format_dividend_date(row.get("ex_date", "")),
                normalize_text(row.get("source", "")),
            ))
    api_rows = fetch_twse_stock_dividend_announcements() + fetch_tpex_stock_dividend_announcements()
    inserted = 0
    sb = supabase_client()
    for record in api_rows:
        code = _plain_stock_code(record.get("code", ""))
        if code not in stock_groups:
            continue
        grp = stock_groups[code]
        primary = _stock_group_primary_row(grp)
        shares_at_ex = _stock_group_current_units(grp)
        if shares_at_ex <= 0:
            continue
        ticker = normalize_ticker(primary.get("ticker", "")) or _format_tw_stock_ticker(code)
        ex_date = _format_dividend_date(record.get("ex_date", ""))
        source = normalize_text(record.get("source", ""))
        key = (_plain_stock_code(ticker), ex_date, source)
        if key in existing_keys:
            continue
        cash_per_share = normalize_number(record.get("cash_dividend_per_share", 0), 0)
        stock_per_share = normalize_number(record.get("stock_dividend_per_share", 0), 0)
        estimated_cash = shares_at_ex * cash_per_share
        estimated_stock_shares = _stock_bonus_shares(shares_at_ex, stock_per_share)
        if estimated_cash <= 0 and estimated_stock_shares <= 0:
            continue
        sb.table("stock_dividend_log").insert({
            "platform": normalize_text(primary.get("platform", "台股"), "台股"),
            "ticker": ticker,
            "name": normalize_text(primary.get("name", record.get("name", ""))),
            "currency": "TWD",
            "ex_date": ex_date if ex_date != "—" else "",
            "cash_pay_date": "",
            "stock_pay_date": "",
            "shares_at_ex": shares_at_ex,
            "cash_dividend_per_share": cash_per_share,
            "estimated_cash_total": round(estimated_cash, 0),
            "actual_cash_total": 0,
            "stock_dividend_per_share": stock_per_share,
            "estimated_stock_shares": estimated_stock_shares,
            "actual_stock_shares": 0,
            "is_cash_received": False,
            "is_stock_received": False,
            "source": source,
            "note": normalize_text(record.get("note", "")) or "自動掃描候選，請確認除權息日與發放日",
        }).execute()
        existing_keys.add(key)
        inserted += 1
    return inserted


def update_stock_cash_dividend_total(ticker: str, platform: str, delta_cash: float) -> bool:
    delta_cash = normalize_number(delta_cash, 0)
    if delta_cash == 0:
        return False
    target_code = _plain_stock_code(ticker)
    target_platform = normalize_text(platform, "台股")
    rows = supabase_client().table("positions").select(
        "id,sort_order,platform,asset_type,ticker,name,currency,dividend_received_original_total"
    ).eq("platform", target_platform).execute().data or []
    matched = [
        row for row in rows
        if normalize_text(row.get("asset_type", "")) == "台股"
        and (
            _plain_stock_code(row.get("ticker", "")) == target_code
            or _plain_stock_code(TW_PRESETS.get(normalize_text(row.get("name", "")), "")) == target_code
        )
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
    current_total = normalize_number(primary.get("dividend_received_original_total", 0), 0)
    supabase_client().table("positions").update({
        "dividend_received_original_total": max(0, current_total + delta_cash),
        "dividend_received_total": 0,
    }).eq("id", int(float(primary["id"]))).execute()
    return True


def add_zero_cost_stock_dividend_position(ticker: str, platform: str, shares: float, ex_date: str, note: str = "") -> bool:
    shares = normalize_number(shares, 0)
    if shares <= 0:
        return False
    current = ensure_columns(load_positions())
    stocks = current[current["asset_type"].astype(str) == "台股"].copy()
    target_code = _plain_stock_code(ticker)
    matched = stocks[
        (stocks["platform"].astype(str) == normalize_text(platform, "台股"))
        & (
            (stocks["ticker"].apply(_plain_stock_code) == target_code)
            | (stocks["name"].apply(lambda value: _plain_stock_code(TW_PRESETS.get(normalize_text(value), ""))) == target_code)
        )
    ].copy()
    if matched.empty:
        return False
    primary = _stock_group_primary_row(matched)
    next_order = int(normalize_number(current["sort_order"].max(), 0)) + 1 if not current.empty else 1
    parsed_ex = _parse_dividend_date(ex_date)
    payload = normalize_payload({
        "sort_order": next_order,
        "platform": normalize_text(primary.get("platform", "台股"), "台股"),
        "asset_type": "台股",
        "name": normalize_text(primary.get("name", "")),
        "ticker": normalize_ticker(primary.get("ticker", ticker)) or _format_tw_stock_ticker(ticker),
        "fund_code": "",
        "fund_pattern": "",
        "currency": "TWD",
        "original_units": shares,
        "units": shares,
        "corporate_action": f"股票股利 {ex_date} 配發 {money(shares, 4)} 股",
        "avg_cost": 0,
        "total_cost_input": 0,
        "monthly_dividend_per_unit": 0,
        "purchase_ym": parsed_ex.strftime("%Y/%m") if parsed_ex is not None else "",
        "dividend_received_original_total": 0,
        "dividend_received_total": 0,
        "dividend_note": "",
        "note": note or "股票股利新增股數，成本 0",
        "is_reinvest": False,
    })
    supabase_client().table("positions").insert(payload).execute()
    return True


def build_stock_dividend_table() -> pd.DataFrame:
    df = load_stock_dividend_log()
    internal_cols = ["_id", "_ticker", "_platform", "_cash_before", "_stock_before"]
    if df.empty:
        return pd.DataFrame(columns=STOCK_DIVIDEND_COLUMNS + internal_cols)
    rows = []
    for _, row in df.iterrows():
        shares_at_ex = normalize_number(row.get("shares_at_ex", 0), 0)
        cash_per_share = normalize_number(row.get("cash_dividend_per_share", 0), 0)
        stock_per_share = normalize_number(row.get("stock_dividend_per_share", 0), 0)
        estimated_cash = normalize_number(row.get("estimated_cash_total", 0), 0)
        if estimated_cash <= 0 and shares_at_ex > 0 and cash_per_share > 0:
            estimated_cash = shares_at_ex * cash_per_share
        estimated_stock = normalize_number(row.get("estimated_stock_shares", 0), 0)
        if estimated_stock <= 0 and shares_at_ex > 0 and stock_per_share > 0:
            estimated_stock = _stock_bonus_shares(shares_at_ex, stock_per_share)
        rows.append({
            "平台": normalize_text(row.get("platform", "台股"), "台股"),
            "股票名稱": normalize_text(row.get("name", "")),
            "股票代碼": normalize_ticker(row.get("ticker", "")),
            "除權息日": _format_dividend_date(row.get("ex_date", "")),
            "現金發放日": _format_dividend_date(row.get("cash_pay_date", "")),
            "股票發放日": _format_dividend_date(row.get("stock_pay_date", "")),
            "除權息股數": shares_at_ex,
            "每股現金股利": cash_per_share,
            "預估現金股利": estimated_cash if estimated_cash > 0 else None,
            "實際現金股利": normalize_number(row.get("actual_cash_total", 0), 0),
            "確認現金入帳": normalize_bool(row.get("is_cash_received", False), False),
            "每股股票股利": stock_per_share,
            "預估股票股數": estimated_stock if estimated_stock > 0 else None,
            "實際股票股數": normalize_number(row.get("actual_stock_shares", 0), 0),
            "確認股票入帳": normalize_bool(row.get("is_stock_received", False), False),
            "備註": normalize_text(row.get("note", "")),
            "_id": row.get("id"),
            "_ticker": normalize_ticker(row.get("ticker", "")),
            "_platform": normalize_text(row.get("platform", "台股"), "台股"),
            "_cash_before": normalize_bool(row.get("is_cash_received", False), False),
            "_stock_before": normalize_bool(row.get("is_stock_received", False), False),
        })
    out = pd.DataFrame(rows)
    out["_sort_date"] = out["除權息日"].apply(lambda value: _parse_dividend_date(value) or datetime.min.date())
    out = out.sort_values("_sort_date", ascending=False).drop(columns=["_sort_date"]).reset_index(drop=True)
    return out[STOCK_DIVIDEND_COLUMNS + internal_cols]


def _stock_position_options(current_positions: pd.DataFrame) -> tuple[list[str], dict[str, dict[str, Any]]]:
    groups = _stock_groups_from_positions(current_positions)
    options: list[str] = []
    lookup: dict[str, dict[str, Any]] = {}
    for code, grp in groups.items():
        primary = _stock_group_primary_row(grp)
        units = _stock_group_current_units(grp)
        ticker = normalize_ticker(primary.get("ticker", "")) or _format_tw_stock_ticker(code)
        label = f"{normalize_text(primary.get('platform', '台股'))}｜{ticker}｜{primary.get('name', '')}｜目前 {money(units, 4)} 股"
        options.append(label)
        lookup[label] = {
            "platform": normalize_text(primary.get("platform", "台股"), "台股"),
            "ticker": ticker,
            "name": normalize_text(primary.get("name", "")),
            "shares": units,
        }
    return options, lookup


def render_manual_stock_dividend_form(current_positions: pd.DataFrame) -> None:
    with st.expander("➕ 手動新增台股股利記錄", expanded=False):
        options, lookup = _stock_position_options(current_positions)
        if not options:
            st.info("目前沒有台股持倉。")
            return
        with st.form("manual_stock_dividend_form"):
            choice = st.selectbox("股票", options, key="manual_stock_dividend_choice")
            selected = lookup.get(choice, {})
            c1, c2, c3 = st.columns(3)
            ex_date = c1.text_input("除權息日（YYYY/MM/DD）", key="manual_stock_dividend_ex_date")
            cash_pay_date = c2.text_input("現金發放日（YYYY/MM/DD）", key="manual_stock_dividend_cash_pay_date")
            stock_pay_date = c3.text_input("股票發放日（YYYY/MM/DD）", key="manual_stock_dividend_stock_pay_date")
            c4, c5, c6 = st.columns(3)
            shares_at_ex = c4.number_input(
                "除權息股數",
                value=float(selected.get("shares", 0) or 0),
                format="%.4f",
                key="manual_stock_dividend_shares",
            )
            cash_per_share = c5.number_input("每股現金股利", value=0.0, format="%.4f", key="manual_stock_dividend_cash_per_share")
            stock_per_share = c6.number_input("每股股票股利", value=0.0, format="%.4f", key="manual_stock_dividend_stock_per_share")
            est_cash = shares_at_ex * cash_per_share
            est_stock = _stock_bonus_shares(shares_at_ex, stock_per_share)
            st.caption(f"預估現金股利：**{money(est_cash)}**｜預估股票股利股數：**{money(est_stock, 4)} 股**")
            note = st.text_input("備註", key="manual_stock_dividend_note")
            submitted = st.form_submit_button("新增台股股利記錄")
        if submitted:
            if not selected or not ex_date:
                st.error("股票和除權息日必填。")
                return
            try:
                supabase_client().table("stock_dividend_log").insert({
                    "platform": selected["platform"],
                    "ticker": selected["ticker"],
                    "name": selected["name"],
                    "currency": "TWD",
                    "ex_date": ex_date,
                    "cash_pay_date": cash_pay_date,
                    "stock_pay_date": stock_pay_date,
                    "shares_at_ex": shares_at_ex,
                    "cash_dividend_per_share": cash_per_share,
                    "estimated_cash_total": round(est_cash, 0),
                    "actual_cash_total": 0,
                    "stock_dividend_per_share": stock_per_share,
                    "estimated_stock_shares": est_stock,
                    "actual_stock_shares": 0,
                    "is_cash_received": False,
                    "is_stock_received": False,
                    "source": "manual",
                    "note": note,
                }).execute()
                st.success("已新增台股股利記錄。")
                st.cache_data.clear()
                st.rerun()
            except Exception as exc:
                st.error(f"新增失敗：{exc}")


def _stock_dividend_upload_template() -> pd.DataFrame:
    return pd.DataFrame([{
        "平台": "台股",
        "股票代碼": "0056.TW",
        "股票名稱": "",
        "除權息日": "2026/07/01",
        "現金發放日": "2026/07/31",
        "股票發放日": "",
        "除權息股數": 0,
        "每股現金股利": 0,
        "實際現金股利": 0,
        "每股股票股利": 0,
        "實際股票股數": 0,
        "確認現金入帳": "是",
        "確認股票入帳": "否",
        "備註": "歷史補資料",
    }])


def _normalize_stock_dividend_upload(upload_df: pd.DataFrame, current_positions: pd.DataFrame) -> pd.DataFrame:
    lookup: dict[str, dict[str, Any]] = {}
    for code, grp in _stock_groups_from_positions(current_positions).items():
        primary = _stock_group_primary_row(grp)
        ticker = normalize_ticker(primary.get("ticker", "")) or _format_tw_stock_ticker(code)
        lookup[_plain_stock_code(ticker)] = {
            "platform": normalize_text(primary.get("platform", "台股"), "台股"),
            "ticker": ticker,
            "name": normalize_text(primary.get("name", "")),
            "shares": _stock_group_current_units(grp),
        }
    rows: list[dict[str, Any]] = []
    for idx, raw in upload_df.iterrows():
        raw_ticker = normalize_text(raw.get("股票代碼", ""))
        position_info = lookup.get(_plain_stock_code(raw_ticker), {})
        ticker = normalize_ticker(raw_ticker) or position_info.get("ticker", "")
        if ticker and "." not in ticker:
            ticker = _format_tw_stock_ticker(ticker, position_info.get("ticker", ""))
        platform = normalize_text(raw.get("平台", "")) or position_info.get("platform", "台股")
        name = normalize_text(raw.get("股票名稱", "")) or position_info.get("name", "")
        shares_at_ex = normalize_number(raw.get("除權息股數", 0), 0) or normalize_number(position_info.get("shares", 0), 0)
        cash_per_share = normalize_number(raw.get("每股現金股利", 0), 0)
        stock_per_share = normalize_number(raw.get("每股股票股利", 0), 0)
        actual_cash = normalize_number(raw.get("實際現金股利", 0), 0) or shares_at_ex * cash_per_share
        actual_stock_shares = normalize_number(raw.get("實際股票股數", 0), 0) or _stock_bonus_shares(shares_at_ex, stock_per_share)
        errors = []
        if not ticker:
            errors.append("股票代碼必填")
        if not normalize_text(raw.get("除權息日", "")):
            errors.append("除權息日必填")
        if shares_at_ex <= 0:
            errors.append("除權息股數必填，或持倉內需有目前股數")
        if cash_per_share <= 0 and stock_per_share <= 0 and actual_cash <= 0 and actual_stock_shares <= 0:
            errors.append("現金股利或股票股利至少填一個")
        rows.append({
            "狀態": "可匯入" if not errors else " / ".join(errors),
            "平台": platform,
            "股票代碼": ticker,
            "股票名稱": name,
            "除權息日": normalize_text(raw.get("除權息日", "")),
            "現金發放日": normalize_text(raw.get("現金發放日", "")),
            "股票發放日": normalize_text(raw.get("股票發放日", "")),
            "除權息股數": shares_at_ex,
            "每股現金股利": cash_per_share,
            "預估現金股利": shares_at_ex * cash_per_share,
            "實際現金股利": actual_cash,
            "確認現金入帳": normalize_bool(raw.get("確認現金入帳", False), False),
            "每股股票股利": stock_per_share,
            "預估股票股數": _stock_bonus_shares(shares_at_ex, stock_per_share),
            "實際股票股數": actual_stock_shares,
            "確認股票入帳": normalize_bool(raw.get("確認股票入帳", False), False),
            "備註": normalize_text(raw.get("備註", "")) or "批次匯入",
            "_row_number": idx + 2,
        })
    return pd.DataFrame(rows)


def apply_stock_dividend_upload(preview_df: pd.DataFrame) -> tuple[int, int, int, list[str]]:
    sb = supabase_client()
    inserted = 0
    cash_synced = 0
    stock_rows_added = 0
    warnings: list[str] = []
    for _, row in preview_df.iterrows():
        if normalize_text(row.get("狀態", "")) != "可匯入":
            continue
        ticker = normalize_text(row.get("股票代碼", ""))
        platform = normalize_text(row.get("平台", "台股"), "台股")
        actual_cash = normalize_number(row.get("實際現金股利", 0), 0)
        actual_stock_shares = normalize_number(row.get("實際股票股數", 0), 0)
        cash_received = normalize_bool(row.get("確認現金入帳", False), False)
        stock_received = normalize_bool(row.get("確認股票入帳", False), False)
        payload = {
            "platform": platform,
            "ticker": ticker,
            "name": normalize_text(row.get("股票名稱", "")),
            "currency": "TWD",
            "ex_date": normalize_text(row.get("除權息日", "")),
            "cash_pay_date": normalize_text(row.get("現金發放日", "")),
            "stock_pay_date": normalize_text(row.get("股票發放日", "")),
            "shares_at_ex": normalize_number(row.get("除權息股數", 0), 0),
            "cash_dividend_per_share": normalize_number(row.get("每股現金股利", 0), 0),
            "estimated_cash_total": normalize_number(row.get("預估現金股利", 0), 0),
            "actual_cash_total": actual_cash,
            "stock_dividend_per_share": normalize_number(row.get("每股股票股利", 0), 0),
            "estimated_stock_shares": normalize_number(row.get("預估股票股數", 0), 0),
            "actual_stock_shares": actual_stock_shares,
            "is_cash_received": cash_received,
            "is_stock_received": stock_received,
            "source": "upload",
            "note": normalize_text(row.get("備註", "批次匯入")),
        }
        sb.table("stock_dividend_log").insert(payload).execute()
        inserted += 1
        if cash_received and actual_cash > 0:
            if update_stock_cash_dividend_total(ticker, platform, actual_cash):
                cash_synced += 1
            else:
                warnings.append(f"第 {int(row.get('_row_number', 0))} 列現金股利已匯入，但找不到台股主列可同步：{ticker}")
        if stock_received and actual_stock_shares > 0:
            if add_zero_cost_stock_dividend_position(ticker, platform, actual_stock_shares, normalize_text(row.get("除權息日", "")), f"股票股利批次匯入：{normalize_text(row.get('股票名稱', ''))}"):
                stock_rows_added += 1
            else:
                warnings.append(f"第 {int(row.get('_row_number', 0))} 列股票股利已匯入，但新增 0 成本持倉失敗：{ticker}")
    return inserted, cash_synced, stock_rows_added, warnings


def render_stock_dividend_upload_section(current_positions: pd.DataFrame) -> None:
    with st.expander("📤 批次匯入台股股利補資料（CSV / Excel）", expanded=False):
        st.caption("適合補今年或歷史台股股利。股票股利確認入帳後會新增 0 成本持倉列。")
        template = _stock_dividend_upload_template()
        st.download_button(
            "下載台股股利補資料範本 CSV",
            data=template.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
            file_name="stock_dividend_upload_template.csv",
            mime="text/csv",
            key="download_stock_dividend_upload_template",
        )
        uploaded = st.file_uploader("上傳台股股利補資料 CSV / Excel", type=["csv", "xlsx", "xls"], key="stock_dividend_upload_file")
        if uploaded is None:
            return
        try:
            upload_df = read_uploaded_table(uploaded)
            missing = [col for col in STOCK_DIVIDEND_UPLOAD_COLUMNS if col not in upload_df.columns]
            if missing:
                st.error("上傳檔案缺少欄位：" + "、".join(missing))
                return
            preview = _normalize_stock_dividend_upload(upload_df, current_positions)
            st.dataframe(
                right_align_numbers(preview.drop(columns=[c for c in preview.columns if c.startswith("_")], errors="ignore")),
                use_container_width=True,
                hide_index=True,
                height=min(42 * len(preview) + 44, 520),
            )
            valid_count = int((preview["狀態"] == "可匯入").sum())
            st.caption(f"可匯入 {valid_count} 筆，錯誤 {len(preview) - valid_count} 筆。")
            confirm = st.checkbox("確認匯入台股股利補資料", key="confirm_stock_dividend_upload")
            if st.button("匯入台股股利補資料", disabled=not confirm or valid_count <= 0, key="apply_stock_dividend_upload"):
                inserted, cash_synced, stock_rows_added, warnings = apply_stock_dividend_upload(preview)
                st.success(f"已匯入 {inserted} 筆；現金股利同步 {cash_synced} 筆；股票股利新增 0 成本持倉 {stock_rows_added} 筆。")
                if warnings:
                    st.warning("\n".join(warnings[:20]))
                st.cache_data.clear()
                st.rerun()
        except Exception as exc:
            st.error(f"匯入失敗：{exc}")


def render_stock_dividend_tab(enriched_df: pd.DataFrame, current_positions: pd.DataFrame) -> None:
    st.subheader("📈 台股股利")
    st.caption("現金股利會加到台股累計配息；股票股利會新增一筆 0 成本持倉列，不會改原本成本。")
    action_col1, action_col2 = st.columns([1, 1])
    if action_col1.button("掃描台股股利候選", key="scan_stock_dividend_candidates"):
        try:
            n = scan_stock_dividend_candidates(current_positions)
            if n:
                st.success(f"已新增 {n} 筆台股股利候選。")
                st.cache_data.clear()
                st.rerun()
            else:
                st.info("沒有新的台股股利候選。")
        except Exception as exc:
            st.error(f"掃描失敗：{exc}")
    if action_col2.button("清除台股股利快取", key="clear_stock_dividend_cache"):
        st.cache_data.clear()
        st.rerun()
    table_df = build_stock_dividend_table()
    received_cash_this_year = stock_cash_dividend_total_for_year(tw_now().year)
    estimated_cash = table_df["預估現金股利"].fillna(0).sum() if not table_df.empty and "預估現金股利" in table_df else 0
    estimated_stock = table_df["預估股票股數"].fillna(0).sum() if not table_df.empty and "預估股票股數" in table_df else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("今年台股現金股利", money(received_cash_this_year))
    c2.metric("預估現金股利", money(estimated_cash))
    c3.metric("預估股票股利股數", money(estimated_stock, 4))
    c4.metric("台股股利記錄筆數", f"{len(table_df):,}")
    if table_df.empty:
        st.info("目前沒有台股股利記錄。可先按「掃描台股股利候選」或手動新增。")
        render_stock_dividend_upload_section(current_positions)
        render_manual_stock_dividend_form(current_positions)
        return
    display_df = table_df[STOCK_DIVIDEND_COLUMNS].copy()
    col_cfg = {
        "股票名稱": st.column_config.TextColumn("股票名稱", width="large"),
        "股票代碼": st.column_config.TextColumn("股票代碼", width="small"),
        "除權息股數": st.column_config.NumberColumn("除權息股數", format="localized"),
        "每股現金股利": st.column_config.NumberColumn("每股現金股利", format="%.4f"),
        "預估現金股利": st.column_config.NumberColumn("預估現金股利", format="localized"),
        "實際現金股利": st.column_config.NumberColumn("實際現金股利", format="localized"),
        "確認現金入帳": st.column_config.CheckboxColumn("確認現金入帳"),
        "每股股票股利": st.column_config.NumberColumn("每股股票股利", format="%.4f"),
        "預估股票股數": st.column_config.NumberColumn("預估股票股數", format="%.4f"),
        "實際股票股數": st.column_config.NumberColumn("實際股票股數", format="%.4f"),
        "確認股票入帳": st.column_config.CheckboxColumn("確認股票入帳"),
    }
    edited = st.data_editor(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=min(42 * len(display_df) + 44, 620),
        column_config=col_cfg,
        disabled=[col for col in STOCK_DIVIDEND_COLUMNS if col not in {"實際現金股利", "確認現金入帳", "實際股票股數", "確認股票入帳", "備註"}],
        key="stock_dividend_editor",
    )
    if st.button("儲存台股股利確認", key="save_stock_dividend_confirm"):
        sb = supabase_client()
        updated = 0
        warnings: list[str] = []
        for pos, (_, row) in enumerate(edited.iterrows()):
            source = table_df.iloc[pos]
            row_id = source.get("_id")
            if row_id is None or normalize_text(row_id, "") in {"", "nan", "None"}:
                continue
            old_cash = normalize_bool(source.get("_cash_before", False), False)
            new_cash = normalize_bool(row.get("確認現金入帳", False), False)
            old_stock = normalize_bool(source.get("_stock_before", False), False)
            new_stock = normalize_bool(row.get("確認股票入帳", False), False)
            estimated_cash_total = normalize_number(row.get("預估現金股利", 0), 0)
            actual_cash_total = normalize_number(row.get("實際現金股利", 0), 0) or estimated_cash_total
            estimated_stock_shares = normalize_number(row.get("預估股票股數", 0), 0)
            actual_stock_shares = normalize_number(row.get("實際股票股數", 0), 0) or estimated_stock_shares
            payload = {
                "actual_cash_total": actual_cash_total,
                "actual_stock_shares": actual_stock_shares,
                "is_cash_received": new_cash,
                "is_stock_received": new_stock if not (old_stock and not new_stock) else True,
                "note": normalize_text(row.get("備註", "")),
            }
            if old_stock and not new_stock:
                warnings.append(f"{row.get('股票代碼', '')} 股票股利已入帳過，不自動刪除新增的 0 成本持倉列。")
            sb.table("stock_dividend_log").update(payload).eq("id", int(float(row_id))).execute()
            if old_cash != new_cash and actual_cash_total > 0:
                delta = actual_cash_total if new_cash else -actual_cash_total
                if not update_stock_cash_dividend_total(normalize_text(source.get("_ticker", row.get("股票代碼", ""))), normalize_text(source.get("_platform", row.get("平台", "台股"))), delta):
                    warnings.append(f"{row.get('股票代碼', '')} 現金股利已更新記錄，但找不到台股主列可同步累計。")
            if not old_stock and new_stock and actual_stock_shares > 0:
                if not add_zero_cost_stock_dividend_position(normalize_text(source.get("_ticker", row.get("股票代碼", ""))), normalize_text(source.get("_platform", row.get("平台", "台股"))), actual_stock_shares, normalize_text(row.get("除權息日", "")), f"股票股利入帳：{row.get('股票名稱', '')}"):
                    warnings.append(f"{row.get('股票代碼', '')} 股票股利已更新記錄，但新增 0 成本持倉失敗。")
            updated += 1
        if warnings:
            st.warning("\n".join(warnings))
        if updated:
            st.success(f"已更新 {updated} 筆台股股利記錄。")
            st.cache_data.clear()
            st.rerun()
        else:
            st.info("沒有需要更新的台股股利記錄。")
    render_stock_dividend_upload_section(current_positions)
    render_manual_stock_dividend_form(current_positions)
