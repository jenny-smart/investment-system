"""用本人平常的 Google Chrome 登入（做法同 tool-system native_chrome）。

有些銀行（渣打）認得出 Playwright 開的 Chrome 而回 403；這裡改用 macOS AppleScript
叫正常 Chrome 開頁面、執行 JavaScript 預填帳密。
需要在 Chrome 開啟：顯示方式 → 開發人員 → 允許來自 Apple 事件的 JavaScript。
"""
from __future__ import annotations

import json
import subprocess
import time

from .banks import WEB_BANKS, WebBank
from .credentials import load_credentials

FILL_JS = r"""
(() => {
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
    const labels = [...d.querySelectorAll('label,span,div,td,th,p,dt,dd,li,strong,b')]
      .filter(e => visible(e) && squash(e.innerText).length > 0 && squash(e.innerText).length <= 20);
    const follows = (a, b) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    const findFor = words => {
      for (const w of words) {
        const ph = inputs.find(e => !used.has(e) && !isCaptcha(e) && (squash(e.placeholder).includes(w) || squash(e.getAttribute('aria-label')).includes(w)));
        if (ph) return ph;
        for (const label of labels.filter(e => squash(e.innerText).includes(w) && !e.closest('a,button'))) {
          const after = inputs.find(e => !used.has(e) && !isCaptcha(e) && follows(label, e));
          if (after) return after;
        }
      }
      return null;
    };
    let previous = null;
    const pwdField = creds.password ? (findFor(hints.password || []) || inputs.find(e => (e.type || '').toLowerCase() === 'password')) : null;
    for (const field of ['id_number', 'user_code', 'password']) {
      if (!creds[field]) continue;
      let input = field === 'password' && pwdField && !used.has(pwdField) ? pwdField : findFor(hints[field] || []);
      if (field === 'user_code' && input === pwdField) input = null;
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
})()
"""

STATE_JS = r"""
(() => {
  const docs = [];
  const walk = d => { docs.push(d); [...d.querySelectorAll('iframe,frame')].forEach(f => { try { if (f.contentDocument) walk(f.contentDocument); } catch (_) {} }); };
  walk(document);
  const text = docs.map(d => d.body ? d.body.innerText : '').join('\n');
  const pwd = docs.some(d => [...d.querySelectorAll('input[type=password]')].some(e => e.getClientRects().length));
  return JSON.stringify({password: pwd, logout: text.includes('登出'), loggedOut: /您已成功登出|已登出/.test(text)});
})()
"""


def _applescript(host: str, marker: str, javascript: str) -> str:
    quoted = json.dumps(" ".join(line.strip() for line in javascript.splitlines() if line.strip()), ensure_ascii=False)
    script = f"""
tell application "Google Chrome"
  repeat with pass from 1 to 2
    repeat with wi from 1 to count of windows
      repeat with ti from 1 to count of tabs of window wi
        set u to URL of tab ti of window wi
        if (pass = 1 and u contains "{marker}") or (pass = 2 and u contains "{host}") then
          return execute tab ti of window wi javascript {quoted}
        end if
      end repeat
    end repeat
  end repeat
  return "TAB_NOT_FOUND"
end tell
"""
    result = subprocess.run(["osascript", "-"], input=script, text=True, capture_output=True, check=False)
    if result.returncode:
        message = (result.stderr or result.stdout).strip()
        if "JavaScript" in message:
            raise RuntimeError("請在 Chrome 開啟：顯示方式 → 開發人員 → 允許來自 Apple 事件的 JavaScript")
        raise RuntimeError(message or "無法控制 Chrome")
    return result.stdout.strip()


def _logged_in(state: dict) -> bool:
    return not state.get("loggedOut") and not state.get("password") and bool(state.get("logout"))


def native_login(login_key: str, bank_code: str, timeout_s: float = 300) -> bool:
    """用正常 Chrome 開銀行、預填帳密，等本人輸入驗證碼登入。回傳是否登入完成。"""
    bank: WebBank = WEB_BANKS[bank_code]
    creds = load_credentials(login_key)
    marker = f"bank-sync-{bank_code}"
    subprocess.run(["open", "-a", "Google Chrome", f"{bank.login_url}#{marker}"], check=False)
    print(f"→ {bank.name}：已用你平常的 Chrome 開啟")
    js = (FILL_JS.replace("__CREDS__", json.dumps(creds, ensure_ascii=False))
          .replace("__HINTS__", json.dumps(bank.field_hints, ensure_ascii=False)))
    deadline = time.time() + 60
    filled = None
    while time.time() < deadline:
        try:
            output = _applescript(bank.host, marker, js)
        except RuntimeError as exc:
            if "允許來自 Apple 事件" in str(exc):
                raise
            output = "WAIT"
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
            state = json.loads(_applescript(bank.host, marker, STATE_JS))
            if _logged_in(state):
                print(f"✓ {bank.name}：登入完成")
                return True
        except (RuntimeError, ValueError):
            pass
        time.sleep(2)
    return False


INSPECT_JS = r"""
(() => {
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
})()
"""


def inspect_page(bank_code: str) -> list[dict]:
    """列出已開啟的銀行登入頁欄位（名稱、類型、位置），不讀取欄位內容。"""
    bank = WEB_BANKS[bank_code]
    rows = json.loads(_applescript(bank.host, f"bank-sync-{bank_code}", INSPECT_JS))
    for i, r in enumerate(rows):
        if r["type"] == "hidden":
            continue
        print(f"{i:>2} {'可見' if r['visible'] else '隱藏'} {r['tag']}/{r['type']:<9} id={r['id']!r} name={r['name']!r} "
              f"placeholder={r['placeholder']!r} aria={r['aria']!r} readonly={r['readonly']} "
              f"位置=({r['x']},{r['y']}) 標籤={r['label']!r}")
    return rows
