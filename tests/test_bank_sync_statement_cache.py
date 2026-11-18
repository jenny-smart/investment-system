import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from bank_sync import ledger_sync, mail_statements
from bank_sync.statement_parser import Charge, Statement


class StatementCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        folder = self.tmp / "台新"
        folder.mkdir()
        (folder / "2026-11_a.pdf").write_bytes(b"x")
        self.st = Statement("taishin", date(2026, 11, 24), 1200, [Charge(date(2026, 11, 2), "全聯", 1200, "1234")])
        source = next(s for s in mail_statements.SOURCES if s.code == "taishin")
        self.patches = [mock.patch.object(ledger_sync, "STATEMENT_DIR", self.tmp),
                        mock.patch.object(ledger_sync, "PARSED_CACHE", self.tmp / "_parsed_cache.json"),
                        mock.patch.object(ledger_sync, "SOURCES", (source,)),
                        mock.patch.object(ledger_sync, "load_section", return_value={"pdf_password": "p"})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_second_run_uses_cache(self):
        opener = mock.Mock(return_value="text")
        with mock.patch.object(ledger_sync, "open_pdf_text", opener), \
                mock.patch.object(ledger_sync, "parse", return_value=self.st):
            first = ledger_sync.parsed_statements(2026)
            second = ledger_sync.parsed_statements(2026)
        self.assertEqual(opener.call_count, 1)
        self.assertEqual(second[0].statement.total_due, 1200)
        self.assertEqual(second[0].statement.charges[0].description, "全聯")
        self.assertEqual(first[0].statement.ledger_month, second[0].statement.ledger_month)


class CheckOnlyNewTest(unittest.TestCase):
    def test_check_only_new_files(self):
        tmp = Path(tempfile.mkdtemp())
        source = next(s for s in mail_statements.SOURCES if s.code == "taishin")
        (tmp / source.name).mkdir()
        old, new = tmp / source.name / "old.pdf", tmp / source.name / "new.pdf"
        old.write_bytes(b"x")
        new.write_bytes(b"x")
        opener = mock.Mock(return_value="x" * 100)
        with mock.patch.object(mail_statements, "STATEMENT_DIR", tmp), \
                mock.patch.object(mail_statements, "load_section", return_value={"pdf_password": "p"}), \
                mock.patch.object(mail_statements, "open_pdf_text", opener), \
                mock.patch("builtins.print"):
            rows = mail_statements.check_statements(only_files=[str(new)])
        self.assertEqual([r["file"] for r in rows], ["new.pdf"])


if __name__ == "__main__":
    unittest.main()
