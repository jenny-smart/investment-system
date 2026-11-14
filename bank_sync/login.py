"""用 Playwright 開 Chrome、預填各銀行帳密；驗證碼由本人輸入（做法參照 tool-system 富邦登入）。

同一個 Chrome 設定檔（~/Bank account/chrome_profile_personal）裡一家銀行一個分頁，
登入狀態會保留；已經是登入中的銀行不會重填。
"""
from __future__ import annotations

import fcntl
import re
import time
from dataclasses import dataclass
from typing import Iterable, TextIO

from .banks import WEB_BANKS, WebBank
from .credentials import BANK_DIR, load_credentials, permission_warning

PROFILE_DIR = BANK_DIR / "chrome_profile_personal"
LOCK_FILE = BANK_DIR / "bank_sync_personal.lock"
FIELD_ORDER = ("id_number", "user_code", "password")
CAPTCHA_HINTS = ("驗證碼", "圖形驗證", "檢核碼")
INPUT = ("input:not([type=hidden]):not([type=button]):not([type=submit]):not([type=checkbox])"
         ":not([type=radio]):not([type=image]):not([type=reset])")
MARK = "bankSyncFilled"


@dataclass
class LoginState:
    login_key: str
    bank: WebBank
    page: object = None
    filled: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    logged_in: bool = False
    error: str = ""


# ---------- 共用小工具 ----------

def acquire_lock() -> TextIO:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    handle = LOCK_FILE.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError("已有個人銀行登入程式在執行；請先關閉那個 Chrome 或在原終端機按 Control+C。") from exc
    return handle


def _contexts(page) -> list:
    return [page, *[f for f in page.frames if f != page.main_frame]]


def _visible(locator) -> bool:
    try:
        return locator.is_visible()
    except Exception:
        return False


def _first_visible(locator):
    try:
        for index in range(locator.count()):
            item = locator.nth(index)
            if _visible(item):
                return item
    except Exception:
        pass
    return None


def _text_visible(page, text: str) -> bool:
    for ctx in _contexts(page):
        if _first_visible(ctx.get_by_text(text, exact=False)) is not None:
            return True
    return False


def _has_visible_password(page) -> bool:
    return any(_first_visible(ctx.locator('input[type="password"]')) is not None for ctx in _contexts(page))


def _claimed(locator) -> bool:
    try:
        return bool(locator.evaluate(f"e => e.dataset.{MARK} === '1'"))
    except Exception:
        return True


def _unclaimed_inputs(locator) -> Iterable:
    try:
        count = locator.count()
    except Exception:
        return
    for index in range(count):
        item = locator.nth(index)
        try:
            if not _visible(item) or not item.is_editable():
                continue
            kind = (item.get_attribute("type") or "text").lower()
        except Exception:
            continue
        if kind in {"hidden", "button", "submit", "checkbox", "radio", "image", "reset"}:
            continue
        if not _claimed(item):
            yield item


# ---------- 找登入框 ----------

def _bank_pages(context, bank: WebBank) -> list:
    return [p for p in context.pages if not p.is_closed() and bank.host in p.url]


def _is_login_frame(ctx, bank: WebBank) -> bool:
    try:
        if ctx.locator(INPUT).filter(visible=True).count() < 2:
            return False
    except Exception:
        return False
    if _first_visible(ctx.locator('input[type="password"]')) is not None:
        return True
    return any(_first_visible(ctx.get_by_text(h, exact=False)) is not None for h in bank.field_hints["password"])


def _click_entry(page, bank: WebBank) -> None:
    for target in bank.entry_clicks:
        for ctx in _contexts(page):
            if target.startswith("css:"):
                item = _first_visible(ctx.locator(target[4:]))
            else:
                item = _first_visible(ctx.get_by_role("link", name=target)) or _first_visible(
                    ctx.get_by_role("button", name=target)) or _first_visible(ctx.get_by_text(target, exact=True))
            if item is not None:
                try:
                    item.evaluate("e => e.click()")
                    page.wait_for_timeout(1500)
                    return
                except Exception:
                    continue


def find_login_frame(context, bank: WebBank, timeout_s: float = 90):
    """在這家銀行的所有分頁（含彈出視窗）與 iframe 裡找登入框；找不到時給本人時間手動點到登入頁。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for page in reversed(_bank_pages(context, bank)):
            for ctx in _contexts(page):
                if _is_login_frame(ctx, bank):
                    return page, ctx
        time.sleep(0.5)
    return None, None


# ---------- 填帳密 ----------

def _input_for_hint(ctx, hint: str):
    for locator in (
        ctx.get_by_label(hint, exact=False),
        ctx.get_by_placeholder(hint, exact=False),
        ctx.locator(f'input[aria-label*="{hint}"], input[title*="{hint}"]'),
    ):
        for item in _unclaimed_inputs(locator):
            return item
    try:
        labels = ctx.get_by_text(hint, exact=False)
        count = labels.count()
    except Exception:
        return None
    for index in range(count):
        label = labels.nth(index)
        if not _visible(label):
            continue
        # 富邦等表格版面：同一列的輸入框；其他版面：標籤後面第一個輸入框
        for path in ("xpath=ancestor::tr[1]//input", "xpath=following::input"):
            for item in _unclaimed_inputs(label.locator(path)):
                return item
    return None


def _type_like_user(page, item, value: str) -> None:
    item.click()
    item.press("ControlOrMeta+a")
    item.press("Backspace")
    item.type(value, delay=30)
    item.evaluate(f"e => {{ e.dataset.{MARK} = '1'; }}")


def _next_input_after(previous):
    """上一個填好的欄位後面第一個可填、且不是驗證碼的輸入框（欄位名稱抓不到時用）。"""
    if previous is None:
        return None
    for item in _unclaimed_inputs(previous.locator("xpath=following::input")):
        try:
            hint = " ".join(filter(None, (item.get_attribute(a) for a in ("name", "id", "placeholder", "aria-label", "title"))))
        except Exception:
            hint = ""
        if re.search(r"captcha|verify|驗證|檢核|vcode|chk", hint, re.I):
            return None
        return item
    return None


def fill_login(page, ctx, bank: WebBank, creds: dict[str, str]) -> tuple[list[str], list[str]]:
    # 部分銀行（如富邦）登入框開啟後才初始化安全鍵盤，太早填會被清空
    page.wait_for_timeout(800)
    filled, missing = [], []
    previous = None
    for field in FIELD_ORDER:
        value = creds.get(field)
        if not value:
            continue
        item = None
        for hint in bank.field_hints.get(field, ()):
            item = _input_for_hint(ctx, hint)
            if item is not None:
                break
        if item is None and field == "password":
            item = next(iter(_unclaimed_inputs(ctx.locator('input[type="password"]'))), None)
        if item is None and field == "password":
            item = _next_input_after(previous)
        if item is None:
            missing.append(field)
            continue
        try:
            _type_like_user(page, item, value)
            filled.append(field)
            previous = item
        except Exception:
            missing.append(field)
    for hint in CAPTCHA_HINTS:
        captcha = _input_for_hint(ctx, hint)
        if captcha is not None:
            try:
                captcha.focus()
            except Exception:
                pass
            break
    return filled, missing


# ---------- 判斷是否已登入 ----------

def _fubon_logged_in(page) -> bool:
    # 參照 tool-system open_login.is_fubon_logged_in：富邦未登入頁首也有「登出」，不能單看文字
    urls = [f.url for f in page.frames]
    if _text_visible(page, "您已成功登出"):
        return False
    if any("/Logout.faces" in u for u in urls) or _text_visible(page, "您上次登入系統時間為"):
        return True
    if any("/PreLogin.faces" in u for u in urls):
        return False
    return any("/B2C/" in u and "/B2C/common/" not in u for u in urls if u.startswith("http"))


def is_logged_in(page, bank: WebBank) -> bool:
    try:
        if page.is_closed():
            return False
        if bank.code == "fubon":
            return _fubon_logged_in(page)
        if any(_text_visible(page, m) for m in bank.logged_out_markers):
            return False
        if _has_visible_password(page):
            return False
        return any(_text_visible(page, m) for m in bank.logged_in_markers)
    except Exception:
        return False


def _logged_in_page(context, bank: WebBank):
    for page in _bank_pages(context, bank):
        if is_logged_in(page, bank):
            return page
    return None


# ---------- 主流程 ----------

def open_bank(context, login_key: str, bank_code: str) -> LoginState:
    bank = WEB_BANKS[bank_code]
    state = LoginState(login_key, bank)
    try:
        creds = load_credentials(login_key)
        existing = _logged_in_page(context, bank)
        if existing is not None:
            state.page, state.logged_in = existing, True
            print(f"✓ {bank.name}：已是登入狀態")
            return state
        page = context.new_page()
        page.goto(bank.login_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(1500)
        if is_logged_in(page, bank):
            state.page, state.logged_in = page, True
            print(f"✓ {bank.name}：已是登入狀態")
            return state
        _click_entry(page, bank)
        login_page, ctx = find_login_frame(context, bank)
        if ctx is None:
            state.page, state.error = page, "找不到登入欄位，請在瀏覽器手動登入"
            print(f"! {bank.name}：{state.error}")
            return state
        filled, missing = fill_login(login_page, ctx, bank, creds)
        state.page, state.filled, state.missing = login_page, tuple(filled), tuple(missing)
        tip = "請輸入驗證碼並按登入" if bank.captcha else "請確認後按登入"
        extra = f"（找不到欄位：{'、'.join(missing)}，請手動填）" if missing else ""
        print(f"→ {bank.name}：已預填 {len(filled)} 欄，{tip}{extra}")
        if bank.note:
            print(f"   {bank.note}")
    except Exception as exc:  # 一家失敗不影響其他銀行
        state.error = f"{type(exc).__name__}: {exc}"
        print(f"! {bank.name}：{state.error}")
    return state


def wait_for_logins(context, states: list[LoginState], timeout_s: float = 900) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        pending = [s for s in states if not s.logged_in]
        if not pending:
            return
        for state in pending:
            page = _logged_in_page(context, state.bank)
            if page is not None:
                state.page, state.logged_in = page, True
                print(f"✓ {state.bank.name}：登入完成")
        time.sleep(2)


def launch_context(playwright):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    options = dict(user_data_dir=str(PROFILE_DIR), headless=False, locale="zh-TW", no_viewport=True)
    try:
        return playwright.chromium.launch_persistent_context(channel="chrome", **options)
    except Exception as exc:
        if "ProcessSingleton" in str(exc) or "already in use" in str(exc):
            raise RuntimeError(f"個人銀行用的 Chrome 還開著（{PROFILE_DIR}），請先關掉再執行。") from exc
        print("找不到 Google Chrome，改用 Playwright Chromium。")
        return playwright.chromium.launch_persistent_context(**options)


def login_banks(targets: list[tuple[str, str]], keep_open: bool = True, timeout_s: float = 300) -> list[LoginState]:
    """targets: [(登入名稱, 銀行代碼)]。一次一家：開好、預填，等本人登入完成才開下一家。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("請先安裝：pip install playwright && playwright install chrome") from exc
    warning = permission_warning()
    if warning:
        print(warning)
    lock = acquire_lock()
    try:
        with sync_playwright() as playwright:
            context = launch_context(playwright)
            states = []
            for index, (key, code) in enumerate(targets, 1):
                print(f"\n[{index}/{len(targets)}] {WEB_BANKS[code].name}")
                state = open_bank(context, key, code)
                states.append(state)
                if not state.error and not state.logged_in:
                    wait_for_logins(context, [state], timeout_s)
                    if not state.logged_in:
                        print(f"✗ {state.bank.name}：{int(timeout_s // 60)} 分鐘內沒有完成登入，先跳到下一家")
            print("\n登入結果：")
            for s in states:
                mark = "✓" if s.logged_in else "✗"
                print(f"  {mark} {s.bank.name}{'' if s.logged_in else '（' + (s.error or '未完成登入') + '）'}")
            if keep_open:
                input("\n查詢完成後，回到終端機按 Enter 關閉 Chrome…")
            context.close()
            return states
    finally:
        lock.close()
