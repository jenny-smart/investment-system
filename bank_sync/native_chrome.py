"""渣打這類會擋「程式控制的 Chrome」的銀行：開一個專用、一般模式的 Chrome 來登入。

不用 Playwright（渣打認得出來會回 403），也不用 AppleScript（同時開著好幾個 Chrome 時
會送錯視窗，例如 ~/EI 那個 Chrome）。改成：
  1. 用一般方式開 Google Chrome，設定資料夾 ~/Bank account/chrome_profile_native，
     加上只在本機的除錯連接埠（不帶任何自動化標記）；
  2. 透過該連接埠只執行預填帳密、判斷登入狀態的 JavaScript。
需要：pip install websocket-client
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .banks import WEB_BANKS, WebBank
from .credentials import BANK_DIR, load_credentials

NATIVE_PROFILE = BANK_DIR / "chrome_profile_native"
DEBUG_PORT = int(os.environ.get("BANK_SYNC_NATIVE_PORT", "9333"))
CHROME_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    "/usr/bin/google-chrome",
)
EXTRA_ARGS = [a for a in os.environ.get("BANK_SYNC_NATIVE_EXTRA_ARGS", "").split() if a]  # 測試用


def _http(path: str, method: str = "GET"):
    req = urllib.request.Request(f"http://127.0.0.1:{DEBUG_PORT}{path}", method=method)
    with urllib.request.urlopen(req, timeout=3) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _running() -> bool:
    try:
        _http("/json/version")
        return True
    except Exception:
        return False


def open_native(url: str) -> None:
    """在專用 Chrome 開網址；還沒開就先啟動。"""
    if _running():
        _http("/json/new?" + urllib.parse.quote(url, safe=""), method="PUT")
        return
    chrome = next((p for p in CHROME_PATHS if Path(p).exists()), None)
    if chrome is None:
        raise RuntimeError("找不到 Google Chrome（/Applications/Google Chrome.app）")
    NATIVE_PROFILE.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [chrome, f"--user-data-dir={NATIVE_PROFILE}", f"--remote-debugging-port={DEBUG_PORT}",
         "--no-first-run", "--no-default-browser-check",
         *EXTRA_ARGS, url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    deadline = time.time() + 20
    while time.time() < deadline and not _running():
        time.sleep(0.5)
    if not _running():
        raise RuntimeError("專用 Chrome 沒有啟動成功")


def evaluate(host: str, javascript: str) -> str:
    """在專用 Chrome 裡網址含 host 的分頁執行 JavaScript，回傳字串結果。"""
    try:
        import websocket
    except ImportError as exc:
        raise RuntimeError("請先安裝：pip install websocket-client") from exc
    tabs = [t for t in _http("/json") if t.get("type") == "page" and host in t.get("url", "")]
    if not tabs:
        return "TAB_NOT_FOUND"
    ws = websocket.create_connection(tabs[0]["webSocketDebuggerUrl"], timeout=10, suppress_origin=True)
    try:
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": javascript, "returnByValue": True}}))
        while True:
            message = json.loads(ws.recv())
            if message.get("id") == 1:
                value = message.get("result", {}).get("result", {}).get("value")
                return "" if value is None else str(value)
    finally:
        ws.close()


FILL_JS = r"""
(() => { try {
  const creds = __CREDS__;
  const hints = __HINTS__;
  const docs = [];
  const walk = d => { docs.push(d); [...d.querySelectorAll('iframe,frame')].forEach(f => { try { if (f.contentDocument) walk(f.contentDocument); } catch (_) {} }); };
  walk(document);
  const visible = e => e && e.getClientRects().length > 0;
  const fillable = e => visible(e) && !e.disabled && !['hidden','button','submit','checkbox','radio','image','reset'].includes((e.type || 'text').toLowerCase());
  const isCaptcha = e => {
    const a = [e.name, e.id, e.placeholder, e.getAttribute('aria-label'), e.title].join(' ');
    if (/captcha|verify|vcode|pict|chkcode|驗證|檢核/i.test(a)) return true;
    let n = e.parentElement;
    for (let i = 0; n && i < 4; i++, n = n.parentElement) {
      const t = (n.innerText || '').trim();
      if (t) return /驗證|檢核碼/.test(t) && !/密碼|代號|代碼|名稱|身分證/.test(t.replace(/驗證碼|檢核碼/g, ''));
    }
    return false;
  };
  for (const d of docs) {
    const inputs = [...d.querySelectorAll('input')].filter(fillable);
    if (!inputs.some(e => (e.type || '').toLowerCase() === 'password') && inputs.length < 2) continue;
    const used = new Set();
    const result = {filled: [], missing: []};
    const squash = t => (t || '').replace(/\s+/g, '');
    const follows = (a, b) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    const candidates = [...d.querySelectorAll('label,span,div,td,th,p,dt,dd,li,strong,b,font')]
      .filter(e => visible(e) && !e.closest('a,button') && squash(e.innerText).length > 0 && squash(e.innerText).length <= 20);
    const innermost = w => candidates.filter(e => squash(e.innerText).includes(w)
      && ![...e.children].some(c => squash(c.innerText).includes(w)));
    const box = e => e.getBoundingClientRect();
    const sameRow = (l, i) => { const a = box(l), b = box(i); return Math.abs((a.top + a.bottom) / 2 - (b.top + b.bottom) / 2) < Math.max(a.height, b.height) / 2 + 8; };
    const forLabel = label => {
      const free = inputs.filter(e => !used.has(e) && !isCaptcha(e));
      const row = free.filter(e => sameRow(label, e) && box(e).left >= box(label).left - 4)
        .sort((x, y) => box(x).left - box(y).left);
      if (row.length) return row[0];
      const below = free.filter(e => box(e).top >= box(label).top - 4 && follows(label, e))
        .sort((x, y) => (box(x).top - box(y).top) || (box(x).left - box(y).left));
      return below[0] || null;
    };
    const findFor = words => {
      for (const w of words) {
        const ph = inputs.find(e => !used.has(e) && !isCaptcha(e) && (squash(e.placeholder).includes(w) || squash(e.getAttribute('aria-label')).includes(w)));
        if (ph) return ph;
        for (const label of innermost(w)) {
          const input = forLabel(label);
          if (input) return input;
        }
      }
      return null;
    };
    let previous = null;
    const pwdField = creds.password ? findFor(hints.password || []) : null;
    for (const field of ['id_number', 'user_code', 'password']) {
      if (!creds[field]) continue;
      let input = field === 'password' && pwdField && !used.has(pwdField) ? pwdField : findFor(hints[field] || []);
      if (field !== 'password' && input && input === pwdField) input = null;
      if (!input && field === 'user_code' && previous && pwdField)
        input = inputs.find(e => !used.has(e) && e !== pwdField && !isCaptcha(e) && follows(previous, e) && follows(e, pwdField));
      if (!input && field === 'password') input = inputs.find(e => !used.has(e) && (e.type || '').toLowerCase() === 'password');
      if (!input && field === 'password' && previous) input = inputs.find(e => !used.has(e) && !isCaptcha(e) && follows(previous, e));
      if (!input) { result.missing.push(field); continue; }
      used.add(input);
      input.removeAttribute('readonly');
      input.focus();
      const setter = Object.getOwnPropertyDescriptor(input.ownerDocument.defaultView.HTMLInputElement.prototype, 'value').set;
      setter.call(input, creds[field]);
      for (const t of ['input', 'change', 'keyup', 'blur']) input.dispatchEvent(new Event(t, {bubbles: true}));
      result.filled.push(field);
      previous = input;
    }
    if (!result.filled.length) continue;
    const captcha = inputs.find(e => !used.has(e) && isCaptcha(e));
    if (captcha) captcha.focus();
    return JSON.stringify(result);
  }
  return 'WAIT';
} catch (err) { return 'JS_ERROR:' + err; } })()
"""

STATE_JS = r"""
(() => { try {
  const docs = [];
  const walk = d => { docs.push(d); [...d.querySelectorAll('iframe,frame')].forEach(f => { try { if (f.contentDocument) walk(f.contentDocument); } catch (_) {} }); };
  walk(document);
  const text = docs.map(d => d.body ? d.body.innerText : '').join('\n');
  const pwd = docs.some(d => [...d.querySelectorAll('input[type=password]')].some(e => e.getClientRects().length));
  return JSON.stringify({password: pwd, logout: text.includes('登出'), loggedOut: /您已成功登出|已登出/.test(text)});
} catch (err) { return 'JS_ERROR:' + err; } })()
"""


def _logged_in(state: dict) -> bool:
    return not state.get("loggedOut") and not state.get("password") and bool(state.get("logout"))


def native_login(login_key: str, bank_code: str, timeout_s: float = 300) -> bool:
    """在專用 Chrome 開銀行、預填帳密，等本人輸入驗證碼登入。回傳是否登入完成。"""
    bank: WebBank = WEB_BANKS[bank_code]
    creds = load_credentials(login_key)
    try:
        if _logged_in(json.loads(evaluate(bank.host, STATE_JS))):
            print(f"✓ {bank.name}：已是登入狀態")
            return True
    except Exception:
        pass
    open_native(bank.login_url)
    print(f"→ {bank.name}：已開在專用 Chrome 視窗")
    js = (FILL_JS.replace("__CREDS__", json.dumps(creds, ensure_ascii=False))
          .replace("__HINTS__", json.dumps(bank.field_hints, ensure_ascii=False)))
    deadline = time.time() + 60
    filled = None
    while time.time() < deadline:
        try:
            output = evaluate(bank.host, js)
        except Exception:
            output = "WAIT"
        if output.startswith("JS_ERROR:"):
            print(f"! {bank.name}：{output}")
            break
        if output not in ("WAIT", "TAB_NOT_FOUND", ""):
            filled = json.loads(output)
            break
        time.sleep(1)
    if filled is None:
        print(f"! {bank.name}：找不到登入欄位，請在 Chrome 手動填寫")
    else:
        extra = f"（找不到欄位：{'、'.join(filled['missing'])}，請手動填）" if filled["missing"] else ""
        print(f"   已預填 {len(filled['filled'])} 欄，請輸入驗證碼並按登入{extra}")
    end = time.time() + timeout_s
    while time.time() < end:
        try:
            if _logged_in(json.loads(evaluate(bank.host, STATE_JS))):
                print(f"✓ {bank.name}：登入完成")
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


INSPECT_JS = r"""
(() => { try {
  const docs = [];
  const walk = d => { docs.push(d); [...d.querySelectorAll('iframe,frame')].forEach(f => { try { if (f.contentDocument) walk(f.contentDocument); } catch (_) {} }); };
  walk(document);
  const rows = [];
  docs.forEach((d, di) => [...d.querySelectorAll('input,select,textarea')].forEach(e => {
    const r = e.getClientRects()[0];
    let label = '';
    if (e.labels && e.labels.length) label = e.labels[0].innerText;
    if (!label) { let n = e.parentElement; for (let i = 0; n && i < 4 && !label; i++, n = n.parentElement) label = (n.innerText || '').trim().slice(0, 30); }
    rows.push({frame: di, tag: e.tagName.toLowerCase(), type: e.type, id: e.id, name: e.name,
               placeholder: e.placeholder, aria: e.getAttribute('aria-label') || '', readonly: e.readOnly,
               visible: !!r, x: r ? Math.round(r.x) : null, y: r ? Math.round(r.y) : null,
               label: label.replace(/\s+/g, ' ')});
  }));
  return JSON.stringify(rows);
} catch (err) { return 'JS_ERROR:' + err; } })()
"""


def inspect_page(bank_code: str) -> list[dict]:
    """列出已開啟的銀行登入頁欄位（名稱、類型、位置），不讀取欄位內容。"""
    bank = WEB_BANKS[bank_code]
    if not _running():
        raise SystemExit(f"專用 Chrome 沒有開著；請先執行 python3 -m bank_sync login {bank_code}")
    output = evaluate(bank.host, INSPECT_JS)
    if output == "TAB_NOT_FOUND":
        raise SystemExit(f"專用 Chrome 裡找不到{bank.name}的分頁；請先執行 login 打開登入頁。")
    if not output.startswith("["):
        raise SystemExit(f"{bank.name}分頁沒有回應正確結果：{output[:200] or '（空白，可能還在載入）'}")
    rows = json.loads(output)
    for i, r in enumerate(rows):
        if r["type"] == "hidden":
            continue
        print(f"{i:>2} {'可見' if r['visible'] else '隱藏'} {r['tag']}/{r['type']:<9} id={r['id']!r} name={r['name']!r} "
              f"placeholder={r['placeholder']!r} aria={r['aria']!r} readonly={r['readonly']} "
              f"位置=({r['x']},{r['y']}) 標籤={r['label']!r}")
    return rows
