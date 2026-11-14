from datetime import date

from bank_sync.bank_ledger import Tx, classify, plan_cells


def tx(bank, account, ledger, d, amount, summary, note, cur="TWD", interest_only=False):
    return Tx(bank, account, ledger, date(2026, 11, d), amount, cur, summary, note,
              f"{bank}|{account}|{d}|{amount}|{note}", interest_only)


RULES = [("早餐", "零用金-餐費")]


def by_note(entries):
    return {e.tx.note: e for e in entries}


def test_classify_rules():
    txs = [
        tx("fubon", "****990 (新店分行)", "富邦", 2, -100, "行動自轉", "測試早餐 新店分行"),
        tx("fubon", "****990 (新店分行)", "富邦", 4, 1000, "網路自轉", "11月LINE 松高分行"),
        tx("fubon", "****990 (新店分行)", "富邦", 10, 5000, "集保基金", "配息新興國家 信義分行"),
        tx("fubon", "****990 (新店分行)", "富邦", 10, -7000, "行動自轉", "A 新店分行"),
        tx("fubon", "****871 (營業部)", "富邦", 10, 7000, "行動自轉", "B 新店分行"),
        tx("fubon", "****871 (營業部)", "富邦", 10, -7000, "行動跨轉", "C 營業部"),
        tx("next", "將來主帳戶", "將來", 10, 7000, "轉入", "台北富邦-X"),
        tx("next", "將來主帳戶", "將來", 5, 3000, "轉入", "元大銀行-X"),
        tx("next", "將來主帳戶", "將來", 6, -50, "轉出", "uncle 借款"),
        tx("taishin", "****867 古亭外幣綜存", "台新外幣", 7, 12.5, "利息", "存款息", "南非幣"),
        tx("taishin", "****867 古亭外幣綜存", "台新外幣", 8, 300, "配息", "基金", "南非幣"),
        tx("taishin", "****313 敦南Richart外幣綜存", "台新外幣", 8, 100, "轉入", "", "美元", True),
        tx("fubon", "****990 (新店分行)", "富邦", 12, -20000, "行動自轉", "新興邊境 申購"),
    ]
    e = by_note(classify(txs, RULES))
    assert [(p.row, p.amount) for p in e["測試早餐 新店分行"].postings] == [(38, -100), ("零用金-餐費", 100)]
    assert [(p.row, p.amount) for p in e["11月LINE 松高分行"].postings] == [(38, 1000), ("零用金-代墊", -1000)]
    assert [(p.row, p.amount) for p in e["配息新興國家 信義分行"].postings] == [(38, 5000), (119, 5000)]
    assert e["A 新店分行"].skip and e["B 新店分行"].skip  # 富邦內部互轉相抵
    assert [(p.row, p.amount) for p in e["C 營業部"].postings] == [(38, -7000)]
    assert [(p.row, p.amount) for p in e["台北富邦-X"].postings] == [(54, 7000)]
    assert [(p.row, p.amount) for p in e["元大銀行-X"].postings] == [(54, 3000)]  # 元大也自動抓了：各記各的
    assert [(p.row, p.amount) for p in e["uncle 借款"].postings] == [(54, -50), (95, 50)]
    assert [(p.row, p.amount) for p in e["存款息"].postings] == [(92, 12.5)]  # 外幣利息只加幣別列
    assert [(p.row, p.amount) for p in e["基金"].postings] == [(92, 300), (126, 300)]
    assert [(p.row, p.amount) for p in e["新興邊境 申購"].postings] == [(38, -20000), (105, 20000)]
    dunnan = [x for x in classify(txs, RULES) if x.tx.currency == "美元"][0]
    assert dunnan.skip


def test_plan_cells_appends_terms():
    labels = [""] * 60
    labels[37] = "富邦"
    labels[1] = "零用金-餐費"
    formulas = [[""] * 13 for _ in range(60)]
    formulas[37][11] = "=1000"
    entries = classify([tx("fubon", "****990 (新店分行)", "富邦", 2, -100, "行動自轉", "測試早餐")], RULES)
    values, notes, errors = plan_cells(entries, formulas, labels, {"2026-11": 11}, date(2026, 11, 14))
    assert errors == []
    assert values == {"L38": "=1000-100", "L2": "=100"}
    assert "測試早餐" in notes["L38"][0]


def test_fullwidth_uncle_and_linebank_interest():
    from bank_sync.bank_ledger import _to_tx
    e = classify([tx("taishin", "****273 敦南Richart二類帳戶", "台新-Richard", 3, -500, "CD轉出", "轉帳 Ｕｎｃｌｅ")], RULES)[0]
    assert [(p.row, p.amount) for p in e.postings] == [(47, -500), (95, 500)]
    blk = {"account": "主帳戶 ****612", "ledger_row": "連線"}
    row = ["整列 2026年11月8日", "整列", "2026年11月8日 02:03", "20261108-1.25%", "存入 NT$12"]
    t = _to_tx("linebank", blk, ["日期", "時間", "摘要", "金額"], row)
    assert t.amount == 12 and t.summary.startswith("利息")
    e = classify([t], RULES)[0]
    assert [(p.row, p.amount) for p in e.postings] == [(52, 12), (53, 12)]


class FakeWS:
    def __init__(self, rows=None):
        self.rows, self.id, self.row_count = rows or [], 7, 100

    def get_values(self):
        return self.rows

    def clear(self):
        self.rows = []

    def add_rows(self, n):
        self.row_count += n

    def update(self, rows, a1, value_input_option=None):
        self.rows = rows


class FakeBook:
    id = "BOOK"

    def __init__(self):
        self.ws = None

    def worksheet(self, title):
        if self.ws is None:
            raise KeyError(title)
        return self.ws

    def add_worksheet(self, title, rows, cols):
        self.ws = FakeWS()
        return self.ws

    def batch_update(self, body):
        self.reqs = body


def test_review_sheet_roundtrip():
    from bank_sync.bank_ledger import apply_review, read_review, write_review
    txs = [tx("fubon", "****990 (新店分行)", "富邦", 2, -100, "行動自轉", "不認得的店"),
           tx("fubon", "****990 (新店分行)", "富邦", 3, -80, "行動自轉", "早餐店")]
    entries = classify(txs, RULES)
    book = FakeBook()
    url = write_review(book, entries, ["x"] * 60, {})
    assert url.endswith("gid=7")
    rows = book.ws.rows
    assert rows[1][0].startswith("⚠️") and rows[1][6] == "不認得的店"  # 要確認的排最上面
    rows[1][10] = "零用金-用品"  # 你改記到
    answers = read_review(book)
    applied = apply_review(classify(txs, RULES), answers)
    first = [e for e in applied if e.tx.note == "不認得的店"][0]
    assert [(p.row, p.amount) for p in first.postings] == [(38, -100), ("零用金-用品", 100)]
    # 沒填答案的待確認項目 → 這次不寫
    pending = apply_review(classify(txs, RULES), {})
    waiting = [e for e in pending if e.tx.note == "不認得的店"][0]
    assert waiting.skip and waiting.waiting


def test_rules_from_review_feedback():
    txs = [
        tx("taishin", "****159 建北綜活儲存款", "台新-建北", 11, 8590, "授權轉入", "基金配息 0056FUND"),
        tx("taishin", "****159 建北綜活儲存款", "台新-建北", 12, 360, "授權轉入", "基金配息00740B"),
        tx("taishin", "****273 敦南Richart二類帳戶", "台新-Richard", 10, -4896, "媒體轉出", "信用卡款星展銀行"),
        tx("taishin", "****780 敦南外幣證券交割", "台新外幣", 6, -68643, "支出", "040750032867ZAR", "南非幣", True),
        tx("taishin", "****780 敦南外幣證券交割", "台新外幣", 9, 11772.86, "存入", "040750032867ZAR", "南非幣", True),
        tx("taishin", "****780 敦南外幣證券交割", "台新外幣", 9, -11773.76, "支出", "88872B0RC170", "南非幣", True),
        tx("taishin", "****867 古亭外幣綜存", "台新外幣", 3, 1234.5, "存入", "ABC1基金XX12345", "南非幣"),
        tx("taishin", "****867 古亭外幣綜存", "台新外幣", 4, 3.2, "存入", "INT202611", "美元"),
    ]
    got = {(e.tx.note, e.tx.day.day): e for e in classify(txs, RULES)}
    assert [(p.row, p.amount) for p in got[("基金配息 0056FUND", 11)].postings] == [(116, 8590)]
    assert [(p.row, p.amount) for p in got[("基金配息00740B", 12)].postings] == [(116, 360)]
    assert [(p.row, p.amount) for p in got[("信用卡款星展銀行", 10)].postings] == [(135, 4896)]
    assert [(p.row, p.amount) for p in got[("040750032867ZAR", 6)].postings] == [(110, 68643)]
    assert got[("040750032867ZAR", 9)].skip
    td = got[("88872B0RC170", 9)]
    assert [(p.row, p.note_only) for p in td.postings] == [(92, True)]
    assert [(p.row, p.amount) for p in got[("ABC1基金XX12345", 3)].postings] == [(92, 1234.5), (126, 1234.5)]
    assert [(p.row, p.amount) for p in got[("INT202611", 4)].postings] == [(90, 3.2)]


def test_plan_cells_note_only_and_linked_formula():
    labels = [""] * 130
    formulas = [[""] * 13 for _ in range(130)]
    formulas[37][11] = "=1000+L119"  # 富邦 38 列公式已引用 119
    e1 = classify([tx("fubon", "****990 (新店分行)", "富邦", 10, 5000, "集保基金", "配息新興國家")], RULES)
    td = classify([tx("taishin", "****780 敦南外幣證券交割", "台新外幣", 9, -11773.76, "支出", "88872B0RC170", "南非幣", True)], RULES)
    values, notes, errors = plan_cells(e1 + td, formulas, labels, {"2026-11": 11}, date(2026, 11, 14))
    assert errors == []
    assert values == {"L119": "=5000"}  # 38 列公式已帶入 119，不重複加；定存只加備註
    assert "L38" not in values and "只記備註" in notes["L92"][0]


def test_mark_existing_and_dedupe(tmp_path, monkeypatch):
    import json
    import bank_sync.bank_ledger as bl
    labels = [""] * 130
    formulas = [[""] * 13 for _ in range(130)]
    formulas[115][11] = "=1200+8590"
    entries = classify([tx("taishin", "****159 建北綜活儲存款", "台新-建北", 11, 8590, "授權轉入", "基金配息 0056FUND")], RULES)
    assert bl.mark_existing(entries, formulas, labels, {"2026-11": 11}) == 1
    assert bl.needs_check(entries[0])
    # 早期檔案把同一筆算在兩個帳戶：只留一筆（以同檔較後面的帳戶為準）
    monkeypatch.setattr(bl, "TX_ROOT", tmp_path)
    (tmp_path / "taishin").mkdir()
    row = ["2026/11/09 10:00", "2026/11/09", "南非幣", "存入", "100.00", "100.00", "", "", "X1"]
    head = ["交易日", "帳務日", "幣別", "摘要", "金額", "餘額", "轉換金額", "交易匯率", "備註"]
    blocks = [{"type": "FX", "account": "****780 敦南外幣證券交割", "ledger_row": "台新外幣各幣別列（只取利息）", "head": head, "rows": [row]},
              {"type": "FX", "account": "****313 敦南Richart外幣綜存", "ledger_row": "台新外幣各幣別列（只取利息）", "head": head, "rows": [row]}]
    (tmp_path / "taishin" / "20261114_2146.json").write_text(json.dumps({"accounts": blocks}), "utf-8")
    txs, _ = bl.load_transactions()
    assert [t.account for t in txs] == ["****313 敦南Richart外幣綜存"]


def test_simulate_balance_check():
    from bank_sync.bank_ledger import simulate
    labels = [""] * 140
    labels[42], labels[46] = "台新-建北", "台新-Richard"
    formulas = [[""] * 13 for _ in range(140)]
    numbers = [[""] * 13 for _ in range(140)]
    formulas[42][11], numbers[42][11] = "=K43+L116", 10000     # 建北公式含 116
    formulas[46][11], numbers[46][11] = "=K47-L135+500", 20000  # Richard 公式減 135（卡費）
    t1 = tx("taishin", "****159 建北綜活儲存款", "台新-建北", 11, 8590, "授權轉入", "基金配息 0056FUND")
    t1.balance, t1.when = 18590, "2026-11-11 10:00"
    t2 = tx("taishin", "****273 敦南Richart二類帳戶", "台新-Richard", 10, -4896, "媒體轉出", "信用卡款星展銀行")
    t2.balance, t2.when = 15000, "2026-11-10 09:00"   # 銀行是 15,104 才對 → 故意差 104
    entries = classify([t1, t2], RULES)
    rows = simulate(entries, [t1, t2], formulas, numbers, labels, {"2026-11": 11})
    got = {r[0]: r for r in rows[1:]}
    assert got[43][4] == 18590 and got[43][8] == "✓ 相符"         # 只記 116，43 透過公式 +8590
    assert got[47][4] == 15104 and got[47][8] == "⚠️ 不相符"      # 47 透過公式 −4896
