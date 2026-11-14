"""銀行明細（台新／富邦／將來）→ 2026細帳：每筆交易記在該帳戶列，另一邊照 Jenny 的規則記到對應列。

規則（Jenny 2026-11-14 確認）：
- 帳戶列：富邦（三個帳號都記）38、將來主帳戶 54、台新 建北 43／信義 45／Richard 47／子帳戶 49／內湖新轉 51（中和綜活併入建北）
  利息：各帳戶「-銀行利息」列（富邦 39、將來 55、台新 44/46/48/50）
  台新外幣（古亭全部、敦南只取利息）：人民幣 83、美金 90、日幣 91、南非 92，原幣記；外幣利息只加在該幣別列
- 股利：台股股利／折讓 116、富邦集保基金配息 119、外幣配息 人民幣 120／日幣 121／美金 125／南非 126
- 投資新興國家、新興邊境（富邦／台新／渣打的台幣）→ 105 基富通-台；基富通人民幣 104、日幣 106 由台新人民幣、日幣扣
- 備註有 uncle → 95 借出+投資；LINE 轉入 → 零用金-代墊 減項
- 自己帳戶之間的轉帳：各記各的帳戶列，不進零用金；同一列（例：富邦新店→營業部）一進一出相抵，略過
- 其他支出 → 零用金分類（對不到 → 零用金-其他，標「待分類」）
預設只產生比對報表；--apply 才寫入 2026細帳（與 2026細帳(含信用卡)），每格加備註與加註日期，並發行事曆。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .credentials import BANK_DIR
from .ledger_sync import (_rc, _set_notes, a1, add_term, categorize, load_rules, month_columns, open_book)
from .taishin_tx import parse_day

TX_ROOT = BANK_DIR / "transactions"
APPLIED_FILE = TX_ROOT / "_ledger_applied.json"

# 帳戶列：(細帳列號, 利息列號, 該列名稱應包含的字)
ACCOUNT_ROWS = {
    "富邦": (38, 39, "富邦"),
    "將來": (54, 55, "將來"),
    "台新-建北": (43, 44, "建北"),
    "台新-信義": (45, 46, "信義"),
    "台新-Richard": (47, 48, "Richard"),
    "台新-子帳戶": (49, 50, "子帳戶"),
    "台新-內湖新轉": (51, None, "內湖"),
    "元大": (40, 41, "元大"),
    "連線": (52, 53, "連線"),
}
FX_ROWS = {"人民幣": 83, "日圓": 91, "美元": 90, "南非幣": 92}
FX_DIVIDEND_ROWS = {"人民幣": 120, "日圓": 121, "美元": 125, "南非幣": 126}
FUND_ROWS = {"TWD": 105, "人民幣": 104, "日圓": 106}
ROW_STOCK_DIVIDEND = 116
ROW_FUBON_FUND_DIVIDEND = 119
ROW_UNCLE = 95
ROW_PETTY_ADVANCE = "零用金-代墊"
OTHER_BANK_ROWS = (("渣打", 56), ("中國信託", 57), ("中信", 57), ("郵局", 42), ("中華郵政", 42), ("樂天", 58))
# 已自動抓明細的銀行：互轉時兩邊各自記，不另外記另一邊
OWN_BANK_WORDS = ("台新", "richard", "Richart", "富邦", "將來", "8168", "營業部", "元大", "LINE Bank", "連線銀行")
FUND_WORDS = ("新興國家", "新興邊境", "基富通", "基金申購", "申購基金")
DIVIDEND_WORDS = ("股利", "股息", "折讓", "現金股利")
FX_DIVIDEND_WORDS = ("配息", "股利", "收益分配", "股息")


@dataclass
class Tx:
    bank: str          # taishin / fubon / next
    account: str       # ****871 (營業部)
    ledger: str        # 富邦／將來／台新-建北…；外幣：台新外幣
    day: date
    amount: float      # 存入 +、支出 -（外幣為原幣）
    currency: str      # TWD 或 人民幣／日圓／美元／南非幣
    summary: str
    note: str
    key: str
    interest_only: bool = False

    @property
    def text(self) -> str:
        return f"{self.summary} {self.note}".strip()


@dataclass
class Posting:
    row: object        # 列號（int）或列名（str，零用金分類）
    amount: float
    label: str = ""


@dataclass
class Entry:
    tx: Tx
    postings: list = field(default_factory=list)
    reason: str = ""
    skip: bool = False


def _num(text: str) -> float | None:
    t = (text or "").replace(",", "").replace("$", "").replace("新臺幣", "").strip()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        m = re.search(r"-?\d+(?:\.\d+)?", t)
        return float(m.group(0)) if m else None


def _col(head: list, *names: str) -> int | None:
    for n in names:
        if n in head:
            return head.index(n)
    return None


# ---------------------------------------------------------------- 讀本機明細

def _blocks(bank: str):
    folder = TX_ROOT / bank
    for path in sorted(folder.glob("2*.json")) if folder.exists() else []:
        try:
            data = json.loads(path.read_text("utf-8"))
        except Exception:
            continue
        for block in data.get("accounts", []):
            yield block


def load_transactions() -> tuple[list[Tx], list[str]]:
    """讀三家已抓到的明細，轉成統一格式。回傳 (交易, 無法解析的警告)。"""
    out, warn, seen = [], [], set()
    for bank in ("fubon", "next", "taishin", "yuanta", "linebank"):
        for block in _blocks(bank):
            head = block.get("head") or []
            for row in block.get("rows") or []:
                tx = _to_tx(bank, block, head, row)
                if tx == "SKIP":
                    continue
                if tx is None:
                    warn.append(f"{bank} {block.get('account')}：看不懂這筆格式 {len(row)} 欄")
                    continue
                if tx.key not in seen:
                    seen.add(tx.key)
                    out.append(tx)
    out.sort(key=lambda t: (t.day, t.bank, t.account))
    return out, warn


ONLY_ACCOUNTS = {"yuanta": ("大同",), "linebank": ("主帳戶",)}  # Jenny：元大只記大同、LINE Bank 只記主帳戶


def _to_tx(bank: str, block: dict, head: list, row: list) -> Tx | None:
    get = lambda i: row[i] if i is not None and i < len(row) else ""
    only = ONLY_ACCOUNTS.get(bank)
    if only and not any(k in block.get("account", "") for k in only):
        return "SKIP"
    day = parse_day(row[0] if row else "")
    if day is None:
        return None
    account = block.get("account", "")
    key = f"{bank}|{account}|" + "|".join(row)
    if bank == "fubon":
        out_, in_ = _num(get(_col(head, "支出金額"))), _num(get(_col(head, "存入金額")))
        amount = (in_ or 0) - (out_ or 0)
        note = re.sub(r"\s*更多$", "", get(_col(head, "附註")))
        return Tx(bank, account, "富邦", day, amount, "TWD", get(_col(head, "摘要")), note, key)
    if bank == "yuanta":
        out_, in_ = _num(get(_col(head, "支出金額"))), _num(get(_col(head, "存入金額")))
        if out_ is None and in_ is None:
            return None
        return Tx(bank, account, "元大", day, (in_ or 0) - (out_ or 0), "TWD", get(_col(head, "交易說明")),
                  get(_col(head, "備註")), key)
    if bank == "linebank":
        raw = get(_col(head, "金額"))
        amount = _num(re.sub(r"[^\d.,\-]", "", raw))
        if amount is None:
            return None
        if any(w in raw for w in ("支出", "轉出", "提款", "扣款")) or raw.strip().startswith("-"):
            amount = -abs(amount)
        return Tx(bank, account, "連線", day, amount, "TWD", get(_col(head, "摘要")), "", key)
    if bank == "next":
        amount = _num(get(_col(head, "金額")))
        if amount is None:
            return None
        note = " ".join(x for x in (get(_col(head, "明細描述")), get(_col(head, "備註"))) if x)
        return Tx(bank, account, "將來", day, amount, "TWD", get(_col(head, "摘要")), note, key)
    # 台新：台幣「交易日/帳務日/摘要/支出/存入/餘額/備註」或「金額」帶正負號；外幣多一欄「幣別」
    ledger = block.get("ledger_row", "")
    if block.get("type") == "FX":
        if not ledger:
            return None
        cur = get(_col(head, "幣別"))
        amount = _signed(head, row)
        if amount is None:
            return None
        return Tx(bank, account, "台新外幣", day, amount, cur, get(_col(head, "摘要")), get(_col(head, "備註")), key,
                  interest_only="只取利息" in ledger)
    if not ledger:
        return None
    amount = _signed(head, row)
    if amount is None:
        return None
    return Tx(bank, account, ledger, day, amount, "TWD", get(_col(head, "摘要")), get(_col(head, "備註")), key)


def _signed(head: list, row: list) -> float | None:
    get = lambda i: row[i] if i is not None and i < len(row) else ""
    out_i, in_i = _col(head, "支出", "支出金額", "提款"), _col(head, "存入", "存入金額", "存款")
    if out_i is not None or in_i is not None:
        o, i = _num(get(out_i)), _num(get(in_i))
        if o is None and i is None:
            return None
        return (i or 0) - (o or 0)
    return _num(get(_col(head, "金額")))


# ---------------------------------------------------------------- 分類

def _internal_pairs(txs: list[Tx]) -> dict[str, str]:
    """自己帳戶之間的轉帳：不同帳號、金額相反、日期相差 2 天內 → 配成一對。"""
    pairs, used = {}, set()
    for a in txs:
        if a.key in used or a.amount >= 0 or a.currency != "TWD":
            continue
        for b in txs:
            if b.key in used or b.key == a.key or b.currency != "TWD" or b.account == a.account:
                continue
            if abs(b.amount + a.amount) < 0.5 and abs((b.day - a.day).days) <= 2:
                pairs[a.key], pairs[b.key] = b.key, a.key
                used.update((a.key, b.key))
                break
    return pairs


def classify(txs: list[Tx], rules=None) -> list[Entry]:
    rules = rules if rules is not None else load_rules()
    pairs = _internal_pairs(txs)
    by_key = {t.key: t for t in txs}
    out = []
    for t in txs:
        e = Entry(t)
        text, low = t.text, t.text.lower()
        if t.ledger == "台新外幣":
            own = FX_ROWS.get(t.currency)
            if own is None:
                e.skip, e.reason = True, f"幣別 {t.currency} 細帳沒有對應列"
            elif t.interest_only and "利息" not in text:
                e.skip, e.reason = True, "敦南外幣帳戶只記利息"
            elif "利息" in text:
                e.postings, e.reason = [Posting(own, t.amount)], "外幣利息"
            elif t.amount > 0 and any(w in text for w in FX_DIVIDEND_WORDS):
                e.postings = [Posting(own, t.amount), Posting(FX_DIVIDEND_ROWS[t.currency], t.amount)]
                e.reason = "外幣配息"
            elif t.amount < 0 and any(w in text for w in FUND_WORDS) and t.currency in FUND_ROWS:
                e.postings = [Posting(own, t.amount), Posting(FUND_ROWS[t.currency], -t.amount)]
                e.reason = "基富通投資（外幣）"
            else:
                e.postings, e.reason = [Posting(own, t.amount)], "外幣進出（另一邊請確認）"
            out.append(e)
            continue
        row, interest_row, _ = ACCOUNT_ROWS[t.ledger]
        mine = Posting(row, t.amount)
        partner = by_key.get(pairs.get(t.key, ""))
        if partner is not None:
            if ACCOUNT_ROWS.get(partner.ledger, (None,))[0] == row:
                e.skip, e.reason = True, "同一列的自己帳戶互轉（一進一出相抵）"
            else:
                e.postings, e.reason = [mine], f"自己帳戶互轉（另一邊：{partner.ledger}）"
        elif "利息" in text:
            e.postings = [mine] + ([Posting(interest_row, t.amount)] if interest_row else [])
            e.reason = "利息"
        elif "集保" in text and "配息" in text and t.amount > 0:
            e.postings, e.reason = [mine, Posting(ROW_FUBON_FUND_DIVIDEND, t.amount)], "集保基金配息"
        elif t.amount > 0 and any(w in text for w in DIVIDEND_WORDS):
            e.postings, e.reason = [mine, Posting(ROW_STOCK_DIVIDEND, t.amount)], "台股股利／折讓"
        elif t.amount < 0 and any(w in text for w in FUND_WORDS):
            e.postings, e.reason = [mine, Posting(FUND_ROWS["TWD"], -t.amount)], "投資基金（基富通-台）"
        elif "uncle" in low:
            e.postings, e.reason = [mine, Posting(ROW_UNCLE, -t.amount)], "uncle → 借出+投資"
        elif "line" in low and t.amount > 0 and "line bank" not in low:
            e.postings, e.reason = [mine, Posting(ROW_PETTY_ADVANCE, -t.amount)], "LINE 轉入 → 零用金-代墊 減項"
        elif (bank_row := next((r for w, r in OTHER_BANK_ROWS if w.lower() in low), None)) is not None:
            e.postings, e.reason = [mine, Posting(bank_row, -t.amount)], "轉到其他自己的銀行"
        elif any(w.lower() in low for w in OWN_BANK_WORDS):
            e.postings, e.reason = [mine], "自己帳戶互轉（另一邊明細尚未配對，請確認）"
        else:
            cat, why = categorize(t.note or t.summary, rules)
            e.postings = [mine, Posting(cat, -t.amount)]
            e.reason = ("零用金" if t.amount < 0 else "轉入 → 零用金減項") + f"（{why}）"
        out.append(e)
    return out


# ---------------------------------------------------------------- 報表、寫入

def _row_index(labels: list, row) -> int | None:
    if isinstance(row, int):
        return row - 1
    for i, v in enumerate(labels):
        if str(v).strip() == row:
            return i
    return None


def note_line(t: Tx, amount: float) -> str:
    who = {"fubon": "富邦", "next": "將來", "taishin": "台新", "yuanta": "元大", "linebank": "LINE"}[t.bank]
    money = f"{amount:+,.2f}" if t.currency != "TWD" else f"{amount:+,.0f}"
    return f"{t.day:%m/%d} {who}{t.account.split(' ')[0]} {t.summary} {t.note} {money}".replace("  ", " ").strip()


def write_report(entries: list[Entry], labels: list, target: Path) -> Path:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "銀行明細比對"
    ws.append(["日期", "銀行帳戶", "細帳", "金額", "摘要", "備註", "記到（列：金額）", "依據"])
    for e in entries:
        t = e.tx
        where = "略過" if e.skip else "；".join(
            f"{p.row if isinstance(p.row, str) else str(p.row) + ' ' + str(labels[p.row - 1] if p.row - 1 < len(labels) else '')}：{p.amount:+,.0f}"
            for p in e.postings)
        ws.append([t.day.isoformat(), f"{t.bank} {t.account}", t.ledger, t.amount, t.summary, t.note, where, e.reason])
    for col, width in zip("ABCDEFGH", (11, 26, 12, 12, 12, 34, 46, 34)):
        ws.column_dimensions[col].width = width
    target.parent.mkdir(parents=True, exist_ok=True)
    wb.save(target)
    os.chmod(target, 0o600)
    return target


def load_applied() -> set:
    try:
        return set(json.loads(APPLIED_FILE.read_text("utf-8")))
    except Exception:
        return set()


def save_applied(keys: set) -> None:
    APPLIED_FILE.parent.mkdir(parents=True, exist_ok=True)
    APPLIED_FILE.write_text(json.dumps(sorted(keys), ensure_ascii=False), "utf-8")
    os.chmod(APPLIED_FILE, 0o600)


def plan_cells(entries: list[Entry], formulas: list, labels: list, cols: dict, stamp: date):
    """→ ({儲存格: 新公式}, {儲存格: 新備註行}, 錯誤)。"""
    values, notes, errors = {}, {}, []
    for e in entries:
        if e.skip:
            continue
        month = f"{e.tx.day:%Y-%m}"
        if month not in cols:
            errors.append(f"細帳沒有 {month} 欄")
            continue
        for p in e.postings:
            r = _row_index(labels, p.row)
            if r is None:
                errors.append(f"細帳找不到「{p.row}」")
                continue
            c = cols[month]
            cell = a1(r, c)
            base = values.get(cell, formulas[r][c] if r < len(formulas) and c < len(formulas[r]) else "")
            amount = round(p.amount, 2) if e.tx.currency != "TWD" else int(round(p.amount))
            values[cell] = add_term(base, amount)
            notes.setdefault(cell, []).append(note_line(e.tx, p.amount))
    return values, notes, errors


def check_rows(labels: list) -> list[str]:
    """寫入前確認列號沒有跑掉：帳戶列名稱要包含對應的字。"""
    bad = []
    for name, (row, _, word) in ACCOUNT_ROWS.items():
        label = str(labels[row - 1]) if row - 1 < len(labels) else ""
        if word.lower() not in label.lower():
            bad.append(f"{row} 列是「{label}」，不像 {name}")
    return bad


def run(year: int, apply: bool = False) -> Path:
    txs, warn = load_transactions()
    for w in warn[:10]:
        print("⚠️", w)
    applied = load_applied()
    pending = [t for t in txs if t.key not in applied]
    if not pending:
        print("沒有新的銀行明細要記。")
    entries = classify(pending)
    from .google_auth import calendar_add_once, credentials
    creds = credentials()
    book = open_book(creds)
    detail_title = f"{year}細帳"
    ws = book.worksheet(detail_title)
    shown = ws.get_values()
    labels = [r[0] if r else "" for r in shown]
    cols = month_columns(shown[0] if shown else [])
    stamp = date.today()
    report = write_report(entries, labels, TX_ROOT / f"_銀行明細比對_{stamp:%Y%m%d}.xlsx")
    n_skip = sum(e.skip for e in entries)
    n_todo = sum("待分類" in e.reason or "請確認" in e.reason for e in entries)
    print(f"新交易 {len(entries)} 筆：要記 {len(entries) - n_skip} 筆、略過 {n_skip} 筆、待確認 {n_todo} 筆")
    for e in entries:
        t = e.tx
        where = "略過" if e.skip else "、".join(f"{p.row}:{p.amount:+,.0f}" for p in e.postings)
        print(f"  {t.day:%m/%d} {t.ledger:<8} {t.amount:>+12,.0f}  {t.summary} {t.note[:24]}  → {where}（{e.reason}）")
    print(f"比對報表：{report}")
    bad = check_rows(labels)
    for b in bad:
        print("⚠️", b)
    if not apply:
        print("（只比對，沒有寫入。確認報表後加 --apply 才會寫入總帳。）")
        return report
    if bad:
        raise SystemExit("細帳列號跟設定對不上，先不寫入。")
    for title in (detail_title, f"{year}細帳(含信用卡)"):
        if title not in [w.title for w in book.worksheets()]:
            continue
        sheet = book.worksheet(title)
        formulas = sheet.get_values(value_render_option="FORMULA")
        shown_t = sheet.get_values()
        labels_t = [r[0] if r else "" for r in shown_t]
        if check_rows(labels_t):
            print(f"⚠️ {title} 列號對不上，略過這張表")
            continue
        values, new_notes, errors = plan_cells(entries, formulas, labels_t, month_columns(shown_t[0]), stamp)
        for err in sorted(set(errors)):
            print("⚠️", err)
        if values:
            sheet.batch_update([{"range": c, "values": [[v]]} for c, v in values.items()], value_input_option="USER_ENTERED")
            old_notes = sheet.get_notes()
            merged = {}
            for c, lines in new_notes.items():
                r, col = _rc(c)
                existing = old_notes[r][col] if r < len(old_notes) and col < len(old_notes[r]) else ""
                merged[c] = "\n".join(x for x in (existing.strip(), "\n".join(lines),
                                                   f"加註日期：{stamp:%Y-%m-%d}（bank_sync 銀行明細）") if x)
            _set_notes(sheet, merged)
        print(f"✓ {title}：更新 {len(values)} 格")
    for e in entries:
        applied.add(e.tx.key)
    save_applied(applied)
    by_month = {}
    for e in entries:
        if not e.skip:
            by_month.setdefault(f"{e.tx.day:%Y-%m}", []).append(e)
    for month, items in by_month.items():
        body = "\n".join(f"{note_line(e.tx, e.tx.amount)} → {e.reason}" for e in items)
        title = f"【銀行明細】{month} 寫入細帳 {len(items)} 筆"
        print("   行事曆：", title, "→",
              calendar_add_once(creds, f"bank_sync:bank:{month}:{stamp}", stamp, title, body))
    return report
