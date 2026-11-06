"""用總帳「YYYY細帳」股利-台股那一列每月儲存格的備註，補齊／確認 App 的台股股利入帳。

細帳「股利-台股」每月的金額是當月台股現金股利合計，備註逐行寫每一檔入帳金額，例如：
    盟立 1404
    折讓 23
    00740B360
    00919 8790
這支逐月讀備註，對到股票（代碼或名稱），再對 App 的台股股利記錄（stock_dividend_log）：

  確認入帳  該股該月附近有應入帳記錄（掃描除權息公告產生的預估）、還沒確認，且金額跟預估相差
            在 2%（至少 30 元）內 → 勾確認現金入帳、實際現金股利＝備註金額
  金額待核  有應入帳記錄但跟預估差太多 → 只列出，到 App 台股股利頁核對後手動確認
  補登      找不到記錄 → 新增一筆已入帳記錄（發放日記為該月 1 日，來源 ledger_note）
只寫股利記錄，不動持倉「累計股利」（那欄原本就含今年，加上去會重複）。
  已一致    已確認且金額相同 → 不動
  金額不同  已確認但金額不同 → 只列出，不改
  無法對應  名稱對不到股票（例如「折讓」）→ 只列出
另外檢查每月備註加總是否等於儲存格金額。

跟基金配息同一個流程：先掃描證交所／櫃買除權息公告建立應入帳（預估）記錄，再用細帳備註確認入帳。
預設只產生報告（--apply 才掃描公告並寫入資料庫）；排程派送時一律 apply。

  python sync_stock_dividends_from_ledger.py --year 2026
  python sync_stock_dividends_from_ledger.py --year 2026 --apply
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
import json
import os
import re
import sys
import unicodedata

SPREADSHEET_ID = "19GikXQGPMl0Uoorh9eGs2CEYJIcj8Ybh6zhXcos-kQ0"  # 2025Jenny-總帳
ROW_LABEL = "股利-台股"
SOURCE = "ledger_note"
MATCH_WINDOW_MONTHS = 4      # 記錄的除息／發放月份與入帳月份相差在這之內才算同一筆
AMOUNT_TOLERANCE = 1.0       # 已確認金額與備註相差超過 1 元才算不同


def estimate_tolerance(estimate):
    """備註金額 vs 應入帳預估：2%，至少 30 元（股數四捨五入、零股）。"""
    return max(30.0, abs(estimate) * 0.02)

# 備註裡不是台股股利的項目（手續費、折讓、基金配息…）：不補登，另列「費用／折讓」
FEE_WORDS = ("折讓", "手續費", "匯費", "轉帳", "補充保費", "健保", "二代健保", "稅", "扣",
             "FUND", "基金")   # 0050FUND 19990：基金配息記在股利-台股，不是台股股利
# 備註常用的簡稱、打錯字 → 股票代碼（報告會標「別名」方便核對；不對就改這裡）
ALIASES = {
    "富邦投等": "00740B",   # 富邦全球投等債
    "740B": "00740B",
    "007408": "00740B",     # 00740B 打成 007408
    "科技優息": "00929",    # 復華台灣科技優息
    "凱基金乙": "2883B",    # 凱基金乙特
    "楠樟電": "2316",       # 楠梓電
}


# ── 解析 ───────────────────────────────────────────────────────────────────────

# 換行、全形標點；半形逗號後面接三位數字時是千分位，不拆
LINE_SPLIT = re.compile(r"[\n，、;；]+|,(?!\d{3}(?!\d))")
CODE_LINE = re.compile(r"^(\d{4,6}[A-Za-z]?)\s*[:：]?\s*(-?[\d,]+(?:\.\d+)?)$")
NAME_LINE = re.compile(r"^(.+?)\s*[:：]?\s*(-?[\d,]+(?:\.\d+)?)$")


@dataclass
class NoteItem:
    month: tuple          # (year, month)
    label: str            # 備註上的名稱或代碼
    amount: float
    code: str = ""        # 對到的股票代碼（不含 .TW）
    how: str = ""         # 怎麼對到的：代碼／名稱／簡稱／別名；費用＝手續費、折讓


def norm(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(text or ""))).upper()


def parse_note(text):
    """'盟立 1404\\n00740B360' → [('盟立', 1404.0), ('00740B', 360.0)]；看不懂的行回傳在第二個值。"""
    items, bad = [], []
    for raw in LINE_SPLIT.split(unicodedata.normalize("NFKC", str(text or ""))):
        line = raw.strip()
        if not line:
            continue
        m = CODE_LINE.match(line) or NAME_LINE.match(line)
        if not m:
            bad.append(line)
            continue
        items.append((m.group(1).strip(), float(m.group(2).replace(",", ""))))
    return items, bad


def number(value):
    try:
        return float(str(value).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


# ── 股票對應 ──────────────────────────────────────────────────────────────────

def plain_code(ticker):
    return norm(ticker).replace(".TWO", "").replace(".TW", "")


def build_stock_index(stocks):
    """stocks: [{"code", "name"}] → (codes set, [(normalized name, code)])."""
    codes = {plain_code(s["code"]) for s in stocks if s.get("code")}
    names = sorted({(norm(s["name"]), plain_code(s["code"])) for s in stocks if s.get("name") and s.get("code")},
                   key=lambda x: -len(x[0]))
    return codes, names


def is_subsequence(short, long):
    it = iter(long)
    return all(ch in it for ch in short)


def resolve(label, index):
    """備註名稱／代碼 → (股票代碼, 怎麼對到的)；對不到或對到多檔回傳 ('', '')。"""
    codes, names = index
    key = norm(label)
    if any(word in key for word in FEE_WORDS):
        return "", "費用"
    if key in ALIASES:
        return ALIASES[key], "別名"
    # 代碼：00936、2344華邦電（代碼後面接名稱）；不在持倉裡的代碼也接受（可能已賣出）
    m = re.match(r"^(\d{4,6}[A-Z]?)(?=[^\dA-Z]|$)", key)
    if m:
        return m.group(1), "代碼"
    # 代碼寫短了（740B → 00740B），只有一檔符合才算
    if re.fullmatch(r"\d{3,5}[A-Z]?", key):
        tail = [c for c in codes if c.endswith(key)]
        if len(tail) == 1:
            return tail[0], "代碼"
    exact = {code for name, code in names if name == key}
    if len(exact) == 1:
        return exact.pop(), "名稱"
    # 簡稱：世紀→世紀鋼、鈺齊→鈺齊-KY；再不行，備註的字依序都出現在名稱裡（富邦特選→富邦特選高股息30）
    for test in (lambda n: n.startswith(key) or key.startswith(n), lambda n: is_subsequence(key, n)):
        hits = {code for name, code in names if len(key) >= 2 and test(name)}
        if len(hits) == 1:
            return hits.pop(), "簡稱"
    return "", ""


# ── 細帳 ──────────────────────────────────────────────────────────────────────

def parse_header_date(value):
    m = re.match(r"\s*(\d{4})[/\-.](\d{1,2})", str(value or ""))
    return (int(m[1]), int(m[2])) if m and 1 <= int(m[2]) <= 12 else None


def month_columns(grid, year, header_rows=5):
    """{month: 0-based col} from the first dated row; fallback C = January."""
    for line in grid[:header_rows]:
        found = {}
        for c, v in enumerate(line):
            ym = parse_header_date(v)
            if ym and ym[0] == year and ym[1] not in found:
                found[ym[1]] = c
        if len(found) >= 6:
            return found
    return {m: 1 + m for m in range(1, 13)}


def formula_terms(formula):
    """'=890+100-20-5313' → [890, 100, -20, -5313]；不是單純加減就回傳 None。"""
    text = str(formula or "").replace(",", "").replace(" ", "")
    if not text.startswith("=") or not re.fullmatch(r"=[+\-]?\d+(?:\.\d+)?(?:[+\-]\d+(?:\.\d+)?)*", text):
        return None
    return [float(t) for t in re.findall(r"[+\-]?\d+(?:\.\d+)?", text[1:])]


def ledger_items(values, notes, year, index, formulas=None):
    """→ (items, problems). values/notes/formulas 是細帳的格子值、備註、公式（同樣大小的二維陣列）。

    儲存格公式（=890+100-20-5313）的正數是各檔入帳、負數是手續費等扣項：
    備註加總跟正數加總比；負數另外列出，不當成錯誤。
    """
    row = next((r for r, line in enumerate(values) if line and norm(line[0]) == norm(ROW_LABEL)), None)
    if row is None:
        return [], [f"{year}細帳 A 欄找不到「{ROW_LABEL}」"]
    cols = month_columns(values, year)
    items, problems = [], []
    for month, col in sorted(cols.items()):
        cell = values[row][col] if col < len(values[row]) else ""
        note = notes[row][col] if row < len(notes) and col < len(notes[row]) else ""
        parsed, bad = parse_note(note)
        for line in bad:
            problems.append(f"{year}/{month:02d} 備註看不懂：{line}")
        total = sum(a for _, a in parsed)
        formula = formulas[row][col] if formulas and row < len(formulas) and col < len(formulas[row]) else ""
        terms = formula_terms(formula)
        if terms is not None:
            income = sum(t for t in terms if t > 0)
            fees = [t for t in terms if t < 0]
            fee_note = f"（扣項 {', '.join(f'{t:,.0f}' for t in fees)}，不計入）" if fees else ""
            if parsed and abs(total - income) > 1:
                missing = [t for t in terms if t > 0 and not any(abs(a - t) < 0.5 for _, a in parsed)]
                hint = f"；公式裡備註沒寫到的金額：{', '.join(f'{t:,.0f}' for t in missing)}" if missing else ""
                problems.append(f"{year}/{month:02d} 備註加總 {total:,.0f} ≠ 公式正數加總 {income:,.0f}{fee_note}{hint}")
        elif parsed and abs(total - number(cell)) > 1:
            problems.append(f"{year}/{month:02d} 備註加總 {total:,.0f} ≠ 儲存格 {number(cell):,.0f}（可能含手續費等扣項）")
        if not parsed and abs(number(cell)) > 0:
            problems.append(f"{year}/{month:02d} 有金額 {number(cell):,.0f} 但沒有備註明細")
        for label, amount in parsed:
            code, how = resolve(label, index)
            items.append(NoteItem((year, month), label, amount, code, how))
    return items, problems


# ── 對 App 記錄 ───────────────────────────────────────────────────────────────

def record_month(rec):
    for key in ("cash_pay_date", "ex_date"):
        ym = parse_header_date(rec.get(key))
        if ym:
            return ym
    return None


def months_between(a, b):
    return (b[0] - a[0]) * 12 + (b[1] - a[1])


def plan(items, records):
    """→ list of {"action", "item", "record"}；每筆記錄最多被用一次。"""
    used, out = set(), []
    for item in sorted(items, key=lambda i: (i.month, i.label)):
        if not item.code:
            out.append({"action": "費用／折讓" if item.how == "費用" else "無法對應", "item": item, "record": None})
            continue
        if item.amount <= 0:
            out.append({"action": "無法對應", "item": item, "record": None})
            continue
        best = None
        for rec in records:
            rid = rec.get("id")
            if rid in used or plain_code(rec.get("ticker")) != item.code:
                continue
            ym = record_month(rec)
            gap = months_between(ym, item.month) if ym else None
            if gap is None or not (0 <= gap <= MATCH_WINDOW_MONTHS):
                continue
            # 已入帳且金額相同的優先，其次是同月份的待確認記錄
            same = rec.get("is_cash_received") and abs(number(rec.get("actual_cash_total")) - item.amount) <= AMOUNT_TOLERANCE
            score = (0 if same else 1, 0 if not rec.get("is_cash_received") else 1, gap)
            if best is None or score < best[0]:
                best = (score, rec)
        if best is None:
            out.append({"action": "補登", "item": item, "record": None})
            continue
        rec = best[1]
        used.add(rec.get("id"))
        if not rec.get("is_cash_received"):
            estimate = number(rec.get("estimated_cash_total"))
            if estimate > 0 and abs(estimate - item.amount) > estimate_tolerance(estimate):
                action = "金額待核"
            else:
                action = "確認入帳"
        elif abs(number(rec.get("actual_cash_total")) - item.amount) <= AMOUNT_TOLERANCE:
            action = "已一致"
        else:
            action = "金額不同"
        out.append({"action": action, "item": item, "record": rec})
    return out


# ── I/O ───────────────────────────────────────────────────────────────────────

def read_ledger(year):
    import gspread
    from google.oauth2.service_account import Credentials
    info = json.loads(os.environ["INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    book = gspread.authorize(creds).open_by_key(SPREADSHEET_ID)
    title = f"{year}細帳"
    meta = book.fetch_sheet_metadata(params={
        "includeGridData": "true", "ranges": f"'{title}'!A1:Z300",
        "fields": "sheets.data.rowData.values(note,formattedValue,userEnteredValue)"})
    rows = meta["sheets"][0]["data"][0].get("rowData", [])
    values = [[c.get("formattedValue", "") for c in r.get("values", [])] for r in rows]
    notes = [[c.get("note", "") for c in r.get("values", [])] for r in rows]
    formulas = [[c.get("userEnteredValue", {}).get("formulaValue", "") for c in r.get("values", [])] for r in rows]
    return values, notes, formulas


def supabase():
    from supabase import create_client
    return create_client(os.environ.get("SUPABASE_URL", "https://qrvdztqyzxlsfskdgiqp.supabase.co"),
                         os.environ["SUPABASE_ANON_KEY"])


def load_stocks_and_records(sb):
    records = sb.table("stock_dividend_log").select("*").execute().data or []
    positions = sb.table("positions").select("platform,asset_type,ticker,name").execute().data or []
    stocks = [{"code": p["ticker"], "name": p.get("name", ""), "platform": p.get("platform", "")}
              for p in positions if str(p.get("asset_type", "")).strip() == "台股" and p.get("ticker")]
    stocks += [{"code": r["ticker"], "name": r.get("name", ""), "platform": r.get("platform", "")}
               for r in records if r.get("ticker")]
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from invest_app.core import TW_PRESETS
        stocks += [{"code": t, "name": n} for n, t in TW_PRESETS.items()]
    except Exception:
        pass
    return stocks, records


def apply(sb, steps, stocks):
    from invest_app.stock_dividends import _format_tw_stock_ticker
    platform_of = {}
    for s in stocks:
        if s.get("platform"):
            platform_of.setdefault(plain_code(s["code"]), s["platform"])
    done, warnings = 0, []
    for step in steps:
        item, rec = step["item"], step["record"]
        if step["action"] == "確認入帳":
            sb.table("stock_dividend_log").update({
                "is_cash_received": True, "actual_cash_total": item.amount,
                "cash_pay_date": rec.get("cash_pay_date") or f"{item.month[0]}/{item.month[1]:02d}/01",
                "note": (str(rec.get("note") or "") + f"｜{item.month[0]}細帳備註確認").strip("｜"),
            }).eq("id", rec["id"]).execute()
        elif step["action"] == "補登":
            platform = platform_of.get(item.code, "台股")
            existing = [s for s in stocks if plain_code(s["code"]) == item.code and "." in str(s["code"])]
            ticker = existing[0]["code"] if existing else _format_tw_stock_ticker(item.code)
            sb.table("stock_dividend_log").insert({
                "platform": platform, "ticker": ticker, "name": item.label, "currency": "TWD",
                "ex_date": "", "cash_pay_date": f"{item.month[0]}/{item.month[1]:02d}/01", "stock_pay_date": "",
                "shares_at_ex": 0, "cash_dividend_per_share": 0, "estimated_cash_total": item.amount,
                "actual_cash_total": item.amount, "stock_dividend_per_share": 0, "estimated_stock_shares": 0,
                "actual_stock_shares": 0, "is_cash_received": True, "is_stock_received": False,
                "source": SOURCE, "note": f"依 {item.month[0]}細帳備註補登（發放日以月份記）",
            }).execute()
        else:
            continue
        done += 1
        # 不動持倉「累計股利」：那欄原本就由你維護（已含今年），這裡只寫股利記錄，避免重複加總
    return done, warnings


UNDO_MARK = "累計已回沖"


def was_added_by_apply(record):
    """那次 apply 有加到持倉累計股利的記錄：只有補登（source=ledger_note）；已回沖過的不再扣。"""
    return record.get("source") == SOURCE and UNDO_MARK not in str(record.get("note") or "")


def undo_position_totals(sb, apply_changes):
    """回沖 2026-11-07 那次 apply 加到持倉累計股利的金額（ledger_note 記錄，只做一次）。"""
    from invest_app.stock_dividends import update_stock_cash_dividend_total
    rows = sb.table("stock_dividend_log").select("id,ticker,platform,name,actual_cash_total,note,source") \
        .execute().data or []
    todo = [r for r in rows if was_added_by_apply(r)]
    total, done, missing = 0.0, 0, []
    for r in todo:
        amount = number(r.get("actual_cash_total"))
        if amount <= 0:
            continue
        print(f"  回沖 {r.get('name')}（{r.get('ticker')}）-{amount:,.0f}")
        if not apply_changes:
            total += amount
            continue
        if update_stock_cash_dividend_total(r["ticker"], r.get("platform") or "台股", -amount):
            total += amount
            done += 1
        else:
            missing.append(f"{r.get('name')} {amount:,.0f}")  # 當初也沒加上去（找不到持倉主列）
        sb.table("stock_dividend_log").update({"note": f"{r.get('note') or ''}｜{UNDO_MARK}".strip("｜")}) \
            .eq("id", r["id"]).execute()
    print(f"== 回沖持倉累計股利：{len(todo)} 筆、合計 {total:,.0f}" + ("" if apply_changes else "（預覽）"))
    if missing:
        print("  找不到持倉主列（當初就沒加，不用回沖）：" + "、".join(missing))
    return done


def scan_expected(sb):
    """先依除權息公告×目前持股建立應入帳（預估）記錄，跟 App「掃描台股股利候選」同一支。"""
    try:
        from invest_app.core import load_positions
        from invest_app.stock_dividends import scan_stock_dividend_candidates
        added = scan_stock_dividend_candidates(load_positions())
        print(f"掃描除權息公告：新增 {added} 筆應入帳記錄")
    except Exception as exc:
        print(f"WARN 掃描除權息公告失敗（仍繼續比對）：{exc}")


def app_only_records(records, steps, years):
    """App 已入帳、但沒對到任何細帳備註的記錄（App「今年台股現金股利」有算、細帳沒有）。

    ledger_note 的補登若跟其中一筆同股票、同金額，標 dup_of（多半是同一筆股利記了兩次）。"""
    from invest_app.stock_dividends import _stock_year_from_record
    used = {s["record"].get("id") for s in steps if s.get("record")}
    loose = [r for r in records if r.get("is_cash_received") and r.get("id") not in used
             and _stock_year_from_record(r) in years]
    ledger = [r for r in loose if r.get("source") == SOURCE]
    app = [r for r in loose if r.get("source") != SOURCE]
    out = []
    for r in app:
        amount = number(r.get("actual_cash_total")) or number(r.get("estimated_cash_total"))
        dup = next((x for x in ledger if plain_code(x.get("ticker")) == plain_code(r.get("ticker"))
                    and abs(number(x.get("actual_cash_total")) - amount) <= max(30.0, amount * 0.02)), None)
        if dup is not None:
            ledger.remove(dup)
        out.append({"record": r, "amount": amount, "dup_of": dup})
    return out


def report_app_only(records, steps, years):
    rows = app_only_records(records, steps, years)
    if not rows:
        return
    total = sum(r["amount"] for r in rows)
    dup_total = sum(r["amount"] for r in rows if r["dup_of"])
    print(f"\n[App 已入帳、細帳沒有] {len(rows)} 筆，合計 {total:,.0f}"
          f"（其中 {sum(1 for r in rows if r['dup_of'])} 筆、{dup_total:,.0f} 跟細帳補登重複）")
    for row in rows:
        r = row["record"]
        dup = f"｜疑似重複：補登 #{row['dup_of'].get('id')}" if row["dup_of"] else ""
        print(f"  #{r.get('id')} {r.get('name', '')}（{r.get('ticker', '')}）{row['amount']:,.0f}｜除息 {r.get('ex_date') or '—'} "
              f"發放 {r.get('cash_pay_date') or '—'}｜來源 {r.get('source') or '—'}｜建立 {str(r.get('created_at') or '')[:10]}"
              f"｜{str(r.get('note') or '')[:30]}{dup}")


# ── 對齊：細帳為準，App 記錄與持倉累計股利跟著細帳 ───────────────────────────────

LEDGER_CONFIRMED = "細帳備註確認"
NOT_IN_LEDGER = "細帳沒有這筆，退回待入帳"


RECONCILE_TOLERANCE = 0.05  # App 記的多半是扣補充保費（2.11%）、匯費前的金額，細帳是實拿


def same_amount(a, b):
    return abs(number(a) - number(b)) <= max(30.0, abs(number(b)) * RECONCILE_TOLERANCE)


def reconcile_plan(records, years, year_of):
    """細帳年度內：App 已入帳的記錄若跟細帳補登同股票、同金額（同年）→ 合併（留 App 那筆、刪補登）；
    沒有對應細帳的 App 已入帳記錄 → 退回待入帳。回傳 (merges [(app, ledger)], returns [app])。"""
    received = [r for r in records if r.get("is_cash_received") and year_of(r) in years]
    ledger = [r for r in received if r.get("source") == SOURCE]
    confirmed_ids = set()
    merges, returns = [], []
    for r in received:
        if r.get("source") == SOURCE:
            continue
        if LEDGER_CONFIRMED in str(r.get("note") or ""):
            confirmed_ids.add(r.get("id"))   # 細帳已確認過的那筆（確認入帳），本來就對應細帳
            continue
        amount = number(r.get("actual_cash_total")) or number(r.get("estimated_cash_total"))
        dup = next((x for x in ledger if plain_code(x.get("ticker")) == plain_code(r.get("ticker"))
                    and year_of(x) == year_of(r) and same_amount(amount, x.get("actual_cash_total"))), None)
        if dup is not None:
            ledger.remove(dup)
            merges.append((r, dup))
        else:
            returns.append(r)
    return merges, returns


def position_targets(records):
    """{股票代碼: 已入帳現金股利合計}（持倉累計股利應該等於這個）。"""
    out = {}
    for r in records:
        if r.get("is_cash_received"):
            code = plain_code(r.get("ticker"))
            out[code] = out.get(code, 0.0) + (number(r.get("actual_cash_total")) or number(r.get("estimated_cash_total")))
    return out


def reconcile(sb, records, years, apply_changes):
    """讓「台股股利記錄」與「持倉累計股利」都等於細帳。預覽時只印出會怎麼改。"""
    from invest_app.stock_dividends import _stock_year_from_record
    merges, returns = reconcile_plan(records, years, _stock_year_from_record)
    tag = "" if apply_changes else "（預覽）"
    print(f"\n== 對齊細帳{tag}：合併重複 {len(merges)} 筆（{sum(number(l.get('actual_cash_total')) for _, l in merges):,.0f}），"
          f"細帳沒有、退回待入帳 {len(returns)} 筆（{sum(number(r.get('actual_cash_total')) for r in returns):,.0f}）")
    for app, led in merges:
        print(f"  合併 #{app.get('id')} {app.get('name')} {number(app.get('actual_cash_total')):,.0f} ← 補登 #{led.get('id')} "
              f"{number(led.get('actual_cash_total')):,.0f}（刪補登，金額以細帳為準）")
    for r in returns:
        print(f"  退回 #{r.get('id')} {r.get('name')}（{r.get('ticker')}）{number(r.get('actual_cash_total')):,.0f}"
              f"｜除息 {r.get('ex_date') or '—'} 發放 {r.get('cash_pay_date') or '—'}")
    deleted = {led.get("id") for _, led in merges}
    after = []
    for r in records:
        if r.get("id") in deleted:
            continue
        r = dict(r)
        for app, led in merges:
            if app.get("id") == r.get("id"):
                r["actual_cash_total"] = number(led.get("actual_cash_total"))
        if any(x.get("id") == r.get("id") for x in returns):
            r["is_cash_received"] = False
        after.append(r)
    if apply_changes:
        for app, led in merges:
            sb.table("stock_dividend_log").update({
                "actual_cash_total": number(led.get("actual_cash_total")),
                "cash_pay_date": app.get("cash_pay_date") or led.get("cash_pay_date"),
                "note": f"{app.get('note') or ''}｜{LEDGER_CONFIRMED}".strip("｜"),
            }).eq("id", app["id"]).execute()
            sb.table("stock_dividend_log").delete().eq("id", led["id"]).execute()
        for r in returns:
            sb.table("stock_dividend_log").update({
                "is_cash_received": False,
                "note": f"{r.get('note') or ''}｜{NOT_IN_LEDGER}".strip("｜"),
            }).eq("id", r["id"]).execute()
    set_position_totals(sb, position_targets(after), apply_changes)
    return after


def set_position_totals(sb, targets, apply_changes):
    """台股持倉累計股利＝股利記錄已入帳合計（每檔寫在主列，其他列歸 0）。"""
    from invest_app.core import TW_PRESETS
    rows = sb.table("positions").select("id,sort_order,platform,asset_type,ticker,name,dividend_received_original_total") \
        .execute().data or []
    groups = {}
    for row in rows:
        if str(row.get("asset_type", "")).strip() != "台股":
            continue
        code = plain_code(row.get("ticker") or TW_PRESETS.get(str(row.get("name", "")).strip(), ""))
        if code:
            groups.setdefault(code, []).append(row)
    before_total = sum(number(r.get("dividend_received_original_total")) for g in groups.values() for r in g)
    after_total, changes, no_position = 0.0, [], []
    for code, target in sorted(targets.items()):
        if code not in groups:
            no_position.append(f"{code} {target:,.0f}")
    for code, group in groups.items():
        group.sort(key=lambda r: (number(r.get("sort_order")) or 999999, number(r.get("id"))))
        target = round(targets.get(code, 0.0), 0)
        after_total += target
        current = sum(number(r.get("dividend_received_original_total")) for r in group)
        if abs(current - target) >= 1 or any(number(r.get("dividend_received_original_total")) for r in group[1:]):
            changes.append((code, group[0].get("name"), current, target))
            if apply_changes:
                sb.table("positions").update({"dividend_received_original_total": target, "dividend_received_total": 0}) \
                    .eq("id", group[0]["id"]).execute()
                for r in group[1:]:
                    sb.table("positions").update({"dividend_received_original_total": 0, "dividend_received_total": 0}) \
                        .eq("id", r["id"]).execute()
    tag = "" if apply_changes else "（預覽）"
    print(f"\n== 持倉累計股利{tag}：{before_total:,.0f} → {after_total:,.0f}（{len(changes)} 檔要改）")
    for code, name, cur, tgt in changes:
        print(f"  {name}（{code}）{cur:,.0f} → {tgt:,.0f}")
    if no_position:
        print("  股利記錄有、但沒有持倉列（首頁不會算到）：" + "、".join(no_position))


FIRST_YEAR = 2026  # 這個流程從 2026 細帳開始；2025 以前的股利已含在持倉累計股利裡，不匯入


def default_years(today):
    """去年＋今年（最早 2026）：去年的股利晚補記在去年細帳也抓得到；已一致的不會重複寫。"""
    return sorted({max(today.year - 1, FIRST_YEAR), today.year})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, help="只讀哪一年的細帳；不填＝去年＋今年（去年晚補的也抓得到）")
    parser.add_argument("--apply", action="store_true", help="寫入資料庫（預設只產生報告）")
    parser.add_argument("--reconcile", action="store_true",
                        help="以細帳為準對齊：合併重複、退回細帳沒有的、持倉累計股利＝股利記錄（搭配 --apply 才寫入）")
    parser.add_argument("--undo-position-totals", action="store_true",
                        help="回沖先前 apply 加到持倉累計股利的金額（搭配 --apply 才寫入）")
    args = parser.parse_args(argv)

    sb = supabase()
    if args.undo_position_totals:
        undo_position_totals(sb, args.apply)
        return 0
    if args.apply:
        scan_expected(sb)
    stocks, records = load_stocks_and_records(sb)
    years = [args.year] if args.year else default_years(date.today())
    index = build_stock_index(stocks)
    items, problems = [], []
    for year in years:
        try:
            values, notes, formulas = read_ledger(year)
        except Exception as exc:
            problems.append(f"讀不到 {year}細帳：{exc}")
            continue
        found, issues = ledger_items(values, notes, year, index, formulas)
        items += found
        problems += issues
    steps = plan(items, [r for r in records if str(r.get("currency", "TWD")).upper() == "TWD"])

    print(f"== {'、'.join(f'{y}細帳' for y in years)}「{ROW_LABEL}」備註：{len(items)} 筆入帳 ==")
    for action in ("確認入帳", "補登", "金額待核", "金額不同", "無法對應", "費用／折讓", "已一致"):
        group = [s for s in steps if s["action"] == action]
        if not group:
            continue
        print(f"\n[{action}] {len(group)} 筆")
        for s in group:
            i, rec = s["item"], s["record"]
            extra = ""
            if rec is not None:
                extra = (f"｜App 記錄 #{rec.get('id')} {rec.get('name', '')} 除息 {rec.get('ex_date') or '—'} "
                         f"發放 {rec.get('cash_pay_date') or '—'} 預估 {number(rec.get('estimated_cash_total')):,.0f} "
                         f"實際 {number(rec.get('actual_cash_total')):,.0f}")
            code = f"（{i.code}{'，' + i.how if i.how in ('簡稱', '別名') else ''}）" if i.code else ""
            print(f"  {i.month[0]}/{i.month[1]:02d} {i.label}{code} {i.amount:,.0f}{extra}")
    for p in problems:
        print(f"WARN {p}")
    report_app_only(records, steps, years)

    if args.apply:
        done, warnings = apply(sb, steps, stocks)
        for w in warnings:
            print(f"WARN {w}")
        print(f"\n已寫入 {done} 筆（確認入帳＋補登）")
        if args.reconcile:
            _stocks, records = load_stocks_and_records(sb)
    else:
        todo = sum(1 for s in steps if s["action"] in ("確認入帳", "補登"))
        print(f"\n預覽：{todo} 筆會寫入；確認無誤後用 apply 執行")
    if args.reconcile:
        reconcile(sb, records, years, args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
