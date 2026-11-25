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
    ftx = sub.add_parser("fetch-taishin", help="台新：自動查詢台幣／外幣交易明細，存在本機")
    ftx.add_argument("--since", help="第一次（或要重抓）從哪天開始，例如 2026-11-01；平常不用給，會從上次最後一筆日期查到今天")
    ftx.add_argument("--keep-open", action="store_true")
    wk = sub.add_parser("weekly", help="每週更新：先查信，每家銀行都登入確認，再抓信用卡帳單、發布到網頁")
    wk.add_argument("--dry-run", action="store_true", help="只查信、列出要登入哪幾家")
    wk.add_argument("--days", type=int, default=7, help="最多往回看幾天的信（預設 7）")
    wk.add_argument("--bank", action="append", default=[], help="只跑這幾家（taishin/fubon/next/linebank/sc/yuanta/post）")
    sub.add_parser("weekly-install", help="裝成 Mac 排程：每週三晚上 10:00 打開終端機跑 weekly")
    sub.add_parser("weekly-uninstall", help="移除每週排程")
    sub.add_parser("app-install", help="把銀行帳戶頁裝成 Mac 背景服務（http://localhost:8502，只要做一次）")
    sub.add_parser("app-status", help="看銀行帳戶頁背景服務狀態")
    sub.add_parser("app-uninstall", help="移除銀行帳戶頁背景服務")
    ffb = sub.add_parser("fetch-fubon", help="富邦：自動查詢臺外幣交易明細，存在本機")
    ffb.add_argument("--since", help="第一次（或要重抓）從哪天開始，例如 2026-11-01")
    ffb.add_argument("--keep-open", action="store_true")
    fnx = sub.add_parser("fetch-next", help="將來銀行：查詢主帳戶明細（先存結果文字＋格式樣本）")
    fnx.add_argument("--since", help="從哪天開始（預設本月 1 日）")
    fnx.add_argument("--keep-open", action="store_true")
    fpo = sub.add_parser("fetch-post", help="郵局：下載存簿交易明細（CSV），存在本機")
    fpo.add_argument("--since", help="從哪天開始（預設本月 1 日）")
    fpo.add_argument("--keep-open", action="store_true")
    fsc = sub.add_parser("fetch-sc", help="渣打：自動查詢外幣活存（各帳戶、各幣別明細）與外幣定存")
    fsc.add_argument("--since", help="從哪天開始（預設本月 1 日）")
    fsc.add_argument("--keep-open", action="store_true")
    for code, label in (("linebank", "LINE Bank"), ("yuanta", "元大")):
        fx = sub.add_parser(f"fetch-{code}", help=f"{label}：自動查詢交易明細，存在本機")
        fx.add_argument("--since", help="第一次（或要重抓）從哪天開始，例如 2026-11-01")
        fx.add_argument("--keep-open", action="store_true")
    br = sub.add_parser("bank-review", help="把抓到的銀行明細列在總帳「銀行明細確認」分頁，要確認的標黃")
    br.add_argument("--year", type=int, default=__import__("datetime").date.today().year)
    ba = sub.add_parser("bank-audit", help="全年核對：複製細帳、把沒記到的明細用底色標出（原細帳不動）")
    ba.add_argument("--year", type=int, default=__import__("datetime").date.today().year)
    ba.add_argument("--bank", action="append", choices=["fubon", "taishin", "next", "yuanta", "linebank", "sc", "post"])
    ba.add_argument("--fetch", action="store_true", help="先從 1/1 下載今年明細（一家一家登入），再核對")
    dg = sub.add_parser("diag", help="檢查本機最新明細檔的格式（數字→9、中文→○，可貼給 Claude）")
    dg.add_argument("bank")
    rb = sub.add_parser("refresh-bank", help="App 用：抓選的銀行明細 → 細帳餘額核對 → 更新網頁明細")
    rb.add_argument("--bank", action="append", default=[], help="taishin/fubon/sc/next/linebank/yuanta/post，可重複；不給＝全部")
    rb.add_argument("--year", type=int, default=__import__("datetime").date.today().year)
    rc = sub.add_parser("refresh-cards", help="App 用：下載新信用卡帳單 → 比對細帳（不寫入）→ 更新網頁明細")
    rc.add_argument("--year", type=int, default=__import__("datetime").date.today().year)
    pb = sub.add_parser("publish", help="把本機銀行明細、信用卡明細寫進總帳「銀行明細」「信用卡明細」分頁（App 網頁看得到）")
    pb.add_argument("--year", type=int, default=__import__("datetime").date.today().year)
    me = sub.add_parser("messenger-explore", help="打開 Messenger 記帳對話，記錄訊息格式（原文只存本機）")
    me.add_argument("--thread", default="https://www.messenger.com/t/111433143973520")
    mf = sub.add_parser("messenger-fetch", help="讀 Messenger 對話裡的收據（日期＋品項＋總金額），之後自動對郵局等扣款")
    mf.add_argument("--since", default="", help="預設：郵局最早一筆支出的前一週")
    mf.add_argument("--thread", default="https://www.messenger.com/t/111433143973520")
    mf.add_argument("--reparse", action="store_true", help="不開瀏覽器，用上次存的對話文字重新解析")
    sub.add_parser("app-password", help="設定／重設本機銀行頁的進入密碼")
    bl = sub.add_parser("bank-ledger", help="銀行明細（台新／富邦／將來）→ 細帳；預設只比對")
    bl.add_argument("--year", type=int, default=__import__("datetime").date.today().year)
    bl.add_argument("--apply", action="store_true", help="確認比對結果後才加：寫入總帳並發行事曆")
    bl.add_argument("--force", action="store_true", help="模擬餘額對不上也照寫（不建議）")
    exp = sub.add_parser("explore", help="探索模式：登入後手動點到明細頁，記錄頁面結構（不含金額）")
    exp.add_argument("login")
    insp = sub.add_parser("inspect", help="列出已開啟的銀行登入頁欄位結構（不讀取內容）")
    insp.add_argument("login")
    fetch = sub.add_parser("fetch-statements", help="從信箱下載信用卡電子帳單 PDF 並試開")
    fetch.add_argument("--months", type=int, default=3, help="往回抓幾個月（預設 3）")
    fetch.add_argument("--bank", action="append", default=[], help="只抓這家（可重複）：fubon taishin sc dbs cathay hsbc ubot")
    fetch.add_argument("--force", action="store_true", help="已下載過的也重新下載")
    fetch.add_argument("--no-notify", action="store_true", help="新帳單不發行事曆提醒")
    fetch.add_argument("--due-reminder", action="store_true", help="另在繳款截止日前一天加一則提醒")
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
    led.add_argument("--check", action="store_true", help="只比對兩表「零用金-淨值」是否每月相等")
    led.add_argument("--rebuild", action="store_true", help="刪掉 含信用卡 表後重新複製並寫入（搭配 --apply）")
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
    elif args.command == "fetch-taishin":
        from .taishin_tx import fetch
        from datetime import date as _date
        fetch(_date.fromisoformat(args.since) if args.since else None, args.keep_open)
    elif args.command == "weekly":
        from .weekly import run as weekly_run
        weekly_run(args.dry_run, args.days, tuple(args.bank))
    elif args.command in ("weekly-install", "weekly-uninstall"):
        from . import weekly
        (weekly.install if args.command == "weekly-install" else weekly.uninstall)()
    elif args.command in ("app-install", "app-status", "app-uninstall"):
        from . import app_service
        {"app-install": app_service.install, "app-status": app_service.status, "app-uninstall": app_service.uninstall}[args.command]()
    elif args.command == "fetch-fubon":
        from datetime import date as _date
        from .fubon_tx import fetch as fubon_fetch
        fubon_fetch(_date.fromisoformat(args.since) if args.since else None, args.keep_open)
    elif args.command == "fetch-next":
        from datetime import date as _date
        from .next_tx import fetch as next_fetch
        next_fetch(_date.fromisoformat(args.since) if args.since else None, args.keep_open)
    elif args.command == "fetch-post":
        from datetime import date as _date
        from .post_tx import fetch as post_fetch
        post_fetch(_date.fromisoformat(args.since) if args.since else None, args.keep_open)
    elif args.command == "fetch-sc":
        from datetime import date as _date
        from .sc_tx import fetch as sc_fetch
        sc_fetch(_date.fromisoformat(args.since) if args.since else None, args.keep_open)
    elif args.command in ("fetch-linebank", "fetch-yuanta"):
        from datetime import date as _date
        from .table_tx import fetch as table_fetch
        table_fetch(args.command.split("-", 1)[1], _date.fromisoformat(args.since) if args.since else None, args.keep_open)
    elif args.command == "bank-review":
        from .bank_ledger import review
        review(args.year)
    elif args.command == "bank-audit":
        from datetime import date as _date
        from .bank_ledger import audit
        banks = tuple(args.bank or ("fubon", "taishin", "next"))
        if args.fetch:
            start = _date(args.year, 1, 1)
            for code in banks:
                print(f"\n=== 下載 {code} {args.year} 全年明細 ===")
                try:
                    if code == "taishin":
                        from .taishin_tx import fetch as f
                    elif code == "fubon":
                        from .fubon_tx import fetch as f
                    elif code == "next":
                        from .next_tx import fetch as f
                    elif code == "sc":
                        from .sc_tx import fetch as f
                    elif code == "post":
                        from .post_tx import fetch as f
                    else:
                        from functools import partial
                        from .table_tx import fetch as tf
                        f = partial(tf, code)
                    f(start)
                except SystemExit as exc:
                    print(f"⚠️ {code} 沒下載成功：{exc}")
        print(audit(args.year, banks))
    elif args.command == "diag":
        import json as _json
        from .credentials import BANK_DIR
        from .taishin_tx import _mask_shape, parse_day
        folder = BANK_DIR / "transactions" / args.bank
        latest = sorted(folder.glob("2*.json"))[-1]
        print(f"檔案：{latest.name}")
        for block in _json.loads(latest.read_text("utf-8")).get("accounts", []):
            rows = block.get("rows") or []
            bad = [i for i, r in enumerate(rows) if not (r and parse_day(r[0]))]
            days = sorted(parse_day(r[0]) for r in rows if r and parse_day(r[0]))
            print(f"\n[{block.get('type')}] {block.get('account')}：存了 {len(rows)} 筆，日期看不懂 {len(bad)} 筆，"
                  f"日期範圍 {days[0] if days else '-'} ～ {days[-1] if days else '-'}")
            print("  欄位：" + " | ".join(block.get("head") or []))
            for i in sorted(set(list(range(0, 2)) + list(range(28, 33)) + bad[:3])):
                if i < len(rows):
                    print(f"  第{i + 1:>3}筆：" + " | ".join(_mask_shape(c) for c in rows[i]))
    elif args.command == "refresh-bank":
        from .mail_activity import BANKS
        from .weekly import refresh_banks
        refresh_banks(tuple(args.bank) or tuple(b.code for b in BANKS), args.year)
    elif args.command == "refresh-cards":
        from .ledger_sync import refresh_cards
        refresh_cards(args.year)
    elif args.command == "publish":
        from .publish import publish
        publish(args.year)
    elif args.command == "messenger-explore":
        from .messenger_notes import explore as m_explore
        m_explore(args.thread)
    elif args.command == "messenger-fetch":
        from datetime import date as _d
        from .messenger_notes import fetch as m_fetch, reparse as m_reparse
        _since = _d.fromisoformat(args.since) if args.since else None
        m_reparse(_since) if args.reparse else m_fetch(_since, args.thread)
    elif args.command == "app-password":
        from .app_auth import set_password_cli
        set_password_cli()
    elif args.command == "bank-ledger":
        from .bank_ledger import run as bank_ledger_run
        bank_ledger_run(args.year, args.apply, args.force)
    elif args.command == "explore":
        from .explore import explore
        explore(args.login, login_bank_code(args.login))
    elif args.command == "inspect":
        from .native_chrome import inspect_page
        inspect_page(login_bank_code(args.login))
    elif args.command == "fetch-statements":
        from .mail_statements import check_statements, fetch_statements, notify_new_statements
        saved = fetch_statements(args.months, banks=tuple(args.bank), force=args.force)
        check_statements(banks=tuple(args.bank))
        if not args.no_notify:
            notify_new_statements(saved, due_reminder=args.due_reminder)
    elif args.command == "google-login":
        from .google_auth import login
        login(args.client_json)
    elif args.command == "ledger":
        from .ledger_sync import run
        run(args.year, apply=args.apply, banks=tuple(args.bank), notes_only=args.notes_only,
            show_unclassified=args.unclassified, check=args.check, rebuild=args.rebuild)
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
