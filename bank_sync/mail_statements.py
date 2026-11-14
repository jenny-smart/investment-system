"""從 jenny@hers.com.tw 信箱抓信用卡電子帳單 PDF，存到 ~/Bank account/statements/<銀行>/，並用本機密碼試開。

信箱用 IMAP + Google 應用程式密碼（做法同 tool-system gmail_401），只讀信、不刪不改。
帳密檔需要：
  "mail":   {"user": "jenny@hers.com.tw", "app_password": "xxxx xxxx xxxx xxxx"}
  "<銀行>": {..., "pdf_password": "帳單開啟密碼"}
"""
from __future__ import annotations

import email
import imaplib
import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from email.header import decode_header, make_header
from pathlib import Path

from .credentials import BANK_DIR, DEFAULT_CREDENTIALS_FILE, load_section

STATEMENT_DIR = BANK_DIR / "statements"
STATE_FILE = STATEMENT_DIR / "_fetched.json"


@dataclass(frozen=True)
class StatementSource:
    code: str               # 帳密檔裡放 pdf_password 的名稱
    name: str
    sender: str             # 寄件者（IMAP FROM 搜尋）
    subject_words: tuple[str, ...]   # 主旨要全部包含
    ledger_row: str = ""    # 2026細帳的列名；空白 = 平常不刷，只提醒
    skip_files: tuple[str, ...] = ()  # 不是帳單的附件（繳款單、簽章）


SOURCES: tuple[StatementSource, ...] = (
    StatementSource("fubon", "富邦", "rs@cf.taipeifubon.com.tw", ("信用卡帳單",), "信用卡-富邦 19"),
    StatementSource("taishin", "台新", "webmaster@bhurecv.taishinbank.com.tw", ("信用卡電子帳單",), "信用卡-台新 18",
                    skip_files=("PaymentSlip",)),
    StatementSource("sc", "渣打", "scbebill@tw-standardchartered.com.tw", ("信用卡", "月結單"), "信用卡-渣打 14"),
    StatementSource("dbs", "星展", "eservicetw@dbs.com", ("信用卡電子對帳單",), "信用卡-星展 08"),
    StatementSource("cathay", "國泰世華", "service@pxbillrc01.cathaybk.com.tw", ("信用卡", "電子帳單"), "信用卡-國泰世華 24",
                    skip_files=(".p7s",)),
    StatementSource("hsbc", "滙豐", "cards@estatements.hsbc.com.tw", ("信用卡帳單",)),
    StatementSource("ubot", "聯邦", "ubot.com.tw", ("信用卡", "電子帳單")),
)


def _decode(value: str | None) -> str:
    return str(make_header(decode_header(value or ""))) if value else ""


def _load_state() -> dict:
    return json.loads(STATE_FILE.read_text("utf-8")) if STATE_FILE.exists() else {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")


def subject_matches(source: StatementSource, subject: str) -> bool:
    return all(word in subject for word in source.subject_words)


def statement_month(subject: str, sent: date) -> str:
    """主旨裡的帳單月份（西元或民國），找不到就用寄件月份。"""
    m = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月", subject)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.search(r"(1\d{2})\s*年\s*(\d{1,2})\s*月", subject)
    if m:
        return f"{int(m.group(1)) + 1911}-{int(m.group(2)):02d}"
    return f"{sent.year}-{sent.month:02d}"


def _imap_date(day: date) -> str:
    return day.strftime("%d-%b-%Y")


def _all_mail_folder(client) -> str:
    """Gmail「所有郵件」的資料夾名稱會依介面語言不同，用 \\All 屬性找。"""
    _, folders = client.list()
    for raw in folders or []:
        line = raw.decode("utf-8", "replace")
        if "\\All" in line:
            return line.split(' "/" ')[-1]
    return "INBOX"


def fetch_statements(months: int = 3, path: Path = DEFAULT_CREDENTIALS_FILE) -> list[dict]:
    """下載最近 N 個月的信用卡帳單 PDF；已下載過的信不重抓。回傳新下載的清單。"""
    mail = load_section("mail", ("user", "app_password"), path)
    since = _imap_date(date.today() - timedelta(days=31 * months))
    state = _load_state()
    saved: list[dict] = []
    client = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        client.login(mail["user"], mail["app_password"].replace(" ", ""))
        client.select(_all_mail_folder(client), readonly=True)
        for source in SOURCES:
            _, data = client.search(None, "FROM", f'"{source.sender}"', "SINCE", since)
            for num in (data[0] or b"").split():
                _, msg_data = client.fetch(num, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])
                msg_id = msg.get("Message-ID", "") or f"{source.code}-{num.decode()}"
                subject = _decode(msg.get("Subject"))
                if msg_id in state or not subject_matches(source, subject):
                    continue
                sent = email.utils.parsedate_to_datetime(msg.get("Date")).date()
                month = statement_month(subject, sent)
                files = []
                for part in msg.walk():
                    filename = _decode(part.get_filename())
                    if not filename or not filename.lower().endswith(".pdf"):
                        continue
                    if any(skip in filename for skip in source.skip_files):
                        continue
                    target = STATEMENT_DIR / source.name / f"{month}_{filename}"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(part.get_payload(decode=True))
                    files.append(str(target))
                state[msg_id] = {"bank": source.code, "month": month, "subject": subject, "files": files}
                saved.append({"bank": source.name, "month": month, "files": files})
                print(f"↓ {source.name} {month}：{len(files)} 個 PDF")
    finally:
        try:
            client.logout()
        except Exception:
            pass
    _save_state(state)
    return saved


def open_pdf_text(pdf_path: Path, password: str) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(pdf_path))
    if reader.is_encrypted and not reader.decrypt(password):
        raise ValueError("密碼不對，打不開")
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def check_statements(path: Path = DEFAULT_CREDENTIALS_FILE) -> list[dict]:
    """用帳密檔裡的 pdf_password 試開已下載的帳單，回報能否讀出文字（不印出帳單內容）。"""
    results = []
    for source in SOURCES:
        folder = STATEMENT_DIR / source.name
        pdfs = sorted(folder.glob("*.pdf")) + sorted(folder.glob("*.PDF")) if folder.exists() else []
        if not pdfs:
            continue
        try:
            password = load_section(source.code, ("pdf_password",), path)["pdf_password"]
        except (KeyError, ValueError):
            password = ""
        for pdf in pdfs:
            row = {"bank": source.name, "file": pdf.name, "ok": False, "chars": 0, "note": ""}
            try:
                text = open_pdf_text(pdf, password)
                row["ok"], row["chars"] = True, len(text.strip())
                if row["chars"] < 50:
                    row["note"] = "打得開但幾乎沒有文字（可能是圖片檔，需要 OCR）"
                elif not source.ledger_row:
                    row["note"] = "這張卡平常不刷，出現帳單請確認"
            except Exception as exc:
                row["note"] = "沒有設定 pdf_password" if not password else str(exc)
            results.append(row)
            mark = "✓" if row["ok"] else "✗"
            print(f"{mark} {source.name} {pdf.name}：{'可讀，' + str(row['chars']) + ' 字' if row['ok'] else ''}{row['note']}")
    return results
