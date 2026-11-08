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


def sheet_name_values(grid: list[list[Any]]) -> dict[str, float]:
    """總帳「台股」分頁 A 欄名稱、B 欄市值 → {名稱: 市值合計}（同名多列相加）。"""
    out: dict[str, float] = {}
    for row in grid:
        name = str(row[0]).strip() if row else ""
        value = _num(row[1]) if len(row) > 1 else None
        if name and value is not None and not name.lower().startswith(("加總", "total")):
            out[name] = out.get(name, 0.0) + value
    return out


def tw_stock_diff(sheet_values: dict[str, float], df: pd.DataFrame) -> pd.DataFrame:
    """逐檔：總帳台股分頁市值 vs App 台幣市值（同名合併），只列差 1 元以上，差最多的在前。"""
    tw = df[df["asset_type"].astype(str) == "台股"].copy()
    if tw.empty or not sheet_values:
        return pd.DataFrame()
    tw["台幣市值"] = pd.to_numeric(tw["台幣市值"], errors="coerce").fillna(0)
    tw["units"] = pd.to_numeric(tw["units"], errors="coerce").fillna(0)
    rows = []
    for name, part in tw.groupby(tw["name"].astype(str).str.strip(), sort=False):
        app = float(part["台幣市值"].sum())
        units = float(part["units"].sum())
        if name not in sheet_values:
            if units > 0:
                rows.append({"名稱": name, "總帳市值": None, "App 市值": app, "差額": None, "股數": units,
                             "App 價格": part["即時價格/淨值"].dropna().iloc[0] if part["即時價格/淨值"].notna().any() else None,
                             "總帳推算價格": None, "價格來源": "、".join(part["價格來源"].astype(str).unique()) if "價格來源" in part else "",
                             "說明": "總帳台股分頁找不到這個名稱"})
            continue
        sheet = sheet_values[name]
        if abs(app - sheet) < TOLERANCE:
            continue
        price = part["即時價格/淨值"].dropna().iloc[0] if part["即時價格/淨值"].notna().any() else None
        rows.append({"名稱": name, "總帳市值": sheet, "App 市值": app, "差額": app - sheet, "股數": units,
                     "App 價格": price, "總帳推算價格": sheet / units if units else None,
                     "價格來源": "、".join(part["價格來源"].astype(str).unique()) if "價格來源" in part else "",
                     "說明": ""})
    for name, sheet in sheet_values.items():
        if name not in set(tw["name"].astype(str).str.strip()) and abs(sheet) >= TOLERANCE:
            rows.append({"名稱": name, "總帳市值": sheet, "App 市值": None, "差額": None, "股數": None,
                         "App 價格": None, "總帳推算價格": None, "價格來源": "", "說明": "App 沒有這檔持倉"})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["_abs"] = out["差額"].abs().fillna(float("inf"))
    out = out.sort_values("_abs", ascending=False).drop(columns="_abs").reset_index(drop=True)
    for col in ("App 價格", "總帳推算價格"):
        out[col] = out[col].map(lambda v: f"{v:,.2f}" if isinstance(v, (int, float)) and pd.notna(v) else "")
    return out


STOCK_LEDGER_ID = "17HPytZKOPR_9Od_wor-xEx9kpccJlPS2v6B0Dz6MRYc"   # 股票總帳
STOCK_LEDGER_GID = "0"                                               # 「台股」工作表
LEDGER_RANGE = "C7:J600"                                             # C 代碼、I 股數、J 市價


def ledger_stocks(rows: list[list[Any]]) -> dict[str, dict[str, float]]:
    """股票總帳台股工作表 C7:J → {代碼: {"units": I 欄合計, "price": J 欄}}。"""
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        if len(row) < 8:
            continue
        code = re.sub(r"\.(TW|TWO)$", "", str(row[0]).strip().upper())
        units, price = _num(row[6]), _num(row[7])
        if not re.fullmatch(r"[0-9]{4,6}[A-Z]?", code) or units is None:
            continue
        item = out.setdefault(code, {"units": 0.0, "price": 0.0})
        item["units"] += units
        if price:
            item["price"] = price
    return out


def tw_ledger_diff(ledger: dict[str, dict[str, float]], df: pd.DataFrame) -> pd.DataFrame:
    """逐檔：股票總帳（I 股數 × J 市價）vs App（股數、價格），標出差在價格還是股數。只列差 ≥1 元。"""
    tw = df[df["asset_type"].astype(str) == "台股"].copy()
    if tw.empty or not ledger:
        return pd.DataFrame()
    tw["_code"] = tw["ticker"].astype(str).str.upper().str.replace(r"\.(TW|TWO)$", "", regex=True)
    tw["units"] = pd.to_numeric(tw["units"], errors="coerce").fillna(0)
    tw["台幣市值"] = pd.to_numeric(tw["台幣市值"], errors="coerce").fillna(0)
    rows = []
    for code, part in tw.groupby("_code", sort=False):
        app_units = float(part["units"].sum())
        app_price = part["即時價格/淨值"].dropna().iloc[0] if part["即時價格/淨值"].notna().any() else None
        app_value = float(part["台幣市值"].sum())
        sh = ledger.get(code)
        if sh is None:
            if app_units > 0:
                rows.append({"名稱": part["name"].iloc[0], "代號": code, "總帳股數": None, "App 股數": app_units,
                             "總帳市價": None, "App 價格": app_price, "總帳市值": None, "App 市值": app_value,
                             "差額": None, "差在哪裡": "股票總帳台股工作表沒有這檔"})
            continue
        sheet_value = sh["units"] * sh["price"]
        diff = app_value - sheet_value
        if abs(diff) < TOLERANCE:
            continue
        reasons = []
        if app_price is not None and abs(app_price - sh["price"]) > 1e-6:
            reasons.append(f"價格不同（影響約 {(app_price - sh['price']) * app_units:+,.0f}）")
        if abs(app_units - sh["units"]) > 1e-6:
            reasons.append(f"股數不同（影響約 {(app_units - sh['units']) * sh['price']:+,.0f}）")
        rows.append({"名稱": part["name"].iloc[0], "代號": code, "總帳股數": sh["units"], "App 股數": app_units,
                     "總帳市價": sh["price"], "App 價格": app_price, "總帳市值": sheet_value, "App 市值": app_value,
                     "差額": diff, "差在哪裡": "；".join(reasons) or "四捨五入"})
    app_codes = set(tw["_code"])
    for code, sh in ledger.items():
        if code not in app_codes and sh["units"] > 0:
            rows.append({"名稱": "", "代號": code, "總帳股數": sh["units"], "App 股數": None, "總帳市價": sh["price"],
                         "App 價格": None, "總帳市值": sh["units"] * sh["price"], "App 市值": None, "差額": None,
                         "差在哪裡": "App 沒有這檔持倉"})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["_abs"] = out["差額"].abs().fillna(float("inf"))
    return out.sort_values("_abs", ascending=False).drop(columns="_abs").reset_index(drop=True)


UNIFIED = ["分類", "名稱", "總帳價格／淨值", "App 價格／淨值", "總帳匯率", "App 匯率", "總帳股數／單位",
           "App 股數／單位", "總帳市值", "App 市值", "差額", "差在哪裡"]
UNIFIED_NUMBERS = {"總帳價格／淨值": 4, "App 價格／淨值": 4, "總帳匯率": 4, "App 匯率": 4,
                   "總帳股數／單位": 4, "App 股數／單位": 4, "總帳市值": 0, "App 市值": 0, "差額": 0}


def unify(label: str, table: pd.DataFrame) -> pd.DataFrame:
    """台股（股票總帳）、美股／基金（總覽）兩種比對表轉成同一組欄位，好合成一張表、欄位對齊。"""
    if table.empty:
        return pd.DataFrame(columns=UNIFIED)
    pick = (lambda *names: next((table[n] for n in names if n in table), pd.Series([None] * len(table))))
    out = pd.DataFrame({
        "分類": label,
        "名稱": pick("名稱"),
        "總帳價格／淨值": pick("總帳市價", "總覽淨值"),
        "App 價格／淨值": pick("App 價格", "App 淨值"),
        "總帳匯率": pick("總覽匯率"),
        "App 匯率": pick("App 匯率"),
        "總帳股數／單位": pick("總帳股數", "總覽單位數"),
        "App 股數／單位": pick("App 股數", "單位數"),
        "總帳市值": pick("總帳市值", "總覽市值"),
        "App 市值": pick("App 市值"),
        "差額": pick("差額"),
        "差在哪裡": pick("差在哪裡"),
    })
    if label.lower().startswith("台股"):
        out["總帳匯率"], out["App 匯率"] = 1.0, 1.0
    return out[UNIFIED]


def load_tw_ledger() -> dict[str, dict[str, float]]:
    """讀股票總帳「台股」工作表 C7:J（需要「知道連結的人可檢視」）。"""
    import csv
    import io

    import requests
    response = requests.get(f"https://docs.google.com/spreadsheets/d/{STOCK_LEDGER_ID}/gviz/tq",
                            params={"tqx": "out:csv", "gid": STOCK_LEDGER_GID, "range": LEDGER_RANGE,
                                    "headers": "0", "tq": "options no_format"}, timeout=30)
    response.raise_for_status()
    if "<html" in response.text[:200].lower():
        raise RuntimeError("股票總帳沒有開放「知道連結的人可檢視」，App 讀不到")
    return ledger_stocks(list(csv.reader(io.StringIO(response.text))))


def load_tw_sheet_values() -> dict[str, float]:
    """總帳（2025Jenny-總帳）「台股」分頁 A/B 欄，用分頁名稱讀（gviz CSV）。"""
    import csv
    import io
    from urllib.parse import quote

    import requests
    from invest_app.core import MAIN_GOOGLE_SHEET_ID
    url = (f"https://docs.google.com/spreadsheets/d/{MAIN_GOOGLE_SHEET_ID}/gviz/tq?tqx=out:csv"
           f"&sheet={quote('台股')}&range=A:B")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return sheet_name_values(list(csv.reader(io.StringIO(response.text))))


SECTION_OF = {"渣打-pypl": "美股", "渣打-sq": "美股", "渣打-大華": "渣打-美金", "基富通-人": "基富通-人民幣"}


def overview_items(grid: list[list[Any]]) -> list[dict[str, Any]]:
    """總覽 F 欄起的投資表：[{section, name, nav, value}]（依標題「投資分類」「現值」「台幣市值」找欄）。"""
    header = next((i for i, r in enumerate(grid) if "投資分類" in [str(c).strip() for c in r]), None)
    if header is None:
        return []
    names = [str(c).strip() for c in grid[header]]
    name_col = names.index("投資分類")
    nav_col = names.index("現值") if "現值" in names else None
    value_col = names.index("台幣市值") if "台幣市值" in names else None
    out, section = [], None
    for row in grid[header + 1:]:
        name = str(row[name_col]).strip() if name_col < len(row) else ""
        if not name:
            continue
        if name in ("美股", *FUND_SECTIONS):
            section = name
            continue
        if section is None or re.fullmatch(r"[\d.,\-]+", name):
            continue
        out.append({"section": section, "name": name,
                    "nav": _num(row[nav_col]) if nav_col is not None and nav_col < len(row) else None,
                    "value": _num(row[value_col]) if value_col is not None and value_col < len(row) else None})
    return out


FUND_SECTIONS = ("基富通-台", "基富通-人民幣", "基富通-日", "渣打-美金", "渣打-南非", "台新-南非", "台新-美金")


def _key(text: Any) -> str:
    import unicodedata
    return re.sub(r"[\s()（）\-—_]", "", unicodedata.normalize("NFKC", str(text or "")).lower())


def item_diff(label: str, items: list[dict[str, Any]], df: pd.DataFrame,
              rates: dict[str, float]) -> pd.DataFrame:
    """美股／基金分類逐檔：總覽（現值、匯率、台幣市值）vs App，並判斷差在哪裡。"""
    import difflib
    mask = category_mask(label, df)
    if mask is None:
        return pd.DataFrame()
    app = df[mask].copy()
    section = SECTION_OF.get(label, label)
    sheet = [i for i in items if i["section"] == section]
    if label == "渣打-大華":
        sheet = [i for i in sheet if "大華" in i["name"]]
    elif label == "渣打-美金":
        sheet = [i for i in sheet if "大華" not in i["name"]]
    elif label.startswith("渣打-") and section == "美股":
        codes = US_ALIASES.get(label.split("-", 1)[1].lower(), {label.split("-", 1)[1].lower()})
        sheet = [i for i in sheet if set(re.findall(r"[a-z]+", i["name"].lower())) & codes]
    # 總覽同名（分批）多列：市值相加
    merged: dict[str, dict[str, Any]] = {}
    for i in sheet:
        m = merged.setdefault(_key(i["name"]), {"name": i["name"], "nav": i["nav"], "value": 0.0})
        m["value"] += i["value"] or 0.0
    rows, used = [], set()
    app["_k"] = app["name"].astype(str).map(_key)
    for k, part in app.groupby("_k", sort=False):
        target = k if k in merged else next(iter(difflib.get_close_matches(k, list(merged), n=1, cutoff=0.5)), None)
        if target is None and len(merged) == 1 and app["_k"].nunique() == 1:
            target = next(iter(merged))   # 美股單檔：名稱寫法不同也算同一檔
        sh = merged.get(target) if target else None
        if target:
            used.add(target)
        cur = str(part["currency"].iloc[0]).upper()
        units = float(pd.to_numeric(part.get("市值股數", part.get("units")), errors="coerce").fillna(0).sum())
        app_nav = part["即時價格/淨值"].dropna().iloc[0] if part["即時價格/淨值"].notna().any() else None
        app_fx = part["匯率"].dropna().iloc[0] if part["匯率"].notna().any() else None
        app_value = float(pd.to_numeric(part["台幣市值"], errors="coerce").fillna(0).sum())
        sheet_fx = rates.get(cur)
        rows.append(_reason_row(str(part["name"].iloc[0]), sh, app_nav, app_fx, sheet_fx, units, app_value))
    for k, sh in merged.items():
        if k not in used:
            rows.append({"名稱": sh["name"], "總覽淨值": sh["nav"], "App 淨值": None, "總覽匯率": None,
                         "App 匯率": None, "單位數": None, "總覽單位數": None, "總覽市值": sh["value"], "App 市值": None,
                         "差額": None, "差在哪裡": "App 沒有這檔"})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out[(out["差額"].isna() & (out["總覽市值"].fillna(0).abs() >= TOLERANCE) | out["App 市值"].notna())
              & (out["差額"].isna() | (out["差額"].abs() >= TOLERANCE))]
    return out.reset_index(drop=True)


def _reason_row(name, sh, app_nav, app_fx, sheet_fx, units, app_value):
    if sh is None:
        return {"名稱": name, "總覽淨值": None, "App 淨值": app_nav, "總覽匯率": sheet_fx, "App 匯率": app_fx,
                "單位數": units, "總覽單位數": None, "總覽市值": None, "App 市值": app_value, "差額": None, "差在哪裡": "總覽找不到這檔"}
    diff = app_value - (sh["value"] or 0.0)
    reasons = []
    sheet_units = (sh["value"] or 0) / (sh["nav"] * sheet_fx) if sh["nav"] and sheet_fx else None
    if sh["nav"] and app_nav and abs(app_nav - sh["nav"]) > 1e-6 * max(1.0, abs(sh["nav"])):
        reasons.append(f"淨值／價格不同（影響約 {(app_nav - sh['nav']) * units * (app_fx or 1):+,.0f}）")
    if sheet_fx and app_fx and abs(app_fx - sheet_fx) > 1e-9:
        reasons.append(f"匯率不同（影響約 {(app_fx - sheet_fx) * units * (app_nav or 0):+,.0f}）")
    if not reasons and sheet_units is not None:
        if units and abs(sheet_units - units) > max(0.01, units * 0.0005):
            reasons.append(f"單位數不同（總覽約 {sheet_units:,.4f}，App {units:,.4f}）")
    if not reasons:
        reasons.append("淨值、匯率、單位數都一樣：四捨五入差")
    return {"名稱": name, "總覽淨值": sh["nav"], "App 淨值": app_nav, "總覽匯率": sheet_fx, "App 匯率": app_fx,
            "單位數": units, "總覽單位數": sheet_units, "總覽市值": sh["value"], "App 市值": app_value, "差額": diff,
            "差在哪裡": "；".join(reasons)}


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
        tables, notes = [], []
        for label in diff["分類"]:
            try:
                if label.lower().startswith("台股"):
                    tables.append(unify(label, tw_ledger_diff(load_tw_ledger(), enriched)))
                    continue
                from invest_app.core import OVERVIEW_SHEET_GID as _gid, load_sheet_raw_grid
                from invest_app.sheet_compare import sheet_fx_rates
                items = overview_items(load_sheet_raw_grid(_gid))
                rates = sheet_fx_rates(load_sheet_grid(_gid))
                tables.append(unify(label, item_diff(label, items, enriched, rates) if items else pd.DataFrame()))
            except Exception as exc:
                notes.append(f"{label}：讀不到總帳明細（{exc}）")
        tables = [t for t in tables if not t.empty]
        if tables:
            merged = pd.concat(tables, ignore_index=True)
            st.markdown(f"**逐檔比對：差在這 {len(merged)} 檔**（總帳 vs App；差額＝App−總帳；"
                        "台股看股票總帳台股工作表 I 股數 × J 價格，美股／基金看總覽）")
            st.markdown(html_table(merged, UNIFIED_NUMBERS), unsafe_allow_html=True)
        for note in notes:
            st.caption(note)
