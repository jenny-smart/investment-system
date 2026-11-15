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
from .taishin_tx import CLICK_JS, _logged_out, _short, keep_new, parse_day, shape_report

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


ACCOUNT_JS = r"""
([index]) => {
  // 帳號下拉：原生 select（可能被美化元件蓋住、本身不可見），選項第一個是 ==請選擇==
  const sel = [...document.querySelectorAll('select')].find(s => [...s.options].some(o => /請選擇/.test(o.text)) && s.options.length > 1);
  if (!sel) return null;
  const opts = [...sel.options].map(o => o.text.replace(/\s+/g, ' ').trim());
  if (index < 0) return opts;
  sel.selectedIndex = index;
  for (const ev of ['input', 'change']) sel.dispatchEvent(new Event(ev, {bubbles: true}));
  if (window.jQuery) { try { const $s = window.jQuery(sel); $s.trigger('change'); if ($s.selectmenu) $s.selectmenu('refresh'); } catch (e) {} }
  return opts[index];
}
"""

ALL_SELECTS_JS = r"""
() => [...document.querySelectorAll('select')].map(s => ({id: s.id, name: s.name, visible: s.getClientRects().length > 0,
  options: [...s.options].slice(0, 15).map(o => o.text.replace(/\d[\d,\-]{3,}\d/g, m => '****' + m.replace(/\D/g, '').slice(-3)).trim())}))
"""


def _accounts(page):
    for frame in page.frames:
        try:
            opts = frame.evaluate(ACCOUNT_JS, [-1])
        except Exception:
            continue
        if opts:
            return frame, opts
    return None, []


def _query_window(page, i: int, kind: str, start: date, end: date, compare: bool) -> dict:
    """選第 i 個帳號、填起訖日、按開始查詢、讀結果。"""
    frame = _goto_query(page)
    frame, _ = _accounts(page)
    frame.evaluate(ACCOUNT_JS, [i])
    frame.wait_for_timeout(800)  # 選帳號後頁面可能重整
    frame = _eval_any(page, READY_JS) or frame
    frame2, _ = _accounts(page)
    if frame2 is not None:
        frame = frame2
        if frame.evaluate("() => { const s=[...document.querySelectorAll('select')].find(s=>[...s.options].some(o=>/請選擇/.test(o.text))); return s ? s.selectedIndex : -1; }") != i:
            frame.evaluate(ACCOUNT_JS, [i])
    msg = frame.evaluate(FILL_JS, [start.strftime("%Y/%m/%d"), end.strftime("%Y/%m/%d")])
    if msg != "ok":
        raise RuntimeError(f"填日期失敗：{msg}")
    try:
        before = json.dumps(frame.evaluate(TABLE_JS, NEED), ensure_ascii=False) if compare else "null"
    except Exception:
        before = "null"
    if not frame.evaluate(LINK_JS, "開始查詢") and not frame.evaluate(CLICK_JS, ["開始查詢", "查詢"]):
        raise RuntimeError("找不到「開始查詢」")
    page.wait_for_timeout(3000)
    frame = _eval_any(page, READY_JS) or frame
    return _read_table(frame, before=before)


def fetch_all(page, state: dict, since: date) -> list[dict]:
    frame = _goto_query(page)
    frame, options = _accounts(page)
    if not options:
        dump = []
        for f in page.frames:
            try:
                dump += f.evaluate(ALL_SELECTS_JS)
            except Exception:
                pass
        raise RuntimeError(f"找不到帳號下拉選單（頁面上的選單：{json.dumps(dump, ensure_ascii=False)[:800]}）")
    accounts = [(i, t) for i, t in enumerate(options) if i > 0 and "請選擇" not in t]
    print(f"  帳號下拉共 {len(accounts)} 個帳號")
    today = date.today()
    out = []
    for i, label in accounts:
        name = _short(label)
        kind = "FX" if any(k in label for k in ("外幣", "外匯", "美元", "USD")) else "TWD"
        key = f"{kind}:{name}"
        start = parse_day(state.get(key, {}).get("last_date", "")) or since
        start = max(start, today - timedelta(days=364))  # 富邦提供近一年
        windows, w = [], start
        while w <= today:  # 每次查詢最多六個月 → 分段查
            windows.append((w, min(w + timedelta(days=179), today)))
            w = w + timedelta(days=180)
        data = {"head": [], "rows": []}
        for w_start, w_end in windows:
            part = _query_window(page, i, kind, w_start, w_end, bool(out) or len(windows) > 1)
            data["head"] = part.get("head") or data["head"]
            data["rows"] += [r for r in part["rows"] if r not in data["rows"]]
            if part.get("note"):
                data["note"] = part["note"]
        if not data["rows"]:
            _debug_snapshot(page, kind)
        total = len(data["rows"])
        data["rows"], state[key] = keep_new(data["rows"], state.get(key, {}), start)
        out.append({"type": kind, "account": name, "ledger_row": "富邦" if kind == "TWD" else "",
                    "from": start.isoformat(), **data})
        print(f"  {name}：{start:%m/%d}～{today:%m/%d} 共 {total} 筆，新的 {len(data['rows'])} 筆{'  ' + data['note'] if data.get('note') else ''}")
    return out


def fetch(since: date = None, keep_open: bool = False) -> Path:
    from playwright.sync_api import sync_playwright
    from .login import acquire_lock, launch_context, logout_all, open_bank, wait_for_logins

    progress = {} if since else _load_state()
    since = since or date.today().replace(day=1)
    TX_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    results = []
    problem = ""
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
    _save_state(progress)
    raw_path = TX_DIR / f"{stamp}.json"
    raw_path.write_text(json.dumps({"fetched_at": stamp, "accounts": results}, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(raw_path, 0o600)
    shape_path = BANK_DIR / "_explore" / f"fubon_shape_{stamp}.txt"
    shape_path.parent.mkdir(parents=True, exist_ok=True)
    shape_path.write_text(shape_report(results), "utf-8")
    print(f"\n明細（只存在本機）：{raw_path}")
    print(f"格式樣本（可上傳給 Claude）：{shape_path}")
    from .progress_log import log_run
    log_run('富邦明細', since, TX_DIR, results, problem)
    return raw_path
