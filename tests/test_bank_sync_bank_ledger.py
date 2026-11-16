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
    assert [(p.row, p.amount) for p in dunnan.postings] == [(90, 100), (125, 100)]  # 外幣列＝古亭＋敦南加總


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
        tx("taishin", "****867 古亭外幣綜存", "台新外幣", 9, -11772.86, "支出", "轉敦南", "南非幣"),
        tx("taishin", "****780 敦南外幣證券交割", "台新外幣", 9, -11773.76, "支出", "88872B0RC170", "南非幣", True),
        tx("taishin", "****867 古亭外幣綜存", "台新外幣", 3, 1234.5, "存入", "ABC1基金XX12345", "南非幣"),
        tx("taishin", "****867 古亭外幣綜存", "台新外幣", 4, 3.2, "存入", "INT202611", "美元"),
    ]
    got = {(e.tx.note, e.tx.day.day): e for e in classify(txs, RULES)}
    assert [(p.row, p.amount) for p in got[("基金配息 0056FUND", 11)].postings] == [(116, 8590)]
    assert [(p.row, p.amount) for p in got[("基金配息00740B", 12)].postings] == [(116, 360)]
    assert [(p.row, p.amount) for p in got[("信用卡款星展銀行", 10)].postings] == [(135, 4896)]
    assert [(p.row, p.amount) for p in got[("040750032867ZAR", 6)].postings] == [(92, -68643), (110, 68643)]
    assert got[("040750032867ZAR", 9)].skip and got[("轉敦南", 9)].skip  # 古亭⇄敦南互轉，加總不變
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


def test_mark_recorded_by_balance():
    from bank_sync.bank_ledger import mark_recorded, simulate
    def b(t, bal, when):
        t.balance, t.when = bal, when
        return t
    t1 = b(tx("fubon", "****990 (新店分行)", "富邦", 2, -100, "行動自轉", "早餐"), 900, "2026-11-02 08:00")
    t2 = b(tx("fubon", "****990 (新店分行)", "富邦", 4, 1000, "網路自轉", "11月LINE"), 1900, "2026-11-04 09:00")
    t3 = b(tx("fubon", "****871 (營業部)", "富邦", 10, 500, "行動自轉", "某某"), 500, "2026-11-10 15:00")
    labels = [""] * 60
    labels[37], labels[1] = "富邦", "零用金-餐費"
    numbers = [[""] * 13 for _ in range(60)]
    numbers[37][11] = 1900          # 你已經記到 11/04 那筆
    formulas = [[""] * 13 for _ in range(60)]
    formulas[37][11] = "=1000-100+1000"
    entries = classify([t1, t2, t3], RULES)
    assert mark_recorded(entries, [t1, t2, t3], numbers, labels, {"2026-11": 11}) == 2
    assert [e.skip for e in entries] == [True, True, False]
    rows = simulate(entries, [t1, t2, t3], formulas, numbers, labels, {"2026-11": 11})
    got = {r[0]: r for r in rows[1:]}
    assert got[38][4] == 2400 and got[38][5] == 2400 and got[38][8] == "✓ 相符"


def test_mark_recorded_fx_time_deposit():
    from bank_sync.bank_ledger import mark_recorded
    def b(t, bal, when):
        t.balance, t.when = bal, when
        return t
    g = b(tx("taishin", "****867 古亭外幣綜存", "台新外幣", 5, -1000, "支出", "轉出", "南非幣"), 0, "2026-11-05 10:00")
    d_in = b(tx("taishin", "****313 敦南Richart外幣綜存", "台新外幣", 5, 1000, "存入", "古亭", "南非幣", True), 1000, "2026-11-05 10:01")
    d_td = b(tx("taishin", "****313 敦南Richart外幣綜存", "台新外幣", 9, -1000, "支出", "88872B0RC170", "南非幣", True), 0, "2026-11-09 10:00")
    labels = [""] * 100
    numbers = [[""] * 13 for _ in range(100)]
    numbers[91][11] = 1000  # 細帳 92 列：古亭＋敦南＋定存本金
    entries = classify([g, d_in, d_td], RULES)
    mark_recorded(entries, [g, d_in, d_td], numbers, labels, {"2026-11": 11})
    assert all("已記過" in e.reason for e in entries)


def test_sc_rules_and_fubon_default():
    from bank_sync.bank_ledger import _to_tx
    blk = {"type": "FX", "account": "渣打外幣 美元", "currency": "美元", "ledger_row": "渣打"}
    head = ["交易時間", "金額", "餘額", "摘要說明"]
    t1 = _to_tx("sc", blk, head, ["2026/11/12", "$1,200.00", "$5,000.00", "大華基金配息"])
    t2 = _to_tx("sc", blk, head, ["2026/11/06", "$300.00", "$3,800.00", "基金配息"])
    t3 = _to_tx("sc", blk, head, ["2026/11/07", "$2.10", "$3,802.10", "存款利息"])
    t4 = _to_tx("sc", blk, head, ["2026/11/08", "-$1,000.00", "$2,802.10", "基金申購扣款"])
    f = tx("fubon", "****990 (新店分行)", "富邦", 3, -900, "行動自轉", "某某代付")
    got = {e.tx.note: e for e in classify([t1, t2, t3, t4, f], RULES)}
    assert [(p.row, p.amount) for p in got["大華基金配息"].postings] == [(88, 1200), ("配息-渣打-大華", 1200)]
    assert [(p.row, p.amount) for p in got["基金配息"].postings] == [(88, 300), (123, 300)]
    assert [(p.row, p.amount) for p in got["存款利息"].postings] == [(88, 2.1)]
    assert [(p.row, p.amount) for p in got["基金申購扣款"].postings] == [(88, -1000), (107, 1000)]
    assert [(p.row, p.amount) for p in got["某某代付"].postings] == [(38, -900), ("零用金-代墊", 900)]
    # 配息列公式會加進渣打美金那列 → 寫入時只記配息列
    labels = [""] * 140
    labels[122] = "配息-渣打-美金"
    formulas = [[""] * 13 for _ in range(140)]
    formulas[87][11] = "=K88+L123"
    values, notes, errors = plan_cells([got["基金配息"]], formulas, labels, {"2026-11": 11}, date(2026, 11, 15))
    assert values == {"L123": "=300"} and errors == []


def test_fubon_reimbursement_matches_card():
    charges = [("sc", date(2026, 10, 20), "彭園餐廳", 2300, "零用金-公司代墊"),
               ("taishin", date(2026, 10, 25), "星全安", 700, "零用金-公司代墊"),
               ("dbs", date(2026, 10, 1), "早餐店", 80, "零用金-餐費")]
    one = tx("fubon", "****871 (營業部)", "富邦", 4, 2300, "跨行轉入", "某公司")
    two = tx("fubon", "****871 (營業部)", "富邦", 5, 3000, "跨行轉入", "某公司B")
    got = {e.tx.note: e for e in classify([one, two], RULES, charges=charges)}
    assert "彭園" in got["某公司"].reason and "請確認" in got["某公司"].reason
    assert "星全安" in got["某公司B"].reason and "彭園" in got["某公司B"].reason  # 兩筆加起來 3000
    assert [(p.row, p.amount) for p in got["某公司"].postings] == [(38, 2300), ("零用金-公司代墊", -2300)]


def test_insurance_rebate_only_row_127():
    a = tx("taishin", "****273 敦南Richart二類帳戶", "台新-Richard", 7, 60000, "跨行轉入", "新光人壽保險")
    b = tx("taishin", "****159 建北綜活儲存款", "台新-建北", 9, 135660, "跨行轉入", "國泰人壽 生存金")
    c = tx("taishin", "****273 敦南Richart二類帳戶", "台新-Richard", 7, 61000, "跨行轉入", "新光人壽保險")
    got = classify([a, b, c], RULES)
    assert [(p.row, p.amount) for p in got[0].postings] == [(127, 60000)] and "請確認" not in got[0].reason
    assert [(p.row, p.amount) for p in got[1].postings] == [(127, 135660)]
    assert "請確認" in got[2].reason


class AuditWS:
    def __init__(self, title, shown, formulas, numbers, wid=1, index=0):
        self.title, self.shown, self.formulas, self.numbers = title, shown, formulas, numbers
        self.id, self.index, self.notes, self.rows = wid, index, {}, None

    def get_values(self, value_render_option=None):
        return {"FORMULA": self.formulas, "UNFORMATTED_VALUE": self.numbers}.get(value_render_option, self.shown)

    def get_notes(self):
        return [[""] * 13 for _ in range(len(self.shown))]

    def update_notes(self, notes):
        self.notes.update(notes)

    def update(self, rows, a1, value_input_option=None):
        self.rows = rows


class AuditBook:
    id = "BOOK"

    def __init__(self, ws):
        self.sheets, self.reqs = [ws], []

    def worksheet(self, title):
        return next(w for w in self.sheets if w.title == title)

    def worksheets(self):
        return list(self.sheets)

    def del_worksheet(self, ws):
        self.sheets.remove(ws)

    def duplicate_sheet(self, sid, insert_sheet_index, new_sheet_name):
        src = self.sheets[0]
        w = AuditWS(new_sheet_name, src.shown, src.formulas, src.numbers, wid=99)
        self.sheets.append(w)
        return w

    def add_worksheet(self, title, rows, cols):
        w = AuditWS(title, [], [], [], wid=100)
        self.sheets.append(w)
        return w

    def batch_update(self, body):
        self.reqs += body["requests"]


def test_audit_marks_missing(monkeypatch):
    import bank_sync.bank_ledger as bl
    shown = [[""] * 13 for _ in range(60)]
    shown[0] = ["2026"] + [f"2026-{m:02d}" for m in range(1, 13)]
    shown[37][0], shown[1][0], shown[21][0] = "富邦", "零用金-餐費", "零用金-代墊"
    formulas = [r[:] for r in shown]
    numbers = [[""] * 13 for _ in range(60)]
    formulas[37][11], numbers[37][11] = "=1000-100-200", 700     # 兩筆支出都記了
    formulas[1][11] = "=100"                                       # 早餐有記到餐費
    a = tx("fubon", "****990 (新店分行)", "富邦", 2, -100, "行動自轉", "早餐")
    b = tx("fubon", "****990 (新店分行)", "富邦", 3, -200, "行動自轉", "不明款")
    a.balance, a.when, b.balance, b.when = 900, "2026-11-02 08:00", 700, "2026-11-03 08:00"
    book = AuditBook(AuditWS("2026細帳", shown, formulas, numbers))
    monkeypatch.setattr(bl, "load_transactions", lambda: ([a, b], []))
    monkeypatch.setattr(bl, "card_charges", lambda y: [])
    monkeypatch.setattr(bl, "open_book", lambda c: book)
    monkeypatch.setattr("bank_sync.google_auth.credentials", lambda: None)
    monkeypatch.setattr("bank_sync.progress_log.log_run", lambda *a, **k: None)
    bl.audit(2026, ("fubon",))
    copy = book.sheets[1]
    assert "L22" in copy.notes and "不明款" in copy.notes["L22"]   # 代墊那列沒記 → 標黃
    assert "L2" not in copy.notes and "L38" not in copy.notes      # 已記、餘額相符 → 不標
    assert len(book.reqs) == 1


def test_taishin_detail_layout():
    from bank_sync.bank_ledger import _to_tx
    head = ["交易日", "帳務日", "摘要", "詳細", "", "金額", "餘額", "備註"]
    blk = {"type": "TWD", "account": "****273 敦南Richart二類帳戶", "ledger_row": "台新-Richard"}
    t = _to_tx("taishin", blk, head, ["2026/11/13 10:00:00", "2026/11/13", "CD轉出", "金額 -60,000 餘額 91,418 備註 轉帳812-1 Ｕｎｃｌｅ", "交易明細"])
    assert t.amount == -60000 and t.balance == 91418 and "Ｕｎｃｌｅ" in t.note
    fx_head = ["交易日", "帳務日", "幣別", "摘要", "金額", "詳細", "餘額", "轉換金額", "交易匯率", "備註"]
    fblk = {"type": "FX", "account": "****867 古亭外幣綜存", "ledger_row": "台新外幣各幣別列（全部）"}
    f = _to_tx("taishin", fblk, fx_head, ["2026/11/10 10:00", "2026/11/10", "南非幣", "存入", "123.45", "餘額 999.99 轉換金額 交易匯率 備註 ABC1基金XX123"])
    assert f.amount == 123.45 and f.balance == 999.99 and f.note == "ABC1基金XX123"


def test_stock_money_rows():
    a = tx("taishin", "****159 建北綜活儲存款", "台新-建北", 3, -20, "轉帳", "抽籤處理費")
    b = tx("taishin", "****159 建北綜活儲存款", "台新-建北", 4, -150000, "證券交割", "買進")
    c = tx("taishin", "****159 建北綜活儲存款", "台新-建北", 5, 300000, "證券交割", "賣出")
    got = classify([a, b, c], RULES)
    assert [(p.row, p.amount) for p in got[0].postings] == [(43, -20), ("台股-新資金", 20)]
    assert [(p.row, p.amount) for p in got[1].postings] == [(43, -150000), ("台股-新資金", 150000)]
    assert [(p.row, p.amount) for p in got[2].postings] == [(43, 300000), ("台股-舊資金", -300000)]


def test_publish_bank_rows(monkeypatch):
    import bank_sync.bank_ledger as bl
    from bank_sync.publish import bank_rows
    shown = [[""] * 13 for _ in range(60)]
    shown[0] = ["2026"] + [f"2026-{m:02d}" for m in range(1, 13)]
    shown[37][0], shown[1][0] = "富邦", "零用金-餐費"
    a = tx("fubon", "****990 (新店分行)", "富邦", 2, -100, "行動自轉", "早餐")
    book = AuditBook(AuditWS("2026細帳", shown, [r[:] for r in shown], [[""] * 13 for _ in range(60)]))
    monkeypatch.setattr(bl, "load_transactions", lambda: ([a], []))
    monkeypatch.setattr(bl, "card_charges", lambda y: [])
    monkeypatch.setattr(bl, "load_applied", lambda: set())
    rows = bank_rows(2026, book)
    assert rows[0] == ["日期", "銀行", "帳戶", "摘要", "收入", "支出", "餘額", "備註", "銀行（細帳）", "其他", "依據", "狀態"]
    assert rows[1][:6] == ["11/02", "富邦", "台幣 新店分行", "行動自轉", "", 100]
    assert rows[1][8] == "富邦:-100" and rows[1][9] == "零用金-餐費 +100" and rows[1][11] == "待寫入"


def test_load_dedupes_layout_variants(tmp_path, monkeypatch):
    import json
    import bank_sync.bank_ledger as bl
    monkeypatch.setattr(bl, "TX_ROOT", tmp_path)
    (tmp_path / "taishin").mkdir()
    blk = {"type": "TWD", "account": "****273 敦南Richart二類帳戶", "ledger_row": "台新-Richard"}
    a = dict(blk, head=["交易日", "帳務日", "摘要", "金額", "餘額", "備註", ""],
             rows=[["2026/11/13 11:05:00", "2026/11/13", "CD轉出", "-60,000", "91,418", "", "交易明細"]])
    b = dict(blk, head=["交易日", "帳務日", "摘要", "詳細", "", "金額", "餘額", "備註"],
             rows=[["2026/11/13 11:05:00", "2026/11/13", "CD轉出", "金額 -60,000 餘額 91,418 備註 網路跨行 Ｕｎｃｌｅ", "交易明細"]])
    (tmp_path / "taishin" / "20261115_1540.json").write_text(json.dumps({"accounts": [b]}), "utf-8")
    (tmp_path / "taishin" / "20261115_1523.json").write_text(json.dumps({"accounts": [a]}), "utf-8")
    txs, _ = bl.load_transactions()
    assert len(txs) == 1 and "Ｕｎｃｌｅ" in txs[0].note


def test_fx_bond_fund_buy():
    t = tx("taishin", "****867 古亭外幣綜存", "台新外幣", 6, -91066, "支出", "IYA5 高盛新興債 FY040000581", "南非幣")
    e = classify([t], RULES)[0]
    assert [(p.row, p.amount) for p in e.postings] == [(92, -91066), (110, 91066)]


def test_post_csv_and_ledger():
    from bank_sync.bank_ledger import _to_tx
    from bank_sync.post_tx import HEAD, parse_csv
    raw = ("帳號,00012345\n交易日期 交易時間,摘要,沖銷記號,提款金額,存款金額,結存金額,備註,附言\n"
           "115/11/05 10:21:33,跨行轉,,500,,1500,轉帳,\n115/11/06 09:00:00,利息,,,3,1503,,\n").encode("big5")
    rows = parse_csv(raw)
    assert rows[0][:2] == ["2026/11/05", "10:21:33"]
    t = _to_tx("post", {"account": "郵局存簿", "ledger_row": "郵局"}, HEAD, rows[0])
    assert t.amount == -500 and t.balance == 1500 and t.when == "2026-11-05 10:21:33"
    e = classify([_to_tx("post", {"account": "郵局存簿", "ledger_row": "郵局"}, HEAD, rows[1])], RULES)[0]
    assert [(p.row, p.amount) for p in e.postings] == [(42, 3)]
