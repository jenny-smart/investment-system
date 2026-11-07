"""總帳「總覽」B1（加總Total）vs App 扣稅後總資產：差 1 元以上時，找出差在哪一類、哪一檔。

只讀取比對、不改任何資料。總覽 A2:B18 每列對應 App：
- 台股total → 台股扣稅後市值（台幣市值 − 賣出稅費）
- 渣打-pypl、渣打-sq → 美股該代號（sq 即 xyz）
- 基富通-台／人／日、渣打-大華／美金／南非、台新-南非／美金 → 基金依平台＋幣別（大華另列）
- 銀行total、保險total、懷思投資、uncle待還、外幣total → 非投資（Jennyall 本月）
- 待還total → −待還
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

TOLERANCE = 1.0  # 差 1 元以上就顯示
FUND_ROWS: dict[str, tuple[str, str, str]] = {  # 標籤 → (平台, 幣別, 名稱條件；! 開頭表示排除)
    "基富通-台": ("基富通", "TWD", ""), "基富通-人": ("基富通", "CNY", ""), "基富通-日": ("基富通", "JPY", ""),
    "渣打-大華": ("渣打基金", "USD", "大華"), "渣打-美金": ("渣打基金", "USD", "!大華"),
    "渣打-南非": ("渣打基金", "ZAR", ""), "台新-南非": ("台新基金", "ZAR", ""), "台新-美金": ("台新基金", "USD", ""),
}
US_ALIASES = {"sq": {"sq", "xyz"}}
OTHER_ROWS = ("銀行total", "保險total", "懷思投資", "uncle待還", "外幣total")


def _num(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value or "").replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def overview_rows(grid: list[list[Any]]) -> list[tuple[str, float]]:
    """總覽 A/B 欄：從「加總Total」那列起到「待還total」為止的 (標籤, 金額)。"""
    out, started = [], False
    for row in grid:
        label = str(row[0]).strip() if row else ""
        value = _num(row[1]) if len(row) > 1 else None
        if label.lower().startswith("加總"):
            started = True
        if started and label and value is not None:
            out.append((label, value))
        if started and label.startswith("待還"):
            break
    return out


def _fund_mask(df: pd.DataFrame, rule: tuple[str, str, str]) -> pd.Series:
    platform, currency, cond = rule
    mask = (df["asset_type"].astype(str) == "基金") & (df["platform"].astype(str) == platform) \
        & (df["currency"].astype(str).str.upper() == currency)
    if cond:
        has = df["name"].astype(str).str.contains(cond.lstrip("!"), regex=False)
        mask &= ~has if cond.startswith("!") else has
    return mask


def category_mask(label: str, df: pd.DataFrame) -> pd.Series | None:
    """這個總覽分類在 App 持倉裡是哪幾列；非投資回 None。"""
    if df.empty:
        return None
    if label.lower().startswith("台股"):
        return df["asset_type"].astype(str) == "台股"
    if label in FUND_ROWS:
        return _fund_mask(df, FUND_ROWS[label])
    if label.startswith("渣打-") and label not in FUND_ROWS:
        code = label.split("-", 1)[1].strip().lower()
        codes = US_ALIASES.get(code, {code})
        is_us = (df["asset_type"].astype(str) == "美股") | (df["platform"].astype(str) == "美股")
        # 代號可能存成 PYPL、PYPL.US、NASDAQ:PYPL，或只有名稱 pypl：拆成英文字詞比對
        words = (df["ticker"].astype(str) + " " + df["name"].astype(str)).str.lower().map(
            lambda text: set(re.findall(r"[a-z]+", text)))
        return is_us & words.map(lambda w: bool(w & codes))
    return None


def _after_tax(df: pd.DataFrame) -> float:
    value = pd.to_numeric(df.get("台幣市值"), errors="coerce").fillna(0).sum()
    tax = pd.to_numeric(df.get("賣出稅費"), errors="coerce").fillna(0).sum() if "賣出稅費" in df else 0
    return float(value - tax)


def app_value(label: str, df: pd.DataFrame, other: dict[str, Any] | None) -> float | None:
    if label.lower().startswith("加總"):
        if other is None:
            return None
        return _after_tax(df) + float(other["other_total"])
    mask = category_mask(label, df)
    if mask is not None:
        return _after_tax(df[mask])
    if other is None:
        return None
    if label in OTHER_ROWS:
        cat = other["categories"].get(label)
        return float(cat["total"]) if cat else None
    if label.startswith("待還"):
        return -float(other["deposits"])
    return None


def compare(rows: list[tuple[str, float]], df: pd.DataFrame, other: dict[str, Any] | None) -> pd.DataFrame:
    """[分類, 總覽, App, 差額(App−總覽)]，全部列。"""
    out = []
    for label, sheet_value in rows:
        app = app_value(label, df, other)
        out.append({"分類": label, "總覽": sheet_value, "App": app,
                    "差額": (app - sheet_value) if app is not None else None})
    return pd.DataFrame(out, columns=["分類", "總覽", "App", "差額"])


def detail(label: str, df: pd.DataFrame) -> pd.DataFrame:
    """有差的投資分類：App 每一檔的價格、價格來源、匯率、市值，給人對照總帳。"""
    mask = category_mask(label, df)
    if mask is None:
        return pd.DataFrame()
    part = df[mask].copy()
    cols = {"name": "名稱", "ticker": "代號", "units": "股數／單位", "即時價格/淨值": "價格／淨值",
            "價格來源": "價格來源", "基金淨值日期": "淨值日期", "匯率": "匯率", "台幣市值": "台幣市值", "賣出稅費": "賣出稅費"}
    keep = [c for c in cols if c in part]
    out = part[keep].rename(columns=cols).reset_index(drop=True)
    for col in ("價格／淨值", "匯率"):
        if col in out:
            out[col] = out[col].map(lambda v: f"{v:,.4f}" if isinstance(v, (int, float)) and pd.notna(v) else "")
    return out


def render(enriched: pd.DataFrame, other: dict[str, Any] | None) -> None:
    import streamlit as st
    from invest_app.core import OVERVIEW_SHEET_GID, html_table, load_sheet_grid, money
    try:
        rows = overview_rows(load_sheet_grid(OVERVIEW_SHEET_GID))
    except Exception as exc:
        st.caption(f"總帳對帳暫時無法讀取總覽：{exc}")
        return
    if not rows or enriched.empty:
        return
    table = compare(rows, enriched, other)
    total = table.iloc[0]
    if total["差額"] is None or pd.isna(total["差額"]) or abs(total["差額"]) < TOLERANCE:
        return
    diff = table.iloc[1:]
    diff = diff[diff["差額"].isna() | (diff["差額"].abs() >= TOLERANCE)]
    with st.expander(f"🔍 總帳對帳：總覽 B1 {money(total['總覽'])}，App 扣稅後 {money(total['App'])}，"
                     f"差 {total['差額']:+,.0f}（只顯示、不改資料）", expanded=False):
        st.markdown(html_table(diff, ["總覽", "App", "差額"]), unsafe_allow_html=True)
        explained = diff["差額"].dropna().sum()
        rest = total["差額"] - explained
        if abs(rest) >= TOLERANCE:
            st.caption(f"以上分類合計 {explained:+,.0f}，還有 {rest:+,.0f} 對不到分類（總覽 B1 公式或其他列）。")
        for label in diff["分類"]:
            part = detail(label, enriched)
            if part.empty:
                continue
            st.markdown(f"**{label}**：App 每一檔（請對照總帳的價格、淨值、匯率）")
            if label.startswith("台股"):
                st.caption("價格來源不是「TWSE即時」或收盤價的（買賣價備援、昨收、Yahoo）最可能跟總帳 J 欄不同。")
            st.markdown(html_table(part, ["股數／單位", "台幣市值", "賣出稅費"]), unsafe_allow_html=True)
