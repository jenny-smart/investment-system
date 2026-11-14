"""將來銀行（金融友善網路銀行 accessibility.nextbank.com.tw）：查詢主帳戶明細，存到本機。

探索結果：/transaction-details/main「主帳戶明細查詢」，用按鈕選區間（近30天、2026年11月、2026年10月…），
結果不是 <table>，所以先把結果區的文字逐行存下（只存在本機），另做「格式樣本」給開發對照，確認格式後再解析成交易。
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path

from .credentials import BANK_DIR
from .taishin_tx import keep_new, parse_day, shape_report

HOST = "https://accessibility.nextbank.com.tw"
TX_DIR = BANK_DIR / "transactions" / "next"
STATE_FILE = TX_DIR / "_state.json"
KEY = "TWD:將來主帳戶"

CLICK_TEXT_JS = r"""
(names) => {
  const vis = e => e.getClientRects().length > 0;
  const els = [...document.querySelectorAll('a,button,[role=button],[role=tab],[onclick],li,span,div')].filter(vis);
  for (const n of names) {
    const e = els.find(x => (x.innerText || '').replace(/\s+/g, '') === n.replace(/\s+/g, ''));
    if (e) { e.click(); return n; }
  }
  return null;
}
"""

# 結果區文字：取 main（沒有就 body），去掉按鈕／連結本身的文字
CONTENT_JS = r"""
() => {
  const root = document.querySelector('main') || document.body;
  const skip = new Set([...root.querySelectorAll('button,nav a,header a,footer a')].map(e => (e.innerText || '').replace(/\s+/g, ' ').trim()));
  return (root.innerText || '').split('\n').map(l => l.replace(/\s+/g, ' ').trim()).filter(l => l && !skip.has(l));
}
"""


def _click(page, name: str) -> bool:
    """用真的滑鼠點：依序試「按鈕名稱」「連結名稱」「完全相同文字」「包含文字」（無障礙網站常有隱藏說明字）。"""
    tries = (lambda: page.get_by_role("button", name=name),
             lambda: page.get_by_role("link", name=name),
             lambda: page.get_by_text(name, exact=True),
             lambda: page.get_by_text(name))
    for make in tries:
        try:
            loc = make()
            for i in range(min(loc.count(), 5)):
                item = loc.nth(i)
                if item.is_visible():
                    item.scroll_into_view_if_needed(timeout=3000)
                    item.click(timeout=4000)
                    return True
        except Exception:
            continue
    try:
        return bool(page.evaluate(CLICK_TEXT_JS, [name]))
    except Exception:
        return False


def _months(since: date, today: date) -> list[str]:
    out, y, m = [], today.year, today.month
    while (y, m) >= (since.year, since.month):
        out.append(f"{y}年{m}月")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out


def _wait_lines(page, before: list, timeout_ms: int = 15000) -> list:
    waited, lines = 0, before
    while waited < timeout_ms:
        page.wait_for_timeout(700)
        waited += 700
        lines = page.evaluate(CONTENT_JS)
        if lines != before:
            page.wait_for_timeout(1200)  # 等全部載完
            return page.evaluate(CONTENT_JS)
    return lines


def _goto_details(page) -> None:
    """只用點選切頁，不重新載入網址（重新載入會被將來銀行登出）。"""
    from .login import drain_stdin, open_menu
    # 首頁「功能清單」→ 新臺幣帳戶總覽（/transaction-details）→ 主帳戶明細查詢（/transaction-details/main）
    menu_tried = False
    for step in range(25):  # 登入後首頁要一點時間才出現按鈕
        page.wait_for_timeout(1000)
        if "/transaction-details/main" in page.url:
            return
        if step in (5, 15):
            print(f"  …還在找明細頁（目前網址 {page.url.split('?')[0]}，分頁數 {len(page.context.pages)}）")
        if _click(page, "主帳戶明細查詢"):
            page.wait_for_timeout(2500)
            continue
        if _click(page, "新臺幣帳戶總覽"):
            page.wait_for_timeout(2500)
            continue
        if step >= 8 and not menu_tried and open_menu(page):  # 等了一陣子還找不到，再從右上角三橫線選單找
            menu_tried = True
            _click(page, "新臺幣帳戶總覽")
            page.wait_for_timeout(2500)
    if "/transaction-details/main" not in page.url:
        drain_stdin()
        input("  請在 Chrome 點到「主帳戶明細查詢」頁，回到這裡按 Enter：")


HEAD = ["交易日", "時間", "摘要", "金額", "餘額", "明細描述", "備註", "交易類型"]
FIELDS = (("金額", "amount"), ("交易類型", "type"), ("明細描述", "desc"), ("摘要", "memo"),
          ("交易時間", "time"), ("備註說明", "note"), ("帳戶餘額", "balance"))


def _money(text: str) -> str:
    m = re.search(r"-?\$?\s*-?[\d,]+(?:\.\d+)?", text.replace("新臺幣", ""))
    return m.group(0).replace("$", "").replace(" ", "") if m else ""


def parse_lines(lines: list[str]) -> list[list[str]]:
    """將來明細是一筆好幾行：金額／交易類型／明細描述／摘要／交易時間／備註說明／帳戶餘額。"""
    rows, cur = [], None
    for line in lines:
        label = next(((lab, key) for lab, key in FIELDS if line.startswith(lab)), None)
        if label is None:
            continue
        lab, key = label
        value = line[len(lab):].strip()
        if key == "amount":
            if cur:
                rows.append(cur)
            cur = {"amount": _money(value)}
            continue
        if cur is None:
            continue
        cur[key] = _money(value) if key == "balance" else value
    if cur:
        rows.append(cur)
    out = []
    for r in rows:
        day, _, clock = (r.get("time", "") + " ").partition(" ")
        if not parse_day(day):
            continue
        out.append([day, clock.strip(), r.get("memo", ""), r.get("amount", ""), r.get("balance", ""),
                    r.get("desc", ""), "" if r.get("note") == "無" else r.get("note", ""), r.get("type", "")])
    return out


def shape(lines: list[str]) -> list[str]:
    """格式樣本：重複出現的短標籤（像「交易日期」）保留，其他中文→○、數字→9、英文→x。"""
    counts = {}
    for l in lines:
        counts[l] = counts.get(l, 0) + 1
    out = []
    for l in lines:
        if counts[l] >= 2 and len(l) <= 8 and not re.search(r"\d", l):
            out.append(l)
        else:
            t = re.sub(r"\d", "9", l)
            t = re.sub(r"[A-Za-z]", "x", t)
            out.append(re.sub(r"[一-鿿]", "○", t))
    return out


def fetch(since: date = None, keep_open: bool = False) -> Path:
    from playwright.sync_api import sync_playwright
    from .login import acquire_lock, launch_context, logout_all, open_bank, wait_for_logins

    progress = {}
    if not since:
        try:
            progress = json.loads(STATE_FILE.read_text("utf-8"))
        except Exception:
            progress = {}
    start = parse_day(progress.get(KEY, {}).get("last_date", "")) or since or date.today().replace(day=1)
    since = start
    TX_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    pages = []
    lock = acquire_lock()
    try:
        with sync_playwright() as p:
            context = launch_context(p)
            state = open_bank(context, "next", "next")
            if not state.logged_in:
                print("請在 Chrome 完成將來銀行登入…")
                wait_for_logins(context, [state], 300)
            if not state.logged_in:
                raise SystemExit("將來銀行沒有登入成功，停止。")
            page = state.page
            page.wait_for_timeout(2000)
            live = [pg for pg in context.pages if not pg.is_closed() and "nextbank.com.tw" in pg.url and "/login" not in pg.url]
            if live:
                page = live[-1]  # 登入後真正顯示功能清單的那個分頁
                page.bring_to_front()
            try:
                _goto_details(page)
                for label in _months(since, date.today()):
                    before = page.evaluate(CONTENT_JS)
                    clicked = None
                    for _ in range(15):  # 按鈕可能還沒出現
                        clicked = _click(page, label)
                        if clicked:
                            break
                        page.wait_for_timeout(700)
                    if not clicked:
                        print(f"  找不到「{label}」按鈕，略過")
                        continue
                    lines = _wait_lines(page, before)
                    pages.append({"period": label, "lines": lines})
                    print(f"  {label}：結果區 {len(lines)} 行")
            except KeyboardInterrupt:
                print("⚠️ 已中斷（Ctrl+C），先幫你登出…")
            except Exception as exc:
                print(f"⚠️ 中斷：{exc}")
            if keep_open:
                input("Chrome 保持開著，按 Enter 關閉…")
            logout_all(context)
            context.close()
    finally:
        lock.close()
    rows = []
    for pg in pages:
        for r in parse_lines(pg["lines"]):
            if r not in rows:
                rows.append(r)
    rows.sort(key=lambda r: (r[0], r[1]))
    total = len(rows)
    accounts = []
    if pages:
        new, progress[KEY] = keep_new(rows, progress.get(KEY, {}), since)
        accounts.append({"type": "TWD", "account": "將來主帳戶", "ledger_row": "將來", "from": since.isoformat(),
                         "head": HEAD, "rows": new})
        print(f"  將來主帳戶：{since:%m/%d} 起共 {total} 筆，新的 {len(new)} 筆")
        STATE_FILE.write_text(json.dumps(progress, ensure_ascii=False, indent=1), "utf-8")
        os.chmod(STATE_FILE, 0o600)
    raw_path = TX_DIR / f"{stamp}.json"
    raw_path.write_text(json.dumps({"fetched_at": stamp, "accounts": accounts}, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(raw_path, 0o600)
    shape_path = BANK_DIR / "_explore" / f"next_shape_{stamp}.txt"
    shape_path.parent.mkdir(parents=True, exist_ok=True)
    shape_path.write_text(shape_report(accounts), "utf-8")
    print(f"\n明細（只存在本機）：{raw_path}")
    print(f"格式樣本（可上傳給 Claude）：{shape_path}")
    return raw_path
