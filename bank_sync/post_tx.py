"""郵局（網路郵局 ipost）：查詢存簿交易明細，存到本機。

探索結果：我的帳戶 → 帳戶查詢 → 交易明細（單頁網站 /pst/index.html），每頁筆數下拉（50筆／100筆／全部）、
「存成CSV」。結果不是 <table>，所以用「全部」＋「存成CSV」下載完整明細再讀（下載檔只存在本機）。
欄位：交易日期 交易時間／摘要／沖銷記號／提款金額／存款金額／結存金額／備註／附言（日期是民國年）。
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import time
from datetime import date, datetime
from pathlib import Path

from .credentials import BANK_DIR
from .taishin_tx import keep_new, parse_day, shape_report

TX_DIR = BANK_DIR / "transactions" / "post"
STATE_FILE = TX_DIR / "_state.json"
HEAD = ["交易日期", "交易時間", "摘要", "提款金額", "存款金額", "結存金額", "備註", "附言"]

READY_JS = "() => /結存金額/.test(document.body.innerText) && /存成CSV/.test(document.body.innerText)"


def _click(page, *names) -> bool:
    for n in names:
        for make in (lambda: page.get_by_role("link", name=n, exact=True), lambda: page.get_by_text(n, exact=True)):
            try:
                loc = make()
                for i in range(min(loc.count(), 5)):
                    if loc.nth(i).is_visible():
                        loc.nth(i).click(timeout=4000)
                        return True
            except Exception:
                continue
    return False


def _goto(page) -> None:
    from .login import drain_stdin
    for step in range(12):
        try:
            if page.evaluate(READY_JS):
                return
        except Exception:
            pass
        if step % 3 == 0:
            _click(page, "我的帳戶")
        elif step % 3 == 1:
            _click(page, "帳戶查詢")
        else:
            _click(page, "交易明細", "存簿交易明細", "交易明細查詢")
        page.wait_for_timeout(1500)
    drain_stdin()
    input("  請在 Chrome 點到「我的帳戶 → 帳戶查詢 → 交易明細」，看到明細後回到這裡按 Enter：")


def _roc(text: str) -> str:
    """民國 115/11/05 → 2026/11/05。"""
    m = re.search(r"(\d{2,4})[/\-.](\d{1,2})[/\-.](\d{1,2})", text or "")
    if not m:
        return ""
    y = int(m.group(1))
    y = y + 1911 if y < 1911 else y
    return f"{y}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"


def parse_csv(raw: bytes) -> list[list[str]]:
    text = None
    for enc in ("utf-8-sig", "big5", "cp950", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return []
    rows = list(csv.reader(io.StringIO(text)))
    hi = next((i for i, r in enumerate(rows) if any("摘要" in c for c in r)), None)
    if hi is None:
        return []
    head = [c.strip() for c in rows[hi]]

    def col(*names):
        return next((i for i, h in enumerate(head) for n in names if n in h), None)

    i_date, i_time = col("交易日期"), col("交易時間")
    i_memo, i_out, i_in = col("摘要"), col("提款", "支出"), col("存款", "存入")
    i_bal, i_note, i_msg = col("結存", "餘額"), col("備註"), col("附言")
    out = []
    for r in rows[hi + 1:]:
        get = lambda i: (r[i].strip() if i is not None and i < len(r) else "")
        day = _roc(get(i_date))
        if not day:
            continue
        if i_time is None or i_time == i_date:  # 「交易日期 交易時間」同一欄
            clock = get(i_date).split(" ")[-1] if " " in get(i_date) else ""
        else:
            clock = get(i_time)
        out.append([day, clock, get(i_memo), get(i_out), get(i_in), get(i_bal), get(i_note), get(i_msg)])
    return out


def fetch(since: date = None, keep_open: bool = False) -> Path:
    from playwright.sync_api import sync_playwright
    from .login import acquire_lock, launch_context, logout_all, open_bank, wait_for_logins
    from .progress_log import log_run
    progress = {}
    if not since:
        try:
            progress = json.loads(STATE_FILE.read_text("utf-8"))
        except Exception:
            progress = {}
    since = since or date.today().replace(day=1)
    TX_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    results, problem = [], ""
    lock = acquire_lock()
    try:
        with sync_playwright() as p:
            context = launch_context(p)
            state = open_bank(context, "post_jenny", "post")
            if not state.logged_in:
                print("請在 Chrome 完成郵局登入（輸入驗證碼）…")
                wait_for_logins(context, [state], 300)
            if not state.logged_in:
                raise SystemExit("郵局沒有登入成功，停止。")
            page = state.page
            page.wait_for_timeout(2000)
            try:
                _goto(page)
                try:  # 每頁筆數選「全部」
                    page.evaluate("""() => { const s = [...document.querySelectorAll('select')].find(x => [...x.options].some(o => o.text.trim() === '全部'));
                        if (s) { s.selectedIndex = [...s.options].findIndex(o => o.text.trim() === '全部'); s.dispatchEvent(new Event('change', {bubbles: true})); } }""")
                    page.wait_for_timeout(1500)
                except Exception:
                    pass
                with page.expect_download(timeout=30000) as info:
                    if not _click(page, "存成CSV"):
                        raise RuntimeError("找不到「存成CSV」")
                target = TX_DIR / f"{stamp}_post.csv"
                info.value.save_as(str(target))
                os.chmod(target, 0o600)
                rows = parse_csv(target.read_bytes())
                key = "TWD:郵局存簿"
                start = parse_day(progress.get(key, {}).get("last_date", "")) or since
                total = len(rows)
                rows.sort(key=lambda r: (r[0], r[1]))
                new, progress[key] = keep_new(rows, progress.get(key, {}), start)
                days = [parse_day(r[0]) for r in rows]
                span = f"{min(days):%Y/%m/%d}～{max(days):%Y/%m/%d}" if days else "沒有資料"
                results.append({"type": "TWD", "account": "郵局存簿", "ledger_row": "郵局", "from": start.isoformat(),
                                "head": HEAD, "rows": new})
                print(f"  郵局存簿：下載 {total} 筆（{span}），新的 {len(new)} 筆")
                if days and min(days) > start:
                    print(f"  ⚠️ 郵局下載的明細從 {min(days):%m/%d} 開始，比要的 {start:%m/%d} 晚；查詢期間要調整（請告訴我郵局的期間怎麼選）")
            except KeyboardInterrupt:
                problem = "已中斷（Ctrl+C）"
                print("⚠️ 已中斷（Ctrl+C），先幫你登出…")
            except Exception as exc:
                problem = f"中斷：{exc}"
                print(f"⚠️ 中斷：{exc}")
            if keep_open:
                input("Chrome 保持開著，按 Enter 關閉…")
            logout_all(context)
            context.close()
    finally:
        lock.close()
    STATE_FILE.write_text(json.dumps(progress, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(STATE_FILE, 0o600)
    raw_path = TX_DIR / f"{stamp}.json"
    raw_path.write_text(json.dumps({"fetched_at": stamp, "accounts": results}, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(raw_path, 0o600)
    shape_path = BANK_DIR / "_explore" / f"post_shape_{stamp}.txt"
    shape_path.parent.mkdir(parents=True, exist_ok=True)
    shape_path.write_text(shape_report(results), "utf-8")
    print(f"\n明細（只存在本機）：{raw_path}")
    print(f"格式樣本（可上傳給 Claude）：{shape_path}")
    log_run("郵局明細", since, TX_DIR, results, problem)
    return raw_path
