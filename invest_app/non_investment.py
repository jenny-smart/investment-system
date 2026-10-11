"""非投資資產：總帳 Jennyall 的銀行／保險／懷思投資／uncle待還／外幣、總資產列、非投資總覽頁、快照欄位。"""
from __future__ import annotations

import html as html_lib
from typing import Any

import pandas as pd
import streamlit as st

from asset_summary import monthly_income_block
from invest_app.dividends import build_estimated_dividend_table
from invest_app.core import (
    html_table,
    OVERVIEW_SHEET_GID,
    load_other_assets,
    load_sheet_grid,
    money,
    normalize_text,
    supabase_client,
    to_float,
    tw_now,
)


OTHER_ASSET_FIELDS = {
    "銀行total": "bank_total",
    "保險total": "insurance_total",
    "懷思投資": "huaisi_total",
    "uncle待還": "uncle_total",
    "外幣total": "fx_cash_total",
}


OTHER_ASSET_ICONS = {"銀行total": "🏦", "保險total": "🛡️", "懷思投資": "🤝", "uncle待還": "👨", "外幣total": "💴"}


# 新增在 portfolio_snapshots / latest_portfolio_values 的欄位；資料表還沒加欄位時自動略過。
OTHER_SNAPSHOT_KEYS = [*OTHER_ASSET_FIELDS.values(), "deposits_total", "other_assets_total", "grand_total"]


def other_asset_snapshot_fields(total_investment: float) -> dict[str, float]:
    return other_asset_fields(load_other_assets(), total_investment)


def other_asset_fields(other: dict[str, Any] | None, total_investment: float) -> dict[str, float]:
    if not other:
        return {}
    fields = {OTHER_ASSET_FIELDS[name]: round(data["total"], 0) for name, data in other["categories"].items()}
    fields["deposits_total"] = round(other["deposits"], 0)
    fields["other_assets_total"] = round(other["other_total"], 0)
    fields["grand_total"] = round(total_investment + other["other_total"], 0)
    return fields


def write_with_optional_columns(table: str, data: dict[str, Any], upsert_on: str = "") -> bool:
    """寫入 Supabase；若新欄位尚未建立，退回只寫原有欄位。回傳是否含新欄位。"""
    query = supabase_client().table(table)
    try:
        (query.upsert(data, on_conflict=upsert_on) if upsert_on else query.insert(data)).execute()
        return True
    except Exception as exc:
        extra = [k for k in OTHER_SNAPSHOT_KEYS if k in data]
        if not extra or not any(k in str(exc) for k in extra):
            raise
        base = {k: v for k, v in data.items() if k not in extra}
        query = supabase_client().table(table)
        (query.upsert(base, on_conflict=upsert_on) if upsert_on else query.insert(base)).execute()
        st.session_state["snapshot_columns_missing"] = True
        return False


def _group_header_html(title: str, fields: list[tuple[str, str, str]]) -> str:
    """與 render_platform_group 相同樣式的大標題列。fields: (標籤, 值, 顏色)"""
    cells = "".join(
        f'<span style="min-width:120px;font-family:monospace">'
        f'<div style="font-size:10px;color:#6b7280;font-family:sans-serif">{label}</div>'
        f'<div style="font-size:14px;font-weight:700;color:{color}">{value}</div></span>'
        for label, value, color in fields
    )
    return f"""
<div style="background:#fff;color:#1a2e22;padding:14px 20px;border-radius:12px;
            display:flex;flex-wrap:wrap;align-items:center;gap:18px;
            margin:24px 0 4px 0;font-size:13px;font-weight:700;
            border:1.5px solid #d1e8dc;border-left:5px solid #10b981;
            box-shadow:0 2px 10px rgba(16,185,129,.08);">
  <span style="font-size:16px;font-family:sans-serif;min-width:90px;font-weight:800;color:#10b981">{title}</span>
  {cells}
</div>"""


def _sub_header_html(label: str, fields: list[tuple[str, str, str]]) -> str:
    """與 render_sub_group 相同樣式的子標題列。"""
    cells = "".join(
        f'<span style="min-width:100px;font-family:monospace">'
        f'<span style="color:#9ca3af;font-size:10px">{name} </span>'
        f'<span style="color:{color}">{value}</span></span>'
        for name, value, color in fields
    )
    return f"""
<div style="background:#f0fdf4;color:#1a2e22;padding:8px 16px;border-radius:8px;
            display:flex;flex-wrap:wrap;align-items:center;gap:14px;
            margin:6px 0 1px 20px;font-size:12px;font-weight:600;
            border:1px solid #bbf7d0;border-left:3px solid #10b981;">
  <span style="font-size:12px;font-family:sans-serif;min-width:90px;font-weight:800;color:#065f46">{label}</span>
  {cells}
</div>"""


# 最上方總資產列顯示的類別；其餘類別留在總覽的投資平台卡片下方。
TOP_ROW_CATEGORIES = ["銀行total", "外幣total"]


def render_total_asset_row(total_investment: float, other: dict[str, Any] | None) -> None:
    """總台幣市值那排下方：總資產、其他資產小計、扣除待還、銀行、外幣（每個分頁都看得到）。"""
    if not other:
        return
    cols = st.columns(7)
    cols[0].metric("💎 總資產", money(total_investment + other["other_total"]))
    cols[1].metric("其他資產小計", money(other["other_total"]))
    cols[2].metric("➖ 扣除待還（別人寄放）", money(-other["deposits"]))
    for col, name in zip(cols[3:], TOP_ROW_CATEGORIES):
        col.metric(f"{OTHER_ASSET_ICONS.get(name, '💼')} {name}", money(other["categories"][name]["total"]))
    cols[5].caption(f"總帳 {other['month']}（Jennyall {other['column']} 欄），每月自動換欄。")


def render_other_assets_tab(enriched: pd.DataFrame) -> None:
    """非投資總覽分頁：各類小卡 + 明細（比照平台群組格式）+ 每月加總。"""
    st.markdown("### 🏦 非投資總覽")
    other = load_other_assets()
    if not other:
        st.warning(f"讀不到總帳其他資產：{st.session_state.get('other_assets_error', '')}")
        return
    st.caption(f"總帳 {other['month']}（Jennyall {other['column']} 欄），每月自動換欄。")
    cols = st.columns(5)
    for col, (name, data) in zip(cols, other["categories"].items()):
        col.metric(f"{OTHER_ASSET_ICONS.get(name, '💼')} {name}", money(data["total"]))
    render_other_asset_groups(other)
    render_monthly_income_summary(enriched)


def render_other_asset_groups(other: dict[str, Any] | None) -> None:
    """台新基金下方：其他資產大標題 + 每項子標題與明細表。"""
    if not other:
        return
    st.markdown(_group_header_html("🏦 其他資產", [
        ("五項合計", money(other["category_sum"]), "#1a2e22"),
        ("扣除待還", money(-other["deposits"]), "#dc2626"),
        ("其他資產小計", money(other["other_total"]), "#059669"),
        ("月份", html_lib.escape(other["month"]), "#6b7280"),
    ]), unsafe_allow_html=True)
    for name, data in other["categories"].items():
        st.markdown(_sub_header_html(f"{OTHER_ASSET_ICONS.get(name, '💼')} {name}", [
            ("金額", money(data["total"]), "#1a2e22"),
            ("筆數", str(len(data["items"])), "#6b7280"),
        ]), unsafe_allow_html=True)
        if data["items"]:
            items = pd.DataFrame(data["items"], columns=["名稱", "金額"])
            items["名稱"] = items["名稱"].replace("", "（無名稱）")
            st.markdown(f'<div style="margin-left:20px">{html_table(items, ["金額"])}</div>', unsafe_allow_html=True)


# 每月加總各列對應的基金配息預估（平台、幣別、名稱篩選）；沒有對應的列（利息、股利…）預估留空。
MONTHLY_ESTIMATE_RULES: dict[str, tuple[str, str, str]] = {
    "配息-基富通-台": ("基富通", "TWD", ""),
    "配息-基富通-人": ("基富通", "CNY", ""),
    "配息-基富通-日": ("基富通", "JPY", ""),
    "配息-渣打-大華": ("渣打基金", "USD", "大華"),
    "配息-渣打-美金": ("渣打基金", "USD", "!大華"),
    "配息-渣打-南非": ("渣打基金", "ZAR", ""),
    "配息-台新-南非": ("台新基金", "ZAR", ""),
    "配息-台新-美金": ("台新基金", "USD", ""),
}
# 小計列 = 下列項目的預估加總（與總帳「總覽」B 欄公式相同結構）
MONTHLY_SUBTOTALS: dict[str, list[str]] = {
    "台幣-加總": ["股利-台股", "配息-懷思投資", "回饋金-保險", "利息-銀行"],
    "台幣-境外": ["配息-基富通-台"],
    "外幣-加總": ["配息-基富通-人", "配息-基富通-日", "配息-渣打-大華", "配息-渣打-美金",
                "配息-渣打-南非", "配息-台新-南非", "配息-台新-美金"],
    "每月加總": ["台幣-加總", "台幣-境外", "外幣-加總"],
}


def monthly_dividend_estimates(estimate_df: pd.DataFrame, labels: list[str]) -> dict[str, float | None]:
    """依平台／幣別把預估配息表（台幣）對到每月加總各列。"""
    out: dict[str, float | None] = {}
    for label in labels:
        rule = MONTHLY_ESTIMATE_RULES.get(label)
        if not rule or estimate_df.empty:
            out[label] = None
            continue
        platform, currency, name_filter = rule
        rows = estimate_df[(estimate_df["平台"] == platform) & (estimate_df["幣別"] == currency)]
        if name_filter.startswith("!"):
            rows = rows[~rows["基金名稱"].astype(str).str.contains(name_filter[1:])]
        elif name_filter:
            rows = rows[rows["基金名稱"].astype(str).str.contains(name_filter)]
        out[label] = float(pd.to_numeric(rows["預估配息台幣"], errors="coerce").fillna(0).sum()) if not rows.empty else None
    for _ in range(2):  # 每月加總依賴其他小計，算兩輪
        for label, parts in MONTHLY_SUBTOTALS.items():
            values = [out.get(p) for p in parts if out.get(p) is not None]
            out[label] = sum(values) if values else None
    return out


def render_monthly_income_summary(enriched: pd.DataFrame) -> None:
    """總帳「總覽」分頁的每月加總；預估 = 依平台、幣別加總的基金配息預估（台幣）。"""
    try:
        rows = monthly_income_block(load_sheet_grid(OVERVIEW_SHEET_GID))
    except Exception as exc:
        st.warning(f"讀不到每月加總：{exc}")
        return
    if not rows:
        return
    try:
        estimates = monthly_dividend_estimates(build_estimated_dividend_table(enriched), [r["項目"] for r in rows])
    except Exception as exc:
        st.caption(f"配息預估暫時算不出來：{exc}")
        estimates = {}
    head, details = rows[0], rows[1:]
    st.markdown(_group_header_html("🧮 每月加總", [
        ("本月金額", money(head["金額"]), "#1a2e22"),
        ("預估", money(estimates.get(head["項目"])), "#7c3aed"),
    ]), unsafe_allow_html=True)
    df = pd.DataFrame([{"名稱": r["項目"], "金額": r["金額"], "台/外": r["台/外"], "預估": estimates.get(r["項目"])}
                       for r in details])
    st.markdown(html_table(df, ["金額", "預估"]), unsafe_allow_html=True)


def _take_snapshot_now(enriched: pd.DataFrame, trigger: str = "manual") -> dict:
    """即時抓取各平台市值並回傳 dict（供手動記錄用）"""
    if enriched is None or enriched.empty:
        return {}

    platform_val: dict[str, float] = {
        "台股": 0, "美股": 0, "基富通": 0, "渣打基金": 0, "台新基金": 0
    }
    total_cost_sum = 0.0
    total_div_sum  = 0.0

    for _, r in enriched.iterrows():
        plt = normalize_text(r.get("platform", ""))
        val = to_float(r.get("台幣市值"))
        cost= to_float(r.get("台幣成本"))
        div = to_float(r.get("累計已領配息"))
        if plt in platform_val and val:
            platform_val[plt] += val
        if cost: total_cost_sum += cost
        if div:  total_div_sum  += div

    total = sum(platform_val.values())

    return {
        "total_twd":           round(total, 0),
        "tw_stock":            round(platform_val["台股"], 0),
        "us_stock":            round(platform_val["美股"], 0),
        "kifutong":            round(platform_val["基富通"], 0),
        "scb":                 round(platform_val["渣打基金"], 0),
        "taishin":             round(platform_val["台新基金"], 0),
        "total_cost":          round(total_cost_sum, 0),
        "total_pnl":           round(total - total_cost_sum, 0),
        "cumulative_dividend": round(total_div_sum, 0),
        "trigger":             trigger,
        "note":                f"手動快照 {tw_now().strftime('%Y-%m-%d %H:%M')}",
        **other_asset_snapshot_fields(total),
    }
