from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .catalog import BankAccountSpec
from .models import BankTransaction


ALIASES = {
    "date": ("交易日期", "日期", "時間", "transaction_date", "date"),
    "description": ("摘要", "交易摘要", "說明", "description", "memo"),
    "amount": ("金額", "交易金額", "amount"),
    "balance": ("餘額", "帳戶餘額", "balance"),
}


def _pick(row: dict[str, str], field: str) -> str:
    for name in ALIASES[field]:
        if name in row and str(row[name]).strip():
            return str(row[name]).strip()
    return ""


def _decimal(value: str) -> Decimal:
    cleaned = value.replace("NT$", "").replace("$", "").replace(",", "").strip()
    if cleaned.startswith("提出"):
        cleaned = "-" + cleaned.removeprefix("提出").strip()
    elif cleaned.startswith("存入"):
        cleaned = cleaned.removeprefix("存入").strip()
    return Decimal(cleaned or "0")


def _date(value: str):
    text = value.strip().replace("年", "/").replace("月", "/").replace("日", "")
    for fmt in ("%Y/%m/%d %H:%M", "%Y/%m/%d", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"無法辨識日期：{value}")


def import_csv(path: Path, account: BankAccountSpec, currency: str = "TWD") -> list[BankTransaction]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    branch = account.branches[0] if len(account.branches) == 1 else ""
    return [BankTransaction(account.owner, account.bank, branch, currency, _date(_pick(row, "date")), _decimal(_pick(row, "amount")), _pick(row, "description"), _decimal(_pick(row, "balance")) if _pick(row, "balance") else None, "csv") for row in rows]
