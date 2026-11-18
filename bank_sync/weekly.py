"""每週三排程：先查信（列出通知）→ 每家銀行都登入確認（一家抓完登出再下一家）→ 信用卡帳單 → 發布到網頁。

python3 -m bank_sync weekly              手動跑一次（會先列出要登入哪幾家，按 Enter 開始）
python3 -m bank_sync weekly --dry-run    只查信、列出要登入哪幾家
python3 -m bank_sync weekly-install      裝成 Mac 排程：每週三 11:00 自動打開「終端機」跑 weekly
python3 -m bank_sync weekly-uninstall    移除排程
"""
from __future__ import annotations

import os
import plistlib
import shlex
import subprocess
import sys
import traceback
from pathlib import Path

from .credentials import BANK_DIR

LABEL = "com.jenny.bank-weekly"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
REPO = Path(__file__).resolve().parent.parent
LOG = BANK_DIR / "_app_logs" / "weekly.log"
WEEKDAY, HOUR, MINUTE = 3, 11, 0   # 週三 11:00


def _fetch(code: str) -> None:
    if code == "taishin":
        from .taishin_tx import fetch
        fetch(None, False)
    elif code == "fubon":
        from .fubon_tx import fetch
        fetch(None, False)
    elif code == "next":
        from .next_tx import fetch
        fetch(None, False)
    elif code == "post":
        from .post_tx import fetch
        fetch(None, False)
    elif code == "sc":
        from .sc_tx import fetch
        fetch(None, False)
    elif code in ("linebank", "yuanta"):
        from .table_tx import fetch
        fetch(code, None, False)


def run(dry_run: bool = False, days: int = 7, only: tuple = (), ask: bool = True) -> list[str]:
    from .mail_activity import check
    try:
        plan = check(days)
    except (Exception, SystemExit) as exc:
        from .mail_activity import BANKS
        print(f"⚠️ 信箱讀不到（{exc}）→ 照樣每家都登入")
        plan = [{"code": b.code, "name": b.name, "run": True} for b in BANKS]
    todo = [b for b in plan if b["run"] and (not only or b["code"] in only)]
    if not todo:
        print("（沒有要登入的銀行）")
    if dry_run:
        return [b["code"] for b in todo]
    if todo and ask:
        names = "、".join(b["name"] for b in todo)
        if input(f"\n要依序登入：{names}。按 Enter 開始（輸入 n 取消）：").strip().lower() == "n":
            return []
    done = []
    for b in todo:
        print(f"\n━━━ {b['name']} ━━━")
        try:
            _fetch(b["code"])
            done.append(b["code"])
        except KeyboardInterrupt:
            print("⚠️ 已中斷，跳到下一家")
        except (Exception, SystemExit):
            print(f"⚠️ {b['name']} 失敗，跳到下一家：")
            traceback.print_exc(limit=2)
    print("\n━━━ 信用卡帳單（信箱）━━━")
    try:
        from .mail_statements import check_statements, fetch_statements
        saved = fetch_statements(1)  # 只看最近一個月的信；下載過的不重抓（statements/_fetched.json）
        new_files = [f for item in saved for f in item["files"]]
        if new_files:
            check_statements(only_files=new_files)
        else:
            print("沒有新帳單（之前下載過的都存在本機，不重抓）")
    except (Exception, SystemExit) as exc:
        print(f"⚠️ 信用卡帳單沒抓到：{exc}")
    print("\n━━━ 發布到網頁（銀行明細／信用卡明細）━━━")
    try:
        from datetime import date
        from .publish import publish
        publish(date.today().year)
    except (Exception, SystemExit) as exc:
        print(f"⚠️ 發布失敗：{exc}")
    try:
        from .progress_log import log_run
        log_run("每週銀行更新", None, BANK_DIR / "transactions", [],
                message=f"登入：{'、'.join(b['name'] for b in todo) or '無'}；完成：{'、'.join(b['name'] for b in todo if b['code'] in done) or '無'}")
    except Exception:
        pass
    return done


def install() -> None:
    if sys.platform != "darwin":
        raise SystemExit("排程只支援 macOS。")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    cmd = f"cd {shlex.quote(str(REPO))} && {shlex.quote(sys.executable)} -m bank_sync weekly"
    script = f'tell application "Terminal" to activate\ntell application "Terminal" to do script "{cmd}"'
    config = {
        "Label": LABEL,
        "ProgramArguments": ["/usr/bin/osascript", "-e", script],
        "StartCalendarInterval": {"Weekday": WEEKDAY, "Hour": HOUR, "Minute": MINUTE},
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
    }
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], capture_output=True)
    PLIST.write_bytes(plistlib.dumps(config))
    result = subprocess.run(["launchctl", "bootstrap", domain, str(PLIST)], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"排程安裝失敗：{result.stderr.strip() or result.stdout.strip()}")
    print("✓ 已安裝：每週三 11:00 自動打開「終端機」，先查信，再每家銀行都登入確認。")
    print("  （那時 Mac 在睡眠的話，醒來後會補跑一次；第一次可能會問是否允許控制「終端機」，請按允許）")


def uninstall() -> None:
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    if PLIST.exists():
        PLIST.unlink()
    print("✓ 已移除每週排程。")
