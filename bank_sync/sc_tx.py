"""渣打（專用一般模式 Chrome，CDP 控制）：查詢台幣／外幣交易明細，存到本機。

探索結果：
  台幣明細 /scb/accOverview/savingTWD/detail：日期 input[name=__DateStart]／[name=__DateEnd] → 「查詢」，
    表格 交易時間／摘要／金額／餘額／摘要說明／票號
  外幣明細 /scb/accOverview/savingForeignDetails：日期 input[name=DateStart]／[name=DateEnd] → 「查詢」，
    表格 交易時間／金額／餘額／摘要說明（頁面上方寫幣別，例 USD）
  登出：「登出」→ 確認視窗「確認」
只查外幣（台幣不查）。全自動、不用按 Enter：
  帳戶綜覽 →「外幣活存」分頁 → 幣別表（幣別／開戶日期／最近交易日期／帳戶金額／明細）
  → 只點「最近交易日期」在查詢起日之後的幣別的「明細」→ 填日期、查詢、讀表格 → 回到幣別表換下一個幣別。
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from .credentials import BANK_DIR
from .taishin_tx import keep_new, parse_day, shape_report

HOST = "ebank.standardchartered.com.tw"
TX_DIR = BANK_DIR / "transactions" / "sc"
STATE_FILE = TX_DIR / "_state.json"
FX_PATH = "savingForeignDetails"
FX_DATES = ("DateStart", "DateEnd")
FX_NEED = ["交易時間", "金額", "摘要說明"]
CURRENCY_CODES = {"USD": "美元", "ZAR": "南非幣", "CNY": "人民幣", "JPY": "日圓", "AUD": "澳幣", "EUR": "歐元"}

DEEP = r"""
  const roots = [];
  const walk = r => { roots.push(r); r.querySelectorAll('*').forEach(e => { if (e.shadowRoot) walk(e.shadowRoot); if (e.tagName === 'IFRAME' || e.tagName === 'FRAME') { try { if (e.contentDocument) walk(e.contentDocument); } catch (_) {} } }); };
  walk(document);
  const all = sel => roots.flatMap(r => [...r.querySelectorAll(sel)]);
  const vis = e => e && e.getClientRects().length > 0;
  const clean = t => (t || '').replace(/\s+/g, ' ').trim();
"""


def _js(body: str, **kw) -> str:
    for k, v in kw.items():
        body = body.replace(f"__{k}__", json.dumps(v, ensure_ascii=False))
    return "(() => { try {" + DEEP + body + "} catch (err) { return 'JS_ERROR:' + err; } })()"


TABLE_BODY = r"""
  const need = __NEED__;
  for (const t of all('table')) {
    if (!vis(t)) continue;
    const rows = [...t.rows];
    const hi = rows.findIndex(r => { const c = [...r.cells].map(x => clean(x.innerText)); return need.every(n => c.includes(n)); });
    if (hi < 0) continue;
    const head = [...rows[hi].cells].map(x => clean(x.innerText));
    const data = rows.slice(hi + 1).filter(vis).map(r => [...r.cells].map(x => clean(x.innerText))).filter(c => c.some(Boolean));
    const text = clean(document.body.innerText);
    const m = text.match(/\b(USD|ZAR|CNY|JPY|AUD|EUR|NZD|GBP|HKD|SGD)\b/);
    return JSON.stringify({head: head, rows: data, currency: m ? m[1] : '', nodata: /查無|無交易|沒有交易|無資料/.test(text)});
  }
  return JSON.stringify({head: [], rows: [], currency: '', nodata: /查無|無交易|沒有交易|無資料/.test(clean(document.body.innerText))});
"""

DATES_BODY = r"""
  const [a, b, va, vb] = __ARGS__;
  let n = 0;
  for (const [name, v] of [[a, va], [b, vb]]) {
    const e = all('input').find(x => x.name === name);
    if (!e) continue;
    e.removeAttribute('readonly');
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(e, v);
    for (const ev of ['input', 'change', 'blur']) e.dispatchEvent(new Event(ev, {bubbles: true}));
    n++;
  }
  return String(n);
"""

CLICK_BODY = r"""
  const names = __NAMES__;
  const els = all('button,a,[role=button],input[type=button],input[type=submit],span,div').filter(vis);
  for (const n of names) {
    const e = els.find(x => clean(x.innerText || x.value) === n && (x.children.length === 0 || ['BUTTON', 'A'].includes(x.tagName)));
    if (e) { (e.closest('button,a,[role=button]') || e).click(); return n; }
  }
  return '';
"""

URL_BODY = "return location.href;"

# 外幣活存分頁的幣別表：回傳每列 [列序, 幣別文字, 最近交易日期]
FX_ROWS_BODY = r"""
  for (const t of all('table')) {
    if (!vis(t)) continue;
    const rows = [...t.rows];
    const hi = rows.findIndex(r => { const c = [...r.cells].map(x => clean(x.innerText)); return c.includes('幣別') && c.includes('最近交易日期'); });
    if (hi < 0) continue;
    const head = [...rows[hi].cells].map(x => clean(x.innerText));
    const ci = head.indexOf('幣別'), li = head.indexOf('最近交易日期');
    return JSON.stringify(rows.slice(hi + 1).map((r, i) => [i, clean((r.cells[ci] || {}).innerText), clean((r.cells[li] || {}).innerText)])
      .filter(x => x[1]));
  }
  return '[]';
"""

# 點幣別表第 __I__ 列的「明細」
FX_DETAIL_BODY = r"""
  const i = __I__;
  for (const t of all('table')) {
    if (!vis(t)) continue;
    const rows = [...t.rows];
    const hi = rows.findIndex(r => { const c = [...r.cells].map(x => clean(x.innerText)); return c.includes('幣別') && c.includes('最近交易日期'); });
    if (hi < 0) continue;
    const row = rows.slice(hi + 1)[i];
    if (!row) return '';
    const e = [...row.querySelectorAll('a,button,[role=button],span,div')].find(x => clean(x.innerText) === '明細');
    if (!e) return '';
    (e.closest('a,button,[role=button]') || e).click();
    return 'ok';
  }
  return '';
"""


def _eval(js: str) -> str:
    from .native_chrome import evaluate
    out = evaluate(HOST, js)
    return out if isinstance(out, str) else ""


def _read(need) -> dict:
    out = _eval(_js(TABLE_BODY, NEED=list(need)))
    try:
        return json.loads(out)
    except Exception:
        return {"head": [], "rows": [], "currency": "", "nodata": False}


def _click(*names) -> bool:
    return bool(_eval(_js(CLICK_BODY, NAMES=list(names))))


def _fx_rows() -> list:
    try:
        return json.loads(_eval(_js(FX_ROWS_BODY)) or "[]")
    except Exception:
        return []


def _open_fx_list() -> list:
    """回到「外幣活存」幣別表；回傳幣別列。找不到就丟錯（不請你手動點）。"""
    for step in range(4):
        rows = _fx_rows()
        if rows:
            return rows
        if step == 1:
            _click("帳戶綜覽")
            time.sleep(3)
        _click("外幣活存")
        time.sleep(3)
    raise RuntimeError("找不到「外幣活存」的幣別表")


def _wait_url(path_part: str, seconds: float = 15) -> bool:
    for _ in range(int(seconds / 1.5)):
        if path_part in _eval(_js(URL_BODY)):
            return True
        time.sleep(1.5)
    return False


def _currency_code(text: str) -> str:
    m = re.search(r"(?<![A-Z])([A-Z]{3})(?![A-Z])", text)
    return m.group(1) if m else text


def _query(kind, names, need, start: date) -> dict:
    today = date.today()
    _eval(_js(DATES_BODY, ARGS=[names[0], names[1], f"{start:%Y/%m/%d}", f"{today:%Y/%m/%d}"]))
    before = json.dumps(_read(need), ensure_ascii=False)
    _click("查詢")
    data = {"head": [], "rows": []}
    for _ in range(12):  # 每 1.5 秒看一次就好（看太勤渣打網頁會變頓）
        time.sleep(1.5)
        data = _read(need)
        if (data["rows"] and json.dumps(data, ensure_ascii=False) != before) or data.get("nodata"):
            break
    head = data.get("head", [])
    rows = [r[-len(head):] if head and len(r) > len(head) else r for r in data.get("rows", [])]
    rows = [r for r in rows if r and parse_day(r[0])]
    return {"head": head, "rows": rows, "currency": data.get("currency", "")}


def logout_sc() -> bool:
    if not _click("登出"):
        return False
    for _ in range(10):
        time.sleep(0.6)
        if _click("確認", "確定"):
            time.sleep(1.5)
            return True
    return False


def fetch(since: date = None, keep_open: bool = False) -> Path:
    from .native_chrome import native_login
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
    if not native_login("sc", "sc"):
        raise SystemExit("渣打沒有登入成功，停止。")
    try:  # 順便記下「帳戶綜覽」頁結構（帳號遮蔽、不含金額），之後用來自動點到明細頁、核對餘額
        from .explore import DEEP_SNAPSHOT_JS, EXPLORE_DIR
        _click("帳戶綜覽")
        time.sleep(3)
        snap = _eval(DEEP_SNAPSHOT_JS)
        EXPLORE_DIR.mkdir(parents=True, exist_ok=True)
        (EXPLORE_DIR / f"sc_overview_{stamp}.json").write_text(snap, "utf-8")
        print(f"  已記錄帳戶綜覽頁結構：sc_overview_{stamp}.json")
    except Exception:
        pass
    try:
        today = date.today()
        for idx, cur_text, last_text in _open_fx_list():
            code = _currency_code(cur_text)
            cur = CURRENCY_CODES.get(code, code)
            key = f"FX:{cur}"
            start = parse_day(progress.get(key, {}).get("last_date", "")) or since
            last_tx = parse_day(last_text)
            name = f"渣打外幣 {cur}"
            if not last_tx or last_tx < start:
                print(f"  {name}：最近交易 {last_text or '—'}，查詢起日 {start} 之後沒有交易，略過")
                continue
            _open_fx_list()
            if not _eval(_js(FX_DETAIL_BODY, I=idx)) or not _wait_url(FX_PATH):
                print(f"  ⚠️ {name}：點不到「明細」，略過")
                problem = problem or f"{name} 點不到明細"
                continue
            data = _query("FX", FX_DATES, FX_NEED, max(start, today - timedelta(days=180)))
            total = len(data["rows"])
            data["rows"], progress[key] = keep_new(data["rows"], progress.get(key, {}), start)
            results.append({"type": "FX", "account": name, "currency": cur, "ledger_row": "渣打",
                            "from": start.isoformat(), "head": data["head"], "rows": data["rows"]})
            print(f"  {name}：共 {total} 筆，新的 {len(data['rows'])} 筆")
            _eval("history.back()")
            time.sleep(3)
    except KeyboardInterrupt:
        problem = "已中斷（Ctrl+C）"
        print("⚠️ 已中斷（Ctrl+C），先幫你登出…")
    except Exception as exc:
        problem = f"中斷：{exc}"
        print(f"⚠️ 中斷：{exc}")
    if keep_open:
        input("Chrome 保持開著，按 Enter 登出…")
    print("  ✓ 已登出：渣打銀行" if logout_sc() else "  ⚠️ 渣打沒登出成功，請手動按「登出 → 確認」")
    STATE_FILE.write_text(json.dumps(progress, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(STATE_FILE, 0o600)
    raw_path = TX_DIR / f"{stamp}.json"
    raw_path.write_text(json.dumps({"fetched_at": stamp, "accounts": results}, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(raw_path, 0o600)
    shape_path = BANK_DIR / "_explore" / f"sc_shape_{stamp}.txt"
    shape_path.parent.mkdir(parents=True, exist_ok=True)
    shape_path.write_text(shape_report(results), "utf-8")
    print(f"\n明細（只存在本機）：{raw_path}")
    print(f"格式樣本（可上傳給 Claude）：{shape_path}")
    log_run("渣打明細", since, TX_DIR, results, problem)
    return raw_path
