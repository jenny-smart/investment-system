import sys
import types

import ledger_year as ly


def test_strip_entries_keeps_only_references():
    assert ly.strip_entries("=195+70+105+78") == ""
    assert ly.strip_entries("=1699*7+1597*9") == ""
    assert ly.strip_entries("1200") == ""
    assert ly.strip_entries("=B28+195+1200+680+2340") == "=B28"
    assert ly.strip_entries("=B38+C34+C37+C39+C119+2000000+250000-2250000-195") == "=B38+C34+C37+C39+C119"
    assert ly.strip_entries("=B43-C102+C116+130000+566-60000") == "=B43-C102+C116"
    assert ly.strip_entries("=SUM(C2:C23)") == "=SUM(C2:C23)"
    assert ly.strip_entries("=C26-C17-C18") == "=C26-C17-C18"
    assert ly.strip_entries("=-500+B3") == "=B3"
    assert ly.strip_entries("=B51") == "=B51"


def test_plan_values_rolls_header_b_column_and_months():
    prev = [
        ["2026", "2025-12", '=$A1&"-1"', '=$A1&"-02"'],
        ["零用金-餐費", "='2025細帳'!N2", "=195+70", "110", "", "", "", "", "", "", "", "", "", "", "=SUM(C2:N2)", "台幣"],
        ["富邦銀行", "='2025細帳'!N38", "=B38+C34+2000000-195", "=C38+D34"],
    ]
    out = ly.plan_values(prev, 2027)
    assert out[0][:4] == ["2027", "2026-12", '=$A1&"-1"', '=$A1&"-02"']
    assert out[1][1] == "='2026細帳'!N2" and out[1][2:14] == [""] * 12
    assert len(out[1]) == 14                      # O 欄以後（合計、試算）不寫
    assert out[2][1:4] == ["='2026細帳'!N38", "=B38+C34", "=C38+D34"]


def test_compatible_detects_old_template():
    new_labels = ["零用金-餐費", "零用金-食材", "富邦銀行", "郵局"]
    assert ly.compatible(["2027", "零用金-餐費", "零用金-食材", "富邦銀行", "郵局"], ["2026"] + new_labels)
    assert not ly.compatible(["2027", "food", "clothes", "富邦銀行", "郵局"], ["2026"] + new_labels)


class FakeWS:
    def __init__(self, title, labels, formulas=None, sid=1, index=0):
        self.title, self.labels, self.formulas, self.id, self.index = title, labels, formulas or [], sid, index
        self.row_count, self.updated, self.renamed = 1000, None, None

    def col_values(self, n):
        return self.labels

    def get(self, rng, value_render_option=None):
        return self.formulas

    def update_title(self, t):
        self.renamed = t

    def update(self, range_name, values, value_input_option):
        self.updated = (range_name, values)


class FakeBook:
    def __init__(self, sheets):
        self.sheets, self.requests = {s.title: s for s in sheets}, []

    def worksheet(self, title):
        if title not in self.sheets:
            raise sys.modules["gspread"].WorksheetNotFound(title)
        return self.sheets[title]

    def duplicate_sheet(self, sid, insert_sheet_index, new_sheet_name):
        ws = FakeWS(new_sheet_name, [], sid=99)
        self.sheets[new_sheet_name] = ws
        return ws

    def batch_update(self, body):
        self.requests.append(body)


def _gspread(monkeypatch):
    mod = types.ModuleType("gspread")

    class WorksheetNotFound(Exception):
        pass

    mod.WorksheetNotFound = WorksheetNotFound
    monkeypatch.setitem(sys.modules, "gspread", mod)


def test_ensure_renames_old_template_and_builds_new(monkeypatch):
    from datetime import date

    _gspread(monkeypatch)
    prev = FakeWS("2026細帳", ["2026", "零用金-餐費", "富邦銀行"],
                  [["2026", "2025-12"], ["零用金-餐費", "='2025細帳'!N2", "=10+5"]])
    old = FakeWS("2027細帳", ["2027", "food", "clothes"], sid=7)
    book = FakeBook([prev, old])
    ws = ly.ensure_ledger(book, 2027, log=lambda m: None, today=date(2026, 12, 25))
    assert old.renamed == "2027細帳_舊版20261225"
    assert ws.id == 99 and ws.updated[1][1][:3] == ["零用金-餐費", "='2026細帳'!N2", ""]
    assert book.requests[0]["requests"][0]["updateCells"]["fields"] == "note"


def test_ensure_keeps_compatible_existing(monkeypatch):
    _gspread(monkeypatch)
    prev = FakeWS("2026細帳", ["2026", "零用金-餐費"])
    cur = FakeWS("2027細帳", ["2027", "零用金-餐費"])
    book = FakeBook([prev, cur])
    assert ly.ensure_ledger(book, 2027, log=lambda m: None) is cur and cur.renamed is None
