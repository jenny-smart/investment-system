from __future__ import annotations

import argparse
import csv
import getpass
from pathlib import Path

from .banks import WEB_BANKS
from .catalog import BANK_ACCOUNTS, get_account, login_bank_code, web_login_keys
from .credentials import DEFAULT_CREDENTIALS_FILE, FIELDS, configured_logins, has_credentials, save_credentials
from .importer import import_csv
from .store import DEFAULT_DB, save_transactions

FIELD_LABELS = {"id_number": "身分證字號", "user_code": "使用者代號（沒有就直接按 Enter）", "password": "密碼"}


def _setup(login_key: str) -> None:
    bank = WEB_BANKS[login_bank_code(login_key)]
    print(f"設定 {bank.name}（{login_key}）帳密，輸入時不會顯示在畫面上。")
    values = {field: getpass.getpass(f"{FIELD_LABELS[field]}: ") for field in FIELDS}
    if not values["password"]:
        raise ValueError("密碼不可為空")
    save_credentials(login_key, values)
    print(f"已存入 {DEFAULT_CREDENTIALS_FILE}（權限 600）。")


def _list() -> None:
    print(f"帳密檔：{DEFAULT_CREDENTIALS_FILE}")
    for key in web_login_keys():
        bank = WEB_BANKS[login_bank_code(key)]
        print(f"{'✓' if has_credentials(key) else '·'} {key:<11} {bank.name}")
    for item in BANK_ACCOUNTS:
        if item.channel != "web":
            print(f"  {item.key:<11} {item.bank}（{item.channel}：不需網銀帳密）")


def _login(keys: list[str], keep_open: bool, timeout_min: float) -> None:
    from .login import login_banks
    if not keys:
        keys = [k for k in web_login_keys() if k in configured_logins()]
        if not keys:
            raise SystemExit(f"{DEFAULT_CREDENTIALS_FILE} 還沒有任何帳密；請先執行 python -m bank_sync setup <登入名稱>")
    login_banks([(k, login_bank_code(k)) for k in keys], keep_open=keep_open, timeout_s=timeout_min * 60)


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="investment-system 本機銀行明細工具")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="列出各銀行與帳密設定狀態")
    setup = sub.add_parser("setup", help="輸入一家銀行的帳密")
    setup.add_argument("login", choices=web_login_keys())
    login = sub.add_parser("login", help="開 Chrome 一次一家預填帳密；不指定銀行 = 帳密檔裡有的全部")
    login.add_argument("logins", nargs="*", metavar="登入名稱")
    login.add_argument("--close", action="store_true", help="全部登入後直接關閉 Chrome")
    login.add_argument("--timeout", type=float, default=5, help="每一家等待登入的分鐘數（預設 5）")
    insp = sub.add_parser("inspect", help="列出已開啟的銀行登入頁欄位結構（不讀取內容）")
    insp.add_argument("login")
    fetch = sub.add_parser("fetch-statements", help="從信箱下載信用卡電子帳單 PDF 並試開")
    fetch.add_argument("--months", type=int, default=3, help="往回抓幾個月（預設 3）")
    fetch.add_argument("--bank", action="append", default=[], help="只抓這家（可重複）：fubon taishin sc dbs cathay hsbc ubot")
    fetch.add_argument("--force", action="store_true", help="已下載過的也重新下載")
    sub.add_parser("check-statements", help="用 pdf_password 試開已下載的帳單")
    dump = sub.add_parser("dump-statements", help="每家最新一期帳單轉成文字檔（卡號、身分證遮蔽）")
    dump.add_argument("--bank", action="append", default=[])
    dump.add_argument("--file", default="", help="只轉檔名含這段文字的帳單（例：2026-04）；不給則每家最新一期")
    gl = sub.add_parser("google-login", help="用 jennytsai26888@gmail.com 授權寫入總帳與行事曆（只要做一次）")
    gl.add_argument("client_json", nargs="?", type=Path, help="OAuth 用戶端 JSON（不給則讀 ~/lemon/.streamlit/secrets.toml）")
    led = sub.add_parser("ledger", help="信用卡帳單 → 2026細帳 備註＋2026細帳(含信用卡)；預設只比對")
    led.add_argument("--year", type=int, default=__import__("datetime").date.today().year)
    led.add_argument("--apply", action="store_true", help="確認比對報表後才加：寫入總帳並發行事曆")
    led.add_argument("--bank", action="append", default=[])
    led.add_argument("--notes-only", action="store_true", help="只在 2026細帳 加備註，不建／不動 含信用卡 表")
    led.add_argument("--unclassified", action="store_true", help="列出對不到分類規則的商店（筆數、金額）")
    prev = sub.add_parser("preview-statements", help="列出每份帳單解析結果（不需要 Google 權限）")
    prev.add_argument("--year", type=int, default=__import__("datetime").date.today().year)
    imp = sub.add_parser("import-csv")
    imp.add_argument("account"); imp.add_argument("input", type=Path)
    imp.add_argument("--currency", default="TWD")
    imp.add_argument("--output", type=Path, default=Path("bank_sync_output/transactions.csv"))
    imp.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args(argv)
    if args.command == "list":
        _list()
    elif args.command == "setup":
        _setup(args.login)
    elif args.command == "login":
        unknown = [k for k in args.logins if k not in web_login_keys()]
        if unknown:
            parser.error(f"不認得的登入名稱：{', '.join(unknown)}（可用：{', '.join(web_login_keys())}）")
        _login(args.logins, keep_open=not args.close, timeout_min=args.timeout)
    elif args.command == "inspect":
        from .native_chrome import inspect_page
        inspect_page(login_bank_code(args.login))
    elif args.command == "fetch-statements":
        from .mail_statements import check_statements, fetch_statements
        fetch_statements(args.months, banks=tuple(args.bank), force=args.force)
        check_statements(banks=tuple(args.bank))
    elif args.command == "google-login":
        from .google_auth import login
        login(args.client_json)
    elif args.command == "ledger":
        from .ledger_sync import run
        run(args.year, apply=args.apply, banks=tuple(args.bank), notes_only=args.notes_only,
            show_unclassified=args.unclassified)
    elif args.command == "preview-statements":
        from .ledger_sync import BANK_NAME, parsed_statements
        for f in parsed_statements(args.year):
            st = f.statement
            spent = sum(c.amount for c in st.purchases)
            print(f"{BANK_NAME[f.bank]:<5} {f.path.name[:40]:<40} 細帳月份={st.ledger_month or '?':<8} "
                  f"應繳={st.total_due if st.total_due is not None else '?':>8} 消費 {len(st.purchases):>3} 筆 合計 {spent:>8,}"
                  + (f"  ⚠️ {'；'.join(st.warnings)}" if st.warnings else ""))
    elif args.command == "dump-statements":
        from .mail_statements import dump_statements
        dump_statements(banks=tuple(args.bank), match=args.file)
    elif args.command == "check-statements":
        from .mail_statements import check_statements
        check_statements()
    else:
        _import(args)
    return 0
