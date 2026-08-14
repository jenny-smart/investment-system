from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from .models import BankTransaction


DEFAULT_DB = Path("bank_sync_output/bank_transactions.sqlite3")


def fingerprint(row: BankTransaction) -> str:
    raw = "|".join((row.owner, row.bank, row.branch, row.currency, row.transaction_date.isoformat(), str(row.amount), row.description))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def save_transactions(rows: list[BankTransaction], path: Path = DEFAULT_DB) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("""
            create table if not exists bank_transactions (
                fingerprint text primary key,
                owner text not null,
                bank text not null,
                branch text not null default '',
                currency text not null,
                transaction_date text not null,
                amount text not null,
                description text not null default '',
                balance text,
                source text not null,
                imported_at text not null default current_timestamp
            )
        """)
        before = db.total_changes
        db.executemany(
            "insert or ignore into bank_transactions values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)",
            [(fingerprint(row), row.owner, row.bank, row.branch, row.currency, row.transaction_date.isoformat(), str(row.amount), row.description, None if row.balance is None else str(row.balance), row.source) for row in rows],
        )
        return db.total_changes - before
