"""LINE Bank、元大：明細是一般 <table>，用同一支程式查詢、存到本機（只存在本機）。

LINE Bank（accessibility.linebank.com.tw/transaction「帳戶交易明細查詢」）：帳戶下拉 #account-dropdown → 按「查詢」，
  表格欄位 時間／摘要／金額（金額前面寫存入或支出）。
元大（/nib/tx/transactiondetails「交易明細查詢」）：帳號下拉 #acctno、「自選」起訖日 #sdate／#edate → 「確認送出」，
  表格欄位 帳務日期／交易日期／交易時間／交易說明／支出金額／存入金額／帳面餘額／票據號碼／備註。
每個帳戶從上次最後一筆日期查到今天、去重、記進度；存成 [日期, …原本欄位]。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .credentials import BANK_DIR
from .taishin_tx import CLICK_JS, keep_new, parse_day, shape_report


@dataclass
class TableBank:
    code: str
    name: str
    ledger: str
    nav_links: tuple            # 從首頁點到明細頁的連結文字
    account_select: str         # 帳號下拉的 CSS
    query_buttons: tuple        # 查詢按鈕／連結文字
    need: tuple                 # 結果表格一定有的欄名
    date_col: str               # 哪一欄是日期
    custom_dates: tuple = ()    # (點「自選」的文字, 起日 CSS, 迄日 CSS)
    max_days: int = 365


BANKS = {
    "linebank": TableBank("linebank", "LINE Bank", "連線", ("帳戶交易明細查詢",), "#account-dropdown", ("查詢",),
                          ("時間", "摘要", "金額"), "時間"),
    "yuanta": TableBank("yuanta", "元大銀行", "元大", ("臺幣交易明細查詢",), "#acctno", ("確認送出",),
                        ("帳務日期", "交易說明"), "帳務日期", ("自選", "#sdate", "#edate"), 365),
}

TABLE_JS = r"""
(need) => {
  const vis = e => e.getClientRects().length > 0;
  const clean = t => (t || '').replace(/\s+/g, ' ').trim();
  for (const t of document.querySelectorAll('table')) {
    if (!vis(t)) continue;
    const rows = [...t.rows];
    const hi = rows.findIndex(r => { const c = [...r.cells].map(x => clean(x.innerText)); return need.every(n => c.includes(n)); });
    if (hi < 0) continue;
    const head = [...rows[hi].cells].map(x => clean(x.innerText));
    const data = [];
    for (const r of rows.slice(hi + 1)) {
      if (!vis(r)) continue;
      const cells = [...r.cells].map(x => clean(x.innerText));
      if (cells.length >= Math.min(head.length, need.length) && cells.some(Boolean)) data.push(cells);
    }
    return {head: head, rows: data};
  }
  return null;
}
"""

SELECT_JS = r"""
([css, index]) => {
  const s = document.querySelector(css);
  if (!s) return null;
  const opts = [...s.options].map(o => o.text.replace(/\s+/g, ' ').trim());
  if (index < 0) return opts;
  s.selectedIndex = index;
  for (const ev of ['input', 'change']) s.dispatchEvent(new Event(ev, {bubbles: true}));
  if (window.jQuery) { try { window.jQuery(s).trigger('change'); } catch (e) {} }
  return opts[index];
}
"""

DATES_JS = r"""
([a, b, va, vb]) => {
  for (const [css, v] of [[a, va], [b, vb]]) {
    const e = document.querySelector(css);
    if (!e) return 'missing ' + css;
    e.removeAttribute('readonly');
    e.value = v;
    for (const ev of ['input', 'change', 'blur']) e.dispatchEvent(new Event(ev, {bubbles: true}));
    if (window.jQuery) { try { window.jQuery(e).val(v).trigger('change'); } catch (x) {} }
  }
  return 'ok';
}
"""


def _short(label: str) -> str:
    import re
    return re.sub(r"\d[\d\-]{3,}\d", lambda m: "****" + re.sub(r"\D", "", m.group(0))[-3:], label or "").strip()


def _click_text(page, names) -> bool:
    for n in names:
        for make in (lambda: page.get_by_role("link", name=n, exact=True), lambda: page.get_by_role("button", name=n, exact=True),
                     lambda: page.get_by_text(n, exact=True)):
            try:
                loc = make()
                for i in range(min(loc.count(), 5)):
                    if loc.nth(i).is_visible():
                        loc.nth(i).click(timeout=4000)
                        return True
            except Exception:
                continue
    try:
        return bool(page.evaluate(CLICK_JS, list(names)))
    except Exception:
        return False


def _goto(page, bank: TableBank) -> None:
    for _ in range(20):
        if page.query_selector(bank.account_select):
            return
        _click_text(page, bank.nav_links)
        page.wait_for_timeout(1500)
    from .login import drain_stdin
    drain_stdin()
    input(f"  請在 Chrome 點到「{bank.nav_links[0]}」頁，回到這裡按 Enter：")


def _read(page, bank: TableBank, before: str, timeout_s: float = 20) -> dict:
    deadline = time.time() + timeout_s
    result = None
    while time.time() < deadline:
        page.wait_for_timeout(800)
        try:
            result = page.evaluate(TABLE_JS, list(bank.need))
        except Exception:
            continue
        if result and result.get("rows") and json.dumps(result, ensure_ascii=False) != before:
            break
        try:
            body = page.evaluate("() => document.body.innerText")
        except Exception:
            body = ""
        if any(k in body for k in ("查無", "無交易", "無資料", "沒有資料", "尚無交易")) and not (result and result.get("rows")):
            return {"head": (result or {}).get("head", []), "rows": []}
    else:
        return {"head": (result or {}).get("head", []), "rows": []}
    head = result["head"]
    di = head.index(bank.date_col) if bank.date_col in head else 0
    rows = [[r[di]] + r for r in result["rows"] if di < len(r) and parse_day(r[di])]
    for _ in range(30):  # 下一頁
        if not _click_text(page, ("下一頁", "下頁")):
            break
        page.wait_for_timeout(1500)
        more = page.evaluate(TABLE_JS, list(bank.need)) or {}
        new = [[r[di]] + r for r in more.get("rows", []) if di < len(r) and parse_day(r[di])]
        new = [r for r in new if r not in rows]
        if not new:
            break
        rows.extend(new)
    return {"head": ["日期"] + head, "rows": rows}


def fetch_accounts(page, bank: TableBank, state: dict, since: date) -> list[dict]:
    _goto(page, bank)
    options = page.evaluate(SELECT_JS, [bank.account_select, -1]) or []
    accounts = [(i, t) for i, t in enumerate(options) if t and "請選擇" not in t]
    print(f"  帳號下拉共 {len(accounts)} 個帳號")
    today = date.today()
    out = []
    for i, label in accounts:
        name = _short(label)
        key = f"TWD:{name}"
        start = parse_day(state.get(key, {}).get("last_date", "")) or since
        start = max(start, today - timedelta(days=bank.max_days))
        _goto(page, bank)
        page.evaluate(SELECT_JS, [bank.account_select, i])
        page.wait_for_timeout(600)
        if bank.custom_dates:
            _click_text(page, (bank.custom_dates[0],))
            page.wait_for_timeout(500)
            page.evaluate(DATES_JS, [bank.custom_dates[1], bank.custom_dates[2], f"{start:%Y/%m/%d}", f"{today:%Y/%m/%d}"])
        try:
            before = json.dumps(page.evaluate(TABLE_JS, list(bank.need)), ensure_ascii=False)
        except Exception:
            before = "null"
        if not _click_text(page, bank.query_buttons):
            raise RuntimeError(f"找不到「{bank.query_buttons[0]}」")
        data = _read(page, bank, before)
        total = len(data["rows"])
        data["rows"], state[key] = keep_new(data["rows"], state.get(key, {}), start)
        out.append({"type": "TWD", "account": name, "ledger_row": bank.ledger, "from": start.isoformat(), **data})
        print(f"  {name}：{start:%m/%d}～{today:%m/%d} 共 {total} 筆，新的 {len(data['rows'])} 筆")
    return out


def fetch(code: str, since: date = None, keep_open: bool = False) -> Path:
    from playwright.sync_api import sync_playwright
    from .login import acquire_lock, launch_context, logout_all, open_bank, wait_for_logins

    bank = BANKS[code]
    tx_dir = BANK_DIR / "transactions" / code
    state_file = tx_dir / "_state.json"
    progress = {}
    if not since:
        try:
            progress = json.loads(state_file.read_text("utf-8"))
        except Exception:
            progress = {}
    since = since or date.today().replace(day=1)
    tx_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    results = []
    lock = acquire_lock()
    try:
        with sync_playwright() as p:
            context = launch_context(p)
            state = open_bank(context, code, code)
            if not state.logged_in:
                print(f"請在 Chrome 完成{bank.name}登入…")
                wait_for_logins(context, [state], 300)
            if not state.logged_in:
                raise SystemExit(f"{bank.name}沒有登入成功，停止。")
            page = state.page
            page.wait_for_timeout(2000)
            try:
                print("查詢交易明細…")
                results = fetch_accounts(page, bank, progress, since)
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
    state_file.write_text(json.dumps(progress, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(state_file, 0o600)
    raw_path = tx_dir / f"{stamp}.json"
    raw_path.write_text(json.dumps({"fetched_at": stamp, "accounts": results}, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(raw_path, 0o600)
    shape_path = BANK_DIR / "_explore" / f"{code}_shape_{stamp}.txt"
    shape_path.parent.mkdir(parents=True, exist_ok=True)
    shape_path.write_text(shape_report(results), "utf-8")
    print(f"\n明細（只存在本機）：{raw_path}")
    print(f"格式樣本（可上傳給 Claude）：{shape_path}")
    return raw_path
