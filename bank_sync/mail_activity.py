"""每週排程的第一步：讀 jenny@hers.com.tw 信箱，看各銀行「上次抓明細之後」有沒有動靜，有才登入。

- 交易信（轉帳、申購、定存、入帳…）→ 一定要登入
- 只有登入通知 → 也列進去（將來、LINE Bank、渣打、郵局轉帳或消費不一定寄信）
- 只有廣告、對帳單、停損停利、信用卡帳單 → 跳過

從「上次抓這家明細的時間」開始看信，所以我們自己抓明細時產生的登入通知不會被算進去。
信箱用 IMAP（同 fetch-statements 的本機設定），只讀主旨與寄件者，不讀內文、不改信。
"""
from __future__ import annotations

import email
import email.utils
import imaplib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .credentials import BANK_DIR, DEFAULT_CREDENTIALS_FILE, load_section
from .mail_statements import _all_mail_folder, _decode, _imap_date

TX_ROOT = BANK_DIR / "transactions"


@dataclass(frozen=True)
class BankMail:
    code: str                 # fetch-<code>
    name: str
    domains: tuple            # 寄件者網域（含子網域）
    skip_senders: tuple = ()  # 廣告信寄件者
    always: bool = False      # 有登入通知就算（轉帳不一定寄信）


BANKS = (
    BankMail("taishin", "台新", ("taishinbank.com.tw",)),
    BankMail("fubon", "富邦", ("taipeifubon.com.tw",), ("mhu.taipeifubon.com.tw",)),
    BankMail("next", "將來", ("nextbank.com.tw",), (), True),
    BankMail("linebank", "LINE Bank", ("linebank.com.tw",), ("edm.linebank.com.tw",), True),
    BankMail("sc", "渣打", ("sc.com",), ("msg.tw.sc.com",), True),
    BankMail("yuanta", "元大", ("yuantabank.com.tw", "yuanta.com"), ("mail01u.yuantabank.com.tw",), True),
    BankMail("post", "郵局", ("post.gov.tw",), (), True),
)

TX_WORDS = ("轉帳", "匯款", "申購", "贖回", "定存", "入帳", "轉入", "轉出", "扣款", "結匯", "換匯", "提款", "交易通知",
            "交易「成功」", "交易成功", "消費")
NOT_TX = ("停損停利", "對帳單", "信用卡", "帳單", "繳款", "公告", "暫停服務", "優惠", "宣導", "申請", "生效前提醒")
LOGIN_WORDS = ("登入",)


def classify(subject: str) -> str:
    """'tx' 交易／'login' 登入／'' 其他"""
    s = subject or ""
    if any(w in s for w in NOT_TX):
        return ""
    if any(w in s for w in LOGIN_WORDS):
        return "login"
    if any(w in s for w in TX_WORDS):
        return "tx"
    return ""


def last_fetch(code: str) -> datetime | None:
    """上次抓這家明細的時間（本機明細檔的修改時間）"""
    folder = TX_ROOT / code
    files = sorted(folder.glob("2*.json"), key=lambda p: p.stat().st_mtime) if folder.exists() else []
    return datetime.fromtimestamp(files[-1].stat().st_mtime, tz=timezone.utc) if files else None


def _domain(sender: str) -> str:
    addr = email.utils.parseaddr(sender or "")[1].lower()
    return addr.split("@")[-1]


def check(days: int = 7, path: Path = DEFAULT_CREDENTIALS_FILE, verbose: bool = True) -> list[dict]:
    """回傳每家：{code, name, since, tx:[主旨…], login:[時間…], run: bool}"""
    mail = load_section("mail", ("user", "app_password"), path)
    floor = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    client = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        client.login(mail["user"], mail["app_password"].replace(" ", ""))
        client.select(_all_mail_folder(client), readonly=True)
        for bank in BANKS:
            last = last_fetch(bank.code)
            since = max(floor, last) if last else floor
            info = {"code": bank.code, "name": bank.name, "since": since, "tx": [], "login": []}
            for domain in bank.domains:
                _, data = client.search(None, "FROM", f'"{domain}"', "SINCE", _imap_date(since.astimezone().date()))
                nums = (data[0] or b"").split()
                for num in nums:
                    _, msg_data = client.fetch(num, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                    msg = email.message_from_bytes(msg_data[0][1])
                    sender = _domain(msg.get("From"))
                    if any(sender == s or sender.endswith("." + s) for s in bank.skip_senders):
                        continue
                    if not any(sender == d or sender.endswith("." + d) for d in bank.domains):
                        continue
                    try:
                        sent = email.utils.parsedate_to_datetime(msg.get("Date"))
                    except Exception:
                        continue
                    if sent.tzinfo is None:
                        sent = sent.replace(tzinfo=timezone.utc)
                    if sent <= since:
                        continue
                    kind = classify(_decode(msg.get("Subject")))
                    if kind == "tx":
                        info["tx"].append(f"{sent.astimezone():%m/%d %H:%M} {_decode(msg.get('Subject'))[:30]}")
                    elif kind == "login":
                        info["login"].append(f"{sent.astimezone():%m/%d %H:%M}")
            info["run"] = bool(info["tx"]) or (bank.always and bool(info["login"]))
            out.append(info)
    finally:
        try:
            client.logout()
        except Exception:
            pass
    if verbose:
        print_plan(out)
    return out


def print_plan(info: list[dict]) -> None:
    print("📬 信箱檢查（上次抓明細之後的銀行通知）")
    for b in info:
        mark = "▶ 要登入" if b["run"] else "　略過　"
        since = f"{b['since'].astimezone():%m/%d %H:%M} 起"
        detail = []
        if b["tx"]:
            detail.append(f"交易 {len(b['tx'])} 封：" + "；".join(sorted(set(t.split(' ', 2)[-1] for t in b["tx"]))[:3]))
        if b["login"]:
            detail.append(f"登入 {len(b['login'])} 次（{', '.join(b['login'][-3:])}）")
        print(f"  {mark} {b['name']:<9}{since}｜{'；'.join(detail) or '沒有通知'}")
