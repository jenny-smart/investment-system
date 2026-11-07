"""總帳「總覽」分頁基金累積配息原幣（N 欄）與資料庫累計配息原幣的比對（用原幣避免匯率差）。純計算，不依賴 Streamlit。"""
from __future__ import annotations

import difflib
import unicodedata
from typing import Any, Callable

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


def _is_number_text(text: str) -> bool:
    try:
        float(text.replace(",", ""))
        return True
    except ValueError:
        return False


def _number(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
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
        if not name or _is_number_text(name):
            section = None  # 空白列（或表尾數字列）結束目前分類
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
    ids: dict[tuple[str, str], dict[str, Any]] = {}
    for _, r in funds.iterrows():
        sec = (str(r.get("platform", "")), str(r.get("currency", "")).upper())
        key = fund_key(r.get("name", ""))
        db.setdefault(sec, {}).setdefault(key, 0.0)
        db[sec][key] += float(pd.to_numeric(r.get("累計配息原幣"), errors="coerce") or 0)
        names.setdefault(sec, {})[key] = str(r.get("name", ""))
        ids.setdefault(sec, {}).setdefault(key, r.get("id"))

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
        rows.append({**item, "資料庫配息原幣": db_value, "_position_id": ids.get(sec, {}).get(key) if key else None})
    # 資料庫有、總帳沒有的基金
    section_of = {v: k for k, v in SHEET_FUND_SECTIONS.items()}
    for sec, funds_in_sec in db.items():
        for key, value in funds_in_sec.items():
            if (sec, key) not in used and value:
                rows.append({"分類": section_of.get(sec, f"{sec[0]}-{sec[1]}"), "基金名稱": names[sec][key],
                             "總帳配息原幣": None, "資料庫配息原幣": value, "_position_id": ids[sec][key]})

    df = pd.DataFrame(rows, columns=["分類", "基金名稱", "總帳配息原幣", "資料庫配息原幣", "_position_id"])
    df.insert(1, "幣別", df["分類"].map(lambda s: SHEET_FUND_SECTIONS.get(s, ("", ""))[1]))
    df["差額"] = df["資料庫配息原幣"].fillna(0) - df["總帳配息原幣"].fillna(0)
    # 只留有差異的基金（原幣差超過 0.5，避免小數進位誤報）
    return df[df["差額"].abs() >= 0.5].reset_index(drop=True)


def sheet_value_for(sheet_rows: list[dict[str, Any]], platform: str, currency: str, name: str) -> float | None:
    """單一基金在總帳的累積配息原幣（N 欄）；平台＋幣別找分類，名稱模糊比對。"""
    sections = {k for k, v in SHEET_FUND_SECTIONS.items() if v == (str(platform), str(currency).upper())}
    candidates = {fund_key(r["基金名稱"]): r["總帳配息原幣"] for r in sheet_rows if r["分類"] in sections}
    key = fund_key(name)
    if key not in candidates:
        close = difflib.get_close_matches(key, list(candidates), n=1, cutoff=0.6)
        key = close[0] if close else None
    return candidates.get(key) if key else None


def monthly_amount_alerts(sheet_rows: list[dict[str, Any]], records: pd.DataFrame,
                          months: set[tuple[int, int]]) -> list[dict[str, Any]]:
    """配息記錄（指定月份）的實際配息原幣 vs 總覽 O 欄「配息金額」（原幣），不同就列出。

    sheet_rows 是 sheet_fund_dividends(grid, value_header="配息金額") 的結果；容許 0.2%（至少 1）。"""
    alerts: list[dict[str, Any]] = []
    if records is None or records.empty or not sheet_rows:
        return alerts
    for idx, row in records.iterrows():
        when = row.get("_sort_date")
        if when is None or (getattr(when, "year", None), getattr(when, "month", None)) not in months:
            continue
        expected = sheet_value_for(sheet_rows, row.get("平台"), row.get("幣別"), row.get("基金名稱"))
        actual = _number(row.get("實際配息原幣"))
        if not expected or not actual:
            continue
        if abs(actual - expected) > max(1.0, abs(expected) * 0.002):
            alerts.append({"_index": idx, "平台": row.get("平台"), "基金名稱": row.get("基金名稱"),
                           "幣別": row.get("幣別"), "月份": f"{when.year}/{when.month:02d}",
                           "App 實際配息原幣": actual, "總覽配息金額": expected, "差額": actual - expected,
                           "已確認": bool(row.get("確認入帳"))})
    return alerts


# 總帳「總覽」每月加總各列對應的基金（平台、幣別、名稱篩選；! 開頭表示排除）。\n# 用於預估配息與「總帳有金額 → 建議確認入帳」；沒有對應的列（利息、股利…）不處理。
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


def _matches_rule(platform: Any, currency: Any, name: Any, rule: tuple[str, str, str]) -> bool:
    want_platform, want_currency, name_filter = rule
    if str(platform).strip() != want_platform or str(currency).strip().upper() != want_currency:
        return False
    name = str(name)
    if name_filter.startswith("!"):
        return name_filter[1:] not in name
    return name_filter in name if name_filter else True


def _ledger_candidates(records: pd.DataFrame, ledger_rows: list[dict[str, Any]],
                       month: tuple[int, int]) -> dict[str, tuple[float, list[int]]]:
    """{每月加總列名: (總帳金額, [本月、尚未確認、平台幣別相符的記錄 index])}，只列總帳金額 > 0 的列。"""
    filled = {r["項目"]: r["金額"] for r in ledger_rows
              if r.get("項目") in MONTHLY_ESTIMATE_RULES and (r.get("金額") or 0) > 0}
    out: dict[str, tuple[float, list[int]]] = {}
    if not filled or records.empty:
        return out
    for idx, row in records.iterrows():
        if bool(row.get("_確認前")) or row.get("_確認前") in ("True", "true", 1):
            continue
        when = row.get("_sort_date")
        if not when or (getattr(when, "year", None), getattr(when, "month", None)) != month:
            continue
        for label, amount in filled.items():
            if _matches_rule(row.get("平台"), row.get("幣別"), row.get("基金名稱"), MONTHLY_ESTIMATE_RULES[label]):
                out.setdefault(label, (amount, []))[1].append(int(idx))
                break
    return out


def amount_tolerance(amount: float) -> float:
    """總帳台幣 vs 記錄原幣×總覽匯率：匯率小數位不同會差幾塊錢，容許 0.2%（至少 2 元）。"""
    return max(2.0, abs(amount) * 0.002)


def _best_subset(amount: float, values: dict[int, float]) -> tuple[list[int], float]:
    """記錄裡加總最接近總帳金額的組合（筆數相同時取先發放的）；候選太多就全部。"""
    idxs = list(values)
    if len(idxs) > 12:
        return idxs, sum(values.values())
    best: tuple[float, list[int], float] | None = None
    for mask in range(1, 1 << len(idxs)):
        chosen = [i for bit, i in enumerate(idxs) if mask >> bit & 1]
        total = sum(values[i] for i in chosen)
        gap = abs(total - amount)
        if best is None or gap < best[0] - 1e-9:
            best = (gap, chosen, total)
    return (best[1], best[2]) if best else ([], 0.0)


def ledger_confirm_plan(records: pd.DataFrame, ledger_rows: list[dict[str, Any]], month: tuple[int, int],
                        twd_of: Callable[[int], float]) -> list[dict[str, Any]]:
    """每一列總帳金額 → 哪幾筆記錄加起來對得上（例：台新-南非兩筆待確認、只入帳一筆）。

    回傳 [{"label", "amount", "candidates", "matched", "matched_twd", "ok"}]；
    ok＝最接近的組合在容許誤差內，只有 ok 的 matched 會預先選好。
    """
    plan = []
    confirmed = _ledger_confirmed(records, ledger_rows, month)
    for label, (amount, idxs) in _ledger_candidates(records, ledger_rows, month).items():
        # 總覽金額＝本月已入帳合計：扣掉本月已確認的，剩下的才要由待確認記錄補上
        paid = sum(float(twd_of(i) or 0) for i in confirmed.get(label, []))
        remaining = float(amount) - paid
        tolerance = amount_tolerance(float(amount))
        if remaining <= tolerance:
            plan.append({"label": label, "amount": float(amount), "candidates": idxs, "matched": [],
                         "matched_twd": 0.0, "paid_twd": paid, "ok": abs(remaining) <= tolerance})
            continue
        values = {i: float(twd_of(i) or 0) for i in idxs}
        matched, total = _best_subset(remaining, values)
        plan.append({"label": label, "amount": float(amount), "candidates": idxs, "matched": matched,
                     "matched_twd": total, "paid_twd": paid, "ok": abs(total - remaining) <= tolerance})
    return plan


def _ledger_confirmed(records: pd.DataFrame, ledger_rows: list[dict[str, Any]],
                      month: tuple[int, int]) -> dict[str, list[int]]:
    """{每月加總列名: [本月、已確認入帳的記錄 index]}。"""
    labels = [r["項目"] for r in ledger_rows if r.get("項目") in MONTHLY_ESTIMATE_RULES and (r.get("金額") or 0) > 0]
    out: dict[str, list[int]] = {}
    if not labels or records.empty:
        return out
    for idx, row in records.iterrows():
        if not (bool(row.get("_確認前")) or row.get("_確認前") in ("True", "true", 1)):
            continue
        when = row.get("_sort_date")
        if not when or (getattr(when, "year", None), getattr(when, "month", None)) != month:
            continue
        for label in labels:
            if _matches_rule(row.get("平台"), row.get("幣別"), row.get("基金名稱"), MONTHLY_ESTIMATE_RULES[label]):
                out.setdefault(label, []).append(int(idx))
                break
    return out


def ledger_confirm_suggestions(records: pd.DataFrame, ledger_rows: list[dict[str, Any]],
                               month: tuple[int, int], twd_of: Callable[[int], float] | None = None) -> dict[int, str]:
    """總帳每月加總某列本月金額 > 0（已入帳），對應平台／幣別且本月、尚未確認入帳的配息記錄 → 建議確認。

    有 twd_of（記錄 index → 台幣金額）時，只選加總對得上總帳金額的那幾筆；對不上就不選。
    records 需有 平台、幣別、基金名稱、_確認前、_sort_date（date）；回傳 {records 的 index: 每月加總列名}。
    只是建議（預先選好），仍由人工按套用才會寫入。
    """
    if twd_of is None:
        return {i: label for label, (_amt, idxs) in _ledger_candidates(records, ledger_rows, month).items()
                for i in idxs}
    return {i: p["label"] for p in ledger_confirm_plan(records, ledger_rows, month, twd_of) if p["ok"]
            for i in p["matched"]}


# 總覽 Q 欄幣別名稱 → 幣別代碼；R 欄為匯率（台幣）
SHEET_FX_LABELS = {"美金": "USD", "南非": "ZAR", "人民": "CNY", "日幣": "JPY"}


def sheet_fx_rates(grid: list[list[Any]], label_col: int = 16, rate_col: int = 17) -> dict[str, float]:
    """總覽 Q/R 欄的匯率（取每個幣別第一次出現的值），TWD 固定 1。"""
    rates: dict[str, float] = {"TWD": 1.0}
    for row in grid:
        if len(row) <= rate_col:
            continue
        code = SHEET_FX_LABELS.get(str(row[label_col]).strip())
        if not code or code in rates:
            continue
        try:
            rates[code] = float(str(row[rate_col]).replace(",", ""))
        except ValueError:
            continue
    return rates
