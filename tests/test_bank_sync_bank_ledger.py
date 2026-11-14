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
    assert [(p.row, p.amount) for p in e["元大銀行-X"].postings] == [(54, 3000), (40, -3000)]
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
