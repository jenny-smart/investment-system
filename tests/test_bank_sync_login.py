import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from bank_sync import credentials
from bank_sync.banks import WEB_BANKS
from bank_sync.catalog import BANK_ACCOUNTS, login_bank_code, web_login_keys


class CredentialsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "personal_bank_accounts.json"

    def tearDown(self):
        self.dir.cleanup()

    def test_save_is_private_and_loads_back(self):
        credentials.save_credentials("fubon", {"id_number": " A1 ", "user_code": "u", "password": " p w "}, self.path)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        self.assertEqual(credentials.load_credentials("fubon", self.path),
                         {"id_number": "A1", "user_code": "u", "password": " p w "})
        self.assertEqual(credentials.permission_warning(self.path), "")

    def test_save_keeps_other_banks(self):
        credentials.save_credentials("fubon", {"password": "a"}, self.path)
        credentials.save_credentials("sc", {"password": "b"}, self.path)
        self.assertEqual(credentials.configured_logins(self.path), ["fubon", "sc"])

    def test_blank_fields_skipped_and_password_required(self):
        self.path.write_text(json.dumps({"_說明": "x", "next": {"id_number": "", "password": "p"},
                                         "sc": {"id_number": "A", "password": ""}}), encoding="utf-8")
        self.assertEqual(credentials.load_credentials("next", self.path), {"password": "p"})
        self.assertFalse(credentials.has_credentials("sc", self.path))
        self.assertEqual(credentials.configured_logins(self.path), ["next"])

    def test_warns_when_others_can_read(self):
        credentials.save_credentials("sc", {"password": "b"}, self.path)
        os.chmod(self.path, 0o644)
        self.assertIn("chmod 600", credentials.permission_warning(self.path))


class StatementTest(unittest.TestCase):
    def test_subject_rules_match_real_subjects(self):
        from bank_sync.mail_statements import SOURCES, subject_matches
        by = {s.code: s for s in SOURCES}
        self.assertTrue(subject_matches(by["fubon"], "台北富邦銀行2026年11月信用卡帳單"))
        self.assertFalse(subject_matches(by["fubon"], "提醒您本期信用卡帳單繳款截止日快到了"[:6]))
        self.assertTrue(subject_matches(by["taishin"], "台新信用卡電子帳單 2026年11月"))
        self.assertFalse(subject_matches(by["taishin"], "台新信用卡行動帳單2026年11月"))
        self.assertTrue(subject_matches(by["sc"], "渣打信用卡2026年10月電子月結單"))
        self.assertTrue(subject_matches(by["dbs"], "星展銀行(台灣)信用卡電子對帳單-2026年10月份"))
        self.assertTrue(subject_matches(by["cathay"], "國泰世華銀行信用卡2026年9月電子帳單"))
        self.assertTrue(subject_matches(by["hsbc"], "115年09月滙豐Live+現金回饋卡信用卡帳單"))
        self.assertFalse(subject_matches(by["ubot"], "用聯邦卡代扣生活帳單還能拿回饋"))

    def test_statement_month(self):
        from datetime import date
        from bank_sync.mail_statements import statement_month
        self.assertEqual(statement_month("渣打信用卡2026年10月電子月結單", date(2026, 10, 19)), "2026-10")
        self.assertEqual(statement_month("115年09月滙豐Live+現金回饋卡信用卡帳單", date(2026, 9, 25)), "2026-09")
        self.assertEqual(statement_month("無月份", date(2026, 3, 2)), "2026-03")

    def test_save_keeps_pdf_password(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "a.json"
            path.write_text(json.dumps({"fubon": {"password": "x", "pdf_password": "P"}}), "utf-8")
            credentials.save_credentials("fubon", {"password": "y"}, path)
            self.assertEqual(credentials.load_section("fubon", ("pdf_password",), path)["pdf_password"], "P")

    def test_open_encrypted_pdf(self):
        from pypdf import PdfWriter
        from bank_sync.mail_statements import open_pdf_text
        with tempfile.TemporaryDirectory() as d:
            pdf = Path(d) / "s.pdf"
            w = PdfWriter(); w.add_blank_page(100, 100); w.encrypt("PW", algorithm="AES-256")
            with pdf.open("wb") as f: w.write(f)
            self.assertEqual(open_pdf_text(pdf, "PW").strip(), "")
            with self.assertRaises(ValueError):
                open_pdf_text(pdf, "wrong")


class CatalogTest(unittest.TestCase):
    def test_every_web_login_has_bank(self):
        for key in web_login_keys():
            self.assertIn(login_bank_code(key), WEB_BANKS)

    def test_requested_banks_present(self):
        expected = {"taishin", "fubon", "sc", "linebank", "yuanta", "next", "ubot", "cathay"}
        self.assertTrue(expected <= set(web_login_keys()))
        self.assertEqual(WEB_BANKS["yuanta"].login_url, "https://ebank.yuantabank.com.tw/nib/")
        self.assertIn("ebank.standardchartered.com.tw", WEB_BANKS["sc"].login_url)

    def test_example_file_matches_logins(self):
        example = json.loads((Path(__file__).parents[1] / "bank_sync/personal_bank_accounts.example.json").read_text("utf-8"))
        from bank_sync.mail_statements import SOURCES
        known = set(web_login_keys()) | {s.code for s in SOURCES} | {"mail"}
        for key in example:
            if not key.startswith("_"):
                self.assertIn(key, known)

    def test_dbs_is_statement_only(self):
        dbs = [a for a in BANK_ACCOUNTS if a.key == "dbs_jenny_card"][0]
        self.assertEqual(dbs.channel, "statement_pdf")


if __name__ == "__main__":
    unittest.main()
