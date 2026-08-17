"""
wake_app.py
排程記錄快照前先執行：用真正的瀏覽器（Playwright）打開 Streamlit App，
等它完整跑完一次運算（畫面出現「總台幣市值」），確保 Supabase 的
latest_portfolio_values 是當下算出來的新鮮資料，而不是上次有人開網頁時的舊資料。

單純用 curl/requests 打網址沒有用：Streamlit 的運算是靠瀏覽器建立
WebSocket 連線後才觸發執行，純 HTTP 請求只會拿到空殼頁面。
"""
from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

APP_URL = os.environ.get("STREAMLIT_APP_URL", "https://investment-system.streamlit.app/")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            page.goto(APP_URL, wait_until="networkidle", timeout=90_000)
            page.get_by_text("總台幣市值").wait_for(timeout=60_000)
            print("✅ App 已完整執行一次，Supabase 資料應已更新。")
        except Exception as exc:
            # 就算喚醒沒等到預期畫面，也不擋後面記錄快照（用現有資料儘量記）。
            print(f"⚠️ 沒等到「總台幣市值」畫面，App 可能還在載入或發生錯誤：{exc}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
    sys.exit(0)
