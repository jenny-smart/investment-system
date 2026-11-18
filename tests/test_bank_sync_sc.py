import builtins
import json
import unittest
from datetime import date
from unittest import mock

from bank_sync import sc_tx


class FakePage:
    """模擬渣打頁面：外幣活存（兩個帳戶各一張幣別表）↔ 外幣明細頁；外幣定存分頁。"""

    def __init__(self, tables):
        self.tables = tables  # [(標題, [[幣別, 最近交易日期], …]), …]
        self.url = "https://x/scb/accOverview"
        self.page = "overview"
        self.clicked = []

    def eval(self, js):
        if js == "history.back()":
            self.url, self.page = "https://x/scb/accOverview/savingForeign", "fx"
            return None
        if "const [ti, i] =" in js:
            ti, i = json.loads(js.split("const [ti, i] = ")[1].split(";")[0])
            label, rows = self.tables[ti]
            self.clicked.append(f"{label}|{rows[i][0]}")
            self.url, self.page = "https://x/scb/accOverview/savingForeignDetails", "detail"
            return "ok"
        if "out.push([ti, i, cur" in js:
            if self.page != "fx":
                return "[]"
            return json.dumps([[ti, i, r[0], r[1], label] for ti, (label, rows) in enumerate(self.tables)
                               for i, r in enumerate(rows)])
        if "all('select')" in js:
            return "[]"
        if "tables: out" in js:
            return json.dumps({"tables": [{"head": ["幣別", "本金"], "rows": [["USD", "1,000"]]}], "nodata": False}) \
                if self.page == "fd" else json.dumps({"tables": [], "nodata": False})
        if "location.href" in js:
            return self.url
        if "const names" in js:
            if '"外幣活存"' in js:
                self.page = "fx"
                return "外幣活存"
            if '"外幣定存"' in js:
                self.page = "fd"
                return "外幣定存"
            return ""
        return ""


TABLES = [("敦化分行 外幣活存帳戶 11305●●●●●8908", [["美金 USD", "2026/11/12"], ["南非幣 ZAR", "2026/11/06"]]),
          ("古亭分行 外幣活存帳戶 22222●●●●●1234", [["日圓 JPY", "2018/07/19"]])]


class ScFxTest(unittest.TestCase):
    def test_currency_code_and_account_name(self):
        self.assertEqual(sc_tx._currency_code("美金 USD"), "USD")
        self.assertEqual(sc_tx._currency_code("人民幣CNY"), "CNY")
        self.assertEqual(sc_tx._account_name("敦化分行 外幣活存帳戶 11305●●●●●8908"), "敦化")
        self.assertEqual(sc_tx._account_name("古亭分行"), "古亭")
        self.assertEqual(sc_tx._account_name("外幣活存帳戶 11305●●●●●8908"), "8908")


class ScFetchTest(unittest.TestCase):
    def test_fetch_every_account_every_currency_then_deposits(self):
        import tempfile
        from pathlib import Path
        tmp = Path(tempfile.mkdtemp())
        page = FakePage(TABLES)
        query = mock.Mock(return_value={"head": ["交易時間", "金額"], "rows": [], "currency": ""})
        with mock.patch.object(sc_tx, "_eval", side_effect=page.eval), \
                mock.patch.object(sc_tx, "_query", query), \
                mock.patch.object(sc_tx, "logout_sc", return_value=True), \
                mock.patch.object(sc_tx, "TX_DIR", tmp / "sc"), \
                mock.patch.object(sc_tx, "STATE_FILE", tmp / "sc" / "_state.json"), \
                mock.patch.object(sc_tx, "BANK_DIR", tmp), \
                mock.patch.object(sc_tx, "_snapshot"), \
                mock.patch("bank_sync.native_chrome.native_login", return_value=True), \
                mock.patch("bank_sync.progress_log.log_run"), \
                mock.patch.object(sc_tx.time, "sleep"), \
                mock.patch("builtins.print"), \
                mock.patch.object(builtins, "input", side_effect=AssertionError("不該要求按 Enter")):
            raw = sc_tx.fetch(since=date(2026, 11, 1))
        self.assertEqual([c.split("|")[1] for c in page.clicked], ["美金 USD", "南非幣 ZAR", "日圓 JPY"])
        accounts = [a["account"] for a in json.loads(raw.read_text("utf-8"))["accounts"]]
        self.assertEqual(accounts, ["渣打外幣 敦化 美元", "渣打外幣 敦化 南非幣", "渣打外幣 古亭 日圓"])
        dep = json.loads(next((tmp / "sc").glob("deposits_*.json")).read_text("utf-8"))
        self.assertEqual(dep["tables"][0]["rows"], [["USD", "1,000"]])


class WeeklyAllBanksTest(unittest.TestCase):
    def test_every_bank_logged_in_even_without_notices(self):
        from bank_sync import weekly
        plan = [{"code": "taishin", "name": "台新", "run": True}, {"code": "yuanta", "name": "元大", "run": True}]
        with mock.patch("bank_sync.mail_activity.check", return_value=plan):
            self.assertEqual(weekly.run(dry_run=True), ["taishin", "yuanta"])

    def test_mail_failure_falls_back_to_all_banks(self):
        from bank_sync import weekly
        from bank_sync.mail_activity import BANKS
        with mock.patch("bank_sync.mail_activity.check", side_effect=SystemExit("no mail")), \
                mock.patch("builtins.print"):
            self.assertEqual(weekly.run(dry_run=True), [b.code for b in BANKS])
