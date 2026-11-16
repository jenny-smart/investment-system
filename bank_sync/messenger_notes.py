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

# 依 DOM 順序抓：日期分隔列（h4 或 短文字）＋每則訊息文字；捲動容器也一併回傳
CAPTURE_JS = r"""
(scroll) => {
  const vis = e => e.getClientRects().length > 0;
  const main = document.querySelector('[role="main"]') || document.body;
  const rows = [...main.querySelectorAll('[role="row"]')].filter(vis);
  let box = rows.length ? rows[0].parentElement : null;
  while (box && !(box.scrollHeight > box.clientHeight + 20 && /auto|scroll/.test(getComputedStyle(box).overflowY))) box = box.parentElement;
  if (box && scroll === 'top') box.scrollTop = 0;
  if (box && scroll === 'down') box.scrollTop = box.scrollTop + box.clientHeight * 0.8;
  return {
    atBottom: box ? box.scrollTop + box.clientHeight >= box.scrollHeight - 5 : true,
    rows: rows.map(r => {
      const h = r.querySelector('h4,h3,[role="heading"]');
      const tips = [...r.querySelectorAll('[aria-label],[title],[data-tooltip-content]')]
        .map(e => e.getAttribute('aria-label') || e.getAttribute('title') || e.getAttribute('data-tooltip-content') || '')
        .filter(t => /\d/.test(t)).slice(0, 3);
      return {text: (r.innerText || '').trim().slice(0, 2000), heading: h ? h.innerText.trim() : '', tips};
    }),
  };
}
"""


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


def rows_to_receipts(rows: list, today) -> list:
    """依序走過訊息列：遇到日期就記住，遇到收據就掛上那天"""
    out, day = [], None
    for r in rows:
        for label in (r.get("heading", ""), r.get("text", "") if len(r.get("text", "")) <= 30 else "", *r.get("tips", [])):
            got = parse_date_label(label, today) if label else None
            if got:
                day = got
                break
        rec = parse_receipt(r.get("text", ""))
        if rec:
            rec["day"] = day.isoformat() if day else ""
            out.append(rec)
    return out


def fetch(since, thread: str = DEFAULT_THREAD) -> Path:
    """打開對話 → 往上捲到 since 之前 → 由上往下讀每一則 → 解析收據存在本機 receipts.json"""
    from datetime import date
    from playwright.sync_api import sync_playwright
    from .login import acquire_lock, launch_context
    MSG_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    seen, ordered = set(), []
    lock = acquire_lock()
    try:
        with sync_playwright() as p:
            context = launch_context(p)
            page = context.new_page()
            page.goto(thread)
            input("請在 Chrome 登入 Messenger、看到記帳對話後，回到這裡按 Enter…")
            # 1) 往上捲，直到最上面的日期早於 since，或再也載不出更舊的
            stale, top = 0, None
            for _ in range(400):
                snap = page.evaluate(CAPTURE_JS, "top")
                page.wait_for_timeout(1500)
                first = next((parse_date_label(r["heading"] or (r["text"] if len(r["text"]) <= 30 else ""), today)
                              for r in snap["rows"] if parse_date_label(r["heading"] or (r["text"] if len(r["text"]) <= 30 else ""), today)), None)
                if first and first < since:
                    break
                key = snap["rows"][0]["text"][:80] if snap["rows"] else ""
                stale = stale + 1 if key == top else 0
                top = key
                if stale >= 6:
                    print(f"  ⚠️ 對話最上面只到 {first or '？'}，載不出更舊的訊息")
                    break
            print(f"  已捲到 {first or '？'}，開始往下讀…")
            # 2) 由上往下讀（Messenger 只保留畫面附近的訊息，所以一段一段讀、去重）
            for _ in range(2000):
                snap = page.evaluate(CAPTURE_JS, "")
                for r in snap["rows"]:
                    k = (r["text"], r["heading"], tuple(r["tips"]))
                    if k not in seen:
                        seen.add(k)
                        ordered.append(r)
                if snap["atBottom"]:
                    break
                page.evaluate(CAPTURE_JS, "down")
                page.wait_for_timeout(700)
            context.close()
    finally:
        lock.close()
    raw = MSG_DIR / f"raw_{stamp}.json"
    raw.write_text(json.dumps(ordered, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(raw, 0o600)
    receipts = [r for r in rows_to_receipts(ordered, today) if not r["day"] or r["day"] >= since.isoformat()]
    old = json.loads(RECEIPTS.read_text("utf-8")) if RECEIPTS.exists() else []
    keyof = lambda r: (r["day"], r["total"], tuple((i["name"], i["qty"]) for i in r["items"]))
    merged = {keyof(r): r for r in old + receipts}
    RECEIPTS.write_text(json.dumps(sorted(merged.values(), key=lambda r: r["day"]), ensure_ascii=False, indent=1), "utf-8")
    os.chmod(RECEIPTS, 0o600)
    nodate = sum(1 for r in receipts if not r["day"])
    print(f"  讀了 {len(ordered)} 則訊息，找到 {len(receipts)} 張收據" + (f"（{nodate} 張認不出日期）" if nodate else ""))
    for r in receipts[-5:]:
        print(f"    {r['day'] or '？'} {r['store']} {len(r['items'])} 項 總金額 {r['total']}")
    shape = BANK_DIR / "_explore" / f"messenger_shape_{stamp}.txt"
    shape.parent.mkdir(parents=True, exist_ok=True)
    shape.write_text("\n".join(_shape(r["text"])[:120] + (f" ｜標題：{_shape(r['heading'])}" if r["heading"] else "")
                               + (f" ｜提示：{' / '.join(_shape(t)[:40] for t in r['tips'])}" if r["tips"] else "")
                               for r in ordered[:300]), "utf-8")
    print(f"  收據（只在本機）：{RECEIPTS}\n  格式樣本（認不出時上傳給 Claude）：{shape}")
    return RECEIPTS


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
    pool.sort(key=lambda x: x[1]["day"], reverse=True)  # 越接近消費日越優先
    for n in (1, 2, 3, 4):
        for combo in combinations(pool[:15], n):
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
