from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class BankTransaction:
    owner: str
    bank: str
    branch: str
    currency: str
    transaction_date: date
    amount: Decimal
    description: str = ""
    balance: Decimal | None = None
    source: str = "web"

    def as_dict(self) -> dict:
        row = asdict(self)
        row["transaction_date"] = self.transaction_date.isoformat()
        row["amount"] = str(self.amount)
        row["balance"] = "" if self.balance is None else str(self.balance)
        return row
