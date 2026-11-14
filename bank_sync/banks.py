"""各銀行網銀登入設定（純資料，方便測試）。"""
from __future__ import annotations

from dataclasses import dataclass, field

ID_HINTS = ("身分證字號", "身分證號", "身分證")
USER_HINTS = ("使用者代號", "使用者代碼", "使用者名稱", "用戶代號", "用戶名稱")
PASSWORD_HINTS = ("使用者密碼", "網銀密碼", "用戶密碼", "網路密碼", "登入密碼", "密碼")


@dataclass(frozen=True)
class WebBank:
    code: str
    name: str
    login_url: str
    host: str                                   # 用來辨認屬於這家銀行的分頁
    entry_clicks: tuple[str, ...] = ()          # 首頁要先點的按鈕（css: 開頭為 CSS selector，其餘為文字）
    field_hints: dict[str, tuple[str, ...]] = field(default_factory=lambda: {
        "id_number": ID_HINTS, "user_code": USER_HINTS, "password": PASSWORD_HINTS})
    captcha: bool = True
    logged_in_markers: tuple[str, ...] = ("登出",)
    logged_out_markers: tuple[str, ...] = ("您已成功登出", "已登出")
    note: str = ""
    native: bool = False                        # True = 用一般模式的專用 Chrome（認得出程式控制的銀行）


WEB_BANKS: dict[str, WebBank] = {bank.code: bank for bank in (
    WebBank("taishin", "台新銀行", "https://my.taishinbank.com.tw/TIBNetBank/", "taishinbank.com.tw"),
    WebBank("fubon", "富邦銀行", "https://ebank.taipeifubon.com.tw/B2C/common/Index.faces", "taipeifubon.com.tw",
            entry_clicks=('css:[id="header_form:header_login"]',),
            field_hints={"id_number": ("身分證字號",), "user_code": ("使用者代碼",), "password": ("使用者密碼",)},
            note="富邦登入框是彈出視窗，程式會先點右上角「登入」。"),
    WebBank("sc", "渣打銀行", "https://ebank.standardchartered.com.tw/scb/public/login?lang=tw",
            "standardchartered.com.tw", native=True,
            note="渣打會擋程式控制的 Chrome，改用一般模式的專用 Chrome 視窗。"),
    WebBank("linebank", "LINE Bank", "https://accessibility.linebank.com.tw/login", "linebank.com.tw",
            captcha=False, note="LINE Bank 可能需要在手機 App 按確認。"),
    WebBank("yuanta", "元大銀行", "https://ebank.yuantabank.com.tw/nib/", "yuantabank.com.tw"),
    WebBank("next", "將來銀行", "https://accessibility.nextbank.com.tw/login", "nextbank.com.tw"),
    WebBank("ubot", "聯邦銀行", "https://www.ubot.com.tw/", "ubot.com.tw",
            entry_clicks=("個人網路銀行", "網路銀行"),
            note="聯邦從官網首頁進入；若沒有自動跳到登入頁，請手動點到登入頁，程式會接著填。"),
    WebBank("cathay", "國泰世華", "https://www.cathaybk.com.tw/MyBank/", "cathaybk.com.tw"),
    WebBank("post", "郵局", "https://ipost.post.gov.tw/pst/home.html", "post.gov.tw"),
)}
