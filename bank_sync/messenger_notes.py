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


# ───────── 抓收據訊息＋對銀行明細 ─────────
# 收據格式（店家傳來）：
#   (嘉興店)1. 竹絲蝦餃(10入/盒)# × 2 = 250
#   (嘉興店)2. 第一石鹼馬桶清潔劑# × 3 = 117
#   總金額 :【367】
RECEIPTS = MSG_DIR / "receipts.json"
ITEM_RE = re.compile(r"(?:[(（]([^()（）]{1,12})[)）])?\s*\d{1,2}\s*[.．、]\s*(.+?)\s*[×xX＊*]\s*(\d+)\s*[=＝]\s*\$?([\d,]+)")
TOTAL_RE = re.compile(r"總金額\s*[:：]?\s*[【\[]?\s*\$?([\d,]+)")
WEEK = "一二三四五六日"

# 找對話的捲動區（main 裡面 overflow auto/scroll、文字最多的那塊），回傳它的文字；可順便捲動
TEXT_JS = r"""
(scroll) => {
  const main = document.querySelector('[role="main"]') || document.body;
  const boxes = [...main.querySelectorAll('div')].filter(e => {
    const s = getComputedStyle(e);
    return /auto|scroll/.test(s.overflowY) && e.scrollHeight > e.clientHeight + 50 && e.clientHeight > 200;
  });
  boxes.sort((a, b) => (b.innerText || '').length - (a.innerText || '').length);
  const box = boxes[0];
  if (box && scroll === 'top') box.scrollTop = 0;
  if (box && scroll === 'down') box.scrollTop = box.scrollTop + box.clientHeight * 0.7;
  const roles = {};
  main.querySelectorAll('[role]').forEach(e => { const r = e.getAttribute('role'); roles[r] = (roles[r] || 0) + 1; });
  return {
    found: !!box, text: box ? box.innerText : '', height: box ? box.scrollHeight : 0,
    atBottom: box ? box.scrollTop + box.clientHeight >= box.scrollHeight - 5 : true,
    url: location.href.split('?')[0], boxes: boxes.length, roles,
  };
}
"""


def merge_lines(merged: list, new: list) -> list:
    """捲動時前後兩段畫面會重疊：把新的一段接在後面（去掉重疊的部分）"""
    if not merged:
        return list(new)
    for k in range(min(len(merged), len(new)), 0, -1):
        if merged[-k:] == new[:k]:
            return merged + new[k:]
    # 找新段開頭在舊段裡的位置
    head = new[:3]
    for i in range(len(merged) - len(head), -1, -1):
        if merged[i:i + len(head)] == head:
            return merged[:i] + new
    return merged + new


def parse_date_label(text: str, today):
    """Messenger 的日期分隔：2026年1月22日／1月22日／11/13／週五／星期五／昨天／今天"""
    from datetime import date, timedelta
    t = (text or "").replace(" ", "")
    if "今天" in t:
        return today
    if "昨天" in t:
        return today - timedelta(days=1)
    m = re.search(r"(20\d{2})\s*[年/\-.]\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})", t)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(?<!\d)(\d{1,2})\s*[月/]\s*(\d{1,2})日?", t)
    if m:
        try:
            d = date(today.year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
        return d if d <= today else date(today.year - 1, d.month, d.day)
    m = re.search(r"(?:週|星期|周)([一二三四五六日天])", t)
    if m:
        want = WEEK.index("日" if m.group(1) == "天" else m.group(1))
        back = (today.weekday() - want) % 7 or 7
        return today - timedelta(days=back)
    return None


def parse_receipt(text: str) -> dict | None:
    total = TOTAL_RE.search(text or "")
    if not total:
        return None
    items, store = [], ""
    for m in ITEM_RE.finditer(text):
        store = store or (m.group(1) or "")
        name = re.sub(r"[#＃]+$", "", m.group(2)).strip()
        items.append({"name": name, "qty": int(m.group(3)), "amount": int(m.group(4).replace(",", ""))})
    return {"store": store, "items": items, "total": int(total.group(1).replace(",", ""))}


STAMP_RE = re.compile(r"(20\d{2}年\d{1,2}月\d{1,2}日|\d{1,2}月\d{1,2}日|(?:週|星期|周)[一二三四五六日天]|昨天|今天)\s*"
                      r"(?:上午|下午|中午|晚上|凌晨|早上)?\s*\d{1,2}:\d{2}")


def _date_line(line: str, today):
    """只認 Messenger 的時間分隔列（整行就是「2026年1月22日 上午10:05」「週五 下午6:24」這種），
    訊息內文的「週六11:00-18:00」「1/24(六)尾牙」不算"""
    m = STAMP_RE.fullmatch(line.strip())
    return parse_date_label(m.group(1), today) if m else None


def lines_to_receipts(lines: list, today) -> list:
    """依序走過對話文字：遇到日期就記住，收集到「總金額」就是一張收據，掛上那天"""
    out, day, buf = [], None, []
    for line in lines:
        got = _date_line(line, today)
        if got:
            day, buf = got, []
            continue
        buf.append(line)
        if TOTAL_RE.search(line):
            rec = parse_receipt("\n".join(buf))
            buf = []
            if rec:
                rec["day"] = day.isoformat() if day else ""
                out.append(rec)
    return out


def rows_to_receipts(rows: list, today) -> list:
    lines = []
    for r in rows:
        lines += [x for x in (r.get("heading", ""), *(r.get("text", "").splitlines())) if x]
    return lines_to_receipts(lines, today)


def _post_expenses() -> list:
    """本機郵局明細裡的支出（消費日、金額）"""
    from .bank_ledger import load_transactions
    txs, _ = load_transactions()
    return [t for t in txs if t.bank == "post" and t.amount < 0 and "利息" not in t.summary]


def fetch(since=None, thread: str = DEFAULT_THREAD) -> Path:
    """先看郵局有支出的日期 → 打開 Messenger 對話往上捲到最早那天 → 讀對話文字 → 每個支出日找那天的收據"""
    from datetime import date, timedelta
    from playwright.sync_api import sync_playwright
    from .login import acquire_lock, launch_context
    MSG_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    spends = _post_expenses()
    if spends:
        print(f"郵局支出 {len(spends)} 筆（{spends[0].day:%m/%d}～{spends[-1].day:%m/%d}）")
        since = since or spends[0].day - timedelta(days=7)
    since = since or date(today.year, 1, 1)
    lines, info = [], {}
    lock = acquire_lock()
    try:
        with sync_playwright() as p:
            context = launch_context(p)
            page = context.new_page()
            page.goto(thread)
            input("請在 Chrome 登入 Messenger、看到記帳對話後，回到這裡按 Enter…")
            info = page.evaluate(TEXT_JS, "")
            if not info["found"]:
                print("  ⚠️ 找不到對話的捲動區（請上傳下面的格式樣本）")
            # 1) 往上捲到 since 之前（Messenger 捲到頂才會載入更舊的）
            last_h, stale, first = 0, 0, None
            for n in range(600):
                snap = page.evaluate(TEXT_JS, "top")
                page.wait_for_timeout(1200)
                days = [d for d in (_date_line(x, today) for x in snap["text"].splitlines()) if d]
                first = min(days) if days else first
                if first and first < since:
                    break
                stale = stale + 1 if snap["height"] == last_h else 0
                last_h = snap["height"]
                if stale >= 8:
                    print(f"  ⚠️ 對話最上面只到 {first or '？'}，載不出更舊的訊息")
                    break
                if n and n % 20 == 0:
                    print(f"  往上捲中…目前到 {first or '？'}")
            print(f"  已捲到 {first or '？'}，開始往下讀…")
            # 2) 由上往下一段一段讀，接起來
            for _ in range(3000):
                snap = page.evaluate(TEXT_JS, "")
                lines = merge_lines(lines, [x.strip() for x in snap["text"].splitlines() if x.strip()])
                if snap["atBottom"]:
                    break
                page.evaluate(TEXT_JS, "down")
                page.wait_for_timeout(500)
            context.close()
    finally:
        lock.close()
    raw = MSG_DIR / f"raw_{stamp}.txt"
    raw.write_text("\n".join(lines), "utf-8")
    os.chmod(raw, 0o600)
    report(lines, since, spends)
    shape = BANK_DIR / "_explore" / f"messenger_shape_{stamp}.txt"
    shape.parent.mkdir(parents=True, exist_ok=True)
    head = [f"url={info.get('url')} 捲動區={info.get('boxes')} roles={info.get('roles')}"]
    shape.write_text("\n".join(head + [_shape(x)[:120] for x in lines[:400]]), "utf-8")
    print(f"  收據（只在本機）：{RECEIPTS}\n  格式樣本（認不出時上傳給 Claude）：{shape}")
    return RECEIPTS


def report(lines: list, since, spends=None) -> list:
    """對話文字 → 收據（存 receipts.json，since 之後的整段換新）→ 每筆郵局支出對當天收據"""
    from datetime import date
    today = date.today()
    spends = _post_expenses() if spends is None else spends
    receipts = [r for r in lines_to_receipts(lines, today) if not r["day"] or r["day"] >= since.isoformat()]
    old = [r for r in load_receipts() if r.get("day") and r["day"] < since.isoformat()]
    allr = sorted(old + receipts, key=lambda r: r["day"])
    RECEIPTS.write_text(json.dumps(allr, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(RECEIPTS, 0o600)
    nodate = sum(1 for r in receipts if not r["day"])
    print(f"  讀了 {len(lines)} 行對話，找到 {len(receipts)} 張收據" + (f"（{nodate} 張認不出日期）" if nodate else ""))
    used, ok = set(), 0
    for t in spends:
        rs = match_receipt(t.day, t.amount, allr, used)
        if rs:
            ok += 1
            print(f"  ✓ {t.day:%m/%d} 郵局 {t.amount:,.0f} → {receipt_note(rs)}")
        else:
            near = [r for r in allr if r.get("day") and 0 <= (t.day - date.fromisoformat(r["day"])).days <= 7]
            hint = "；".join(f"{r['day'][5:].replace('-', '/')} 總 {r['total']}" for r in near[-3:]) or "前一週沒有收據"
            print(f"  ✗ {t.day:%m/%d} 郵局 {t.amount:,.0f} → 對不到（{hint}）")
    print(f"  對到 {ok}/{len(spends)} 筆")
    return allr


def reparse(since=None) -> list:
    """不開瀏覽器：用本機上次存的對話文字重新解析、重新對"""
    from datetime import date, timedelta
    raws = sorted(MSG_DIR.glob("raw_*.txt"))
    if not raws:
        print("本機還沒有對話文字，請先跑 messenger-fetch")
        return []
    spends = _post_expenses()
    since = since or (spends[0].day - timedelta(days=7) if spends else date(date.today().year, 1, 1))
    print(f"用 {raws[-1].name} 重新解析")
    return report(raws[-1].read_text("utf-8").splitlines(), since, spends)


def load_receipts() -> list:
    try:
        return json.loads(RECEIPTS.read_text("utf-8"))
    except Exception:
        return []


def match_receipt(day, amount: float, receipts: list, used: set, window: int = 45):
    """用消費（取貨）日回找 Messenger 收據：收據日期 ≤ 消費日（往前 window 天內）。
    先找金額完全一樣的一張（最近的優先）；不然找幾張加起來剛好的（取貨時一起到貨）。
    回傳收據清單；對不到回傳 []"""
    from datetime import date
    from itertools import combinations
    want = round(abs(amount))
    pool = [(i, r) for i, r in enumerate(receipts)
            if i not in used and r.get("day") and 0 <= (day - date.fromisoformat(r["day"])).days <= window]
    pool.sort(key=lambda x: x[1]["day"], reverse=True)  # 同一天優先，再往前找
    for n in (1, 2, 3, 4):
        # 幾張加總（取貨時一起到貨）只找三週內的
        cands = pool if n == 1 else [x for x in pool if (day - date.fromisoformat(x[1]["day"])).days <= 21]
        for combo in combinations(cands[:15], n):
            if sum(r["total"] for _, r in combo) == want:
                used.update(i for i, _ in combo)
                return [r for _, r in combo]
    return []


def receipt_note(rs: list) -> str:
    """嘉興店 11/13 竹絲蝦餃×2 250、第一石鹼馬桶清潔劑×3 117"""
    parts = []
    for r in rs:
        items = "、".join(f"{re.sub(r'[(（][^)）]*[)）]?', '', i['name']).strip()}×{i['qty']} {i['amount']}" for i in r["items"])
        parts.append(f"{r['store']} {r['day'][5:].replace('-', '/')} {items}".strip())
    return "；".join(parts)
