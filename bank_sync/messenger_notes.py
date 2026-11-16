"""Messenger 記帳對話：讀你在 Messenger 對話裡寫的「今天買了什麼」，之後拿來對銀行／信用卡明細（同一天、同金額）。

第一步（探索）：用程式開的 Chrome 打開對話，你登入 Facebook（只要一次，之後會記住），
捲到要的日期後按 Enter，程式把畫面上的訊息存在本機 ~/Bank account/messenger/（原文，只在本機），
另存一份「格式樣本」（數字→9、中文→○）在 ~/Bank account/_explore/ 給開發對照。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

from .credentials import BANK_DIR

DEFAULT_THREAD = "https://www.messenger.com/t/111433143973520"
MSG_DIR = BANK_DIR / "messenger"

# 對話區：每個 role=row 的文字（日期分隔列、訊息）＋可能的時間提示（aria-label / title / data-tooltip）
ROWS_JS = r"""
() => {
  const vis = e => e.getClientRects().length > 0;
  const clean = t => (t || '').replace(/\s+/g, ' ').trim();
  const main = document.querySelector('[role="main"]') || document.body;
  const rows = [...main.querySelectorAll('[role="row"]')].filter(vis);
  return rows.map(r => {
    const tips = [...r.querySelectorAll('[aria-label],[title],[data-tooltip-content]')]
      .map(e => e.getAttribute('aria-label') || e.getAttribute('title') || e.getAttribute('data-tooltip-content') || '')
      .filter(t => /\d/.test(t)).slice(0, 3);
    const h = r.querySelector('h4,h3,[role="heading"]');
    return {text: clean(r.innerText).slice(0, 400), heading: h ? clean(h.innerText) : '', tips: tips};
  });
}
"""


def _shape(text: str) -> str:
    text = re.sub(r"\d", "9", text or "")
    text = re.sub(r"[A-Za-z]", "x", text)
    return re.sub(r"[一-鿿]", "○", text)


def explore(thread: str = DEFAULT_THREAD) -> Path:
    from playwright.sync_api import sync_playwright
    from .login import acquire_lock, launch_context
    MSG_DIR.mkdir(parents=True, exist_ok=True)
    (BANK_DIR / "_explore").mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    raw_path = MSG_DIR / f"raw_{stamp}.json"
    shape_path = BANK_DIR / "_explore" / f"messenger_shape_{stamp}.txt"
    captured = []
    lock = acquire_lock()
    try:
        with sync_playwright() as p:
            context = launch_context(p)
            page = context.new_page()
            page.goto(thread)
            print("請在 Chrome 登入 Facebook／Messenger（第一次才需要），打開記帳對話。")
            print("往上捲到想要的日期（例如這個月 1 號），讓訊息顯示在畫面上，回到這裡按 Enter 記錄；可以重複；完成輸入 q。")
            while True:
                if input("Enter＝記錄畫面上的訊息／q＝結束：").strip().lower() == "q":
                    break
                rows = page.evaluate(ROWS_JS)
                captured.append({"time": datetime.now().strftime("%H:%M:%S"), "url": page.url.split("?")[0], "rows": rows})
                raw_path.write_text(json.dumps(captured, ensure_ascii=False, indent=1), "utf-8")
                os.chmod(raw_path, 0o600)
                print(f"  記錄了 {len(rows)} 列")
            context.close()
    finally:
        lock.close()
    lines = []
    for snap in captured:
        lines.append(f"[{snap['time']}] {len(snap['rows'])} 列")
        for r in snap["rows"][:80]:
            lines.append("  " + _shape(r["text"])[:120] + (f"  ｜標題：{_shape(r['heading'])}" if r["heading"] else "")
                         + (f"  ｜提示：{' / '.join(_shape(t)[:40] for t in r['tips'])}" if r["tips"] else ""))
    shape_path.write_text("\n".join(lines), "utf-8")
    print(f"\n訊息原文（只在本機）：{raw_path}")
    print(f"格式樣本（可上傳給 Claude）：{shape_path}")
    return shape_path
