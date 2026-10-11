"""基金配息：自動快照／認列、預估與實際配息表、配息記錄頁。"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st
from invest_app.core import (
    load_sheet_raw_grid,
    html_table,
    OVERVIEW_SHEET_GID,
    load_sheet_grid,
    CURRENCIES,
    PLATFORMS,
    _format_dividend_date,
    _get_gas_data,
    _parse_dividend_date,
    ensure_columns,
    fetch_fx,
    load_positions,
    money,
    normalize_bool,
    normalize_match_name,
    normalize_number,
    normalize_text,
    supabase_client,
    tw_now,
)


def _date_diff_days(date_str: str) -> int | None:
    """YYYY/MM/DD 距今幾天（負=過去，正=未來）"""
    try:
        from datetime import date
        parts = date_str.split("/")
        d = date(int(parts[0]), int(parts[1]), int(parts[2]))
        return (d - date.today()).days
    except Exception:
        return None


def _position_counts_on_ex_date(row: pd.Series, ex_date: str | None) -> bool:
    if not ex_date:
        return True
    purchase_date = _parse_dividend_date(row.get("purchase_ym", ""))
    ex_dt = _parse_dividend_date(ex_date)
    if purchase_date is None or ex_dt is None:
        return True
    return purchase_date <= ex_dt


def _position_dividend_units(row: pd.Series) -> float:
    units = normalize_number(row.get("units", 0), 0)
    original_units = normalize_number(row.get("original_units", 0), 0)
    note = normalize_text(row.get("note", ""))
    is_closed = any(term in note for term in ["已賣出", "已結清", "結清", "賣出"])
    return units if units > 0 or is_closed else original_units


def _fund_name_from_rows(rows: list[pd.Series]) -> str:
    names: list[str] = []
    for row in rows:
        name = normalize_text(row.get("name", ""))
        if name and name not in names:
            names.append(name)
    return " / ".join(names[:2])


def auto_dividend_update(positions: pd.DataFrame, recognize: bool = True) -> int:
    """
    按「執行配息快照 / 認列」時執行：
    1. 【快照】今天在 [ex_date-1天, ex_date+2天] 且該基金當月還沒有記錄
       → 加總同基金所有 units → 寫入 fund_dividends
    2. 【認列】pay_date <= 今天 且 is_paid=False（只有按按鈕時；recognize=False 時跳過，由人工確認入帳）
       → twd_total = units_at_ex × actual_div_amount × fx_rate
       → is_paid = True
       → 依已確認記錄去重後重算持倉累計配息
    回傳：更新筆數
    """
    from datetime import date as dt_date
    today_str = dt_date.today().strftime("%Y/%m/%d")
    today = dt_date.today()

    positions = ensure_columns(pd.DataFrame(positions))

    if positions.empty:
        return 0

    sb = supabase_client()
    updated = 0

    # 取得所有已有記錄的 fund_dividends
    try:
        existing_rows = sb.table("fund_dividends").select("fund_code,fund_name,platform,currency,ex_date,pay_date,is_paid,units_at_ex,div_amount,actual_div_amount,fx_rate,twd_total,id").execute()
        existing = {
            (r["fund_code"], r["platform"], r["currency"], r["ex_date"]): r
            for r in (existing_rows.data or [])
        }
    except Exception:
        existing = {}

    # 每檔基金每月只能有一筆：已有同月記錄（任一表、任一除息日）就不再新增
    month_keys = _existing_dividend_record_keys(_combined_dividend_records())

    # 按基金分組處理
    fund_groups: dict[tuple, list[pd.Series]] = {}
    for _, r in positions.iterrows():
        if normalize_text(r.get("asset_type","")) != "基金":
            continue
        fc  = normalize_text(r.get("fund_code",""))
        plt = normalize_text(r.get("platform",""))
        cur = normalize_text(r.get("currency","TWD"))
        if not fc:
            continue
        key = (fc, plt, cur)
        fund_groups.setdefault(key, []).append(r)

    for (fc, plt, cur), rows in fund_groups.items():
        gas = _get_gas_data(fc)
        ex_date  = gas.get("ex_date")   # YYYY/MM/DD
        pay_date = gas.get("pay_date")  # YYYY/MM/DD
        div_amt  = gas.get("monthly_div")

        if not ex_date or not div_amt:
            continue

        # 取即時匯率
        fx_val, _ = fetch_fx(cur)
        fx_val = fx_val or 1.0

        exist_key = (fc, plt, cur, ex_date)
        exist_row = existing.get(exist_key)

        # ── Step 1：快照（除息日前 1 天到除息後 45 天內，且還沒有記錄；過期沒按到的會補登）──
        diff = _date_diff_days(ex_date)
        month_key = _dividend_business_key(fc, plt, cur, _fund_name_from_rows(rows), ex_date, pay_date)
        if diff is not None and -1 <= diff <= 2 and not exist_row and month_key not in month_keys:
            # 加總這個基金所有持倉的單位數
            total_units = sum(
                _position_dividend_units(r)
                for r in rows
                if _position_counts_on_ex_date(r, ex_date)
            )
            if total_units > 0:
                try:
                    sb.table("fund_dividends").insert({
                        "fund_code":   fc,
                        "fund_name":   _fund_name_from_rows(rows),
                        "platform":    plt,
                        "currency":    cur,
                        "ex_date":     ex_date,
                        "pay_date":    pay_date,
                        "div_amount":  float(div_amt),
                        "actual_div_amount": 0,
                        "units_at_ex": float(total_units),
                        "fx_rate":     float(fx_val),
                        "twd_total":   0,
                        "is_paid":     False,
                    }).execute()
                    exist_row = {
                        "fund_code": fc, "platform": plt, "currency": cur,
                        "ex_date": ex_date, "pay_date": pay_date,
                        "div_amount": div_amt, "units_at_ex": total_units,
                        "actual_div_amount": 0, "fx_rate": fx_val, "is_paid": False,
                    }
                    updated += 1
                except Exception:
                    pass  # 唯一鍵衝突表示已存在

        # ── Step 2：認列（發放日已到，且 is_paid=False）──
        if not recognize:
            continue
        if not exist_row:
            continue
        if exist_row.get("is_paid"):
            continue
        if not pay_date:
            continue

        diff_pay = _date_diff_days(pay_date)
        if diff_pay is None or diff_pay > 0:
            continue  # 發放日還沒到

        # 計算台幣配息總額
        units_at_ex = float(exist_row.get("units_at_ex") or 0)
        fx_at_ex    = float(exist_row.get("fx_rate") or fx_val)
        div_amount  = float(exist_row.get("div_amount") or div_amt)
        actual_div_amount = float(exist_row.get("actual_div_amount") or div_amount)
        twd_total   = units_at_ex * actual_div_amount * fx_at_ex

        if twd_total <= 0:
            continue

        # 更新 fund_dividends
        try:
            row_id = exist_row.get("id")
            if row_id:
                sb.table("fund_dividends").update({
                    "is_paid":   True,
                    "twd_total": twd_total,
                    "actual_div_amount": actual_div_amount,
                    "fx_rate":   fx_at_ex,
                    "updated_at": "now()",
                }).eq("id", int(row_id)).execute()

            recompute_position_dividend_original_total(fc, plt, cur, pay_date)

            updated += 1
        except Exception:
            pass

    return updated


ESTIMATED_DIVIDEND_COLUMNS = [
    "平台",
    "基金名稱",
    "幣別",
    "目前單位數",
    "除息日期",
    "每單位配息",
    "預估配息原幣",
    "匯率",
    "預估配息台幣",
]


ACTUAL_DIVIDEND_COLUMNS = [
    "平台",
    "基金名稱",
    "幣別",
    "配息單位數",
    "發放日期",
    "每單位配息",
    "實際配息原幣",
    "匯率",
    "實際配息台幣",
    "確認入帳",
    "累計配息原幣",
    "總帳累積配息原幣",
    "累計配息台幣",
    "總帳累積配息台幣",
]


def _fund_name_lookup(enriched_df: pd.DataFrame) -> dict[tuple[str, str, str], str]:
    lookup: dict[tuple[str, str, str], str] = {}
    if enriched_df is None or enriched_df.empty:
        return lookup
    funds = enriched_df[enriched_df["asset_type"].astype(str) == "基金"].copy()
    for _, row in funds.iterrows():
        fc = normalize_text(row.get("fund_code", ""))
        platform = normalize_text(row.get("platform", ""))
        currency = normalize_text(row.get("currency", ""))
        name = normalize_text(row.get("name", ""))
        if not name:
            continue
        lookup[(fc, platform, currency)] = name
        lookup[(fc, "", currency)] = name
        lookup[(fc, "", "")] = name
    return lookup


def _fund_lookup_key(fund_code: Any, platform: Any, currency: Any, name: Any = "") -> tuple[str, str, str]:
    key_code = normalize_text(fund_code).lower() or normalize_match_name(name)
    return (
        key_code,
        normalize_text(platform),
        normalize_text(currency).upper(),
    )


def _position_dividend_total_lookup(enriched_df: pd.DataFrame) -> dict[tuple[str, str, str], dict[str, float]]:
    lookup: dict[tuple[str, str, str], dict[str, float]] = {}
    try:
        source_df = ensure_columns(load_positions())
    except Exception:
        source_df = pd.DataFrame()

    if source_df.empty and enriched_df is not None and not enriched_df.empty:
        source_df = ensure_columns(enriched_df)

    if source_df.empty:
        return lookup

    funds = source_df[source_df["asset_type"].astype(str) == "基金"].copy()
    if funds.empty:
        return lookup

    funds["_sort_num"] = funds["sort_order"].apply(lambda v: normalize_number(v, 999999))
    funds["_id_num"] = funds["id"].apply(lambda v: normalize_number(v, 999999))
    for _, grp in funds.groupby(
        funds.apply(
            lambda r: _fund_lookup_key(
                r.get("fund_code", ""),
                r.get("platform", ""),
                r.get("currency", ""),
                r.get("name", ""),
            ),
            axis=1,
        ),
        dropna=False,
    ):
        grp = grp.sort_values(["_sort_num", "_id_num"]).copy()
        first = grp.iloc[0]
        key = _fund_lookup_key(
            first.get("fund_code", ""),
            first.get("platform", ""),
            first.get("currency", ""),
            first.get("name", ""),
        )
        primary_original = normalize_number(first.get("dividend_received_original_total", first.get("累計配息原幣", 0)), 0)
        group_original = sum(
            normalize_number(v, 0)
            for v in grp.get("dividend_received_original_total", grp.get("累計配息原幣", pd.Series(dtype=float))).tolist()
        )
        original_total = primary_original if primary_original > 0 else group_original
        fx = _first_positive(grp.get("匯率", pd.Series(dtype=float)).tolist())
        lookup[key] = {
            "original": original_total,
            "fx": fx,
        }
    return lookup


def _position_dividend_totals_for(
    lookup: dict[tuple[str, str, str], dict[str, float]],
    fund_code: Any,
    platform: Any,
    currency: Any,
    name: Any = "",
    fx: float = 1.0,
) -> dict[str, float]:
    key = _fund_lookup_key(fund_code, platform, currency, name)
    totals = lookup.get(key, {})
    original = normalize_number(totals.get("original", 0), 0)
    fx_value = normalize_number(fx, 0)
    if fx_value <= 0:
        fx_value = normalize_number(totals.get("fx", 0), 0)
    twd = original * fx_value if fx_value > 0 else 0
    return {"original": original, "twd": twd, "fx": fx_value}


def _first_positive(values: list[Any]) -> float:
    for value in values:
        number = normalize_number(value, 0)
        if number > 0:
            return number
    return 0.0


def _latest_past_date(values: list[Any]) -> str:
    today = tw_now().date()
    parsed_dates = []
    for value in values:
        parsed = _parse_dividend_date(value)
        if parsed is not None and parsed < today:
            parsed_dates.append(parsed)
    if not parsed_dates:
        return "—"
    return max(parsed_dates).strftime("%Y/%m/%d")


def _dividend_record_variants(fund_code: str, platform: str, currency: str) -> list[tuple[str, str, str]]:
    return [
        (fund_code, platform, currency),
        (fund_code, "", currency),
        (fund_code, platform, ""),
        (fund_code, "", ""),
    ]


def _dividend_history_index(records: list[dict[str, Any]]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        fund_code = normalize_text(record.get("fund_code", ""))
        platform = normalize_text(record.get("platform", ""))
        currency = normalize_text(record.get("currency", ""))
        for key in _dividend_record_variants(fund_code, platform, currency):
            index.setdefault(key, []).append(record)
    return index


def _history_records_for(
    index: dict[tuple[str, str, str], list[dict[str, Any]]],
    fund_code: str,
    platform: str,
    currency: str,
) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for key in _dividend_record_variants(fund_code, platform, currency):
        for record in index.get(key, []):
            marker = (normalize_text(record.get("_source_table", "")), normalize_text(record.get("id", "")))
            if marker in seen:
                continue
            seen.add(marker)
            rows.append(record)
    return rows


def _latest_past_record(records: list[dict[str, Any]], date_col: str) -> dict[str, Any] | None:
    today = tw_now().date()
    candidates: list[tuple[Any, dict[str, Any]]] = []
    for record in records:
        parsed = _parse_dividend_date(record.get(date_col, ""))
        if parsed is not None and parsed < today:
            candidates.append((parsed, record))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0], reverse=True)[0][1]


def _record_date_key(record: dict[str, Any]) -> str:
    """配息月份（YYYY/MM）：每檔基金每月只算一筆，優先用發放日，沒有才用除息日。"""
    for field in ("pay_date", "ex_date"):
        date = _format_dividend_date(record.get(field, ""))
        if date != "—":
            return date[:7]
    return ""


def _dividend_name_key(value: Any) -> str:
    text = normalize_match_name(value)
    for old, new in {
        "Ｕ": "u", "Ｙ": "y", "Ａ": "a", "Ｂ": "b",
        "（": "(", "）": ")", "－": "-", "–": "-", "—": "-",
    }.items():
        text = text.replace(old.lower(), new).replace(old, new)
    return text


def _dividend_business_key(
    fund_code: Any,
    platform: Any,
    currency: Any,
    fund_name: Any,
    ex_date: Any,
    pay_date: Any,
) -> tuple[str, str, str, str]:
    fund_key = _dividend_name_key(fund_name) or normalize_text(fund_code).lower()
    date_key = _record_date_key({"ex_date": ex_date, "pay_date": pay_date})
    return (
        fund_key,
        normalize_text(platform),
        normalize_text(currency).upper(),
        date_key,
    )


def _dividend_record_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    return _dividend_business_key(
        record.get("fund_code", ""),
        record.get("platform", ""),
        record.get("currency", ""),
        record.get("fund_name", record.get("name", "")),
        record.get("ex_date", ""),
        record.get("pay_date", ""),
    )


def _dividend_record_rank(record: dict[str, Any]) -> tuple:
    """同基金同月多筆時保留：已入帳 > fund_dividends > 較早建立（id 小）。"""
    try:
        record_id = int(float(record.get("id") or 0))
    except (TypeError, ValueError):
        record_id = 0
    return (
        0 if normalize_bool(record.get("is_paid", False), False) else 1,
        0 if record.get("_source_table") == "fund_dividends" else 1,
        record_id,
    )


def _split_dividend_records() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """fund_dividends + dividend_log，每檔基金每月一筆；回傳（保留的, 重複的）。"""
    records = [dict(r, _source_table="fund_dividends") for r in _fetch_dividend_rows("fund_dividends")]
    records += [dict(r, _source_table="dividend_log") for r in _fetch_dividend_rows("dividend_log")]
    kept: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    unkeyed: list[dict[str, Any]] = []
    for record in sorted(records, key=_dividend_record_rank):
        key = _dividend_record_key(record)
        if not key[0] or not key[3]:
            unkeyed.append(record)
        elif key in kept:
            # 同月重複：保留的那筆缺日期／名稱時，用另一份補上（例如 fund_dividends 沒有發放日、dividend_log 有）
            target = kept[key]
            for field in ("pay_date", "ex_date", "fund_name"):
                if normalize_text(target.get(field, "")) in {"", "—", "None", "nan"} and normalize_text(record.get(field, "")):
                    target[field] = record.get(field)
            duplicates.append(record)
        else:
            kept[key] = record
    return list(kept.values()) + unkeyed, duplicates


def _combined_dividend_records() -> list[dict[str, Any]]:
    return _split_dividend_records()[0]


def _existing_dividend_record_keys(records: list[dict[str, Any]]) -> set[tuple[str, str, str, str]]:
    keys: set[tuple[str, str, str, str]] = set()
    for record in records:
        key = _dividend_record_key(record)
        if key[0] and key[3]:
            keys.add(key)
    return keys


def _fund_dividend_groups(enriched_df: pd.DataFrame) -> list[tuple[tuple[str, str, str], pd.DataFrame]]:
    if enriched_df is None or enriched_df.empty:
        return []
    funds = enriched_df[enriched_df["asset_type"].astype(str) == "基金"].copy()
    if funds.empty:
        return []
    funds["_dividend_key"] = funds.apply(
        lambda r: (
            normalize_text(r.get("platform", "")),
            normalize_text(r.get("fund_code", "")) or normalize_match_name(r.get("name", "")),
            normalize_text(r.get("currency", "")).upper(),
        ),
        axis=1,
    )
    return [(key, grp.copy()) for key, grp in funds.groupby("_dividend_key", dropna=False)]


def _dividend_estimate_from_group(
    grp: pd.DataFrame,
    history_index: dict[tuple[str, str, str], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    if grp.empty:
        return None
    first = grp.iloc[0]
    platform = normalize_text(first.get("platform", ""))
    fund_code = normalize_text(first.get("fund_code", ""))
    currency = normalize_text(first.get("currency", "")).upper()
    fund_name = normalize_text(first.get("name", ""))
    units = sum(normalize_number(r.get("市值股數", r.get("units", 0)), 0) for _, r in grp.iterrows())
    if units <= 0:
        return None

    history_rows = _history_records_for(history_index, fund_code, platform, currency)
    latest_history = _latest_past_record(history_rows, "ex_date") or _latest_past_record(history_rows, "pay_date")
    gas = _get_gas_data(fund_code) if fund_code else {}

    ex_date = _latest_past_date([gas.get("ex_date")] + [r.get("ex_date", "") for r in history_rows])
    pay_date = _latest_past_date([gas.get("pay_date")] + [r.get("pay_date", "") for r in history_rows])
    display_date = ex_date if ex_date != "—" else pay_date

    div_per_unit = _first_positive(grp.get("每單位月配息估算", pd.Series(dtype=float)).tolist())
    if div_per_unit <= 0:
        div_per_unit = _first_positive(grp.get("monthly_dividend_per_unit", pd.Series(dtype=float)).tolist())
    if div_per_unit <= 0:
        div_per_unit = normalize_number(gas.get("monthly_div"), 0)
    if div_per_unit <= 0 and latest_history:
        div_per_unit = _first_positive([
            latest_history.get("actual_div_amount", 0),
            latest_history.get("div_amount", 0),
        ])

    fx = _first_positive(grp.get("匯率", pd.Series(dtype=float)).tolist())
    if fx <= 0:
        fx, _ = fetch_fx(currency)
        fx = fx or 1.0

    if div_per_unit <= 0 and units > 0 and fx > 0:
        monthly_div_twd = _first_positive(grp.get("每月配息", pd.Series(dtype=float)).tolist())
        if monthly_div_twd > 0:
            div_per_unit = monthly_div_twd / fx / units

    if div_per_unit <= 0:
        return None

    total_amount = units * div_per_unit
    return {
        "platform": platform,
        "fund_code": fund_code,
        "currency": currency,
        "fund_name": fund_name,
        "units": units,
        "div_per_unit": div_per_unit,
        "total_amount": total_amount,
        "fx": fx,
        "twd_total": total_amount * fx,
        "ex_date": "" if ex_date == "—" else ex_date,
        "pay_date": "" if pay_date == "—" else pay_date,
        "display_date": display_date,
        "sort_date": _parse_dividend_date(pay_date if pay_date != "—" else ex_date),
    }


def build_estimated_dividend_table(enriched_df: pd.DataFrame) -> pd.DataFrame:
    if enriched_df is None or enriched_df.empty:
        return pd.DataFrame(columns=ESTIMATED_DIVIDEND_COLUMNS + ["_預估配息台幣"])

    fund_groups = _fund_dividend_groups(enriched_df)
    if not fund_groups:
        return pd.DataFrame(columns=ESTIMATED_DIVIDEND_COLUMNS + ["_預估配息台幣"])

    history_index = _dividend_history_index(_combined_dividend_records())

    rows: list[dict[str, Any]] = []
    for _, grp in fund_groups:
        estimate = _dividend_estimate_from_group(grp, history_index)
        if not estimate:
            continue
        rows.append({
            "平台": estimate["platform"],
            "基金名稱": estimate["fund_name"],
            "幣別": estimate["currency"],
            "目前單位數": estimate["units"],
            "除息日期": estimate["display_date"],
            "每單位配息": estimate["div_per_unit"],
            "預估配息原幣": estimate["total_amount"],
            "匯率": estimate["fx"],
            "預估配息台幣": estimate["twd_total"],
            "_預估配息台幣": estimate["twd_total"],
        })
    return pd.DataFrame(rows, columns=ESTIMATED_DIVIDEND_COLUMNS + ["_預估配息台幣"]).sort_values(["平台", "基金名稱"])


def _fetch_dividend_rows(table_name: str) -> list[dict[str, Any]]:
    try:
        return supabase_client().table(table_name).select("*").execute().data or []
    except Exception:
        return []


def _roll_estimate_to_current_month(estimate: dict[str, Any] | None) -> dict[str, Any] | None:
    """月配息基金的來源（GAS／歷史）若還停在上個月，推算本月同一天的除息／發放日作為候選列，
    到期後就出現在配息記錄表等人工確認；來源更新後會以來源日期為準。"""
    if not estimate:
        return estimate
    today = tw_now().date()
    ex = _parse_dividend_date(estimate.get("ex_date"))
    pay = _parse_dividend_date(estimate.get("pay_date"))
    ref = pay or ex
    if ref is None or (ref.year, ref.month) >= (today.year, today.month):
        return estimate

    def this_month(d):
        import calendar
        return d.replace(year=today.year, month=today.month,
                         day=min(d.day, calendar.monthrange(today.year, today.month)[1]))

    new_ex = this_month(ex) if ex else None
    new_pay = this_month(pay) if pay else None
    if (new_pay or new_ex) > today:
        return estimate  # 本月還沒到發放日
    rolled = dict(estimate)
    rolled["ex_date"] = new_ex.strftime("%Y/%m/%d") if new_ex else ""
    rolled["pay_date"] = new_pay.strftime("%Y/%m/%d") if new_pay else ""
    rolled["sort_date"] = new_pay or new_ex
    return rolled


def build_actual_dividend_table(enriched_df: pd.DataFrame) -> pd.DataFrame:
    name_lookup = _fund_name_lookup(enriched_df)
    position_totals = _position_dividend_total_lookup(enriched_df)
    records = _combined_dividend_records()
    existing_keys = _existing_dividend_record_keys(records)
    history_index = _dividend_history_index(records)

    rows: list[dict[str, Any]] = []
    for record in records:
        fund_code = normalize_text(record.get("fund_code", ""))
        platform = normalize_text(record.get("platform", ""))
        currency = normalize_text(record.get("currency", ""))
        name = (
            normalize_text(record.get("fund_name", ""))
            or name_lookup.get((fund_code, platform, currency), "")
            or name_lookup.get((fund_code, "", currency), "")
            or name_lookup.get((fund_code, "", ""), "")
            or fund_code
        )
        units = normalize_number(record.get("units_at_ex", 0), 0)
        estimated_div = normalize_number(record.get("div_amount", 0), 0)
        is_paid = normalize_bool(record.get("is_paid", False), False)
        actual_div = normalize_number(record.get("actual_div_amount", 0), 0)
        if is_paid and actual_div <= 0:
            actual_div = estimated_div
        display_div = actual_div if actual_div > 0 else estimated_div
        total_amount = units * display_div if units > 0 and display_div > 0 else None
        fx = normalize_number(record.get("fx_rate", 1), 1)
        twd_total = normalize_number(record.get("twd_total", 0), 0)
        if twd_total <= 0 and total_amount is not None:
            twd_total = total_amount * fx
        if total_amount is None and twd_total > 0 and fx > 0:
            total_amount = twd_total / fx
        current_totals = _position_dividend_totals_for(
            position_totals,
            fund_code,
            platform,
            currency,
            name,
            fx,
        )
        rows.append({
            "平台": platform,
            "基金名稱": name,
            "幣別": currency,
            "配息單位數": units,
            # 沒有發放日的（東方匯理等 GAS 不提供）以除息日顯示，不留空白
            "發放日期": _format_dividend_date(record.get("pay_date", "") or record.get("ex_date", "")),
            "每單位配息": display_div if display_div > 0 else None,
            "實際配息原幣": total_amount if total_amount is not None else None,
            "匯率": fx,
            "實際配息台幣": twd_total if twd_total > 0 else None,
            "確認入帳": is_paid,
            "累計配息原幣": current_totals["original"],
            "累計配息台幣": current_totals["twd"],
            "_確認前": is_paid,
            "_累計用配息金額": total_amount if is_paid and total_amount is not None else 0,
            "_累計用配息台幣": twd_total if is_paid else 0,
            "_實際配息台幣": twd_total,
            "_fund_code": fund_code,
            "_fund_name": name,
            "_platform": platform,
            "_currency": currency,
            "_ex_date": normalize_text(record.get("ex_date", "")),
            "_pay_date": normalize_text(record.get("pay_date", "")),
            "_id": record.get("id"),
            "_source_table": record.get("_source_table", "fund_dividends"),
            "_fx_rate": fx,
            # 沒有發放日的用除息日排序，避免整批被排到最下面
            "_sort_date": _parse_dividend_date(record.get("pay_date", "")) or _parse_dividend_date(record.get("ex_date", "")),
        })

    for _, grp in _fund_dividend_groups(enriched_df):
        estimate = _roll_estimate_to_current_month(_dividend_estimate_from_group(grp, history_index))
        if not estimate:
            continue
        fund_code = normalize_text(estimate.get("fund_code", "")).lower()
        estimate_key = _dividend_business_key(
            fund_code,
            estimate.get("platform", ""),
            estimate.get("currency", ""),
            estimate.get("fund_name", ""),
            estimate.get("ex_date", ""),
            estimate.get("pay_date", ""),
        )
        if estimate_key[0] and estimate_key[3] and estimate_key in existing_keys:
            continue
        if any(
            normalize_text(row.get("_source_table", "")) == "dividend_log_candidate"
            and normalize_text(row.get("_fund_code", "")).lower() == fund_code
            and normalize_text(row.get("_platform", "")) == normalize_text(estimate.get("platform", ""))
            and normalize_text(row.get("_currency", "")).upper() == normalize_text(estimate.get("currency", "")).upper()
            for row in rows
        ):
            continue
        current_totals = _position_dividend_totals_for(
            position_totals,
            estimate["fund_code"],
            estimate["platform"],
            estimate["currency"],
            estimate["fund_name"],
            estimate["fx"],
        )
        rows.append({
            "平台": estimate["platform"],
            "基金名稱": estimate["fund_name"],
            "幣別": estimate["currency"],
            "配息單位數": estimate["units"],
            "發放日期": estimate["pay_date"] or estimate["ex_date"] or "—",
            "每單位配息": estimate["div_per_unit"],
            "實際配息原幣": estimate["total_amount"],
            "匯率": estimate["fx"],
            "實際配息台幣": round(estimate["twd_total"], 0),
            "確認入帳": False,
            "累計配息原幣": current_totals["original"],
            "累計配息台幣": current_totals["twd"],
            "_確認前": False,
            "_累計用配息金額": 0,
            "_累計用配息台幣": 0,
            "_實際配息台幣": estimate["twd_total"],
            "_fund_code": estimate["fund_code"],
            "_fund_name": estimate["fund_name"],
            "_platform": estimate["platform"],
            "_currency": estimate["currency"],
            "_ex_date": estimate["ex_date"],
            "_pay_date": estimate["pay_date"],
            "_id": None,
            "_source_table": "dividend_log_candidate",
            "_fx_rate": estimate["fx"],
            "_sort_date": estimate["sort_date"],
        })

    internal_cols = [
        "_確認前", "_累計用配息金額", "_累計用配息台幣", "_實際配息台幣",
        "_fund_code", "_fund_name", "_platform", "_currency", "_ex_date", "_pay_date",
        "_id", "_source_table", "_fx_rate", "_sort_date",
    ]
    columns = ACTUAL_DIVIDEND_COLUMNS + internal_cols
    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(rows)
    df["_sort_date"] = df["_sort_date"].apply(lambda d: pd.Timestamp(d) if d is not None else pd.Timestamp.min)
    df["_dedupe_key"] = df.apply(
        lambda r: _dividend_business_key(
            r.get("_fund_code", ""),
            r.get("_platform", ""),
            r.get("_currency", ""),
            r.get("_fund_name", r.get("基金名稱", "")),
            r.get("_ex_date", ""),
            r.get("_pay_date", ""),
        ),
        axis=1,
    )
    df["_dedupe_paid"] = df["確認入帳"].apply(lambda v: 1 if normalize_bool(v, False) else 0)
    df["_dedupe_source"] = df["_source_table"].map({"fund_dividends": 2, "dividend_log": 1}).fillna(0)
    df = df.sort_values(
        ["_sort_date", "_dedupe_paid", "_dedupe_source"],
        ascending=[False, False, False],
    ).drop_duplicates("_dedupe_key", keep="first").copy()
    df["累計配息原幣"] = df["累計配息原幣"].apply(lambda v: round(normalize_number(v, 0), 2))
    # 對照欄：總帳「總覽」N 欄的累積配息原幣
    try:
        from invest_app.sheet_compare import sheet_fund_dividends, sheet_value_for
        grid = load_sheet_raw_grid(OVERVIEW_SHEET_GID)
        sheet_rows = sheet_fund_dividends(grid)                                   # N 欄
        sheet_twd_rows = sheet_fund_dividends(grid, value_header="累積配息台幣")   # L 欄
    except Exception:
        sheet_rows, sheet_twd_rows = [], []
    df["總帳累積配息原幣"] = df.apply(
        lambda r: sheet_value_for(sheet_rows, r["平台"], r["幣別"], r["基金名稱"]) if sheet_rows else None, axis=1)
    df["總帳累積配息台幣"] = df.apply(
        lambda r: sheet_value_for(sheet_twd_rows, r["平台"], r["幣別"], r["基金名稱"]) if sheet_twd_rows else None, axis=1)
    df["累計配息台幣"] = df["累計配息台幣"].apply(lambda v: round(normalize_number(v, 0), 0))
    df = df.sort_values("_sort_date", ascending=False).reset_index(drop=True)
    return df[columns]


def render_estimated_dividend_table(df: pd.DataFrame, height_cap: int = 520) -> None:
    if df.empty:
        st.info("目前沒有資料。")
        return
    display_df = df[ESTIMATED_DIVIDEND_COLUMNS].copy()
    col_cfg = {
        "基金名稱": st.column_config.TextColumn("基金名稱", width="large"),
        "目前單位數": st.column_config.NumberColumn("目前單位數", format="%.4f"),
        "每單位配息": st.column_config.NumberColumn("每單位配息", format="%.6f"),
        "預估配息原幣": st.column_config.NumberColumn("預估配息原幣", format="localized"),
        "匯率": st.column_config.NumberColumn("匯率", format="%.4f"),
        "預估配息台幣": st.column_config.NumberColumn("預估配息台幣", format="localized"),
    }
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=min(42 * len(display_df) + 44, height_cap),
        column_config=col_cfg,
    )


def _paid_dividend_original_amount(record: dict[str, Any]) -> float:
    if not normalize_bool(record.get("is_paid", False), False):
        return 0.0
    units = normalize_number(record.get("units_at_ex", 0), 0)
    per_unit = normalize_number(record.get("actual_div_amount", 0), 0)
    if per_unit <= 0:
        per_unit = normalize_number(record.get("div_amount", 0), 0)
    amount = units * per_unit if units > 0 and per_unit > 0 else 0
    if amount <= 0:
        twd_total = normalize_number(record.get("twd_total", 0), 0)
        fx = normalize_number(record.get("fx_rate", 0), 0)
        if twd_total > 0 and fx > 0:
            amount = twd_total / fx
    return max(0.0, amount)


def set_position_dividend_original_total_by_fund(
    fund_code: str,
    platform: str,
    currency: str,
    target_original_total: float,
    dividend_pay_date: str = "",
) -> bool:
    fund_code_key = normalize_text(fund_code).lower()
    platform_key = normalize_text(platform)
    currency_key = normalize_text(currency).upper()
    if not fund_code_key:
        return False
    try:
        rows = supabase_client().table("positions").select(
            "id,sort_order,fund_code,platform,currency,dividend_received_original_base"
        ).eq("platform", platform_key).eq("currency", currency_key).execute().data or []
    except Exception:
        rows = []
    matched = [
        row for row in rows
        if normalize_text(row.get("fund_code", "")).lower() == fund_code_key
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
    primary_id = int(float(matched[0]["id"]))
    historical_base = normalize_number(matched[0].get("dividend_received_original_base", 0), 0)
    sb = supabase_client()
    target = max(0, normalize_number(target_original_total, 0))
    for row in matched:
        rid = int(float(row["id"]))
        payload = {
            "dividend_received_original_total": (historical_base + target) if rid == primary_id else 0,
            "dividend_received_total": 0,
        }
        if rid == primary_id and dividend_pay_date:
            payload["dividend_pay_date"] = dividend_pay_date
        sb.table("positions").update(payload).eq("id", rid).execute()
    return True


def recompute_position_dividend_original_total(
    fund_code: str,
    platform: str,
    currency: str,
    fallback_pay_date: str = "",
) -> bool:
    fund_code_key = normalize_text(fund_code).lower()
    platform_key = normalize_text(platform)
    currency_key = normalize_text(currency).upper()
    if not fund_code_key:
        return False

    paid_by_key: dict[tuple[str, str, str, str], float] = {}
    pay_dates: list[Any] = []
    for record in _combined_dividend_records():
        if normalize_text(record.get("fund_code", "")).lower() != fund_code_key:
            continue
        if normalize_text(record.get("platform", "")) != platform_key:
            continue
        if normalize_text(record.get("currency", "")).upper() != currency_key:
            continue
        amount = _paid_dividend_original_amount(record)
        if amount <= 0:
            continue
        key = _dividend_record_key(record)
        paid_by_key[key] = max(amount, paid_by_key.get(key, 0))
        pay_dates.append(record.get("pay_date") or record.get("ex_date"))

    latest_date = fallback_pay_date
    parsed_dates = [d for d in (_parse_dividend_date(v) for v in pay_dates) if d is not None]
    if parsed_dates:
        latest_date = max(parsed_dates).strftime("%Y/%m/%d")
    return set_position_dividend_original_total_by_fund(
        fund_code_key,
        platform_key,
        currency_key,
        sum(paid_by_key.values()),
        latest_date,
    )


def set_position_dividend_original_total(position_id: int, target_original_total: float) -> bool:
    target_original_total = max(0, normalize_number(target_original_total, 0))
    current = ensure_columns(load_positions())
    if current.empty:
        return False

    current["_id_num"] = current["id"].apply(lambda v: int(float(v)) if not pd.isna(v) else 0)
    selected_rows = current[current["_id_num"] == int(position_id)]
    if selected_rows.empty:
        return False

    selected = selected_rows.iloc[0]
    target_platform = normalize_text(selected.get("platform", ""))
    target_currency = normalize_text(selected.get("currency", "")).upper()
    target_fund_code = normalize_text(selected.get("fund_code", "")).lower()
    if not target_fund_code:
        return False

    funds = current[current["asset_type"].astype(str) == "基金"].copy()
    matched = funds[
        (funds["platform"].astype(str).str.strip() == target_platform)
        & (funds["currency"].astype(str).str.strip().str.upper() == target_currency)
        & (funds["fund_code"].astype(str).str.strip().str.lower() == target_fund_code)
    ].copy()
    if matched.empty:
        matched = selected_rows.copy()

    matched["_sort_num"] = matched["sort_order"].apply(lambda v: normalize_number(v, 999999))
    matched["_id_num"] = matched["id"].apply(lambda v: int(float(v)) if not pd.isna(v) else 999999)
    matched = matched.sort_values(["_sort_num", "_id_num"])
    primary_id = int(float(matched.iloc[0]["id"]))

    paid_by_key: dict[tuple[str, str, str, str], float] = {}
    for record in _combined_dividend_records():
        if normalize_text(record.get("fund_code", "")).lower() != target_fund_code:
            continue
        if normalize_text(record.get("platform", "")) != target_platform:
            continue
        if normalize_text(record.get("currency", "")).upper() != target_currency:
            continue
        amount = _paid_dividend_original_amount(record)
        if amount > 0:
            key = _dividend_record_key(record)
            paid_by_key[key] = max(amount, paid_by_key.get(key, 0))
    historical_base = max(0, target_original_total - sum(paid_by_key.values()))

    sb = supabase_client()
    for _, row in matched.iterrows():
        rid = int(float(row["id"]))
        sb.table("positions").update({
            "dividend_received_original_total": target_original_total if rid == primary_id else 0,
            "dividend_received_original_base": historical_base if rid == primary_id else 0,
            "dividend_received_total": 0,
        }).eq("id", rid).execute()

    return True


def render_position_dividend_total_fix_tool() -> None:
    with st.expander("修正持倉累計配息原幣", expanded=False):
        current = ensure_columns(load_positions())
        funds = current[current["asset_type"].astype(str) == "基金"].copy()
        funds = funds[funds["fund_code"].astype(str).str.strip() != ""].copy()
        if funds.empty:
            st.info("沒有基金持倉可修正。")
            return

        funds["_id_num"] = funds["id"].apply(lambda v: int(float(v)) if not pd.isna(v) else 0)
        funds["_sort_num"] = funds["sort_order"].apply(lambda v: normalize_number(v, 999999))
        funds["_group_key"] = funds.apply(
            lambda r: (
                normalize_text(r.get("platform", "")),
                normalize_text(r.get("currency", "")).upper(),
                normalize_text(r.get("fund_code", "")).lower(),
            ),
            axis=1,
        )

        primary_rows: list[pd.Series] = []
        for _, grp in funds.groupby("_group_key", dropna=False):
            grp = grp.sort_values(["_sort_num", "_id_num"]).copy()
            primary = grp.iloc[0].copy()
            primary["_group_count"] = len(grp)
            primary["_group_original_total"] = grp["dividend_received_original_total"].apply(lambda v: normalize_number(v, 0)).sum()
            primary_rows.append(primary)

        primary_df = pd.DataFrame(primary_rows)
        if primary_df.empty:
            st.info("沒有可修正的基金主列。")
            return

        primary_df = primary_df.sort_values(["platform", "currency", "fund_code", "_sort_num", "_id_num"])
        primary_df["_label"] = primary_df.apply(
            lambda r: (
                f"主列 ID {int(r['_id_num'])}｜{r.get('platform', '')}｜{r.get('currency', '')}｜"
                f"{r.get('fund_code', '')}｜{r.get('name', '')}｜"
                f"主列目前 {money(r.get('dividend_received_original_total', 0), 4)}｜"
                f"同基金合計 {money(r.get('_group_original_total', 0), 4)}｜"
                f"同基金 {int(r.get('_group_count', 1))} 筆"
            ),
            axis=1,
        )

        choice_options = [""] + primary_df["_label"].tolist()
        saved_choice = st.session_state.get("fix_position_dividend_total_choice_applied", "")
        with st.form("fix_position_dividend_total_choice_form"):
            pending_choice = st.selectbox(
                "選擇要修正的持倉主列",
                choice_options,
                index=choice_options.index(saved_choice) if saved_choice in choice_options else 0,
                key="fix_position_dividend_total_choice_primary_only",
            )
            choice_submitted = st.form_submit_button("載入這筆")
        if choice_submitted:
            st.session_state["fix_position_dividend_total_choice_applied"] = pending_choice
            st.rerun()
        choice = st.session_state.get("fix_position_dividend_total_choice_applied", "")
        if not choice:
            st.caption("只列出每檔基金的第一筆主列；更新後同基金其他持倉列會歸零，避免重複累計。")
            return

        selected = primary_df[primary_df["_label"] == choice].iloc[0]
        position_id = int(selected["_id_num"])
        current_total = normalize_number(selected.get("dividend_received_original_total", 0), 0)

        with st.form(f"fix_position_dividend_total_form_{position_id}"):
            st.write(f"目前主列累計配息原幣：{money(current_total, 4)}")
            target_total = st.number_input(
                "正確累計配息原幣",
                value=float(current_total),
                format="%.4f",
                key=f"fix_position_dividend_total_value_{position_id}",
            )
            confirm = st.checkbox(
                "我確認這是此基金主列的正確累計配息原幣，並將同基金其他列歸零",
                key=f"fix_position_dividend_total_confirm_{position_id}",
            )
            submitted = st.form_submit_button("更新這檔基金累計配息原幣")

        if submitted:
            if not confirm:
                st.warning("請先勾選確認。")
                return
            if set_position_dividend_original_total(position_id, target_total):
                st.success(f"已更新主列 ID {position_id} 的累計配息原幣為 {money(target_total, 4)}。")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("更新失敗。")


def render_actual_dividend_table(df: pd.DataFrame, height_cap: int = 520) -> None:
    if df.empty:
        st.info("目前沒有實際配息記錄。")
        return
    display_df = df[ACTUAL_DIVIDEND_COLUMNS].copy()
    col_cfg = {
        "基金名稱": st.column_config.TextColumn("基金名稱", width="large"),
        "配息單位數": st.column_config.NumberColumn("配息單位數", format="localized"),
        "每單位配息": st.column_config.NumberColumn("每單位配息", format="%.6f"),
        "實際配息原幣": st.column_config.NumberColumn("實際配息原幣", format="localized"),
        "匯率": st.column_config.NumberColumn("匯率", format="%.4f"),
        "實際配息台幣": st.column_config.NumberColumn("實際配息台幣", format="localized"),
        "確認入帳": st.column_config.CheckboxColumn("確認入帳"),
        "累計配息原幣": st.column_config.NumberColumn("累計配息原幣", format="localized"),
        "總帳累積配息原幣": st.column_config.NumberColumn("總帳累積配息原幣", format="localized"),
        "總帳累積配息台幣": st.column_config.NumberColumn("總帳累積配息台幣", format="localized"),
        "累計配息台幣": st.column_config.NumberColumn("累計配息台幣", format="localized"),
    }
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=min(42 * len(display_df) + 44, height_cap),
        column_config=col_cfg,
    )

    def _option_label(idx: int, row: pd.Series) -> str:
        return (
            f"{idx + 1}｜{normalize_text(row.get('平台', ''))}｜"
            f"{normalize_text(row.get('基金名稱', ''))}｜"
            f"{normalize_text(row.get('發放日期', ''))}｜"
            f"{money(normalize_number(row.get('實際配息原幣', 0), 0), 2)} {normalize_text(row.get('幣別', ''))}"
        )

    pending_options: dict[str, int] = {}
    confirmed_options: dict[str, int] = {}
    for idx, row in df.iterrows():
        label = _option_label(int(idx), row)
        if normalize_bool(row.get("_確認前", row.get("確認入帳", False)), False):
            confirmed_options[label] = int(idx)
        else:
            pending_options[label] = int(idx)

    with st.form("actual_dividend_confirm_form"):
        confirm_labels = st.multiselect("確認入帳", list(pending_options.keys()))
        cancel_labels = st.multiselect("取消確認", list(confirmed_options.keys()))
        submitted = st.form_submit_button("💾 套用確認狀態")
        recompute_submitted = st.form_submit_button("重算已確認累計")

    if submitted or recompute_submitted:
        changes = {pending_options[label]: True for label in confirm_labels}
        changes.update({confirmed_options[label]: False for label in cancel_labels})
        if not changes and not recompute_submitted:
            st.info("沒有選擇需要更新的記錄。")
            return
        sb = supabase_client()
        updated = 0
        affected_groups: dict[tuple[str, str, str], str] = {}
        warnings: list[str] = []
        existing_keys = _existing_dividend_record_keys(_combined_dividend_records())
        for idx, new_confirmed in changes.items():
            row = display_df.iloc[idx]
            old_confirmed = normalize_bool(df.iloc[idx].get("_確認前", False), False)
            if old_confirmed == new_confirmed:
                continue
            row_id = df.iloc[idx].get("_id")
            source_table = normalize_text(df.iloc[idx].get("_source_table", "fund_dividends"), "fund_dividends")
            fund_code = normalize_text(df.iloc[idx].get("_fund_code", ""))
            platform = normalize_text(df.iloc[idx].get("_platform", row.get("平台", "")))
            currency = normalize_text(df.iloc[idx].get("_currency", row.get("幣別", "")))
            pay_date = normalize_text(df.iloc[idx].get("_pay_date", row.get("發放日期", "")))
            ex_date = normalize_text(df.iloc[idx].get("_ex_date", ""))
            units = normalize_number(row.get("配息單位數", 0), 0)
            div_amount = normalize_number(row.get("每單位配息", 0), 0)
            total_amount = normalize_number(row.get("實際配息原幣", 0), 0)
            if total_amount <= 0 and units > 0 and div_amount > 0:
                total_amount = units * div_amount
            actual_div = total_amount / units if total_amount > 0 and units > 0 else div_amount
            fx = normalize_number(df.iloc[idx].get("_fx_rate", 1), 1)
            payload = {
                "is_paid": new_confirmed,
                "actual_div_amount": actual_div,
                "twd_total": round(total_amount * fx, 0) if total_amount > 0 else 0,
            }
            if source_table == "dividend_log_candidate":
                if not new_confirmed:
                    continue
                insert_payload = {
                    "fund_code": fund_code,
                    "fund_name": normalize_text(df.iloc[idx].get("_fund_name", row.get("基金名稱", ""))),
                    "platform": platform,
                    "currency": currency,
                    "ex_date": ex_date,
                    "pay_date": pay_date,
                    "div_amount": div_amount,
                    "actual_div_amount": actual_div,
                    "units_at_ex": units,
                    "fx_rate": fx,
                    "twd_total": round(total_amount * fx, 0) if total_amount > 0 else 0,
                    "is_paid": True,
                    "note": f"持倉候選確認入帳 {tw_now().strftime('%Y/%m/%d')}",
                }
                insert_key = _dividend_record_key(insert_payload)
                if insert_key not in existing_keys:
                    sb.table("dividend_log").insert(insert_payload).execute()
                    existing_keys.add(insert_key)
            else:
                if row_id is None or normalize_text(row_id, "") in {"", "nan", "None"}:
                    warnings.append(f"{row.get('基金名稱', '')} 缺少記錄 ID，略過。")
                    continue
                if source_table == "fund_dividends":
                    payload["updated_at"] = "now()"
                sb.table(source_table).update(payload).eq("id", int(float(row_id))).execute()
            affected_groups[(fund_code, platform, currency)] = pay_date or ex_date
            updated += 1
        if recompute_submitted:
            for _, row in df[df["確認入帳"].apply(lambda v: normalize_bool(v, False))].iterrows():
                affected_groups[(
                    normalize_text(row.get("_fund_code", "")),
                    normalize_text(row.get("_platform", row.get("平台", ""))),
                    normalize_text(row.get("_currency", row.get("幣別", ""))),
                )] = normalize_text(row.get("_pay_date", row.get("發放日期", ""))) or normalize_text(row.get("_ex_date", ""))
        for (fund_code, platform, currency), pay_date in affected_groups.items():
            if not recompute_position_dividend_original_total(fund_code, platform, currency, pay_date):
                warnings.append(f"{fund_code} 累計配息重算失敗，請確認持倉主列。")
        if warnings:
            st.warning("\n".join(warnings))
        if updated or recompute_submitted:
            msg = f"已更新 {updated} 筆確認狀態。" if updated else "已重算已確認配息累計。"
            st.success(msg)
            st.cache_data.clear()
            st.rerun()
        else:
            st.info("沒有勾選狀態需要更新。")


def render_dividend_log_tab(enriched_df: pd.DataFrame, positions: pd.DataFrame) -> None:
    """💰 配息記錄"""
    st.subheader("💰 配息記錄")
    render_auto_catch_up_cleanup()  # 只在還有 10/11 自動補登記錄時出現

    source = enriched_df
    estimate_df = build_estimated_dividend_table(source)
    actual_df = build_actual_dividend_table(source)

    platforms = sorted(
        set(estimate_df.get("平台", pd.Series(dtype=str)).dropna().astype(str))
        | set(actual_df.get("平台", pd.Series(dtype=str)).dropna().astype(str))
    )
    platform_options = ["全部"] + platforms
    saved_platform = st.session_state.get("div_record_platform_applied", "全部")
    with st.form("div_record_platform_form"):
        pending_platform = st.selectbox(
            "篩選平台",
            platform_options,
            index=platform_options.index(saved_platform) if saved_platform in platform_options else 0,
            key="div_record_platform",
        )
        platform_submitted = st.form_submit_button("套用篩選")
    if platform_submitted:
        st.session_state["div_record_platform_applied"] = pending_platform
        st.rerun()
    selected_platform = st.session_state.get("div_record_platform_applied", "全部")
    if selected_platform != "全部":
        estimate_df = estimate_df[estimate_df["平台"] == selected_platform]
        actual_df = actual_df[actual_df["平台"] == selected_platform]

    est_twd = estimate_df["_預估配息台幣"].fillna(0).sum() if "_預估配息台幣" in estimate_df else 0
    paid_df = actual_df[actual_df["確認入帳"] == True] if "確認入帳" in actual_df else pd.DataFrame()
    paid_twd = paid_df["_實際配息台幣"].fillna(0).sum() if not paid_df.empty and "_實際配息台幣" in paid_df else 0
    c1, c2, c3 = st.columns(3)
    c1.metric("預估配息折台幣", money(est_twd))
    c2.metric("已確認實際配息折台幣", money(paid_twd))
    c3.metric("配息記錄筆數", f"{len(actual_df):,}")

    st.markdown("#### 預估配息表")
    st.caption("目前單位數 × 最近一次每單位配息 = 預估配息原幣，再乘匯率得到台幣。")
    render_estimated_dividend_table(estimate_df)

    st.markdown("#### 配息記錄表")
    st.caption("未勾確認入帳的是待確認的配息（含本月候選）；勾選並套用後才計入累計配息。")
    render_actual_dividend_table(actual_df)


    # 對帳與維護工具平常收起來，需要時再打開
    if not st.toggle("🔧 顯示對帳與維護工具（總帳比對、本月檢查、重複記錄、手動新增）", key="dividend_tools"):
        return
    render_sheet_dividend_diff(enriched_df)
    render_monthly_dividend_check(positions)
    render_duplicate_dividend_cleanup()
    render_position_dividend_total_fix_tool()

    with st.expander("➕ 手動新增配息記錄（補填歷史）"):
        st.caption("用於補填歷史配息；實際配息留 0 時，已發放記錄會用預估配息代入。")
        with st.form("manual_div_log"):
            c1, c2, c3 = st.columns(3)
            m_platform  = c1.selectbox("平台", PLATFORMS[2:], key="mdl_platform")
            m_currency  = c2.selectbox("幣別", CURRENCIES[1:], key="mdl_currency")
            m_fund_code = c3.text_input("基金代號", key="mdl_fund_code")
            m_fund_name = st.text_input("基金名稱", key="mdl_fund_name")
            c4, c5 = st.columns(2)
            m_ex_date  = c4.text_input("除息日（YYYY/MM/DD）", key="mdl_ex_date")
            m_pay_date = c5.text_input("發放日（YYYY/MM/DD）", key="mdl_pay_date")
            c6, c7, c8, c9 = st.columns(4)
            m_div_amt = c6.number_input("每單位配息", value=0.0, format="%.6f", key="mdl_div_amt")
            m_units = c7.number_input("配息單位數", value=0.0, format="%.4f", key="mdl_units")
            m_actual_total = c8.number_input("實際配息原幣", value=0.0, format="%.2f", key="mdl_actual_total")
            m_fx = c9.number_input("匯率", value=1.0, format="%.4f", key="mdl_fx")
            m_total = m_actual_total if m_actual_total > 0 else m_units * m_div_amt
            st.caption(f"總配息原幣：**{money(m_total, 2)} {m_currency}**｜換算台幣：**{money(m_total * m_fx)}**")
            m_is_paid = st.checkbox("確認入帳（加入累計配息原幣）", key="mdl_is_paid")
            m_note = st.text_input("備註", key="mdl_note")

            if st.form_submit_button("💾 新增"):
                if not m_fund_code or not m_ex_date:
                    st.error("基金代號和除息日必填")
                else:
                    try:
                        actual_div = m_total / m_units if m_units > 0 and m_total > 0 else m_div_amt
                        twd_total = m_total * m_fx
                        payload = {
                            "fund_code": m_fund_code,
                            "fund_name": m_fund_name,
                            "platform": m_platform,
                            "currency": m_currency,
                            "ex_date": m_ex_date,
                            "pay_date": m_pay_date,
                            "div_amount": m_div_amt,
                            "actual_div_amount": actual_div if m_is_paid else 0,
                            "units_at_ex": m_units,
                            "fx_rate": m_fx,
                            "twd_total": round(twd_total, 0),
                            "is_paid": m_is_paid,
                            "note": m_note or "手動新增",
                        }
                        supabase_client().table("dividend_log").insert(payload).execute()
                        if m_is_paid:
                            recompute_position_dividend_original_total(
                                m_fund_code,
                                m_platform,
                                m_currency,
                                m_pay_date or m_ex_date,
                            )
                        st.success("已新增！"); st.rerun()
                    except Exception as e:
                        st.error(f"新增失敗：{e}")


def render_sheet_dividend_diff(enriched_df: pd.DataFrame) -> None:
    """總帳「總覽」N 欄累積配息原幣 vs 資料庫累計配息原幣：只列有差異的基金。"""
    from invest_app.sheet_compare import compare_fund_dividends, sheet_fund_dividends
    try:
        diff = compare_fund_dividends(sheet_fund_dividends(load_sheet_raw_grid(OVERVIEW_SHEET_GID)), enriched_df)
    except Exception as exc:
        st.caption(f"總帳累積配息比對暫時無法執行：{exc}")
        return
    if diff.empty:
        st.success("總帳「總覽」N 欄累積配息原幣與資料庫一致。")
        return
    st.markdown(f"#### ⚠️ 與總帳累積配息原幣不一致（{len(diff)} 檔，差額 = 資料庫 − 總帳，原幣）")
    st.markdown(html_table(diff.drop(columns=["_position_id"]), ["總帳配息原幣", "資料庫配息原幣", "差額"], decimals=2),
                unsafe_allow_html=True)
    updatable = diff[diff["總帳配息原幣"].notna() & diff["_position_id"].notna()]
    if updatable.empty:
        return
    with st.form("sync_sheet_dividend_totals"):
        confirmed = st.checkbox(f"我確認把以上 {len(updatable)} 檔的資料庫累計配息原幣改成總帳 N 欄數字"
                                "（只調整歷史基準，配息記錄不變）")
        if st.form_submit_button("🔄 以總帳 N 欄更新資料庫") and confirmed:
            # 重新讀總帳（不用 10 分鐘快取），確保用到最新、含小數的 N 欄
            load_sheet_raw_grid.clear()
            load_sheet_grid.clear()
            fresh = compare_fund_dividends(sheet_fund_dividends(load_sheet_raw_grid(OVERVIEW_SHEET_GID)), enriched_df)
            updatable = fresh[fresh["總帳配息原幣"].notna() & fresh["_position_id"].notna()]
            done = sum(bool(set_position_dividend_original_total(int(float(r["_position_id"])), float(r["總帳配息原幣"])))
                       for _, r in updatable.iterrows())
            st.cache_data.clear()
            st.success(f"已更新 {done} 檔基金的累計配息原幣。")
            st.rerun()


def render_duplicate_dividend_cleanup() -> None:
    """列出同基金同月的重複配息記錄（fund_dividends），確認後刪除並重算累計配息。"""
    _, duplicates = _split_dividend_records()
    removable = [r for r in duplicates if r.get("_source_table") == "fund_dividends" and r.get("id") is not None]
    if not removable:
        return
    st.markdown(f"#### ⚠️ 重複的配息記錄（同基金同月 {len(removable)} 筆，表中已不重複計算）")
    preview = pd.DataFrame([{
        "平台": r.get("platform", ""), "基金名稱": r.get("fund_name", ""), "幣別": r.get("currency", ""),
        "除息日": _format_dividend_date(r.get("ex_date", "")), "發放日": _format_dividend_date(r.get("pay_date", "")),
        "單位數": r.get("units_at_ex"), "每單位配息": r.get("actual_div_amount") or r.get("div_amount"),
        "已入帳": "是" if normalize_bool(r.get("is_paid", False), False) else "否",
    } for r in removable])
    st.markdown(html_table(preview, ["單位數", "每單位配息"]), unsafe_allow_html=True)
    with st.form("delete_duplicate_dividends"):
        confirmed = st.checkbox("我確認刪除以上重複記錄（保留同月另一筆已入帳／較早建立的記錄）")
        if st.form_submit_button("🗑️ 刪除重複記錄") and confirmed:
            sb = supabase_client()
            groups = set()
            for r in removable:
                sb.table("fund_dividends").delete().eq("id", int(float(r["id"]))).execute()
                groups.add((normalize_text(r.get("fund_code", "")), normalize_text(r.get("platform", "")),
                            normalize_text(r.get("currency", ""))))
            for fund_code, platform, currency in groups:
                recompute_position_dividend_original_total(fund_code, platform, currency)
            st.cache_data.clear()
            st.success(f"已刪除 {len(removable)} 筆重複記錄並重算累計配息。")
            st.rerun()


def monthly_dividend_check(positions: pd.DataFrame, month: str) -> pd.DataFrame:
    """每檔持有基金在 month（YYYY/MM）是否已有配息記錄，以及 GAS 最近一次除息資料。"""
    positions = ensure_columns(pd.DataFrame(positions))
    # (代碼或名稱, 平台, 幣別, 月份) → 是否已入帳；代碼、名稱任一對上即算有記錄
    seen: dict[tuple[str, str, str, str], bool] = {}
    for record in _combined_dividend_records():
        rec_month = _record_date_key(record)
        paid = normalize_bool(record.get("is_paid", False), False)
        for ident in (normalize_text(record.get("fund_code", "")).lower(),
                      _dividend_name_key(record.get("fund_name", ""))):
            if ident:
                k = (ident, normalize_text(record.get("platform", "")),
                     normalize_text(record.get("currency", "")).upper(), rec_month)
                seen[k] = seen.get(k, False) or paid
    groups: dict[tuple[str, str, str], list[pd.Series]] = {}
    for _, r in positions.iterrows():
        if normalize_text(r.get("asset_type", "")) != "基金" or not normalize_text(r.get("fund_code", "")):
            continue
        key = (normalize_text(r.get("fund_code", "")), normalize_text(r.get("platform", "")),
               normalize_text(r.get("currency", "TWD")))
        groups.setdefault(key, []).append(r)
    rows = []
    for (fc, plt, cur), grp in groups.items():
        units = sum(_position_dividend_units(r) for r in grp)
        if units <= 0:
            continue
        name = _fund_name_from_rows(grp)
        gas = _get_gas_data(fc)
        gas_month = _record_date_key({"ex_date": gas.get("ex_date"), "pay_date": gas.get("pay_date")})
        found = [seen[k] for k in ((fc.lower(), plt, cur.upper(), month),
                                   (_dividend_name_key(name), plt, cur.upper(), month)) if k in seen]
        if any(found):
            status = "已入帳"
        elif found:
            status = "已有記錄（未入帳）"
        elif gas_month == month:
            status = "GAS 有本月資料，尚未建立記錄"
        else:
            status = "GAS 尚無本月資料"
        rows.append({
            "平台": plt, "基金名稱": name, "幣別": cur, "單位數": units,
            "GAS除息日": _format_dividend_date(gas.get("ex_date") or ""),
            "GAS發放日": _format_dividend_date(gas.get("pay_date") or ""),
            "GAS每單位配息": gas.get("monthly_div"),
            "狀態": status,
            "_fund_code": fc,
        })
    return pd.DataFrame(rows)


def render_monthly_dividend_check(positions: pd.DataFrame) -> None:
    """本月配息檢查：缺記錄的基金可手動新增（未入帳，再由人工確認入帳）。"""
    month = tw_now().strftime("%Y/%m")
    df = monthly_dividend_check(positions, month)
    if df.empty:
        return
    missing = df[~df["狀態"].str.startswith("已")]
    title = f"#### 📋 {month} 配息檢查" + (f"（{len(missing)} 檔尚無本月記錄）" if len(missing) else "（全部已有記錄）")
    with st.expander(title.replace("#### ", ""), expanded=bool(len(missing))):
        st.markdown(html_table(df.drop(columns=["_fund_code"]), ["單位數"]), unsafe_allow_html=True)
        if missing.empty:
            return
        st.caption("GAS 尚無本月資料時，可依對帳單手動新增；新增的記錄為未入帳，確認後再到下方表單勾選入帳。")
        options = {f"{r['平台']}｜{r['基金名稱']}｜{r['幣別']}": r for _, r in missing.iterrows()}
        with st.form("manual_monthly_dividend"):
            label = st.selectbox("基金", list(options))
            c1, c2, c3, c4 = st.columns(4)
            ex_date = c1.text_input("除息日（YYYY/MM/DD）", value=f"{month}/01")
            pay_date = c2.text_input("發放日（YYYY/MM/DD）", value="")
            per_unit = c3.number_input("每單位配息（原幣）", min_value=0.0, value=0.0, step=0.0001, format="%.4f")
            units = c4.number_input("配息單位數", min_value=0.0, value=float(options[label]["單位數"]), step=0.01)
            if st.form_submit_button("➕ 新增本月配息記錄（未入帳）"):
                row = options[label]
                if per_unit <= 0 or not _parse_dividend_date(ex_date) or not _parse_dividend_date(pay_date):
                    st.error("請填寫正確的除息日、發放日與每單位配息。")
                else:
                    fx, _ = fetch_fx(row["幣別"])
                    supabase_client().table("fund_dividends").insert({
                        "fund_code": row["_fund_code"], "fund_name": row["基金名稱"],
                        "platform": row["平台"], "currency": row["幣別"],
                        "ex_date": _format_dividend_date(ex_date), "pay_date": _format_dividend_date(pay_date),
                        "div_amount": float(per_unit), "actual_div_amount": 0,
                        "units_at_ex": float(units), "fx_rate": float(fx or 1), "twd_total": 0, "is_paid": False,
                    }).execute()
                    st.cache_data.clear()
                    st.success("已新增，請在下方配息記錄表確認入帳。")
                    st.rerun()


# v77 曾在這些日期（台灣時間）自動補登配息快照，造成 10 月候選列消失、發放日空白
AUTO_CATCH_UP_DATES = {"2026-10-11"}


def _tw_day(value: Any) -> str:
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    return "" if pd.isna(ts) else ts.tz_convert("Asia/Taipei").strftime("%Y-%m-%d")


def _auto_catch_up_changes() -> list[dict[str, Any]]:
    """v77 在 10/11 造成的變動：每筆附 _action（delete／unconfirm）與 _table。"""
    out = []
    for r in _fetch_dividend_rows("fund_dividends"):
        if normalize_text(r.get("note", "")):
            continue  # 有備註的是人工建立的
        if _tw_day(r.get("created_at")) in AUTO_CATCH_UP_DATES:
            out.append({**r, "_table": "fund_dividends", "_action": "delete"})
        elif normalize_bool(r.get("is_paid", False), False) and _tw_day(r.get("updated_at")) in AUTO_CATCH_UP_DATES:
            out.append({**r, "_table": "fund_dividends", "_action": "unconfirm"})
    for r in _fetch_dividend_rows("dividend_log"):
        if any(f"同步 {day}" in normalize_text(r.get("note", "")) for day in AUTO_CATCH_UP_DATES):
            out.append({**r, "_table": "dividend_log", "_action": "delete"})
    return out


def render_auto_catch_up_cleanup() -> None:
    """還原 10/11 自動執行造成的變動：新增的刪除、被自動勾入帳的改回未入帳。"""
    changes = _auto_catch_up_changes()
    if not changes:
        return
    st.markdown(f"#### ⚠️ 10/11 程式自動寫入／自動入帳的配息記錄（{len(changes)} 筆）")
    st.caption("這些不是你操作的：10/11 新增的會刪除，被自動勾成已入帳的會改回未入帳（記錄保留）。"
               "處理後，10 月會變成待確認，由你核對後勾確認入帳。")
    preview = pd.DataFrame([{
        "處理方式": "刪除" if r["_action"] == "delete" else "改回未入帳",
        "來源": r["_table"], "平台": r.get("platform", ""), "基金名稱": r.get("fund_name", ""), "幣別": r.get("currency", ""),
        "除息日": _format_dividend_date(r.get("ex_date", "")), "發放日": _format_dividend_date(r.get("pay_date", "")),
        "單位數": r.get("units_at_ex"), "每單位配息": r.get("actual_div_amount") or r.get("div_amount"),
        "已入帳": "是" if normalize_bool(r.get("is_paid", False), False) else "否",
    } for r in changes])
    st.markdown(html_table(preview, ["單位數", "每單位配息"]), unsafe_allow_html=True)
    with st.form("delete_auto_catch_up"):
        confirmed = st.checkbox("我確認以上記錄都不是我操作的，執行還原")
        if st.form_submit_button("↩️ 還原 10/11 自動變動") and confirmed:
            sb = supabase_client()
            groups = set()
            for r in changes:
                rid = int(float(r["id"]))
                if r["_action"] == "delete":
                    sb.table(r["_table"]).delete().eq("id", rid).execute()
                else:
                    sb.table(r["_table"]).update({"is_paid": False}).eq("id", rid).execute()
                groups.add((normalize_text(r.get("fund_code", "")), normalize_text(r.get("platform", "")),
                            normalize_text(r.get("currency", ""))))
            for fund_code, platform, currency in groups:
                recompute_position_dividend_original_total(fund_code, platform, currency)
            st.cache_data.clear()
            st.success(f"已還原 {len(changes)} 筆並重算累計配息。")
            st.rerun()
