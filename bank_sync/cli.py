from __future__ import annotations

import argparse
import csv
import getpass
from pathlib import Path

from .adapters import BANKS, open_and_prefill
from .catalog import BANK_ACCOUNTS, get_account
from .credentials import has_secret, save_secret
from .importer import import_csv
from .store import DEFAULT_DB, save_transactions


def _setup(account_key: str) -> None:
    account = get_account(account_key)
    if account.channel != "web":
        raise ValueError(f"{account.bank} 不需要設定網銀帳密")
    for field in BANKS[account.bank].credential_fields:
        save_secret(account.login_key, field, getpass.getpass(f"{field}: "))
    print("已安全存入 macOS Keychain。")


def _list() -> None:
    for item in BANK_ACCOUNTS:
        fields = BANKS[item.bank].credential_fields if item.bank in BANKS else ()
        ready = item.channel == "app_import" or all(has_secret(item.login_key, field) for field in fields)
        print(f"{'✓' if ready else '·'} {item.key}: {item.bank}/{item.owner} {','.join(item.currencies)} [{item.channel}]")


def _import(args) -> None:
    rows = import_csv(args.input, get_account(args.account), args.currency)
    inserted = save_transactions(rows, args.db)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].as_dict()))
            writer.writeheader()
            writer.writerows(row.as_dict() for row in rows)
    print(f"已轉換 {len(rows)} 筆、新增 {inserted} 筆：{args.output}")


def main() -> int:
    parser = argparse.ArgumentParser(description="investment-system 本機銀行明細工具")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    setup = sub.add_parser("setup"); setup.add_argument("account")
    launch = sub.add_parser("open"); launch.add_argument("account"); launch.add_argument("--no-prompt", action="store_true")
    imp = sub.add_parser("import-csv"); imp.add_argument("account"); imp.add_argument("input", type=Path); imp.add_argument("--currency", default="TWD"); imp.add_argument("--output", type=Path, default=Path("bank_sync_output/transactions.csv")); imp.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    if args.command == "list": _list()
    elif args.command == "setup": _setup(args.account)
    elif args.command == "open": open_and_prefill(get_account(args.account), interactive=not args.no_prompt)
    else: _import(args)
    return 0
