#!/bin/bash
# 在 Finder 雙擊這個檔案：更新程式後開啟「銀行帳戶與信用卡」頁（瀏覽器會自動打開）
cd "$(dirname "$0")" || exit 1
git pull -q || true
exec python3 -m streamlit run bank_app.py --server.headless false
