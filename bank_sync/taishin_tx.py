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
from datetime import date, datetime
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
TWD_SKIP = ("建北活儲存款-證券", "中和活儲存款-證券", "天母活儲存款-證券", "數位三類")  # Jenny：略過
FX_LEDGER_ACCOUNT = "古亭"  # 細帳的台新人民幣/美金/日幣/南非：古亭外幣綜存全部進出
FX_INTEREST_ONLY = "敦南"  # 敦南外幣帳戶只取「利息」，加到同幣別那一列
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
  const sel = [...document.querySelectorAll('select')].find(s => [...s.options].some(o => o.text.includes(marker)) && s.options.length > 1 && s.getClientRects().length > 0)
           || [...document.querySelectorAll('select')].find(s => [...s.options].some(o => o.text.includes(marker)) && s.options.length > 1)
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
    digits = re.sub(r"\D", "", (label or "").split(" ")[0])[-3:]
    name = re.sub(r"^[\d\-\s*]+", "", label or "").strip()
    return f"****{digits} {name}".strip()


# ---------- 從「上次最後一筆日期」查到今天 ----------
STATE_FILE = TX_DIR / "_state.json"
PERIODS = [(7, "7天"), (14, "14天"), (31, "1個月"), (62, "2個月"), (92, "3個月"), (183, "6個月"), (365, "12個月")]


def parse_day(text: str):
    m = re.search(r"(\d{2,4})\s*[/\-.年]\s*(\d{1,2})\s*[/\-.月]\s*(\d{1,2})", text or "")
    if not m:
        return None
    y = int(m.group(1))
    if y < 1911:
        y += 1911  # 民國年
    try:
        return date(y, int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def period_for(since: date, today: date) -> str:
    need = (today - since).days + 1
    return next((label for days, label in PERIODS if days >= need), PERIODS[-1][1])


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text("utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(STATE_FILE, 0o600)


def keep_new(rows: list, last: dict, since: date) -> tuple[list, dict]:
    """只留「上次最後一筆日期」當天之後（含當天但沒抓過）的交易，並回傳新的進度。"""
    last_day = parse_day(last.get("last_date", "")) if last else None
    seen = set(last.get("seen", [])) if last else set()
    start = last_day or since
    new = []
    for row in rows:
        day = parse_day(row[0] if row else "")
        if day is None or day < start:
            continue
        key = "|".join(row)
        if last_day and day == last_day and key in seen:
            continue
        new.append(row)
    days = [parse_day(r[0]) for r in rows if r and parse_day(r[0])]
    if not days:
        return new, last or {}
    newest = max(days)
    newest_keys = ["|".join(r) for r in rows if r and parse_day(r[0]) == newest]
    if last_day == newest:
        newest_keys = sorted(seen | set(newest_keys))
    return new, {"last_date": newest.isoformat(), "seen": newest_keys}


def _ledger_row(name: str) -> str:
    return next((row for key, row in TWD_ACCOUNTS.items() if key in name), "")


def _app_frame(page):
    """台新網銀的功能頁在 iframe 裡（網址含 /svc/rwd/），主頁網址一直是 /TIBNetBank/。"""
    for frame in page.frames:
        if "/svc/rwd/" in (frame.url or ""):
            return frame
    return None


READY_JS = r"""
(marker) => {
  const sels = [...document.querySelectorAll('select')];
  const acct = sels.find(s => [...s.options].some(o => o.text.includes(marker)) && s.options.length > 1);
  const period = sels.find(s => [...s.options].some(o => o.text.includes('請選擇查詢期間')));
  return !!(acct && period);
}
"""


def _find_select_frame(page, marker: str):
    """要同時有「帳號選單（有帳號）」和「查詢期間」才算到了明細頁（首頁也有「請選擇帳號」的選單）。"""
    for frame in page.frames:
        try:
            if frame.evaluate(READY_JS, marker):
                return frame
        except Exception:
            continue
    return None


CLICK_LINK_JS = "t => { const a = [...document.querySelectorAll('a')].find(x => x.innerText.trim() === t); if (a) { a.click(); return true; } return false; }"


def _click_link_any(page, text: str) -> bool:
    for frame in page.frames:
        try:
            if frame.evaluate(CLICK_LINK_JS, text):
                return True
        except Exception:
            continue
    return False


def _goto(page, url: str, link_text: str, marker: str, timeout_s: float = 25):
    """切到功能頁（只改 iframe 的 #hash 或點選單，不重新載入），回傳有選單的那個 frame。"""
    route = "#" + url.split("#", 1)[1] if "#" in url else ""
    deadline = time.time() + timeout_s
    tried_hash = tried_link = False
    while time.time() < deadline:
        if _logged_out(page):
            raise RuntimeError("台新已登出")
        frame = _find_select_frame(page, marker)
        if frame is not None:
            return frame
        app = _app_frame(page)
        if app is not None and route and not tried_hash:
            try:
                app.evaluate("h => { window.location.hash = h; }", route)
            except Exception:
                pass
            tried_hash = True
        elif not tried_link and time.time() > deadline - timeout_s * 0.6:
            _click_link_any(page, link_text)
            tried_link = True
        page.wait_for_timeout(700)
    print(f"  自動切換到「{link_text}」沒成功")
    input(f"  請在 Chrome 手動點到「{link_text}」頁，出現帳號選單後回到這裡按 Enter：")
    frame = _find_select_frame(page, marker)
    if frame is None:
        raise RuntimeError(f"找不到「{link_text}」頁面的選單（各 frame：{[f.url.split('?')[0] for f in page.frames]}）")
    return frame


def _logged_out(page) -> bool:
    main = getattr(page, "main_frame", None) or page
    try:
        has_password = main.evaluate("() => [...document.querySelectorAll('input[type=password]')].some(e => e.getClientRects().length > 0)")
    except Exception:
        return False
    return bool(has_password)


def _query(page, button_names: list[str], need: list[str], timeout_s: float = 20) -> dict:
    before = json.dumps(page.evaluate(TABLE_JS, need), ensure_ascii=False)
    if not page.evaluate(CLICK_JS, button_names):
        raise RuntimeError(f"找不到按鈕：{button_names}")
    deadline = time.time() + timeout_s
    result = None
    fresh = False
    while time.time() < deadline:
        page.wait_for_timeout(700)
        if _logged_out(page):
            raise RuntimeError("台新已登出")
        result = page.evaluate(TABLE_JS, need)
        if result and result.get("rows") and json.dumps(result, ensure_ascii=False) != before:
            fresh = True
            break
        body = page.evaluate("() => document.body.innerText")
        if any(k in body for k in ("查無", "無交易", "無資料", "沒有資料")):
            return {"head": [], "rows": []}
    if not fresh:  # 表格沒有更新＝這個帳戶這段期間沒有交易（不能拿上一個帳戶的結果）
        return {"head": (result or {}).get("head", []), "rows": []}
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


def _fresh(frame, url: str, other_url: str, link_text: str, marker: str):
    """切到別頁再切回來，讓查詢結果清空，避免沿用上一個帳戶的表格。"""
    try:
        frame.evaluate("h => { window.location.hash = h; }", "#" + other_url.split("#", 1)[1])
        frame.wait_for_timeout(1500)
    except Exception:
        pass
    return _goto(frame.page, url, link_text, marker)


def fetch_twd(page, state: dict, since: date) -> list[dict]:
    page = _goto(page, TWD_URL, "查詢交易明細", "請選擇帳號")
    options = page.evaluate(SELECT_JS, ["請選擇帳號", -1, ""]) or []
    print(f"  帳號選單共 {max(len(options) - 1, 0)} 個帳戶")
    out = []
    for i, label in enumerate(options):
        if i == 0 or "請選擇" in label or any(k in label for k in TWD_SKIP):
            continue
        if out:
            page = _fresh(page, TWD_URL, FX_URL, "查詢交易明細", "請選擇帳號")
        name = _short(label)
        key = "TWD:" + name
        start = parse_day(state.get(key, {}).get("last_date", "")) or since
        period = period_for(start, date.today())
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
        total = len(data["rows"])
        if not data.get("error"):
            data["rows"], state[key] = keep_new(data["rows"], state.get(key, {}), since)
        out.append({"type": "TWD", "account": name, "ledger_row": _ledger_row(name), "from": start.isoformat(), **data})
        print(f"  台幣 {name}：{start:%m/%d} 起查「{period}」共 {total} 筆，新的 {len(data['rows'])} 筆{'' if _ledger_row(name) else '（細帳未對應）'}{'  ⚠️ ' + data['error'] if data.get('error') else ''}")
    return out


def fetch_fx(page, state: dict, since: date) -> list[dict]:
    page = _goto(page, FX_URL, "查詢外幣交易明細", "請選擇查詢帳號")
    options = page.evaluate(SELECT_JS, ["請選擇查詢帳號", -1, ""])
    out = []
    for i, label in enumerate(options):
        if i == 0 or "請選擇" in label:
            continue
        if out:
            page = _fresh(page, FX_URL, TWD_URL, "查詢外幣交易明細", "請選擇查詢帳號")
        name = _short(label)
        key = "FX:" + name
        start = parse_day(state.get(key, {}).get("last_date", "")) or since
        period = period_for(start, date.today())
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
        total = len(data["rows"])
        if not data.get("error"):
            data["rows"], state[key] = keep_new(data["rows"], state.get(key, {}), since)
        out.append({"type": "FX", "account": name, "from": start.isoformat(), "ledger_row": "台新外幣各幣別列（全部）" if FX_LEDGER_ACCOUNT in name else ("台新外幣各幣別列（只取利息）" if FX_INTEREST_ONLY in name else ""), **data})
        print(f"  外幣 {name}：{start:%m/%d} 起查「{period}」共 {total} 筆，新的 {len(data['rows'])} 筆{'  ⚠️ ' + data['error'] if data.get('error') else ''}")
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


def fetch(since: date = None, keep_open: bool = False) -> Path:
    """每個帳戶從「上次抓到的最後一筆日期」查到今天；第一次沒有紀錄時從 since（預設本月 1 日）開始。"""
    progress = {} if since else load_state()  # 有指定 --since 就從那天重抓
    since = since or date.today().replace(day=1)
    from playwright.sync_api import sync_playwright
    from .login import acquire_lock, launch_context, logout_all, open_bank, wait_for_logins

    TX_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    problem = ""
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
                results += fetch_twd(page, progress, since)
                print("查詢外幣交易明細…")
                results += fetch_fx(page, progress, since)
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
    save_state(progress)
    raw_path = TX_DIR / f"{stamp}.json"
    raw_path.write_text(json.dumps({"fetched_at": stamp, "accounts": results}, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(raw_path, 0o600)
    shape_path = BANK_DIR / "_explore" / f"taishin_shape_{stamp}.txt"
    shape_path.parent.mkdir(parents=True, exist_ok=True)
    shape_path.write_text(shape_report(results), "utf-8")
    print(f"\n明細（只存在本機）：{raw_path}")
    print(f"格式樣本（可上傳給 Claude）：{shape_path}")
    from .progress_log import log_run
    log_run('台新明細', since, TX_DIR, results, problem)
    return raw_path
