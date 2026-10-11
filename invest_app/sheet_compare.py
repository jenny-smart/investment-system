"""總帳「總覽」分頁基金累積配息原幣（N 欄）與資料庫累計配息原幣的比對（用原幣避免匯率差）。純計算，不依賴 Streamlit。"""
from __future__ import annotations

import difflib
import unicodedata
from typing import Any

import pandas as pd

# 總覽 F 欄的分類列 → (平台, 幣別)；分類列下方到空白列為止是該分類的基金
SHEET_FUND_SECTIONS: dict[str, tuple[str, str]] = {
    "基富通-台": ("基富通", "TWD"),
    "基富通-人民幣": ("基富通", "CNY"),
    "基富通-日": ("基富通", "JPY"),
    "渣打-美金": ("渣打基金", "USD"),
    "渣打-南非": ("渣打基金", "ZAR"),
    "台新-南非": ("台新基金", "ZAR"),
    "台新-美金": ("台新基金", "USD"),
}


def fund_key(name: Any) -> str:
    """名稱比對用：全形轉半形、去空白、小寫。"""
    return "".join(unicodedata.normalize("NFKC", str(name or "")).lower().split())


def _number(value: Any) -> float:
    text = str(value or "").replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def sheet_fund_dividends(grid: list[list[str]], name_header: str = "投資分類",
                         value_header: str = "累積配息原幣") -> list[dict[str, Any]]:
    """讀出每檔基金的總帳累積配息原幣；同分類同名的多列（分批買進）合併。"""
    header_row = next((i for i, row in enumerate(grid) if name_header in row and value_header in row), None)
    if header_row is None:
        raise RuntimeError(f"總覽分頁找不到「{name_header}」「{value_header}」標題")
    name_col = grid[header_row].index(name_header)
    value_col = grid[header_row].index(value_header)
    totals: dict[tuple[str, str], dict[str, Any]] = {}
    section = None
    for row in grid[header_row + 1:]:
        name = str(row[name_col]).strip() if name_col < len(row) else ""
        if not name:
            section = None  # 空白列結束目前分類
            continue
        if name in SHEET_FUND_SECTIONS:
            section = name
            continue
        if section is None:
            continue
        value = _number(row[value_col]) if value_col < len(row) else 0.0
        item = totals.setdefault((section, fund_key(name)), {"分類": section, "基金名稱": name, "總帳配息原幣": 0.0})
        item["總帳配息原幣"] += value
    return list(totals.values())


def compare_fund_dividends(sheet_rows: list[dict[str, Any]], enriched: pd.DataFrame) -> pd.DataFrame:
    """逐檔比對總帳與資料庫的累積配息原幣，只回傳有差異的基金。"""
    funds = enriched[enriched["asset_type"].astype(str) == "基金"] if not enriched.empty else enriched
    db: dict[tuple[str, str], dict[str, float]] = {}
    names: dict[tuple[str, str], dict[str, str]] = {}
    for _, r in funds.iterrows():
        sec = (str(r.get("platform", "")), str(r.get("currency", "")).upper())
        key = fund_key(r.get("name", ""))
        db.setdefault(sec, {}).setdefault(key, 0.0)
        db[sec][key] += float(pd.to_numeric(r.get("累計配息原幣"), errors="coerce") or 0)
        names.setdefault(sec, {})[key] = str(r.get("name", ""))

    rows: list[dict[str, Any]] = []
    used: set[tuple[tuple[str, str], str]] = set()
    for item in sheet_rows:
        sec = SHEET_FUND_SECTIONS[item["分類"]]
        candidates = db.get(sec, {})
        key = fund_key(item["基金名稱"])
        if key not in candidates:
            close = difflib.get_close_matches(key, list(candidates), n=1, cutoff=0.6)
            key = close[0] if close else None
        db_value = candidates.get(key) if key else None
        if key:
            used.add((sec, key))
        rows.append({**item, "資料庫配息原幣": db_value})
    # 資料庫有、總帳沒有的基金
    section_of = {v: k for k, v in SHEET_FUND_SECTIONS.items()}
    for sec, funds_in_sec in db.items():
        for key, value in funds_in_sec.items():
            if (sec, key) not in used and value:
                rows.append({"分類": section_of.get(sec, f"{sec[0]}-{sec[1]}"), "基金名稱": names[sec][key],
                             "總帳配息原幣": None, "資料庫配息原幣": value})

    df = pd.DataFrame(rows, columns=["分類", "基金名稱", "總帳配息原幣", "資料庫配息原幣"])
    df.insert(1, "幣別", df["分類"].map(lambda s: SHEET_FUND_SECTIONS.get(s, ("", ""))[1]))
    df["差額"] = df["資料庫配息原幣"].fillna(0) - df["總帳配息原幣"].fillna(0)
    # 只留有差異的基金（原幣差超過 0.5，避免小數進位誤報）
    return df[df["差額"].abs() >= 0.5].reset_index(drop=True)
