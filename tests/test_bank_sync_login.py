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
        for key in example:
            if not key.startswith("_"):
                self.assertIn(key, web_login_keys())

    def test_dbs_is_statement_only(self):
        dbs = [a for a in BANK_ACCOUNTS if a.key == "dbs_jenny_card"][0]
        self.assertEqual(dbs.channel, "statement_pdf")


if __name__ == "__main__":
    unittest.main()
