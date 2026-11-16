"""把本機已下載的銀行明細、信用卡帳單明細整理好，寫進總帳的「銀行明細」「信用卡明細」分頁，讓 App 網頁可以看。

每筆後面加：記到細帳哪一列＋正負金額（例「38 富邦：-100；零用金-餐費：+100」）、依據、狀態。
帳號只留末 3 碼。寫入用本機 google-login 的授權；只在你的 Mac 執行。
"""
from __future__ import annotations

from datetime import datetime

BANK_TITLE = "銀行明細"
CARD_TITLE = "信用卡明細"
BANK_HEAD = ["日期", "銀行", "帳戶", "摘要", "收入", "支出", "餘額", "備註", "銀行（細帳）", "其他", "依據", "狀態"]


def account_label(t) -> str:
    """「****159 建北綜活儲存款」→「台幣 建北綜活儲存款」；「****990 (新店分行)」→「台幣 新店分行」。"""
    import re
    name = re.sub(r"\*{2,}\d*", "", t.account or "").replace("(", " ").replace(")", " ")
    name = re.sub(r"\s+", " ", name).strip() or t.account
    kind = "台幣" if t.currency == "TWD" else f"外幣{t.currency}"
    return f"{kind} {name}"
CARD_HEAD = ["帳單月份", "卡別", "消費日", "店名", "金額（＋消費／−退款）", "零用金分類",
             "記到細帳（列：正負金額）", "狀態"]
WHO = {"fubon": "富邦", "next": "將來", "taishin": "台新", "yuanta": "元大", "linebank": "LINE Bank", "sc": "渣打", "post": "郵局"}


def _write(book, title: str, rows: list[list]) -> str:
    try:
        ws = book.worksheet(title)
    except Exception:
        ws = book.add_worksheet(title, rows=len(rows) + 50, cols=len(rows[0]))
    ws.clear()
    if ws.row_count < len(rows) + 10:
        ws.add_rows(len(rows) + 10 - ws.row_count)
    ws.update(rows, "A1", value_input_option="RAW")
    try:
        book.batch_update({"requests": [
            {"updateSheetProperties": {"properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": 1}},
                                       "fields": "gridProperties.frozenRowCount"}},
            {"repeatCell": {"range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1},
                            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                            "fields": "userEnteredFormat.textFormat.bold"}}]})
    except Exception:
        pass
    return f"https://docs.google.com/spreadsheets/d/{book.id}/edit#gid={ws.id}"


def _split_postings(e, labels: list) -> tuple[str, str]:
    """→ (銀行那邊「富邦:-115」, 其他「零用金-餐費 +115；119 配息-基富通-台 +97,292」)。只記備註的寫「備註」。"""
    from .bank_ledger import ACCOUNT_ROWS, FX_ROWS, SC_FX_ROWS
    names = {row: name for name, (row, _, _) in ACCOUNT_ROWS.items()}
    names.update({row: f"台新{cur}" for cur, row in FX_ROWS.items()})
    names.update({row: f"渣打{cur}" for cur, row in SC_FX_ROWS.items()})
    if e.skip:
        return "", ""
    fmt = lambda a: f"{a:+,.2f}".replace(".00", "")
    bank, other = [], []
    for p in e.postings:
        if isinstance(p.row, int) and p.row in names:
            bank.append(f"{names[p.row]}:" + ("備註" if p.note_only else fmt(p.amount)))
        else:
            label = p.row if isinstance(p.row, str) else f"{p.row} {labels[p.row - 1] if p.row - 1 < len(labels) else ''}".strip()
            other.append(f"{label} " + ("備註" if p.note_only else fmt(p.amount)))
    return "；".join(bank), "；".join(other)


def bank_rows(year: int, book) -> list[list]:
    from .bank_ledger import (_describe, card_charges, classify, load_applied, load_transactions,
                              mark_existing, mark_recorded, needs_check)
    from .ledger_sync import month_columns
    txs, _ = load_transactions()
    txs = [t for t in txs if t.day.year == year]
    entries = classify(txs, charges=card_charges(year))
    detail = book.worksheet(f"{year}細帳")
    shown = detail.get_values()
    labels = [r[0] if r else "" for r in shown]
    cols = month_columns(shown[0] if shown else [])
    mark_recorded(entries, txs, detail.get_values(value_render_option="UNFORMATTED_VALUE"), labels, cols)
    mark_existing(entries, detail.get_values(value_render_option="FORMULA"), labels, cols)
    applied = load_applied()
    rows = [BANK_HEAD]
    for e in sorted(entries, key=lambda x: (x.tx.day, x.tx.when), reverse=True):
        t = e.tx
        if t.key in applied:
            state = "已寫入細帳"
        elif "已記過（細帳" in e.reason:
            state = "細帳已有"
        elif e.skip:
            state = "略過"
        elif needs_check(e):
            state = "待確認"
        else:
            state = "待寫入"
        bank_part, other_part = _split_postings(e, labels)
        money = (lambda x: round(x, 2) if t.currency != "TWD" else int(round(x)))
        rows.append([f"{t.day:%m/%d}", WHO.get(t.bank, t.bank), account_label(t), t.summary + ("" if t.currency == "TWD" else f"（{t.currency}）"),
                     money(t.amount) if t.amount > 0 else "", money(-t.amount) if t.amount < 0 else "",
                     "" if t.balance is None else t.balance, t.note, bank_part, other_part, e.reason, state])
    return rows


def card_rows(year: int) -> list[list]:
    from .ledger_sync import BANK_NAME, CARD_ROW_PREFIX, block_label, categorize, load_rules, parsed_statements
    rules = load_rules()
    rows = [CARD_HEAD]
    items = []
    for f in parsed_statements(year):
        st = f.statement
        for c in st.purchases:
            cat, why = categorize(c.description, rules)
            block = block_label(cat)
            items.append([st.ledger_month, BANK_NAME.get(f.bank, f.bank), c.day.isoformat(), c.description, c.amount, cat,
                          f"{block}：{c.amount:+,}（含信用卡表）；{CARD_ROW_PREFIX.get(f.bank, '')}：備註",
                          "待分類" if cat == "零用金-其他" else why])
    items.sort(key=lambda r: (r[0], r[2]), reverse=True)
    return rows + items


def publish(year: int) -> None:
    from .google_auth import credentials
    from .ledger_sync import open_book
    book = open_book(credentials())
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    b = bank_rows(year, book)
    print(f"銀行明細 {len(b) - 1} 筆 → {_write(book, BANK_TITLE, b)}")
    try:
        c = card_rows(year)
        print(f"信用卡明細 {len(c) - 1} 筆 → {_write(book, CARD_TITLE, c)}")
    except Exception as exc:
        print(f"⚠️ 信用卡明細沒寫成：{exc}")
    print(f"（{stamp} 更新；App 的「銀行明細」「信用卡」頁會讀這兩個分頁）")
