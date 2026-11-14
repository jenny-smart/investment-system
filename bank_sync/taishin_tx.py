"""台新網銀：自動查詢台幣／外幣交易明細，存到本機（不上傳任何地方）。

頁面結構來自 explore 探索模式：
  台幣 #/RB0102/0100：帳號選單（請選擇帳號）、查詢期間、資料排序、按「查詢」
  外幣 #/RB0802/0100：account、currency、periodFixed、資料排序、按「確認查詢」

存檔：~/Bank account/transactions/taishin/<時間>.json（chmod 600）
另產生一份「格式樣本」（數字變 9、文字變 ○，只保留摘要與欄位名稱）給開發對照用。
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from .credentials import BANK_DIR

BASE = "https://my.taishinbank.com.tw/TIBNetBank/svc/rwd/"
TWD_URL = BASE + "#/RB0102/0100"
FX_URL = BASE + "#/RB0802/0100"
TX_DIR = BANK_DIR / "transactions" / "taishin"

# 帳戶名稱關鍵字 → 細帳列名稱（沒列到的帳戶照抓，但標「未對應」）
TWD_ACCOUNTS = {
    "建北綜活": "台新-建北",
    "信義MMR": "台新-信義",
    "Richart二類": "台新-Richard",
    "Richart子帳戶": "台新-子帳戶",
    "內湖綜活": "台新-內湖新轉",
    "中和綜活": "台新-建北",  # Jenny：中和綜活比照建北登記
}
FX_CURRENCIES = {"人民幣": "台新人民幣", "日圓": "台新日幣", "美元": "台新美金", "南非幣": "台新南非"}

TABLE_JS = r"""
(need) => {
  const vis = e => e.getClientRects().length > 0;
  const clean = t => (t || '').replace(/\s+/g, ' ').trim();
  for (const t of document.querySelectorAll('table')) {
    if (!vis(t)) continue;
    const head = [...t.querySelectorAll('th')].map(c => clean(c.innerText));
    if (!need.every(n => head.includes(n))) continue;
    const rows = [];
    t.querySelectorAll('tbody tr').forEach(r => {
      if (!vis(r)) return;
      const cells = [...r.children].filter(vis).map(c => clean(c.innerText));
      if (cells.some(Boolean)) rows.push(cells);
    });
    const thVisible = [...t.querySelectorAll('th')].filter(vis).map(c => clean(c.innerText));
    return {head: thVisible, rows: rows};
  }
  return null;
}
"""

SELECT_JS = r"""
([marker, index, label]) => {
  const sel = [...document.querySelectorAll('select')].find(s => [...s.options].some(o => o.text.includes(marker)) && s.getClientRects().length > 0)
           || [...document.querySelectorAll('select')].find(s => [...s.options].some(o => o.text.includes(marker)));
  if (!sel) return null;
  const opts = [...sel.options];
  if (index === -1) return opts.map(o => o.text.trim());
  let i = index;
  if (label) { i = opts.findIndex(o => o.text.trim() === label); if (i < 0) return 'missing:' + label; }
  sel.selectedIndex = i;
  sel.dispatchEvent(new Event('input', {bubbles: true}));
  sel.dispatchEvent(new Event('change', {bubbles: true}));
  return opts[i].text.trim();
}
"""

CLICK_JS = r"""
(names) => {
  const vis = e => e.getClientRects().length > 0;
  const els = [...document.querySelectorAll('button,a,input[type=button],input[type=submit],[role=button]')].filter(vis);
  for (const n of names) {
    const e = els.find(x => (x.innerText || x.value || '').replace(/\s+/g, '').trim() === n);
    if (e) { e.click(); return n; }
  }
  return null;
}
"""


def _mask_shape(text: str) -> str:
    text = re.sub(r"\d", "9", text)
    text = re.sub(r"[A-Za-z]", "x", text)
    return re.sub(r"[一-鿿]", "○", text)


def _short(label: str) -> str:
    """帳戶選項文字只留名稱與末 3 碼。"""
    m = re.search(r"(\d{3})\D*$", label.split(" ")[0]) if label else None
    name = re.sub(r"^[\d\-\s*]+", "", label).strip()
    return f"****{m.group(1) if m else ''} {name}".strip()


def _ledger_row(name: str) -> str:
    return next((row for key, row in TWD_ACCOUNTS.items() if key in name), "")


def _goto(page, url: str, link_text: str, marker: str, timeout_s: float = 25) -> None:
    """在網銀單頁程式裡切換頁面：只改 #hash 或點選單，不重新載入（重新載入會被台新登出）。"""
    route = url.split("#", 1)[1] if "#" in url else ""
    if route and "/svc/rwd/" in page.url:
        page.evaluate("h => { window.location.hash = h; }", route)
    else:
        page.evaluate("t => { const a = [...document.querySelectorAll('a')].find(x => x.innerText.trim() === t); if (a) a.click(); }", link_text)
    deadline = time.time() + timeout_s
    clicked = False
    while time.time() < deadline:
        if _logged_out(page):
            raise RuntimeError("台新已登出")
        if page.evaluate(SELECT_JS, [marker, -1, ""]):
            return
        if not clicked and time.time() > deadline - timeout_s / 2:
            page.evaluate("t => { const a = [...document.querySelectorAll('a')].find(x => x.innerText.trim() === t); if (a) a.click(); }", link_text)
            clicked = True
        page.wait_for_timeout(500)
    raise RuntimeError(f"找不到「{link_text}」頁面的選單（目前網址 {page.url.split('?')[0]}）")


def _logged_out(page) -> bool:
    try:
        body = page.evaluate("() => document.body.innerText")
    except Exception:
        return False
    return any(k in body for k in ("已登出", "請重新登入", "登入逾時", "連線逾時"))


def _query(page, button_names: list[str], need: list[str], timeout_s: float = 20) -> dict:
    before = json.dumps(page.evaluate(TABLE_JS, need), ensure_ascii=False)
    if not page.evaluate(CLICK_JS, button_names):
        raise RuntimeError(f"找不到按鈕：{button_names}")
    deadline = time.time() + timeout_s
    result = None
    while time.time() < deadline:
        page.wait_for_timeout(700)
        if _logged_out(page):
            raise RuntimeError("台新已登出")
        result = page.evaluate(TABLE_JS, need)
        body = page.evaluate("() => document.body.innerText")
        if result and json.dumps(result, ensure_ascii=False) != before:
            break
        if "查無" in body or "無交易" in body:
            return {"head": [], "rows": []}
    rows = list((result or {}).get("rows", []))
    for _ in range(30):  # 有「更多」就一直點
        if not page.evaluate(CLICK_JS, ["載入更多", "顯示更多", "更多", "下一頁"]):
            break
        page.wait_for_timeout(1200)
        more = page.evaluate(TABLE_JS, need) or {}
        new = [r for r in more.get("rows", []) if r not in rows]
        if not new:
            break
        rows.extend(new)
    return {"head": (result or {}).get("head", []), "rows": rows}


def fetch_twd(page, period: str = "2個月") -> list[dict]:
    _goto(page, TWD_URL, "查詢交易明細", "請選擇帳號")
    options = page.evaluate(SELECT_JS, ["請選擇帳號", -1, ""])
    out = []
    for i, label in enumerate(options):
        if i == 0 or "請選擇" in label:
            continue
        page.evaluate(SELECT_JS, ["請選擇帳號", i, ""])
        page.evaluate(SELECT_JS, ["請選擇查詢期間", 0, period])
        page.evaluate(SELECT_JS, ["由新到舊", 0, "由舊到新"])
        page.wait_for_timeout(400)
        try:
            data = _query(page, ["查詢"], ["交易日", "摘要"])
        except Exception as exc:
            if "登出" in str(exc):
                raise
            data = {"head": [], "rows": [], "error": str(exc)}
        name = _short(label)
        out.append({"type": "TWD", "account": name, "ledger_row": _ledger_row(name), **data})
        print(f"  台幣 {name}：{len(data['rows'])} 筆{'' if _ledger_row(name) else '（細帳未對應）'}{'  ⚠️ ' + data['error'] if data.get('error') else ''}")
    return out


def fetch_fx(page, period: str = "2個月") -> list[dict]:
    _goto(page, FX_URL, "查詢外幣交易明細", "請選擇查詢帳號")
    options = page.evaluate(SELECT_JS, ["請選擇查詢帳號", -1, ""])
    out = []
    for i, label in enumerate(options):
        if i == 0 or "請選擇" in label:
            continue
        page.evaluate(SELECT_JS, ["請選擇查詢帳號", i, ""])
        page.wait_for_timeout(600)
        page.evaluate(SELECT_JS, ["請選擇幣別", 0, "全部"])
        page.evaluate(SELECT_JS, ["請選擇查詢期間", 0, period])
        page.evaluate(SELECT_JS, ["由新到舊", 0, "由舊到新"])
        page.wait_for_timeout(400)
        try:
            data = _query(page, ["確認查詢"], ["交易日", "幣別", "摘要"])
        except Exception as exc:
            if "登出" in str(exc):
                raise
            data = {"head": [], "rows": [], "error": str(exc)}
        name = _short(label)
        out.append({"type": "FX", "account": name, **data})
        print(f"  外幣 {name}：{len(data['rows'])} 筆{'  ⚠️ ' + data['error'] if data.get('error') else ''}")
    return out


def shape_report(results: list[dict], per_account: int = 4) -> str:
    """給開發對照的格式樣本：摘要保留，其他欄位數字→9、英文→x、中文→○。"""
    lines = []
    for block in results:
        lines.append(f"[{block['type']}] {block['account']}  →  {block.get('ledger_row') or '未對應'}  共 {len(block['rows'])} 筆")
        lines.append("  欄位：" + " | ".join(block.get("head", [])))
        head = block.get("head", [])
        keep = {i for i, h in enumerate(head) if h in ("摘要", "幣別")}
        for row in block["rows"][:per_account]:
            lines.append("  " + " | ".join(c if i in keep else _mask_shape(c) for i, c in enumerate(row)))
        if block.get("error"):
            lines.append("  錯誤：" + block["error"])
    return "\n".join(lines)


def fetch(period: str = "2個月", keep_open: bool = False) -> Path:
    from playwright.sync_api import sync_playwright
    from .login import acquire_lock, launch_context, open_bank, wait_for_logins

    TX_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    lock = acquire_lock()
    try:
        with sync_playwright() as p:
            context = launch_context(p)
            state = open_bank(context, "taishin", "taishin")
            if not state.logged_in:
                print("請在 Chrome 完成台新登入（輸入驗證碼）…")
                wait_for_logins(context, [state], 300)
            if not state.logged_in:
                raise SystemExit("台新沒有登入成功，停止。")
            page = state.page
            page.wait_for_timeout(2000)
            print(f"登入後網址：{page.url.split('?')[0]}")
            results = []
            try:
                print("查詢台幣交易明細…")
                results += fetch_twd(page, period)
                print("查詢外幣交易明細…")
                results += fetch_fx(page, period)
            except Exception as exc:
                print(f"⚠️ 中斷：{exc}（目前網址 {page.url.split('?')[0]}）")
            if keep_open:
                input("Chrome 保持開著，按 Enter 關閉…")
            context.close()
    finally:
        lock.close()
    raw_path = TX_DIR / f"{stamp}.json"
    raw_path.write_text(json.dumps({"fetched_at": stamp, "period": period, "accounts": results}, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(raw_path, 0o600)
    shape_path = BANK_DIR / "_explore" / f"taishin_shape_{stamp}.txt"
    shape_path.parent.mkdir(parents=True, exist_ok=True)
    shape_path.write_text(shape_report(results), "utf-8")
    print(f"\n明細（只存在本機）：{raw_path}")
    print(f"格式樣本（可上傳給 Claude）：{shape_path}")
    return raw_path
