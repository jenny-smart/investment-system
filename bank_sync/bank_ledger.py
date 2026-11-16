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
import unicodedata
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
    "渣打": (56, None, "渣打"),   # 渣打台幣沒有利息
    "郵局": (42, None, "郵局"),
}
FX_ROWS = {"人民幣": 83, "日圓": 91, "美元": 90, "南非幣": 92}
# 渣打外幣（Jenny 2026-11-15）：外幣利息加在該幣別列；基金投資 107/108；基金配息 123/124；
# 大華、PYPL 配息有自己的列（列名對照）。配息列的公式會自動加進渣打美金／南非那列，所以只記配息列。
SC_FX_ROWS = {"美元": 88, "南非幣": 89}
SC_FUND_ROWS = {"美元": 107, "南非幣": 108}
SC_DIVIDEND_ROWS = {"美元": 123, "南非幣": 124}
SC_SPECIAL_DIVIDENDS = (("大華", "配息-渣打-大華"), ("PYPL", "配息-PYPL"), ("PAYPAL", "配息-PYPL"))
FX_DIVIDEND_ROWS = {"人民幣": 120, "日圓": 121, "美元": 125, "南非幣": 126}
FUND_ROWS = {"TWD": 105, "人民幣": 104, "日圓": 106}
FX_FUND_ROWS = {"美元": 109, "南非幣": 110}  # 台新-美金、台新-南非（基金投資）
CARD_WORDS = ("信用卡", "卡款", "卡費")
CARD_ROWS = (("渣打", 132), ("富邦", 133), ("聯邦", 134), ("星展", 135), ("DBS", 135), ("台新", 136),
             ("國泰", 137))  # Jenny：信用卡扣款金額記在 132–137
ROW_STOCK_DIVIDEND = 116
ROW_FUBON_FUND_DIVIDEND = 119
ROW_UNCLE = 95
ROW_PETTY_ADVANCE = "零用金-代墊"
ROW_COMPANY_ADVANCE = "零用金-公司代墊"
ROW_STOCK_OLD = "台股-舊資金"   # 賣出持有一年以上的股票
ROW_STOCK_NEW = "台股-新資金"   # 抽籤（申購、中籤、未中籤退款）或買新股票
STOCK_LOTTERY_WORDS = ("抽籤", "申購", "中籤", "預扣", "退款", "處理費")
STOCK_WORDS = ("證券", "交割", "股票", "買進", "賣出", "股款")
ROW_INSURANCE_REBATE = 127  # 回饋金-保險：新光（60,000，每 3 年 120,000）、國泰；公式會自動加進入帳的台新帳戶列
INSURERS = (("新光", (60000, 120000)), ("國泰人壽", ()), ("國壽", ()), ("國泰", ()))
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
    balance: float | None = None   # 這筆交易後的帳戶餘額（銀行給的）
    when: str = ""                 # 排序用：日期＋時間

    @property
    def text(self) -> str:
        return f"{self.summary} {self.note}".strip()


@dataclass
class Posting:
    row: object        # 列號（int）或列名（str，零用金分類）
    amount: float
    label: str = ""
    note_only: bool = False  # 只加備註、不加金額（例：轉入定存）


@dataclass
class Entry:
    tx: Tx
    postings: list = field(default_factory=list)
    reason: str = ""
    skip: bool = False
    waiting: bool = False


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
    """新的檔案先讀；同一個檔案裡後面的帳戶先讀。
    （早期版本查詢沒清空表格，會把下一個帳戶的明細也算到前一個帳戶，所以同樣內容以「較新／較後面」為準。）"""
    folder = TX_ROOT / bank
    for path in sorted(folder.glob("2*.json"), reverse=True) if folder.exists() else []:
        try:
            data = json.loads(path.read_text("utf-8"))
        except Exception:
            continue
        for block in reversed(data.get("accounts", [])):
            yield block


def load_transactions() -> tuple[list[Tx], list[str]]:
    """讀三家已抓到的明細，轉成統一格式。回傳 (交易, 無法解析的警告)。"""
    out, warn, seen, keys = [], [], {}, set()
    for bank in ("fubon", "next", "taishin", "yuanta", "linebank", "sc", "post"):
        for block in _blocks(bank):
            head = block.get("head") or []
            rows = block.get("rows") or []
            if bank == "post":
                from .post_tx import clean_rows
                rows = clean_rows(rows)
            for row in rows:
                tx = _to_tx(bank, block, head, row)
                if tx == "SKIP":
                    continue
                if tx is None:
                    warn.append(f"{bank} {block.get('account')}：看不懂這筆格式 {len(row)} 欄")
                    continue
                # 同一筆交易可能在不同次下載、不同表格版面各存了一次（欄位排法不同）：
                # 用「銀行＋時間＋金額＋餘額」認同一筆；備註空白的那份用有備註的補上
                ident = (bank, tx.when, round(tx.amount, 2), None if tx.balance is None else round(tx.balance, 2),
                         tx.currency, tx.ledger)
                if tx.balance is None:
                    ident = ident + (tx.key,)
                if ident in seen:
                    first = seen[ident]
                    if not first.note and tx.note:
                        first.note = tx.note
                    continue
                if tx.key in keys:
                    continue
                seen[ident] = tx
                keys.add(tx.key)
                out.append(tx)
    out.sort(key=lambda t: (t.day, t.bank, t.account))
    attach_receipts(out)
    return out, warn


def attach_receipts(txs: list) -> int:
    """郵局消費扣款 → 用消費日回找 Messenger 收據（同金額，或幾張加總），品項寫進備註"""
    from .messenger_notes import load_receipts, match_receipt, receipt_note
    receipts = load_receipts()
    if not receipts:
        return 0
    used, hit = set(), 0
    for t in txs:
        if t.bank != "post" or t.amount >= 0 or "利息" in t.summary:
            continue
        rs = match_receipt(t.day, t.amount, receipts, used)
        if rs:
            t.note = receipt_note(rs)
            hit += 1
    return hit


ONLY_ACCOUNTS = {"yuanta": ("大同",), "linebank": ("主帳戶",)}  # Jenny：元大只記大同、LINE Bank 只記主帳戶


def _to_tx(bank: str, block: dict, head: list, row: list):
    tx = _to_tx_core(bank, block, head, row)
    if isinstance(tx, Tx):
        get = lambda i: row[i] if i is not None and i < len(row) else ""
        if bank == "linebank":
            tx.balance = None  # LINE Bank 明細沒有餘額
        else:
            detail = _detail_cell(row) if (bank == "taishin" and "詳細" in head) else None
            tx.balance = detail[1] if detail else _num(get(_col(head, "即時餘額", "帳面餘額", "帳戶餘額", "結存金額", "餘額")))
            if tx.balance is None and bank == "taishin":
                tx.balance = _num(_labeled(row, "餘額"))
        clock = get(_col(head, "交易時間", "時間"))
        tx.when = f"{tx.day.isoformat()} {clock or row[0]}"
    return tx


def _to_tx_core(bank: str, block: dict, head: list, row: list):
    get = lambda i: row[i] if i is not None and i < len(row) else ""
    only = ONLY_ACCOUNTS.get(bank)
    if only and not any(k in block.get("account", "") for k in only):
        return "SKIP"
    day = parse_day(row[0] if row else "")
    if day is None:
        return None
    account = block.get("account", "")
    key = f"{bank}|" + "|".join(row)  # 同一筆交易不論被算在哪個帳戶，都只記一次
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
        # 表格每列前面多一格「整列文字」，欄位跟表頭差一格：一律取最後三格＝時間／摘要／金額
        raw = row[-1] if row else ""
        summary = row[-2] if len(row) >= 2 else ""
        amount = _num(re.sub(r"[^\d.,\-]", "", raw))
        if amount is None:
            return None
        if any(w in raw for w in ("支出", "轉出", "提款", "扣款")) or raw.strip().startswith("-"):
            amount = -abs(amount)
        if re.fullmatch(r"\d{8}-\d+(?:\.\d+)?%", summary.strip()):
            summary = f"利息 {summary}"  # LINE Bank 利息的摘要是「日期-利率%」
        return Tx(bank, account, "連線", day, amount, "TWD", summary, "", key)
    if bank == "post":
        out_, in_ = _num(get(_col(head, "提款金額"))), _num(get(_col(head, "存款金額")))
        if out_ is None and in_ is None:
            return None
        note = " ".join(x for x in (get(_col(head, "備註")), get(_col(head, "附言"))) if x)
        summary = re.sub(r"\s", "", get(_col(head, "摘要")))  # 「利　　息」→「利息」
        return Tx(bank, account, "郵局", day, (in_ or 0) - (out_ or 0), "TWD", summary, note, key)
    if bank == "sc":
        amount = _num(get(_col(head, "金額")).replace("$", ""))
        if amount is None:
            return None
        if block.get("type") == "FX":
            cur = block.get("currency", "")
            return Tx(bank, account, "渣打外幣", day, amount, cur, "", get(_col(head, "摘要說明")), key)
        return Tx(bank, account, "渣打", day, amount, "TWD", get(_col(head, "摘要")), get(_col(head, "摘要說明")), key)
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
        note = get(_col(head, "備註")) or _labeled(row, "備註")
        return Tx(bank, account, "台新外幣", day, amount, cur, get(_col(head, "摘要")), note, key,
                  interest_only="只取利息" in ledger)
    if not ledger:
        return None
    amount = _signed(head, row)
    if amount is None:
        return None
    detail = _detail_cell(row) if "詳細" in head else None
    note = detail[2] if detail else get(_col(head, "備註"))
    return Tx(bank, account, ledger, day, amount, "TWD", get(_col(head, "摘要")), note, key)


DETAIL_RE = re.compile(r"金額\s*(-?[\d,]+(?:\.\d+)?)\s*餘額\s*(-?[\d,]+(?:\.\d+)?)\s*(?:備註\s*(.*))?$")


def _detail_cell(row: list):
    """台新明細有時變成「詳細」一格：『金額 -1,000 餘額 9,000 備註 …』→ (金額, 餘額, 備註)。"""
    for cell in row:
        m = DETAIL_RE.search(cell or "")
        if m:
            return _num(m.group(1)), _num(m.group(2)), (m.group(3) or "").strip()
    return None


def _labeled(row: list, label: str) -> str:
    """從「餘額 999.99 轉換金額 交易匯率 備註 …」這種合併格取出某個標籤後面的內容。"""
    for cell in row:
        m = re.search(rf"{label}\s*(.*?)(?=\s*(?:餘額|轉換金額|交易匯率|備註)\b|$)", cell or "")
        if m and cell.strip().startswith(("金額", "餘額")):
            return m.group(1).strip()
    return ""


def _signed(head: list, row: list) -> float | None:
    get = lambda i: row[i] if i is not None and i < len(row) else ""
    detail = _detail_cell(row)
    if detail and (_col(head, "金額") is None or _col(head, "金額") >= len(row) - 1 or "詳細" in head):
        return detail[0]
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
        if a.key in used or a.amount >= 0:
            continue
        for b in txs:
            if b.key in used or b.key == a.key or b.currency != a.currency or b.account == a.account:
                continue
            if a.currency != "TWD" and not (a.ledger == b.ledger == "台新外幣"):
                continue
            if abs(b.amount + a.amount) < 0.5 and abs((b.day - a.day).days) <= 2:
                pairs[a.key], pairs[b.key] = b.key, a.key
                used.update((a.key, b.key))
                break
    return pairs


def card_charges(year: int) -> list[tuple]:
    """信用卡帳單的逐筆消費 [(卡別, 日期, 店名, 金額, 零用金分類)]（今年＋去年，比對公司匯回的代墊款用）。"""
    from .ledger_sync import parsed_statements
    rules = load_rules()
    out = []
    for y in (year - 1, year):
        try:
            files = parsed_statements(y)
        except Exception:
            continue
        for f in files:
            for c in f.statement.purchases:
                out.append((f.bank, c.day, c.description, c.amount, categorize(c.description, rules)[0]))
    return out


def match_card(t: Tx, charges: list[tuple], days: int = 120) -> list[tuple] | None:
    """富邦轉入金額＝之前刷卡的一筆，或幾筆公司代墊加起來 → 可能是公司匯回刷卡代墊的錢。"""
    from itertools import combinations
    want = int(round(t.amount))
    near = [c for c in charges if 0 <= (t.day - c[1]).days <= days]
    one = [c for c in near if c[3] == want]
    if one:
        return [one[-1]]
    company = [c for c in near if "代墊" in c[4]][-12:]
    for n in (2, 3, 4):
        for combo in combinations(company, n):
            if sum(c[3] for c in combo) == want:
                return list(combo)
    return None


def classify(txs: list[Tx], rules=None, charges: list[tuple] | None = None) -> list[Entry]:
    rules = rules if rules is not None else load_rules()
    pairs = _internal_pairs(txs)
    by_key = {t.key: t for t in txs}
    out = []
    for t in txs:
        e = Entry(t)
        text = unicodedata.normalize("NFKC", t.text)  # 全形 Ｕｎｃｌｅ → Uncle
        low = text.lower()
        if t.ledger == "渣打外幣":
            own = SC_FX_ROWS.get(t.currency)
            up = text.upper()
            special = next((label for w, label in SC_SPECIAL_DIVIDENDS if w in up), None)
            if own is None:
                e.skip, e.reason = True, f"渣打幣別 {t.currency} 細帳沒有對應列"
            elif "利息" in text or re.search(r"\bINT", up):
                e.postings, e.reason = [Posting(own, t.amount)], "渣打外幣利息（加在幣別列）"
            elif t.amount > 0 and special:
                e.postings, e.reason = [Posting(own, t.amount), Posting(special, t.amount)], f"{special}"
            elif t.amount > 0 and any(w in text for w in ("配息", "收益分配", "股利", "基金")):
                e.postings = [Posting(own, t.amount), Posting(SC_DIVIDEND_ROWS[t.currency], t.amount)]
                e.reason = "渣打外幣基金配息"
            elif t.amount < 0 and any(w in text for w in ("基金", "申購", "扣款", "投資")):
                e.postings = [Posting(own, t.amount), Posting(SC_FUND_ROWS[t.currency], -t.amount)]
                e.reason = "渣打外幣基金投資"
            elif pairs.get(t.key):
                e.postings, e.reason = [Posting(own, t.amount)], "自己帳戶互轉"
            else:
                e.postings, e.reason = [Posting(own, t.amount)], "渣打外幣進出 — 另一邊請確認"
            out.append(e)
            continue
        if t.ledger == "台新外幣":
            own = FX_ROWS.get(t.currency)
            note_up = text.upper()
            is_interest = "利息" in text or re.search(r"\bINT", note_up) is not None  # Jenny：有 INT 就是利息
            is_fund_buy = (re.search(r"\d{6,}(ZAR|USD|CNY|JPY|RMB)\b", note_up) is not None  # 例：0407…ZAR＝投資基金
                           or (t.amount < 0 and re.search(r"FY\d{6,}|基金|債", text) is not None))  # 例：IYA5 高盛新興債 FY0400…
            if own is None:
                e.skip, e.reason = True, f"幣別 {t.currency} 細帳沒有對應列"
            elif is_interest:
                e.postings, e.reason = [Posting(own, t.amount)], "外幣利息（加在幣別列）"
            elif pairs.get(t.key):  # 古亭⇄敦南：細帳外幣列＝兩個帳戶加總，互轉不變
                e.skip, e.reason = True, "台新外幣帳戶互轉（外幣列是加總，不變）"
            elif t.amount < 0 and is_fund_buy and t.currency in FX_FUND_ROWS:
                e.postings = [Posting(own, t.amount), Posting(FX_FUND_ROWS[t.currency], -t.amount)]
                e.reason = f"外幣投資基金 → {FX_FUND_ROWS[t.currency]}"
            elif t.amount < 0 and t.currency in FUND_ROWS and any(w in text for w in FUND_WORDS):
                e.postings = [Posting(own, t.amount), Posting(FUND_ROWS[t.currency], -t.amount)]
                e.reason = "基富通投資（外幣）"
            elif t.amount < 0 and t.interest_only:  # Jenny：敦南轉入定存只加備註，到期利息再加
                e.postings = [Posting(own, t.amount, note_only=True)]
                e.reason = "轉入定存（只加備註，不加金額；到期利息再記）"
            elif t.amount > 0:
                e.postings = [Posting(own, t.amount), Posting(FX_DIVIDEND_ROWS[t.currency], t.amount)]
                e.reason = "外幣基金收入（配息）"
            else:
                e.postings, e.reason = [Posting(own, t.amount)], "外幣轉出 — 另一邊請確認"
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
        elif t.amount > 0 and (ins := next(((w, exp) for w, exp in INSURERS if w in text), None)) and (
                "保險" in text or "人壽" in text or "國壽" in text or "回饋" in text or "生存" in text or ins[0] == "新光"):
            e.postings = [Posting(ROW_INSURANCE_REBATE, t.amount)]  # Jenny：只記 127，勿重複加進帳戶列
            e.reason = "保險回饋金 → 只記 127（帳戶列公式自動帶入）"
            if ins[1] and int(round(t.amount)) not in ins[1]:
                e.reason += f"— 金額跟往年（{'／'.join(f'{x:,}' for x in ins[1])}）不同，請確認"
        elif t.amount < 0 and any(w in text for w in CARD_WORDS):
            card = next((r for w, r in CARD_ROWS if w.lower() in low), None)
            if card is None:
                e.postings, e.reason = [mine], "信用卡扣款（哪一家卡？請確認）"
            else:  # Jenny：只記信用卡列，帳戶列公式會自動帶入
                e.postings, e.reason = [Posting(card, -t.amount)], "信用卡扣款 → 只記信用卡列（帳戶列公式自動帶入）"
        elif t.amount > 0 and "配息" in text and "集保" not in text and re.search(r"\b0\d{3,4}[A-Z]?\b|\d{4}FUND|0\d{3,4}[A-Z]?$", text.upper().replace(" ", " ")):
            e.postings = [Posting(ROW_STOCK_DIVIDEND, t.amount)]  # Jenny：只記 116，帳戶列公式會自動帶入
            e.reason = "台股（ETF）配息 → 只記 116（帳戶列公式自動帶入）"
        elif ("集保" not in text and "基金" not in text and not any(w in text for w in FUND_WORDS)
              and any(w in text for w in STOCK_LOTTERY_WORDS + STOCK_WORDS)):
            if any(w in text for w in STOCK_LOTTERY_WORDS) or t.amount < 0:
                e.postings = [mine, Posting(ROW_STOCK_NEW, -t.amount)]
                e.reason = "台股新資金（抽籤／買股票）— 請確認"
            else:
                e.postings = [mine, Posting(ROW_STOCK_OLD, -t.amount)]
                e.reason = "台股舊資金（賣出持有一年以上）— 請確認"
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
        elif (bank_row := next((r for w, r in OTHER_BANK_ROWS if w.lower() in low and r != row), None)) is not None:
            e.postings, e.reason = [mine, Posting(bank_row, -t.amount)], "轉到其他自己的銀行"
        elif any(w.lower() in low for w in OWN_BANK_WORDS):
            e.postings, e.reason = [mine], "自己帳戶互轉（另一邊明細尚未配對，請確認）"
        else:
            cat, why = categorize(t.note or t.summary, rules)
            matched = match_card(t, charges) if (charges and t.amount > 0 and t.ledger == "富邦") else None
            if matched:
                cards = "、".join(f"{c[0]}卡 {c[1]:%m/%d} {c[2][:10]} {c[3]:,}" for c in matched)
                e.postings = [mine, Posting(ROW_COMPANY_ADVANCE, -t.amount)]  # Jenny：零用金-公司代墊 減項
                e.reason = f"可能是公司匯回刷卡代墊（對到 {cards}）→ 零用金-公司代墊 減項，請確認"
                out.append(e)
                continue
            if t.ledger == "富邦" and cat == "零用金-其他":
                # Jenny：富邦 38 除了基富通配息，多半是代墊款進出，偶爾是個人帳 → 預設代墊，請確認
                cat, why = ROW_PETTY_ADVANCE, "富邦多為代墊款，請確認"
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
    who = {"fubon": "富邦", "next": "將來", "taishin": "台新", "yuanta": "元大", "linebank": "LINE", "sc": "渣打", "post": "郵局"}[t.bank]
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


def _refs(formula: str) -> set:
    return set(re.findall(r"\$?([A-Z]{1,2})\$?(\d+)", str(formula or "").upper()))


def plan_cells(entries: list[Entry], formulas: list, labels: list, cols: dict, stamp: date):
    """→ ({儲存格: 新公式}, {儲存格: 新備註行}, 錯誤)。
    帳戶列的公式如果已經引用另一邊那一格（例：建北 43 列公式含 116 列），就不在帳戶列重複加。"""
    values, notes, errors = {}, {}, []
    for e in entries:
        if e.skip:
            continue
        month = f"{e.tx.day:%Y-%m}"
        if month not in cols:
            errors.append(f"細帳沒有 {month} 欄")
            continue
        c = cols[month]
        rows = [(_row_index(labels, p.row), p) for p in e.postings]
        if any(r is None for r, _ in rows):
            errors.append("細帳找不到「" + "、".join(str(p.row) for r, p in rows if r is None) + "」")
            continue
        if len(rows) >= 2:
            first_r = rows[0][0]
            base = formulas[first_r][c] if first_r < len(formulas) and c < len(formulas[first_r]) else ""
            col_letter = re.match(r"[A-Z]+", a1(0, c)).group(0)
            linked = {(col_letter, str(r + 1)) for r, _ in rows[1:]} & _refs(base)
            if linked:
                rows = rows[1:]
                e.reason += "（帳戶列公式已帶入，不重複加）"
        for r, p in rows:
            cell = a1(r, c)
            if not p.note_only:
                base = values.get(cell, formulas[r][c] if r < len(formulas) and c < len(formulas[r]) else "")
                amount = round(p.amount, 2) if e.tx.currency != "TWD" else int(round(p.amount))
                if amount == int(amount):
                    amount = int(amount)  # 300.0 → 300
                values[cell] = add_term(base, amount)
            notes.setdefault(cell, []).append(note_line(e.tx, p.amount) + ("（只記備註）" if p.note_only else ""))
    return values, notes, errors


def check_rows(labels: list) -> list[str]:
    """寫入前確認列號沒有跑掉：帳戶列名稱要包含對應的字。"""
    bad = []
    for name, (row, _, word) in ACCOUNT_ROWS.items():
        label = str(labels[row - 1]) if row - 1 < len(labels) else ""
        if word.lower() not in label.lower():
            bad.append(f"{row} 列是「{label}」，不像 {name}")
    return bad


# ---------------------------------------------------------------- 確認表（總帳裡的「銀行明細確認」分頁）

REVIEW_TITLE = "銀行明細確認"
REVIEW_HEAD = ["狀態", "日期", "銀行帳戶", "細帳", "金額", "摘要", "備註", "記到（列：金額）", "依據",
               "你的確認", "改記到（另一邊列號或列名）", "代碼"]
CHOICES = ["確認", "略過"]


def needs_check(e: Entry) -> bool:
    return any(k in e.reason for k in ("待分類", "請確認", "另一邊請確認", "零用金減項", "可能已記過"))


def _has_term(formula: str, amount: float) -> bool:
    """公式裡已經有這個金額（例：=1000+8590 裡的 8590）。"""
    text = str(formula or "").replace(",", "")
    num = f"{abs(amount):.2f}".rstrip("0").rstrip(".")
    return re.search(rf"(?<![\d.]){re.escape(num)}(?![\d.])", text) is not None


def mark_existing(entries: list[Entry], formulas: list, labels: list, cols: dict) -> int:
    """細帳那一格已經有相同金額 → 可能你手動記過了，標「可能已記過」、要你確認才寫。"""
    n = 0
    for e in entries:
        if e.skip or not e.postings:
            continue
        c = cols.get(f"{e.tx.day:%Y-%m}")
        if c is None:
            continue
        for p in e.postings:
            if p.note_only:
                continue
            r = _row_index(labels, p.row)
            if r is not None and r < len(formulas) and c < len(formulas[r]) and _has_term(formulas[r][c], p.amount):
                e.reason += f"（{p.row} 列這個月已有 {abs(p.amount):,.0f}，可能已記過）"
                n += 1
                break
    return n


def _describe(e: Entry, labels: list) -> str:
    if e.skip:
        return "略過"
    def name(row):
        if isinstance(row, str):
            return row
        return f"{row} {labels[row - 1] if row - 1 < len(labels) else ''}".strip()
    return "；".join(f"{name(p.row)}：" + ("只加備註" if p.note_only else f"{p.amount:+,.2f}".replace(".00", ""))
                    for p in e.postings)


def read_review(book) -> dict:
    """{代碼: (你的確認, 改記到)}"""
    try:
        ws = book.worksheet(REVIEW_TITLE)
    except Exception:
        return {}
    rows = ws.get_values()
    if not rows:
        return {}
    head = rows[0]
    try:
        ki, ci, ri = head.index("代碼"), head.index("你的確認"), head.index("改記到（另一邊列號或列名）")
    except ValueError:
        return {}
    out = {}
    for r in rows[1:]:
        if ki < len(r) and r[ki]:
            out[r[ki]] = (r[ci].strip() if ci < len(r) else "", r[ri].strip() if ri < len(r) else "")
    return out


def apply_review(entries: list[Entry], answers: dict) -> list[Entry]:
    """套用你在確認表填的答案；需要確認但還沒填「確認」的，這次先不寫入。"""
    out = []
    for e in entries:
        code = _code(e.tx)
        choice, target = answers.get(code, ("", ""))
        if choice == "略過":
            e.skip, e.reason = True, "你在確認表選了略過"
        elif target:
            row = int(target) if target.isdigit() else target
            if e.tx.ledger == "台新外幣":
                own = None if e.tx.interest_only else FX_ROWS.get(e.tx.currency)
            else:
                own = ACCOUNT_ROWS.get(e.tx.ledger, (None,))[0]
            mine = [Posting(own, e.tx.amount)] if own else []
            e.postings, e.reason, e.skip = mine + [Posting(row, -e.tx.amount)], f"你改記到 {target}", False
        elif needs_check(e) and choice != "確認":
            e.skip, e.reason, e.waiting = True, "等你在確認表確認（這次先不寫）", True
        out.append(e)
    return out


def _code(t: Tx) -> str:
    import hashlib
    return hashlib.sha1(t.key.encode("utf-8")).hexdigest()[:12]


def write_review(book, entries: list[Entry], labels: list, answers: dict) -> str:
    try:
        ws = book.worksheet(REVIEW_TITLE)
    except Exception:
        ws = book.add_worksheet(REVIEW_TITLE, rows=500, cols=len(REVIEW_HEAD))
    rows = [REVIEW_HEAD]
    order = sorted(entries, key=lambda e: ("已記過（細帳" in e.reason, not needs_check(e), e.tx.day))
    for e in order:
        t = e.tx
        choice, target = answers.get(_code(t), ("", ""))
        state = ("已記過" if "已記過（細帳" in e.reason else "⚠️ 請確認" if needs_check(e) else ("略過" if e.skip else "自動"))
        who = {"fubon": "富邦", "next": "將來", "taishin": "台新", "yuanta": "元大", "linebank": "LINE", "sc": "渣打", "post": "郵局"}.get(t.bank, t.bank)
        money = t.amount if t.currency != "TWD" else int(round(t.amount))
        rows.append([state, t.day.isoformat(), f"{who} {t.account}", t.ledger + ("" if t.currency == "TWD" else f"（{t.currency}）"),
                     money, t.summary, t.note, _describe(e, labels), e.reason, choice, target, _code(t)])
    ws.clear()
    if ws.row_count < len(rows) + 10:
        ws.add_rows(len(rows) + 10 - ws.row_count)
    ws.update(rows, "A1", value_input_option="RAW")
    try:  # 「你的確認」下拉選單、標題粗體凍結、要確認的列標黃
        sid = ws.id
        reqs = [
            {"setDataValidation": {"range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": len(rows),
                                             "startColumnIndex": 9, "endColumnIndex": 10},
                                   "rule": {"condition": {"type": "ONE_OF_LIST",
                                                          "values": [{"userEnteredValue": c} for c in CHOICES]},
                                            "showCustomUi": True, "strict": False}}},
            {"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1}},
                                       "fields": "gridProperties.frozenRowCount"}},
            {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}}, "fields": "userEnteredFormat.textFormat.bold"}},
            {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 2000},
                            "cell": {"userEnteredFormat": {"backgroundColor": {"red": 1, "green": 1, "blue": 1}}},
                            "fields": "userEnteredFormat.backgroundColor"}},
        ]
        for i, r in enumerate(rows[1:], start=1):
            if r[0].startswith("⚠️"):
                reqs.append({"repeatCell": {"range": {"sheetId": sid, "startRowIndex": i, "endRowIndex": i + 1,
                                                      "startColumnIndex": 0, "endColumnIndex": len(REVIEW_HEAD)},
                                            "cell": {"userEnteredFormat": {"backgroundColor": {"red": 1, "green": 0.95, "blue": 0.75}}},
                                            "fields": "userEnteredFormat.backgroundColor"}})
        book.batch_update({"requests": reqs})
    except Exception as exc:
        print(f"（確認表格式沒套上：{exc}）")
    return f"https://docs.google.com/spreadsheets/d/{book.id}/edit#gid={ws.id}"


def review(year: int) -> str:
    """把目前抓到、還沒寫進細帳的明細，列在總帳的「銀行明細確認」分頁，要你確認的排最上面並標黃。"""
    txs, warn = load_transactions()
    for w in warn[:10]:
        print("⚠️", w)
    applied = load_applied()
    entries = classify([t for t in txs if t.key not in applied], charges=card_charges(year))
    from .google_auth import credentials
    book = open_book(credentials())
    detail = book.worksheet(f"{year}細帳")
    shown = detail.get_values()
    labels = [r[0] if r else "" for r in shown]
    formulas = detail.get_values(value_render_option="FORMULA")
    numbers = detail.get_values(value_render_option="UNFORMATTED_VALUE")
    cols = month_columns(shown[0] if shown else [])
    rec = mark_recorded(entries, txs, numbers, labels, cols)
    if rec:
        print(f"✓ {rec} 筆你已經記過（細帳金額＝銀行該筆之後的餘額），不會重複寫")
    dup = mark_existing(entries, formulas, labels, cols)
    if dup:
        print(f"⚠️ {dup} 筆在細帳那一格已有相同金額，可能你已手動記過，標成要確認")
    answers = read_review(book)
    url = write_review(book, entries, labels, answers)
    sim_entries = apply_review(entries, answers)
    sim = simulate(sim_entries, txs, formulas, numbers, labels, cols)
    print("\n模擬記入後的餘額核對（只算已確認／自動的項目）：")
    bad = print_balance(sim)
    print(f"餘額核對表：{write_balance_sheet(book, sim)}")
    if bad:
        print(f"⚠️ {bad} 列對不上：可能還有沒確認的項目、手動記過的重複、或帳戶沒有餘額資料")
    n_check = sum(needs_check(e) for e in entries)
    print(f"還沒寫進細帳的明細 {len(entries)} 筆，其中要你確認 {n_check} 筆（排最上面、標黃）。")
    print(f"確認表：{url}")
    print("在「你的確認」選 確認／略過；另一邊要改的，在「改記到」填列號（例 105）或列名（例 零用金-餐費）。")
    print("填好後執行：python3 -m bank_sync bank-ledger --apply")
    _publish_quietly(year)
    from .progress_log import log_run
    log_run("銀行明細確認表", None, f"總帳「{REVIEW_TITLE}」分頁", [], message=f"待寫入 {len(entries)} 筆｜要確認 {n_check} 筆")
    return url


# ---------------------------------------------------------------- 餘額核對（模擬記入後，細帳要等於銀行餘額）

BALANCE_TITLE = "銀行餘額核對"


def ledger_row_of(t: Tx) -> int | None:
    if t.ledger == "台新外幣":
        return FX_ROWS.get(t.currency)
    if t.ledger == "渣打外幣":
        return SC_FX_ROWS.get(t.currency)
    return ACCOUNT_ROWS.get(t.ledger, (None,))[0]


def _is_time_deposit(t: Tx) -> bool:
    """敦南外幣轉入定存：銀行活存少了，但細帳那列不變（定存本金還在）。"""
    if t.ledger != "台新外幣" or not t.interest_only or t.amount >= 0:
        return False
    text = unicodedata.normalize("NFKC", t.text).upper()
    return not re.search(r"\d{6,}(ZAR|USD|CNY|JPY|RMB)\b", text) and not re.search(r"\bINT|利息", text)


FX_BALANCE_FILE = TX_ROOT / "taishin" / "_fx_balance.json"
FX_BALANCE_ACCOUNTS = ("古亭", "Richart外幣綜存")  # Jenny：外幣列＝這兩個帳戶加總＋定存（總覽的「總計」已含定存）


def fx_overview() -> dict:
    """{細帳列號: (總計, 說明)}：外幣總覽各幣別（兩個帳戶的活期＋定期）。"""
    try:
        data = json.loads(FX_BALANCE_FILE.read_text("utf-8"))
    except Exception:
        return {}
    out = {}
    for r in data.get("rows", []):
        row = FX_ROWS.get(r["currency"])
        if row is None or not any(k in r["account"] for k in FX_BALANCE_ACCOUNTS):
            continue
        total, parts = out.get(row, (0.0, []))
        parts.append(f"{r['account']}：活期 {r['demand']:,.2f}＋定存 {r['time']:,.2f}")
        out[row] = (total + r["total"], parts)
    return {k: (v, "；".join(p) + f"（外幣總覽 {data.get('at', '')}）") for k, (v, p) in out.items()}


def mark_recorded(entries: list[Entry], all_txs: list[Tx], numbers: list, labels: list, cols: dict) -> int:
    """用銀行餘額找出「你已經手動記到哪一筆」：
    依時間順序算各帳戶加總餘額，細帳那一格目前的金額等於哪個時間點的餘額，那個時間點以前的交易就是已記過。"""
    by_row = {}
    for t in all_txs:
        r = ledger_row_of(t)
        if r is not None and t.balance is not None:
            by_row.setdefault(r, []).append(t)
    done = set()
    overview = fx_overview()
    this_month = date.today().strftime("%Y-%m")
    for row_no, (total, _) in overview.items():  # 外幣：細帳目前＝總覽總計 → 這個月都記過了
        c = cols.get(this_month)
        if c is not None and row_no - 1 < len(numbers) and c < len(numbers[row_no - 1]):
            cur = _num(str(numbers[row_no - 1][c]))
            if cur is not None and abs(cur - total) < 0.5:
                done.update(t.key for t in all_txs if ledger_row_of(t) == row_no and f"{t.day:%Y-%m}" == this_month)
    for row_no, txs in by_row.items():
        if row_no in overview:
            continue
        txs.sort(key=lambda t: t.when)
        months = sorted({f"{t.day:%Y-%m}" for t in txs})
        for month in months:
            c = cols.get(month)
            if c is None or row_no - 1 >= len(numbers) or c >= len(numbers[row_no - 1]):
                continue
            current = _num(str(numbers[row_no - 1][c]))
            if current is None:
                continue
            latest, adj, cut, started = {}, 0.0, None, False
            for t in txs:  # 各帳戶第一筆之前的餘額
                name = t.account + t.currency
                latest.setdefault(name, t.balance - t.amount)
            for t in txs:
                if f"{t.day:%Y-%m}" > month:
                    break
                if f"{t.day:%Y-%m}" == month and not started:
                    started = True
                    if abs(sum(latest.values()) + adj - current) < 0.5:
                        cut = ""  # 這個月一筆都還沒記
                latest[t.account + t.currency] = t.balance
                if _is_time_deposit(t):
                    adj += -t.amount
                if f"{t.day:%Y-%m}" == month and abs(sum(latest.values()) + adj - current) < 0.5:
                    cut = t.when
            if cut:
                done.update(t.key for t in txs if f"{t.day:%Y-%m}" == month and t.when <= cut)
    n = 0
    for e in entries:
        if e.tx.key in done and not e.skip:
            e.skip, e.reason, n = True, "已記過（細帳目前金額＝銀行這筆之後的餘額）", n + 1
        elif e.tx.key in done:
            e.reason += "（已記過）"
    return n


def bank_balances(txs: list[Tx]) -> dict:
    """{(細帳列號): {帳戶: (時間, 餘額)}}：每個帳戶最後一筆交易後的銀行餘額。"""
    out = {}
    for t in txs:
        if t.balance is None:
            continue
        row = ledger_row_of(t)  # 外幣列＝古亭＋敦南（錢在台新外幣帳戶之間移動，細帳那列不變）
        if row is None:
            continue
        acct = out.setdefault(row, {})
        name = t.account + ("" if t.currency == "TWD" else f" {t.currency}")
        if name not in acct or t.when >= acct[name][0]:
            acct[name] = (t.when, t.balance)
    return out


def _linked_sign(formula: str, col_letter: str, row_no: int) -> int:
    """帳戶列公式引用另一格時的正負號（=…+L116 → +1；=…-L135 → -1；沒引用 → 0）。"""
    m = re.search(rf"([+\-]?)\s*\$?{col_letter}\$?{row_no}(?!\d)", str(formula or "").upper())
    if not m:
        return 0
    return -1 if m.group(1) == "-" else 1


def simulate(entries: list[Entry], all_txs: list[Tx], formulas: list, numbers: list, labels: list, cols: dict,
             month: str = "") -> list[list]:
    """模擬把這次的明細記進細帳後，每個帳戶列的金額，跟銀行最後餘額比對。"""
    month = month or max((e.tx.day for e in entries if not e.skip), default=date.today()).strftime("%Y-%m")
    c = cols.get(month)
    if c is None:
        return [["細帳沒有 " + month + " 欄"]]
    col_letter = re.match(r"[A-Z]+", a1(0, c)).group(0)
    adds = {}
    for e in entries:
        if e.skip or f"{e.tx.day:%Y-%m}" != month:
            continue
        for p in e.postings:
            if p.note_only:
                continue
            r = _row_index(labels, p.row)
            if r is not None:
                adds[r] = adds.get(r, 0) + p.amount
    balances = bank_balances(all_txs)
    rows = [["細帳列", "列名", f"{month} 細帳目前", "本次要加", "模擬記入後", "銀行最後餘額", "差額", "銀行餘額來源", "結果"]]
    targets = sorted({v[0] for v in ACCOUNT_ROWS.values()} | set(FX_ROWS.values()))
    for row_no in targets:
        r = row_no - 1
        cur = numbers[r][c] if r < len(numbers) and c < len(numbers[r]) else ""
        cur_v = _num(str(cur)) or 0.0
        add = adds.get(r, 0.0)
        f = formulas[r][c] if r < len(formulas) and c < len(formulas[r]) else ""
        for other_r, amount in adds.items():  # 帳戶列公式自動帶入的另一格（例：43 含 116、47 含 −135）
            if other_r != r:
                add += _linked_sign(f, col_letter, other_r + 1) * amount
        sim = cur_v + add
        bank = balances.get(row_no, {})
        ov = fx_overview().get(row_no)
        if ov is not None:  # 外幣列用外幣總覽（兩個帳戶的活期＋定存）
            total, src = ov
            diff = round(sim - total, 2)
            rows.append([row_no, labels[r] if r < len(labels) else "", cur_v, add, sim, total, diff, src,
                         "✓ 相符" if abs(diff) < 0.5 else "⚠️ 不相符"])
            continue
        if not bank:
            if add:
                rows.append([row_no, labels[r] if r < len(labels) else "", cur_v, add, sim, "", "", "沒有銀行餘額資料", "⚠️ 無法核對"])
            continue
        total = sum(v for _, v in bank.values())
        td = sum(-t.amount for t in all_txs if _is_time_deposit(t) and ledger_row_of(t) == row_no)
        if td:
            total += td  # 定存本金：銀行活存沒有、細帳那列還在
        diff = round(sim - total, 2)
        src = "；".join(f"{k}：{w[:16]}" for k, (w, _) in bank.items()) + (f"；＋定存 {td:,.2f}" if td else "")
        ok = abs(diff) < 0.5
        rows.append([row_no, labels[r] if r < len(labels) else "", cur_v, add, sim, total, diff, src,
                     "✓ 相符" if ok else "⚠️ 不相符"])
    return rows


def write_balance_sheet(book, rows: list[list]) -> str:
    try:
        ws = book.worksheet(BALANCE_TITLE)
    except Exception:
        ws = book.add_worksheet(BALANCE_TITLE, rows=60, cols=10)
    ws.clear()
    ws.update(rows, "A1", value_input_option="RAW")
    return f"https://docs.google.com/spreadsheets/d/{book.id}/edit#gid={ws.id}"


def print_balance(rows: list[list]) -> int:
    bad = 0
    for r in rows[1:]:
        if len(r) < 9:
            print("⚠️", r[0])
            continue
        mark = r[8]
        bad += mark != "✓ 相符"
        bank = f"{r[5]:,.2f}" if isinstance(r[5], (int, float)) else "—"
        print(f"  {mark}  {r[0]} {r[1]}：模擬後 {r[4]:,.2f}　銀行 {bank}　差 {r[6]}")
    return bad


def _publish_quietly(year: int) -> None:
    """順便更新總帳「銀行明細」「信用卡明細」分頁（App 網頁讀這兩頁）；失敗不影響主流程。"""
    try:
        from .publish import publish
        publish(year)
    except (Exception, SystemExit) as exc:
        print(f"（App 用的明細分頁沒更新：{exc}）")


def run(year: int, apply: bool = False, force: bool = False) -> Path:
    txs, warn = load_transactions()
    for w in warn[:10]:
        print("⚠️", w)
    applied = load_applied()
    pending = [t for t in txs if t.key not in applied]
    if not pending:
        print("沒有新的銀行明細要記。")
    entries = classify(pending, charges=card_charges(year))
    from .google_auth import calendar_add_once, credentials
    creds = credentials()
    book = open_book(creds)
    detail_title = f"{year}細帳"
    _shown = book.worksheet(detail_title).get_values()
    _labels, _cols = [r[0] if r else "" for r in _shown], month_columns(_shown[0] if _shown else [])
    mark_recorded(entries, txs, book.worksheet(detail_title).get_values(value_render_option="UNFORMATTED_VALUE"), _labels, _cols)
    mark_existing(entries, book.worksheet(detail_title).get_values(value_render_option="FORMULA"), _labels, _cols)
    entries = apply_review(entries, read_review(book))
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
    ws_detail = book.worksheet(detail_title)
    sim = simulate(entries, txs, ws_detail.get_values(value_render_option="FORMULA"),
                   ws_detail.get_values(value_render_option="UNFORMATTED_VALUE"), labels, cols)
    month = next((r[2].split(" ")[0] for r in sim[:1] if len(r) > 2), "")
    print("\n模擬記入後的餘額核對：")
    mismatch = print_balance(sim)
    write_balance_sheet(book, sim)
    if not apply:
        print("（只模擬，沒有寫入。餘額都相符、確認表也確認過，再加 --apply 寫入總帳。）")
        return report
    if bad:
        raise SystemExit("細帳列號跟設定對不上，先不寫入。")
    if mismatch and not force:
        raise SystemExit(f"模擬記入後有 {mismatch} 列餘額跟銀行對不上，先不寫入。"
                         "看「銀行餘額核對」分頁找原因；確定要寫可加 --force。")
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
        if not getattr(e, "waiting", False):  # 等你確認的下次再寫
            applied.add(e.tx.key)
    save_applied(applied)
    after = simulate([], txs, ws_detail.get_values(value_render_option="FORMULA"),
                     ws_detail.get_values(value_render_option="UNFORMATTED_VALUE"), labels, cols, month=month)
    print("\n寫入後的餘額核對（細帳 vs 銀行）：")
    after_bad = print_balance(after)
    write_balance_sheet(book, after)
    if after_bad:
        print(f"⚠️ 寫入後還有 {after_bad} 列跟銀行餘額不同，請看「銀行餘額核對」分頁")
    _publish_quietly(year)
    from .progress_log import log_run
    banks_done = {}
    for e in entries:
        if not e.skip:
            banks_done[e.tx.ledger] = banks_done.get(e.tx.ledger, 0) + 1
    log_run("銀行明細→細帳", None, f"{year}細帳／{year}細帳(含信用卡)", [], message=
            "寫入 " + "；".join(f"{k} {v} 筆" for k, v in banks_done.items()) + f"｜略過 {n_skip} 筆｜待確認 {n_todo} 筆")
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


# ---------------------------------------------------------------- 全年核對（不改細帳，複製一份標顏色）

AUDIT_COLORS = {
    "missing_other": {"red": 1, "green": 0.92, "blue": 0.45},   # 黃：另一邊沒記
    "missing_own": {"red": 1, "green": 0.75, "blue": 0.45},     # 橘：帳戶列沒記
    "elsewhere": {"red": 0.75, "green": 0.88, "blue": 1},       # 藍：記在別列（請看是不是對的）
    "balance": {"red": 1, "green": 0.6, "blue": 0.6},           # 紅：月底跟銀行餘額不同
}


def _find_in_column(formulas: list, c: int, amount: float, skip_rows: set) -> list[int]:
    return [r for r in range(len(formulas)) if r not in skip_rows and c < len(formulas[r]) and _has_term(formulas[r][c], amount)]


def audit(year: int, banks: tuple = ("fubon", "taishin", "next")) -> str:
    """把今年（指定銀行）抓到的每筆明細，對照 {year}細帳：
    帳戶列有沒有這筆、另一邊（零用金、配息、投資…）有沒有記；月底帳戶列＝銀行餘額嗎。
    先把 {year}細帳 複製成新工作表，在副本上用底色＋備註標出問題，原本的細帳不動；另外列一張清單。"""
    txs, warn = load_transactions()
    txs = [t for t in txs if t.day.year == year and t.bank in banks]
    if not txs:
        raise SystemExit(f"本機沒有 {year} 年 {'/'.join(banks)} 的明細，請先用 --since {year}-01-01 抓全年。")
    entries = classify(txs, charges=card_charges(year))
    from .google_auth import credentials
    book = open_book(credentials())
    src = book.worksheet(f"{year}細帳")
    shown = src.get_values()
    labels = [r[0] if r else "" for r in shown]
    cols = month_columns(shown[0] if shown else [])
    formulas = src.get_values(value_render_option="FORMULA")
    numbers = src.get_values(value_render_option="UNFORMATTED_VALUE")
    stamp = datetime.now()
    title = f"{year}細帳-銀行核對{stamp:%m%d}"
    for ws in book.worksheets():
        if ws.title == title:
            book.del_worksheet(ws)
    copy = book.duplicate_sheet(src.id, insert_sheet_index=src.index + 1, new_sheet_name=title)

    marks, notes, listing = {}, {}, []

    priority = {"balance": 4, "missing_own": 3, "missing_other": 2, "elsewhere": 1}

    def mark(r: int, c: int, kind: str, text: str):
        cell = a1(r, c)
        if priority[kind] > priority.get(marks.get(cell), 0):
            marks[cell] = kind
        notes.setdefault(cell, []).append(text)

    for e in entries:
        t = e.tx
        month = f"{t.day:%Y-%m}"
        c = cols.get(month)
        line = note_line(t, t.amount)
        if c is None or e.skip or not e.postings:
            listing.append([month, t.day.isoformat(), line, "", "略過" if e.skip else "", e.reason])
            continue
        rows = [(_row_index(labels, p.row), p) for p in e.postings if not p.note_only]
        if any(r is None for r, _ in rows):
            listing.append([month, t.day.isoformat(), line, "", "找不到列", e.reason])
            continue
        own_r = rows[0][0] if rows else None
        who = {"fubon": "富邦", "next": "將來", "taishin": "台新", "yuanta": "元大", "linebank": "LINE", "sc": "渣打", "post": "郵局"}.get(t.bank, t.bank)
        memo = re.sub(r"\s*\S*分行$|\d{6,}", "", t.note or t.summary).strip()[:12]
        short = f"{t.day:%m/%d} {who} {memo}"
        col_letter = re.match(r"[A-Z]+", a1(0, c)).group(0)
        status = []
        for k, (r, p) in enumerate(rows):
            f = formulas[r][c] if r < len(formulas) and c < len(formulas[r]) else ""
            if _has_term(f, p.amount):
                status.append(f"{r + 1} 已記")
                continue
            if k == 0 and len(rows) > 1 and any(_linked_sign(f, col_letter, rr + 1) for rr, _ in rows[1:]):
                status.append(f"{r + 1} 公式帶入")
                continue
            elsewhere = _find_in_column(formulas, c, p.amount, {rr for rr, _ in rows})
            if elsewhere:
                where = "、".join(f"{x + 1} {labels[x]}" for x in elsewhere[:3])
                mark(r, c, "elsewhere", f"{short} → 在 {where}")
                status.append(f"{r + 1} 記在別列（{where}）")
            else:
                kind = "missing_own" if k == 0 else "missing_other"
                mark(r, c, kind, f"{short} 未記 {p.amount:+,.2f}".replace(".00", ""))
                status.append(f"{r + 1} 沒記")
        bad = any("沒記" in x or "別列" in x for x in status)
        listing.append([month, t.day.isoformat(), line, "；".join(status), "⚠️" if bad else "✓", e.reason])

    # 月底餘額：每個帳戶列，該月最後一筆交易後的銀行餘額 vs 細帳
    by_row = {}
    for t in sorted(txs, key=lambda x: x.when):
        r = ledger_row_of(t)
        if r is None or t.balance is None:
            continue
        by_row.setdefault((r, f"{t.day:%Y-%m}"), {})[t.account + t.currency] = t.balance
    carry = {}
    for (row_no, month) in sorted(by_row, key=lambda k: (k[0], k[1])):
        acct = carry.setdefault(row_no, {})
        acct.update(by_row[(row_no, month)])
        c = cols.get(month)
        if c is None or row_no - 1 >= len(numbers) or c >= len(numbers[row_no - 1]):
            continue
        cur = _num(str(numbers[row_no - 1][c]))
        bank = sum(acct.values())
        if row_no in FX_ROWS.values() or row_no in SC_FX_ROWS.values():
            continue  # 外幣列含定存，用 bank-review 的外幣總覽核對
        if cur is not None and abs(cur - bank) >= 0.5:
            mark(row_no - 1, c, "balance", f"月底 細帳 {cur:,.0f}／銀行 {bank:,.0f}")
            listing.append([month, "", f"{row_no} {labels[row_no - 1]} 月底餘額", f"細帳 {cur:,.0f}／銀行 {bank:,.0f}", "⚠️", "月底餘額不同"])

    # 寫到副本：底色＋備註（保留原本的備註）
    reqs = []
    for cell, kind in marks.items():
        r, c = _rc(cell)
        reqs.append({"repeatCell": {"range": {"sheetId": copy.id, "startRowIndex": r, "endRowIndex": r + 1,
                                              "startColumnIndex": c, "endColumnIndex": c + 1},
                                    "cell": {"userEnteredFormat": {"backgroundColor": AUDIT_COLORS[kind]}},
                                    "fields": "userEnteredFormat.backgroundColor"}})
    if reqs:
        book.batch_update({"requests": reqs})
    old = copy.get_notes()
    merged = {}
    for cell, lines in notes.items():
        r, c = _rc(cell)
        existing = old[r][c] if r < len(old) and c < len(old[r]) else ""
        merged[cell] = "\n".join(x for x in ("【核對】" + "；".join(lines), existing.strip()) if x)
    if merged:
        _set_notes(copy, merged)

    # 清單分頁
    list_title = f"銀行核對清單{stamp:%m%d}"
    for ws in book.worksheets():
        if ws.title == list_title:
            book.del_worksheet(ws)
    lst = book.add_worksheet(list_title, rows=len(listing) + 10, cols=6)
    head = ["月份", "日期", "交易", "細帳情況", "結果", "依據"]
    body = sorted(listing, key=lambda x: (x[4] != "⚠️", x[0], x[1]))
    lst.update([head] + body, "A1", value_input_option="RAW")
    n_bad = sum(1 for x in listing if x[4] == "⚠️")
    print(f"核對 {len(entries)} 筆：有問題 {n_bad} 筆，標色 {len(marks)} 格")
    print(f"細帳副本（標色）：{title}")
    print(f"清單：{list_title}（有問題的排最上面）")
    print("顏色：黃＝另一邊沒記、橘＝帳戶列沒記、藍＝金額記在別列、紅＝月底跟銀行餘額不同")
    from .progress_log import log_run
    log_run("銀行明細全年核對", None, f"總帳「{title}」", [], message=f"{year} {'/'.join(banks)}｜核對 {len(entries)} 筆｜有問題 {n_bad} 筆")
    return f"https://docs.google.com/spreadsheets/d/{book.id}/edit#gid={copy.id}"
