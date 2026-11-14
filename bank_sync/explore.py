"""探索模式：登入某家網銀後，由本人手動點到想自動化的頁面，程式只記錄「頁面結構」給開發用。

記錄：網址（去掉參數）、標題、選單選項文字、輸入框、按鈕／連結文字、表格欄位名稱、iframe。
不記錄：任何金額、交易內容、表格資料列；帳號等 4 碼以上的數字一律遮成 ****後3碼。
下載的檔案（例如交易明細 CSV）只記錄檔名與欄位標題列，存在 ~/Bank account/_explore/。
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

from .banks import WEB_BANKS
from .credentials import BANK_DIR

EXPLORE_DIR = BANK_DIR / "_explore"

SNAPSHOT_JS = r"""
() => {
  const mask = t => (t || '').replace(/\s+/g, ' ').trim().replace(/\d[\d,\-]{3,}\d/g, m => '****' + m.replace(/\D/g, '').slice(-3)).slice(0, 80);
  const vis = e => e && e.getClientRects().length > 0;
  const out = {title: document.title, headings: [], selects: [], inputs: [], buttons: [], links: [], tables: [], iframes: []};
  document.querySelectorAll('h1,h2,h3,h4,legend,.title,[class*="title"]').forEach(e => { if (vis(e)) { const t = mask(e.innerText); if (t && t.length < 40 && !out.headings.includes(t)) out.headings.push(t); } });
  document.querySelectorAll('select').forEach(e => { if (vis(e)) out.selects.push({name: e.name, id: e.id, options: [...e.options].slice(0, 30).map(o => mask(o.text))}); });
  document.querySelectorAll('input,textarea').forEach(e => { if (vis(e) && !['hidden', 'password'].includes(e.type)) out.inputs.push({type: e.type, name: e.name, id: e.id, placeholder: mask(e.placeholder)}); });
  document.querySelectorAll('button,input[type=button],input[type=submit],[role=button]').forEach(e => { if (vis(e)) { const t = mask(e.innerText || e.value); if (t) out.buttons.push(t); } });
  document.querySelectorAll('a').forEach(e => { if (vis(e)) { const t = mask(e.innerText); if (t && t.length < 30) out.links.push(t); } });
  document.querySelectorAll('table').forEach(t => {
    if (!vis(t)) return;
    let head = [...t.querySelectorAll('thead th, tr:first-child th')].map(c => mask(c.innerText));
    if (!head.length) { const r = t.querySelector('tr'); if (r) head = [...r.children].map(c => mask(c.innerText)); }
    const rows = t.querySelectorAll('tbody tr').length || t.querySelectorAll('tr').length;
    if (head.some(Boolean)) out.tables.push({columns: head.slice(0, 20), rows: rows});
  });
  document.querySelectorAll('iframe,frame').forEach(f => out.iframes.push((f.src || '').split('?')[0]));
  out.links = [...new Set(out.links)].slice(0, 60);
  out.buttons = [...new Set(out.buttons)].slice(0, 40);
  return out;
}
"""


def _mask(text: str) -> str:
    return re.sub(r"\d[\d,\-]{3,}\d", lambda m: "****" + re.sub(r"\D", "", m.group(0))[-3:], text or "")


def snapshot(page) -> list[dict]:
    """這個分頁所有 frame 的結構。"""
    shots = []
    for frame in page.frames:
        try:
            data = frame.evaluate(SNAPSHOT_JS)
        except Exception as exc:  # 跨網域或已關閉的 frame
            data = {"error": type(exc).__name__}
        data["url"] = (frame.url or "").split("?")[0]
        if any(data.get(k) for k in ("selects", "inputs", "buttons", "tables", "links")) or data.get("error"):
            shots.append(data)
    return shots


def describe_download(path: Path) -> dict:
    """下載檔只留檔名、類型和第一列（欄位標題）。"""
    info = {"file": path.name, "size": path.stat().st_size}
    raw = path.read_bytes()[:4000]
    for enc in ("utf-8-sig", "big5", "cp950", "utf-16"):
        try:
            text = raw.decode(enc)
            first = next((l for l in text.splitlines() if l.strip()), "")
            info.update(encoding=enc, header=_mask(first)[:300])
            break
        except UnicodeDecodeError:
            continue
    if raw[:4] == b"PK\x03\x04":
        info["type"] = "xlsx/zip"
    elif raw[:5] == b"%PDF-":
        info["type"] = "pdf"
    return info


def explore(login_key: str, bank_code: str) -> Path:
    from playwright.sync_api import sync_playwright
    from .login import acquire_lock, launch_context, open_bank, wait_for_logins
    bank = WEB_BANKS[bank_code]
    if bank.native:
        raise SystemExit(f"{bank.name} 用的是一般模式 Chrome，探索模式目前只支援程式開的 Chrome。")
    EXPLORE_DIR.mkdir(parents=True, exist_ok=True)
    dl_dir = EXPLORE_DIR / "downloads"
    dl_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = EXPLORE_DIR / f"{bank_code}_{stamp}.json"
    record = {"bank": bank.name, "visited": [], "snapshots": [], "downloads": []}

    def save():
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=1), "utf-8")

    lock = acquire_lock()
    try:
        with sync_playwright() as p:
            context = launch_context(p)
            context.on("page", lambda pg: _watch(pg, record, dl_dir))
            for pg in context.pages:
                _watch(pg, record, dl_dir)
            state = open_bank(context, login_key, bank_code)
            if not state.logged_in:
                wait_for_logins(context, [state], 300)
            print("\n=== 探索模式 ===")
            print("請在 Chrome 裡用平常的方式點到「交易明細查詢」等頁面（可以選帳戶、日期、按查詢、按下載）。")
            print("每到一個想讓程式自動化的頁面，回到終端機按 Enter 記錄一次；全部完成後輸入 q 再按 Enter。")
            while True:
                cmd = input("Enter＝記錄目前頁面／q＝結束：").strip().lower()
                if cmd == "q":
                    break
                n = 0
                for pg in context.pages:
                    if pg.is_closed() or bank.host not in pg.url:
                        continue
                    record["snapshots"].append({"time": datetime.now().strftime("%H:%M:%S"), "frames": snapshot(pg)})
                    n += 1
                save()
                print(f"  已記錄 {n} 個分頁的結構（累計 {len(record['snapshots'])} 次）")
            time.sleep(1)
            record["downloads"] = [describe_download(f) for f in sorted(dl_dir.glob("*")) if f.is_file()]
            save()
            context.close()
    finally:
        lock.close()
    print(f"\n結構記錄：{out_path}\n請打開檢查（不含金額、帳號已遮蔽），沒問題再上傳給我。")
    return out_path


def _watch(page, record: dict, dl_dir: Path) -> None:
    def on_nav(frame):
        if frame == page.main_frame:
            url = (frame.url or "").split("?")[0]
            if url and (not record["visited"] or record["visited"][-1] != url):
                record["visited"].append(url)

    def on_download(download):
        target = dl_dir / download.suggested_filename
        try:
            download.save_as(str(target))
            print(f"  已存下載檔：{target.name}")
        except Exception as exc:
            print(f"  下載檔存不下來：{exc}")

    page.on("framenavigated", on_nav)
    page.on("download", on_download)
