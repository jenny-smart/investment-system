import builtins
import json
import unittest
from datetime import date
from unittest import mock

from bank_sync import sc_tx


class FakePage:
    """模擬渣打頁面：幣別表 ↔ 外幣明細頁。"""

    def __init__(self, rows):
        self.rows = rows
        self.url = "https://x/scb/accOverview"
        self.on_list = False
        self.clicked = []

    def eval(self, js):
        if js == "history.back()":
            self.url, self.on_list = "https://x/scb/accOverview/savingForeign", True
            return None
        if "最近交易日期" in js and "__I__" not in js and "'明細'" not in js:
            return json.dumps(self.rows) if self.on_list else "[]"
        if "'明細'" in js:
            i = int(js.split("const i = ")[1].split(";")[0])
            self.clicked.append(self.rows[i][1])
            self.url, self.on_list = "https://x/scb/accOverview/savingForeignDetails", False
            return "ok"
        if "location.href" in js:
            return self.url
        if "const names" in js:  # _click
            if '"外幣活存"' in js:
                self.on_list = True
                return "外幣活存"
            return ""
        return ""


class ScFxTest(unittest.TestCase):
    def test_currency_code(self):
        self.assertEqual(sc_tx._currency_code("美金 USD"), "USD")
        self.assertEqual(sc_tx._currency_code("人民幣CNY"), "CNY")

    def test_only_recent_currencies_and_no_input(self):
        page = FakePage([[0, "人民幣 CNY", "2018/07/19"], [1, "美金 USD", "2026/11/12"],
                         [2, "南非幣 ZAR", "2026/11/06"]])
        query = mock.Mock(return_value={"head": ["交易時間"], "rows": [], "currency": ""})
        with mock.patch.object(sc_tx, "_eval", side_effect=page.eval), \
                mock.patch.object(sc_tx, "_query", query), \
                mock.patch.object(sc_tx.time, "sleep"), \
                mock.patch.object(builtins, "input", side_effect=AssertionError("不該要求按 Enter")):
            rows = sc_tx._open_fx_list()
            self.assertEqual(len(rows), 3)
        # 模擬 fetch 的迴圈判斷：只有 USD、ZAR 在起日之後
        since = date(2026, 11, 1)
        picked = [r[1] for r in rows if sc_tx.parse_day(r[2]) and sc_tx.parse_day(r[2]) >= since]
        self.assertEqual(picked, ["美金 USD", "南非幣 ZAR"])


if __name__ == "__main__":
    unittest.main()


class ScFetchTest(unittest.TestCase):
    def test_fetch_clicks_every_currency_detail(self):
        import tempfile
        from pathlib import Path
        tmp = Path(tempfile.mkdtemp())
        page = FakePage([[0, "人民幣 CNY", "2018/07/19"], [1, "美金 USD", "2026/11/12"],
                         [2, "南非幣 ZAR", "2026/11/06"]])
        page.on_list = True
        query = mock.Mock(return_value={"head": ["交易時間", "金額"], "rows": [], "currency": ""})
        with mock.patch.object(sc_tx, "_eval", side_effect=page.eval), \
                mock.patch.object(sc_tx, "_query", query), \
                mock.patch.object(sc_tx, "logout_sc", return_value=True), \
                mock.patch.object(sc_tx, "TX_DIR", tmp / "sc"), \
                mock.patch.object(sc_tx, "STATE_FILE", tmp / "sc" / "_state.json"), \
                mock.patch.object(sc_tx, "BANK_DIR", tmp), \
                mock.patch("bank_sync.native_chrome.native_login", return_value=True), \
                mock.patch("bank_sync.progress_log.log_run"), \
                mock.patch.object(sc_tx.time, "sleep"), \
                mock.patch("builtins.print"), \
                mock.patch.object(builtins, "input", side_effect=AssertionError("不該要求按 Enter")):
            sc_tx.fetch(since=date(2026, 11, 1))
        self.assertEqual(page.clicked, ["人民幣 CNY", "美金 USD", "南非幣 ZAR"])
        self.assertEqual(query.call_count, 3)


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
