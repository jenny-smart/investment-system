"""富邦網銀：自動查詢「臺外幣交易明細」，存到本機。

頁面結構（explore 探索結果）：功能頁在 iframe 內（/B2C/cdsqu/cdsqu001/CDSQU001_Home.faces）
  查詢內容 radio form1:rdoTxDetail（交易明細）
  自訂查詢 form1:startDate / form1:endDate（YYYY/MM/DD，一次最多六個月）→ 連結「開始查詢」
  結果分「臺幣活期存款／外幣活期存款」，欄位：帳務日期、交易時間、摘要、支出金額、存入金額、即時餘額、附註
每次從上次最後一筆日期查到今天（直接填自訂日期），去重、記進度。
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from .credentials import BANK_DIR
from .taishin_tx import CLICK_JS, _logged_out, keep_new, parse_day, shape_report

TX_DIR = BANK_DIR / "transactions" / "fubon"
STATE_FILE = TX_DIR / "_state.json"
NEED = ["帳務日期", "摘要"]

READY_JS = "() => !!document.getElementById('form1:startDate')"

LINK_JS = r"""
(t) => {
  const vis = e => e.getClientRects().length > 0;
  const a = [...document.querySelectorAll('a')].find(x => x.innerText.replace(/\s+/g, '') === t && vis(x))
         || [...document.querySelectorAll('a')].find(x => x.innerText.replace(/\s+/g, '') === t);
  if (a) { a.click(); return true; }
  return false;
}
"""

FILL_JS = r"""
([start, end]) => {
  const pick = document.getElementById('form1:rdoTxDetail');
  if (pick && !pick.checked) pick.click();
  for (const [id, v] of [['form1:startDate', start], ['form1:endDate', end]]) {
    const e = document.getElementById(id);
    if (!e) return 'missing ' + id;
    e.removeAttribute('readonly');
    e.value = v;
    e.dispatchEvent(new Event('input', {bubbles: true}));
    e.dispatchEvent(new Event('change', {bubbles: true}));
    e.dispatchEvent(new Event('blur', {bubbles: true}));
  }
  return 'ok';
}
"""

# 表頭可能是 th 也可能是 td：找「某一列包含所有需要欄名」的表格，回傳那列之後的資料列
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
      if (cells.length >= head.length - 1 && cells.some(Boolean)) data.push(cells);
    }
    return {head: head, rows: data};
  }
  return null;
}
"""


def _frames(page):
    return list(page.frames)


def _eval_any(page, js, arg=None):
    for frame in _frames(page):
        try:
            if frame.evaluate(js, arg) if arg is not None else frame.evaluate(js):
                return frame
        except Exception:
            continue
    return None


def _goto_query(page, timeout_s: float = 30):
    deadline = time.time() + timeout_s
    step = 0
    while time.time() < deadline:
        if _logged_out(page):
            raise RuntimeError("富邦已登出")
        frame = _eval_any(page, READY_JS)
        if frame is not None:
            return frame
        if step == 0:
            _eval_any(page, LINK_JS, "存款/外匯/轉帳")
            step = 1
        elif step == 1:
            if _eval_any(page, LINK_JS, "臺外幣交易明細查詢"):
                step = 2
        page.wait_for_timeout(1000)
    print("  自動切換到「臺外幣交易明細查詢」沒成功")
    input("  請在 Chrome 點「存款/外匯/轉帳 → 臺外幣交易明細查詢」，出現查詢條件後回到這裡按 Enter：")
    frame = _eval_any(page, READY_JS)
    if frame is None:
        raise RuntimeError("找不到「臺外幣交易明細查詢」頁")
    return frame


NO_DATA = ("查無", "無交易", "無資料", "沒有資料")


def _read_table(frame, timeout_s: float = 25, before: str = "null") -> dict:
    """等結果表格出現。只有「表格裡」寫查無資料才算沒資料（頁面說明文字裡也可能有「查無」）。"""
    deadline = time.time() + timeout_s
    result = None
    while time.time() < deadline:
        frame.wait_for_timeout(800)
        try:
            result = frame.evaluate(TABLE_JS, NEED)
        except Exception:
            continue  # 送出查詢後頁面重新載入中
        if not result:
            continue
        joined = " ".join(" ".join(r) for r in result.get("rows", []))
        if result.get("rows") and any(k in joined for k in NO_DATA):
            return {"head": result["head"], "rows": []}
        if result.get("rows") and json.dumps(result, ensure_ascii=False) != before:
            break
    else:
        return {"head": (result or {}).get("head", []), "rows": [], "note": "逾時沒有看到結果"}
    rows = [r for r in result["rows"] if parse_day(r[0] if r else "")]
    for _ in range(30):  # 下一頁
        if not frame.evaluate(CLICK_JS, ["下一頁", "下頁"]):
            break
        frame.wait_for_timeout(1500)
        more = frame.evaluate(TABLE_JS, NEED) or {}
        new = [r for r in more.get("rows", []) if r not in rows and parse_day(r[0] if r else "")]
        if not new:
            break
        rows.extend(new)
    return {"head": result["head"], "rows": rows}


def _debug_snapshot(page, name: str) -> None:
    """結果是 0 筆時，存一份遮蔽過的頁面結構（不含金額），方便查原因。"""
    try:
        from .explore import snapshot
        path = BANK_DIR / "_explore" / f"fubon_debug_{name}_{datetime.now():%H%M%S}.json"
        path.write_text(json.dumps(snapshot(page), ensure_ascii=False, indent=1), "utf-8")
        print(f"  （已存頁面結構供檢查：{path.name}）")
    except Exception:
        pass


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text("utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(STATE_FILE, 0o600)


def fetch_all(page, state: dict, since: date) -> list[dict]:
    frame = _goto_query(page)
    starts = [parse_day(v.get("last_date", "")) for v in state.values() if v.get("last_date")]
    start = min(starts) if len(starts) == 2 else since  # 台幣、外幣都有進度才用進度
    start = max(start, date.today() - timedelta(days=180))  # 一次最多六個月
    print(f"  查詢 {start:%Y/%m/%d} ～ {date.today():%Y/%m/%d}")
    msg = frame.evaluate(FILL_JS, [start.strftime("%Y/%m/%d"), date.today().strftime("%Y/%m/%d")])
    if msg != "ok":
        raise RuntimeError(f"填日期失敗：{msg}")
    if not frame.evaluate(LINK_JS, "開始查詢") and not frame.evaluate(CLICK_JS, ["開始查詢", "查詢"]):
        raise RuntimeError("找不到「開始查詢」")
    page.wait_for_timeout(3000)
    frame = _eval_any(page, READY_JS) or frame
    try:
        filled = frame.evaluate("() => [document.getElementById('form1:startDate')?.value, document.getElementById('form1:endDate')?.value]")
        print(f"  送出後日期欄：{filled}")
    except Exception:
        pass
    out = []
    for kind, tab in (("TWD", "臺幣活期存款"), ("FX", "外幣活期存款")):
        before = "null"
        try:
            before = json.dumps(frame.evaluate(TABLE_JS, NEED), ensure_ascii=False)
        except Exception:
            pass
        if kind == "FX":
            if not frame.evaluate(LINK_JS, tab):
                continue  # 沒有外幣帳戶
            page.wait_for_timeout(1500)
            frame = _eval_any(page, READY_JS) or frame
        data = _read_table(frame, before=before if kind == "FX" else "null")
        if not data["rows"]:
            _debug_snapshot(page, kind)
        key = f"{kind}:富邦"
        total = len(data["rows"])
        data["rows"], state[key] = keep_new(data["rows"], state.get(key, {}), start)
        out.append({"type": kind, "account": f"富邦{tab}", "ledger_row": "富邦" if kind == "TWD" else "",
                    "from": start.isoformat(), **data})
        print(f"  {tab}：共 {total} 筆，新的 {len(data['rows'])} 筆")
    return out


def fetch(since: date = None, keep_open: bool = False) -> Path:
    from playwright.sync_api import sync_playwright
    from .login import acquire_lock, launch_context, logout_all, open_bank, wait_for_logins

    progress = {} if since else _load_state()
    since = since or date.today().replace(day=1)
    TX_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    results = []
    lock = acquire_lock()
    try:
        with sync_playwright() as p:
            context = launch_context(p)
            state = open_bank(context, "fubon", "fubon")
            if not state.logged_in:
                print("請在 Chrome 完成富邦登入（輸入驗證碼）…")
                wait_for_logins(context, [state], 300)
            if not state.logged_in:
                raise SystemExit("富邦沒有登入成功，停止。")
            page = state.page
            page.wait_for_timeout(2500)
            try:
                print("查詢臺外幣交易明細…")
                results = fetch_all(page, progress, since)
            except Exception as exc:
                print(f"⚠️ 中斷：{exc}")
            if keep_open:
                input("Chrome 保持開著，按 Enter 關閉…")
            logout_all(context)
            context.close()
    finally:
        lock.close()
    _save_state(progress)
    raw_path = TX_DIR / f"{stamp}.json"
    raw_path.write_text(json.dumps({"fetched_at": stamp, "accounts": results}, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(raw_path, 0o600)
    shape_path = BANK_DIR / "_explore" / f"fubon_shape_{stamp}.txt"
    shape_path.parent.mkdir(parents=True, exist_ok=True)
    shape_path.write_text(shape_report(results), "utf-8")
    print(f"\n明細（只存在本機）：{raw_path}")
    print(f"格式樣本（可上傳給 Claude）：{shape_path}")
    return raw_path
