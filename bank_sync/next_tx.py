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

HOST = "https://accessibility.nextbank.com.tw"
TX_DIR = BANK_DIR / "transactions" / "next"

CLICK_TEXT_JS = r"""
(names) => {
  const vis = e => e.getClientRects().length > 0;
  const els = [...document.querySelectorAll('a,button,[role=button],[role=tab],li,span')].filter(vis);
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
    if "/transaction-details/main" in page.url:
        return
    if not page.evaluate(CLICK_TEXT_JS, ["主帳戶明細查詢", "交易明細查詢", "交易明細", "明細查詢"]):
        page.goto(HOST + "/transaction-details")
    page.wait_for_timeout(2000)
    if "/transaction-details/main" not in page.url:
        page.evaluate(CLICK_TEXT_JS, ["主帳戶明細查詢", "主帳戶", "臺幣主帳戶"])
        page.wait_for_timeout(2000)
    if "/transaction-details/main" not in page.url:
        input("  請在 Chrome 點到「主帳戶明細查詢」頁，回到這裡按 Enter：")


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

    since = since or date.today().replace(day=1)
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
            try:
                _goto_details(page)
                for label in _months(since, date.today()):
                    before = page.evaluate(CONTENT_JS)
                    if not page.evaluate(CLICK_TEXT_JS, [label]):
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
    raw_path = TX_DIR / f"{stamp}.json"
    raw_path.write_text(json.dumps({"fetched_at": stamp, "pages": pages}, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(raw_path, 0o600)
    shape_path = BANK_DIR / "_explore" / f"next_shape_{stamp}.txt"
    shape_path.parent.mkdir(parents=True, exist_ok=True)
    shape_path.write_text("\n\n".join(f"[{p['period']}]\n" + "\n".join(shape(p["lines"])[:80]) for p in pages), "utf-8")
    print(f"\n明細（只存在本機）：{raw_path}")
    print(f"格式樣本（可上傳給 Claude）：{shape_path}")
    return raw_path
