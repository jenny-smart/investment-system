from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BankAccountSpec:
    key: str
    bank: str
    owner: str
    currencies: tuple[str, ...]
    branches: tuple[str, ...] = ()
    channel: str = "web"
    credential_key: str = ""

    @property
    def login_key(self) -> str:
        return self.credential_key or self.key


BANK_ACCOUNTS: tuple[BankAccountSpec, ...] = (
    BankAccountSpec("taishin_jenny_twd", "台新銀行", "Jenny", ("TWD",), ("建北", "敦南"), credential_key="taishin_jenny"),
    BankAccountSpec("taishin_jenny_fx", "台新銀行", "Jenny", ("USD", "JPY", "CNY", "EUR", "CAD", "ZAR", "SGD"), ("古亭", "敦南"), credential_key="taishin_jenny"),
    BankAccountSpec("fubon_jenny_twd", "富邦銀行", "Jenny", ("TWD",), ("新店", "網銀")),
    BankAccountSpec("yuanta_jenny_twd", "元大銀行", "Jenny", ("TWD",), ("新店",)),
    BankAccountSpec("post_jenny_twd", "郵局", "Jenny", ("TWD",)),
    BankAccountSpec("post_mom_twd", "郵局", "媽媽", ("TWD",)),
    BankAccountSpec("sc_jenny_fx", "渣打銀行", "Jenny", ("USD", "ZAR")),
    BankAccountSpec("line_jenny_twd", "LINE BANK", "Jenny", ("TWD",)),
    BankAccountSpec("next_jenny_twd", "將來銀行", "Jenny", ("TWD",)),
)


def get_account(key: str) -> BankAccountSpec:
    for account in BANK_ACCOUNTS:
        if account.key == key:
            return account
    raise KeyError(f"找不到帳戶設定：{key}")
