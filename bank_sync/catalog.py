from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BankAccountSpec:
    key: str
    bank: str                       # 銀行名稱（顯示用）
    owner: str
    currencies: tuple[str, ...]
    branches: tuple[str, ...] = ()
    channel: str = "web"            # web=網銀自動登入；statement_pdf=放帳單 PDF 到本機資料夾
    bank_code: str = ""             # banks.WEB_BANKS 的代碼
    credential_key: str = ""        # personal_bank_accounts.json 裡的登入名稱

    @property
    def login_key(self) -> str:
        return self.credential_key or self.bank_code or self.key


BANK_ACCOUNTS: tuple[BankAccountSpec, ...] = (
    BankAccountSpec("taishin_jenny_twd", "台新銀行", "Jenny", ("TWD",), ("建北", "信義", "Richard", "子帳戶", "內湖新轉"), bank_code="taishin"),
    BankAccountSpec("taishin_jenny_fx", "台新銀行", "Jenny", ("USD", "JPY", "ZAR"), bank_code="taishin"),
    BankAccountSpec("fubon_jenny_twd", "富邦銀行", "Jenny", ("TWD",), bank_code="fubon"),
    BankAccountSpec("yuanta_jenny_twd", "元大銀行", "Jenny", ("TWD",), bank_code="yuanta"),
    BankAccountSpec("sc_jenny_twd", "渣打銀行", "Jenny", ("TWD",), bank_code="sc"),
    BankAccountSpec("sc_jenny_fx", "渣打銀行", "Jenny", ("USD", "ZAR"), bank_code="sc"),
    BankAccountSpec("line_jenny_twd", "LINE Bank", "Jenny", ("TWD",), bank_code="linebank"),
    BankAccountSpec("next_jenny_twd", "將來銀行", "Jenny", ("TWD",), bank_code="next"),
    BankAccountSpec("ubot_jenny_card", "聯邦銀行", "Jenny", ("TWD",), bank_code="ubot"),
    BankAccountSpec("cathay_jenny_card", "國泰世華", "Jenny", ("TWD",), channel="statement_pdf"),  # 只有信用卡，帳單從信箱抓
    BankAccountSpec("dbs_jenny_card", "星展銀行", "Jenny", ("TWD",), channel="statement_pdf"),
    BankAccountSpec("post_jenny_twd", "郵局", "Jenny", ("TWD",), bank_code="post", credential_key="post_jenny"),
    BankAccountSpec("post_mom_twd", "郵局", "媽媽", ("TWD",), bank_code="post", credential_key="post_mom"),
)


def get_account(key: str) -> BankAccountSpec:
    for account in BANK_ACCOUNTS:
        if account.key == key:
            return account
    raise KeyError(f"找不到帳戶設定：{key}")


def login_bank_code(login_key: str) -> str:
    """personal_bank_accounts.json 的登入名稱 → 銀行代碼。"""
    for account in BANK_ACCOUNTS:
        if account.channel == "web" and account.login_key == login_key:
            return account.bank_code
    raise KeyError(f"不認得的登入名稱：{login_key}")


def web_login_keys() -> list[str]:
    keys: list[str] = []
    for account in BANK_ACCOUNTS:
        if account.channel == "web" and account.login_key not in keys:
            keys.append(account.login_key)
    return keys
