from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Iterable

from .catalog import BankAccountSpec
from .credentials import load_secret


@dataclass(frozen=True)
class WebBank:
    name: str
    login_url: str
    credential_fields: tuple[str, ...]
    field_hints: dict[str, tuple[str, ...]]
    captcha: bool = False
    after_login: tuple[str, ...] = ()


BANKS: dict[str, WebBank] = {
    "台新銀行": WebBank("台新銀行", "https://my.taishinbank.com.tw/TIBNetBank/", ("id_number", "user_code", "password"), {"id_number": ("身分證",), "user_code": ("使用者代號",), "password": ("使用者密碼", "密碼")}, True, ("帳戶總覽", "臺幣總覽", "外幣總覽")),
    "富邦銀行": WebBank("富邦銀行", "https://ebank.taipeifubon.com.tw/B2C/common/Index.faces", ("id_number", "user_code", "password"), {"id_number": ("身分證字號",), "user_code": ("使用者代碼",), "password": ("使用者密碼", "密碼")}, True, ("帳戶服務", "交易明細查詢")),
    "元大銀行": WebBank("元大銀行", "https://b2bank.yuantabank.com.tw/B2C/login/LOGIN_Home.faces", ("id_number", "user_code", "password"), {"id_number": ("身分證字號", "身分證"), "user_code": ("使用者代碼", "使用者代號"), "password": ("網銀密碼", "密碼")}, True, ("帳務查詢", "交易明細")),
    "郵局": WebBank("郵局", "https://ipost.post.gov.tw/pst/home.html", ("id_number", "user_code", "password"), {"id_number": ("身分證號",), "user_code": ("使用者代號",), "password": ("網路密碼", "密碼")}, True, ("我的帳戶", "交易明細查詢")),
    "渣打銀行": WebBank("渣打銀行", "https://www.sc.com/tw/digital-banking/online-banking/", ("id_number", "user_code", "password"), {"id_number": ("身分證字號",), "user_code": ("使用者名稱",), "password": ("網銀密碼", "密碼")}, True, ("登入", "網路銀行", "帳戶綜覽", "台幣活存", "外幣活存")),
    "LINE BANK": WebBank("LINE BANK", "https://accessibility.linebank.com.tw/login", ("id_number", "user_code", "password"), {"id_number": ("身分證字號",), "user_code": ("使用者代號",), "password": ("密碼",)}, False, ("帳戶交易明細查詢",)),
    "將來銀行": WebBank("將來銀行", "https://accessibility.nextbank.com.tw/login", ("id_number", "user_code", "password"), {"id_number": ("身分證字號",), "user_code": ("使用者代號",), "password": ("使用者密碼", "密碼")}, True, ("新臺幣帳戶總覽", "主帳戶明細查詢", "近30天")),
}


def _frames(page) -> Iterable:
    yield page
    yield from page.frames


def _fill_by_hint(page, hints: tuple[str, ...], value: str) -> bool:
    for frame in _frames(page):
        for hint in hints:
            for getter in (lambda: frame.get_by_label(hint, exact=False), lambda: frame.get_by_placeholder(hint, exact=False)):
                try:
                    locator = getter()
                    for index in range(locator.count()):
                        control = locator.nth(index)
                        if control.is_visible() and control.is_editable():
                            control.fill(value)
                            return True
                except Exception:
                    continue
    return False


def open_and_prefill(account: BankAccountSpec, profile_dir: Path | None = None, interactive: bool = True) -> None:
    if account.channel != "web":
        raise ValueError(f"{account.bank} 目前只支援 App 匯出後匯入")
    bank = BANKS[account.bank]
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("請先安裝 playwright 並執行 playwright install chromium") from exc
    profile_dir = profile_dir or Path.home() / "Library/Application Support/investment-system-bank-sync" / account.key
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(str(profile_dir), headless=False)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(bank.login_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(1_500)
        missing = []
        for field in bank.credential_fields:
            if not _fill_by_hint(page, bank.field_hints[field], load_secret(account.login_key, field)):
                missing.append(field)
        if missing:
            print("未找到欄位：" + "、".join(missing) + "；請在瀏覽器手動填寫。")
        if account.bank == "渣打銀行":
            print("渣打：先點登入，再點網路銀行；若已到登入頁可直接填寫。")
        print("請手動輸入驗證碼並登入。" if bank.captcha else "帳密已預填，請確認後登入。")
        print("登入後路徑：" + " → ".join(bank.after_login))
        if interactive:
            input("完成查詢或下載後，回到終端機按 Enter 關閉銀行視窗…")
        else:
            print("關閉銀行視窗後，本次測試會自動結束。")
            while context.pages:
                time.sleep(1)
        context.close()
