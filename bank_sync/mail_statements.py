"""從 jenny@hers.com.tw 信箱抓信用卡電子帳單 PDF，存到 ~/Bank account/statements/<銀行>/，並用本機密碼試開。

信箱用 IMAP + Google 應用程式密碼（做法同 tool-system gmail_401），只讀信、不刪不改。
帳密檔需要：
  "mail":   {"user": "jenny@hers.com.tw", "app_password": "xxxx xxxx xxxx xxxx"}
  "<銀行>": {..., "pdf_password": "帳單開啟密碼"}
"""
from __future__ import annotations

import email
import email.utils
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


def fetch_statements(months: int = 3, path: Path = DEFAULT_CREDENTIALS_FILE, banks: tuple = (), force: bool = False) -> list[dict]:
    """下載最近 N 個月的信用卡帳單 PDF；已下載過的信不重抓（force=True 時重抓）。banks 可限定銀行代碼。"""
    mail = load_section("mail", ("user", "app_password"), path)
    since = _imap_date(date.today() - timedelta(days=31 * months))
    state = _load_state()
    saved: list[dict] = []
    client = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        client.login(mail["user"], mail["app_password"].replace(" ", ""))
        client.select(_all_mail_folder(client), readonly=True)
        for source in SOURCES:
            if banks and source.code not in banks:
                continue
            _, data = client.search(None, "FROM", f'"{source.sender}"', "SINCE", since)
            for num in (data[0] or b"").split():
                _, msg_data = client.fetch(num, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])
                msg_id = msg.get("Message-ID", "") or f"{source.code}-{num.decode()}"
                subject = _decode(msg.get("Subject"))
                if (msg_id in state and not force) or not subject_matches(source, subject):
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


def check_statements(path: Path = DEFAULT_CREDENTIALS_FILE, banks: tuple = ()) -> list[dict]:
    """用帳密檔裡的 pdf_password 試開已下載的帳單，回報能否讀出文字（不印出帳單內容）。"""
    results = []
    for source in SOURCES:
        if banks and source.code not in banks:
            continue
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


def mask_text(text: str) -> str:
    """遮掉卡號（13–19 碼數字，可含空白／-）與身分證字號，只留後 4 碼。"""
    def card(m):
        digits = re.sub(r"\D", "", m.group(0))
        return "****" + digits[-4:]
    text = re.sub(r"\b(?:\d[ -]?){12,18}\d\b", card, text)
    text = re.sub(r"\b[A-Z][12]\d{8}\b", "A*********", text)
    return text


def dump_statements(path: Path = DEFAULT_CREDENTIALS_FILE, banks: tuple = (), match: str = "") -> list[Path]:
    """每家最新一期帳單轉成文字檔（卡號、身分證遮蔽），存在 statements/_文字樣本/，給本人檢查後再分享。"""
    out_dir = STATEMENT_DIR / "_文字樣本"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for source in SOURCES:
        if banks and source.code not in banks:
            continue
        folder = STATEMENT_DIR / source.name
        pdfs = sorted(list(folder.glob("*.pdf")) + list(folder.glob("*.PDF"))) if folder.exists() else []
        if not pdfs:
            continue
        try:
            password = load_section(source.code, ("pdf_password",), path)["pdf_password"]
        except (KeyError, ValueError):
            password = ""
        chosen = [p for p in pdfs if match in p.name] if match else pdfs[-1:]
        for pdf in chosen:
            try:
                text = open_pdf_text(pdf, password)
            except Exception as exc:
                print(f"✗ {source.name}：{exc}")
                continue
            target = out_dir / f"{source.name}_{pdf.stem}.txt"
            target.write_text(mask_text(text), "utf-8")
            written.append(target)
            print(f"✓ {source.name}：{target}")
    return written


def notify_new_statements(saved: list[dict], path: Path = DEFAULT_CREDENTIALS_FILE, due_reminder: bool = False) -> None:
    """新下載的帳單各發一則行事曆提醒（同一份只發一次）；due_reminder=True 時再於繳款截止日前一天加一則。"""
    if not saved:
        return
    from datetime import date, timedelta
    from .google_auth import calendar_add_once, credentials
    from .statement_parser import parse
    try:
        creds = credentials(path)
    except SystemExit as exc:
        print(f"（沒有發行事曆：{exc}）")
        return
    code_by_name = {s.name: s.code for s in SOURCES}
    today = date.today()
    for item in saved:
        code = code_by_name.get(item["bank"], "")
        files = item.get("files") or []
        summary = f"【信用卡帳單】{item['bank']} {item['month']}"
        body = f"帳單已存到 {files[0]}" if files else "帳單信沒有 PDF 附件"
        due = None
        if code in ("fubon", "taishin", "sc", "dbs", "cathay") and files:
            try:
                password = load_section(code, ("pdf_password",), path)["pdf_password"]
                st = parse(code, open_pdf_text(Path(files[0]), password))
                if st.total_due is not None:
                    summary += f" 應繳 {st.total_due:,}"
                due = st.due
                body = (f"繳款截止 {st.due:%Y/%m/%d}、" if st.due else "") + f"消費 {len(st.purchases)} 筆\n" + body
                if st.warnings:
                    body += "\n⚠️ " + "；".join(st.warnings)
            except Exception as exc:  # 打不開也照樣提醒
                body += f"\n⚠️ 讀不出內容：{exc}"
        elif code in ("hsbc", "ubot"):
            summary = f"⚠️【信用卡帳單】{item['bank']} {item['month']}（平常不刷，請確認）"
        key = f"stmt:{code}:{Path(files[0]).name if files else item['month']}"
        print(f"   行事曆：{summary} → {calendar_add_once(creds, 'bank_sync:' + key, today, summary, body)}")
        if due_reminder and due and due > today:
            remind = max(due - timedelta(days=1), today)
            due_title = "⏰ " + item["bank"] + "信用卡 明天繳款截止"
            result = calendar_add_once(creds, "bank_sync:due:" + key, remind, due_title, body)
            print(f"   行事曆：{due_title} → {result}")
