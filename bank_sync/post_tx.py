"""郵局（網路郵局 ipost）：查詢存簿交易明細，存到本機。

探索結果：我的帳戶 → 帳戶查詢 → 交易明細（單頁網站 /pst/index.html），每頁筆數下拉（50筆／100筆／全部）、
「存成CSV」。結果不是 <table>，所以用「全部」＋「存成CSV」下載完整明細再讀（下載檔只存在本機）。
欄位：交易日期 交易時間／摘要／沖銷記號／提款金額／存款金額／結存金額／備註／附言（日期是民國年）。
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from .credentials import BANK_DIR
from .taishin_tx import keep_new, parse_day, shape_report

TX_DIR = BANK_DIR / "transactions" / "post"
STATE_FILE = TX_DIR / "_state.json"
HEAD = ["交易日期", "交易時間", "摘要", "提款金額", "存款金額", "結存金額", "備註", "附言"]

READY_JS = "() => /區間查詢/.test(document.body.innerText) && /自訂/.test(document.body.innerText)"  # 查詢條件頁


def _click(page, *names) -> bool:
    for n in names:
        for make in (lambda: page.get_by_role("link", name=n, exact=True), lambda: page.get_by_text(n, exact=True)):
            try:
                loc = make()
                for i in range(min(loc.count(), 5)):
                    if loc.nth(i).is_visible():
                        loc.nth(i).click(timeout=4000)
                        return True
            except Exception:
                continue
    return False


def _goto(page) -> None:
    from .login import drain_stdin
    for step in range(12):
        try:
            if page.evaluate(READY_JS):
                return
        except Exception:
            pass
        if step % 3 == 0:
            _click(page, "我的帳戶")
        elif step % 3 == 1:
            _click(page, "帳戶查詢")
        else:
            _click(page, "交易明細查詢", "交易明細", "存簿交易明細")
        page.wait_for_timeout(1500)
    drain_stdin()
    input("  請在 Chrome 點到「我的帳戶 → 交易明細查詢」（看得到「區間查詢／自訂」的那頁），回到這裡按 Enter：")


def _roc(text: str) -> str:
    """民國 115/11/05 → 2026/11/05。"""
    m = re.search(r"(\d{2,4})[/\-.](\d{1,2})[/\-.](\d{1,2})", text or "")
    if not m:
        return ""
    y = int(m.group(1))
    y = y + 1911 if y < 1911 else y
    return f"{y}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"


def parse_csv(raw: bytes) -> list[list[str]]:
    text = None
    for enc in ("utf-8-sig", "big5", "cp950", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return []
    rows = list(csv.reader(io.StringIO(text)))
    hi = next((i for i, r in enumerate(rows) if any("摘要" in c for c in r)), None)
    if hi is None:
        return []
    head = [c.strip() for c in rows[hi]]

    def col(*names):
        return next((i for i, h in enumerate(head) for n in names if n in h), None)

    i_date, i_time = col("交易日期"), col("交易時間")
    i_memo, i_out, i_in = col("摘要"), col("提款", "支出"), col("存款", "存入")
    i_bal, i_note, i_msg = col("結存", "餘額"), col("備註"), col("附言")
    out = []
    for r in rows[hi + 1:]:
        get = lambda i: (r[i].strip() if i is not None and i < len(r) else "")
        day = _roc(get(i_date))
        if not day:
            continue
        if i_time is None or i_time == i_date:  # 「交易日期 交易時間」同一欄
            clock = get(i_date).split(" ")[-1] if " " in get(i_date) else ""
        else:
            clock = get(i_time)
        out.append([day, clock, get(i_memo), get(i_out), get(i_in), get(i_bal), get(i_note), get(i_msg)])
    return out


RADIO_JS = r"""
(name) => {
  // 點「文字＝name」旁邊的 radio（區間查詢／一週／一個月／自訂…）
  const vis = e => e.getClientRects().length > 0;
  const radios = [...document.querySelectorAll('input[type=radio]')];
  for (const r of radios) {
    const lab = (r.id && document.querySelector(`label[for="${r.id}"]`)) || r.closest('label');
    let text = lab ? lab.innerText : '';
    if (!text) { let n = r.nextSibling; while (n && !(n.textContent || '').trim()) n = n.nextSibling; text = n ? n.textContent : ''; }
    if (text.replace(/\s+/g, '') === name) { (lab && vis(lab) ? lab : r).click(); if (!r.checked) r.click(); return r.checked; }
  }
  return false;
}
"""

PERIODS = ((1, "當日"), (7, "一週"), (31, "一個月"), (92, "三個月"), (183, "六個月"))


def plan_queries(start: date, today: date) -> list:
    """要查哪幾次：六個月內 → 一個剛好涵蓋的選項；超過 → 先「六個月」，再「自訂」補更早那段（自訂一次不超過六個月）。"""
    need = (today - start).days + 1
    label = next((name for days, name in PERIODS if days >= need), None)
    if label:
        return [label]
    out, cursor = ["六個月"], start
    six_start = today - timedelta(days=182)
    while cursor < six_start:
        end = min(cursor + timedelta(days=179), six_start + timedelta(days=30))  # 跟「六個月」重疊一點，不會漏
        out.append((cursor, end))
        cursor = end + timedelta(days=1)
    return out


def _set_period(page, period) -> str:
    """period：「一週／一個月／六個月…」或 (起日, 迄日) 用自訂。"""
    page.evaluate(RADIO_JS, "區間查詢")
    if isinstance(period, str):
        page.evaluate(RADIO_JS, period)
        return period
    start, end = period
    page.evaluate(RADIO_JS, "自訂")
    roc = lambda d: f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"
    want = [roc(start), roc(end)]
    set_js = r"""
    (vals) => {
      // 日期欄（值像 115/11/16，可能沒寫 type、可能唯讀）：直接改值並觸發事件
      const boxes = [...document.querySelectorAll('input')].filter(i => /^\d{3}\/\d{2}\/\d{2}$/.test(i.value || '') || /date|Date|DT|dt/.test(i.name + i.id));
      boxes.slice(0, 2).forEach((b, k) => {
        b.removeAttribute('readonly');
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        setter.call(b, vals[k]);
        for (const ev of ['input', 'change', 'blur']) b.dispatchEvent(new Event(ev, {bubbles: true}));
        if (window.jQuery) { try { window.jQuery(b).val(vals[k]).trigger('change'); } catch (e) {} }
      });
      return boxes.slice(0, 2).map(b => b.value);
    }
    """
    # 1) jQuery 日曆元件：用元件自己的 setDate（郵局的日期欄只認日曆選的值）
    dates = [start, end]
    got = page.evaluate(r"""
    (ymd) => {
      const $ = window.jQuery;
      const boxes = [...document.querySelectorAll('input')].filter(i => /^\d{3}\/\d{2}\/\d{2}$/.test(i.value || ''));
      if (!$ || !boxes.length) return null;
      boxes.slice(0, 2).forEach((b, k) => {
        try { if ($(b).datepicker) $(b).datepicker('setDate', new Date(ymd[k][0], ymd[k][1] - 1, ymd[k][2])); } catch (e) {}
        try { $(b).trigger('change'); } catch (e) {}
      });
      return boxes.slice(0, 2).map(b => b.value);
    }
    """, [[d.year, d.month, d.day] for d in dates])
    if got != want:  # 2) 真的用滑鼠點日曆：點日期欄 → 選年、選月 → 點日
        boxes = page.locator("input")
        idx = [i for i in range(boxes.count()) if re.fullmatch(r"\d{3}/\d{2}/\d{2}", boxes.nth(i).input_value() or "")]
        months = ["一月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "十一月", "十二月"]
        for i, d in zip(idx[:2], dates):
            try:
                boxes.nth(i).click(timeout=3000)
                page.wait_for_timeout(500)
                sels = page.locator("select:visible")
                for k in range(sels.count()):
                    opts = sels.nth(k).locator("option").all_inner_texts()
                    if str(d.year - 1911) in [o.strip() for o in opts]:
                        sels.nth(k).select_option(label=str(d.year - 1911))
                    elif months[d.month - 1] in [o.strip() for o in opts]:
                        sels.nth(k).select_option(label=months[d.month - 1])
                page.wait_for_timeout(300)
                cell = page.locator("td:visible, a:visible").filter(has_text=re.compile(rf"^\s*{d.day}\s*$"))
                for k in range(cell.count()):
                    c = cell.nth(k)
                    if "disabled" not in (c.get_attribute("class") or "") and "unselectable" not in (c.get_attribute("class") or ""):
                        c.click(timeout=3000)
                        break
                page.wait_for_timeout(300)
            except Exception:
                continue
        got = [boxes.nth(i).input_value() for i in idx[:2]]
    if got != want:  # 3) 最後才直接改值
        got = page.evaluate(set_js, want)
    page.keyboard.press("Escape")  # 關掉日曆
    if got != want:
        print(f"  ⚠️ 自訂日期沒填進去（要 {want}，現在是 {got}）")
    return f"自訂 {roc(start)}～{roc(end)}"


def fetch(since: date = None, keep_open: bool = False) -> Path:
    from playwright.sync_api import sync_playwright
    from .login import acquire_lock, launch_context, logout_all, open_bank, wait_for_logins
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
    lock = acquire_lock()
    try:
        with sync_playwright() as p:
            context = launch_context(p)
            state = open_bank(context, "post_jenny", "post")
            if not state.logged_in:
                print("請在 Chrome 完成郵局登入（輸入驗證碼）…")
                wait_for_logins(context, [state], 300)
            if not state.logged_in:
                raise SystemExit("郵局沒有登入成功，停止。")
            page = state.page
            page.wait_for_timeout(2000)
            try:
                _goto(page)
                key = "TWD:郵局存簿"
                start = parse_day(progress.get(key, {}).get("last_date", "")) or since
                rows, earliest = [], None
                for n, period in enumerate(plan_queries(start, date.today())):
                    if n:
                        _goto(page)
                    label = _set_period(page, period)
                    _click(page, "查詢")
                    page.wait_for_timeout(3000)
                    shown = page.evaluate(r"""() => { const t = document.body.innerText;
                        const p = t.match(/查詢期間\s*[:：]?\s*(\d{3}\/\d{1,2}\/\d{1,2})\s*[~～－-]\s*(\d{3}\/\d{1,2}\/\d{1,2})/);
                        if (p) return [p[1], p[2]];
                        const a = t.match(/查詢起始日期\s*(\d{3}\/\d{1,2}\/\d{1,2})/); const b = t.match(/查詢迄止日期\s*(\d{3}\/\d{1,2}\/\d{1,2})/);
                        return [a ? a[1] : '', b ? b[1] : '']; }""")
                    got = parse_day(shown[0])
                    if got and (earliest is None or got < earliest):
                        earliest = got
                    try:  # 每頁筆數選「全部」
                        page.evaluate("""() => { const s = [...document.querySelectorAll('select')].find(x => [...x.options].some(o => o.text.trim() === '全部'));
                            if (s) { s.selectedIndex = [...s.options].findIndex(o => o.text.trim() === '全部'); s.dispatchEvent(new Event('change', {bubbles: true})); } }""")
                        page.wait_for_timeout(1500)
                    except Exception:
                        pass
                    part = []
                    if "查無資料" not in page.evaluate("() => document.body.innerText"):
                        with page.expect_download(timeout=30000) as info:
                            if not _click(page, "存成CSV"):
                                raise RuntimeError("找不到「存成CSV」")
                        target = TX_DIR / f"{stamp}_post_{n + 1}.csv"
                        info.value.save_as(str(target))
                        os.chmod(target, 0o600)
                        part = parse_csv(target.read_bytes())
                    rows += [r for r in part if r not in rows]
                    print(f"  查詢 {label}（郵局實際 {shown[0]}～{shown[1]}）：{len(part)} 筆")
                    _click(page, "回上一頁", "上一頁", "重新查詢")
                    page.wait_for_timeout(1500)
                total = len(rows)
                rows.sort(key=lambda r: (r[0], r[1]))
                new, progress[key] = keep_new(rows, progress.get(key, {}), start)
                days = [parse_day(r[0]) for r in rows]
                span = f"{min(days):%Y/%m/%d}～{max(days):%Y/%m/%d}" if days else "沒有資料"
                results.append({"type": "TWD", "account": "郵局存簿", "ledger_row": "郵局", "from": start.isoformat(),
                                "head": HEAD, "rows": new})
                print(f"  郵局存簿：下載 {total} 筆（{span}），新的 {len(new)} 筆")
                if earliest and earliest > start:
                    print(f"  ⚠️ 郵局實際查詢只從 {earliest:%Y/%m/%d} 開始，比要的 {start:%Y/%m/%d} 晚，前面那段沒查到")
                elif days and min(days) > start:
                    print(f"  （{start:%m/%d}～{min(days):%m/%d} 之間郵局沒有交易）")
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
    STATE_FILE.write_text(json.dumps(progress, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(STATE_FILE, 0o600)
    raw_path = TX_DIR / f"{stamp}.json"
    raw_path.write_text(json.dumps({"fetched_at": stamp, "accounts": results}, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(raw_path, 0o600)
    shape_path = BANK_DIR / "_explore" / f"post_shape_{stamp}.txt"
    shape_path.parent.mkdir(parents=True, exist_ok=True)
    shape_path.write_text(shape_report(results), "utf-8")
    print(f"\n明細（只存在本機）：{raw_path}")
    print(f"格式樣本（可上傳給 Claude）：{shape_path}")
    log_run("郵局明細", since, TX_DIR, results, problem)
    return raw_path
