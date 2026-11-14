# 銀行明細同步（本機）

帳密只放在本機 `~/Bank account/personal_bank_accounts.json`（和 tool-system 的 `bank_accounts.json` 同資料夾，權限 600，不進 git）。
程式開 Chrome 預填帳密，**圖形驗證碼由本人輸入**；登入狀態保留在 `~/Bank account/chrome_profile_personal/`。

## 第一次使用

```bash
pip install playwright "pypdf[crypto]" websocket-client && playwright install chrome
python -m bank_sync setup taishin      # 逐家輸入帳密（輸入時不顯示），或照範本手動建檔
python -m bank_sync list               # 看哪幾家已設定
```

範本：`bank_sync/personal_bank_accounts.example.json`

## 登入

```bash
python -m bank_sync login              # 帳密檔裡有的銀行，一次一家：預填 → 你登入 → 才開下一家
python -m bank_sync login fubon sc     # 只開指定銀行
```

| 登入名稱 | 銀行 | 備註 |
|---|---|---|
| taishin | 台新 | |
| fubon | 富邦 | 先點右上「登入」開彈窗再填（參照 tool-system） |
| sc | 渣打 | 渣打會擋程式控制的 Chrome：改開一個一般模式的專用 Chrome（~/Bank account/chrome_profile_native），不影響平常的 Chrome |
| linebank | LINE Bank | 無圖形驗證碼，可能要在手機 App 確認 |
| yuanta | 元大（個人網銀） | |
| next | 將來銀行 | |


## 信用卡帳單（從 jenny@hers.com.tw 信箱）

帳密檔加上 `"mail": {"user": "jenny@hers.com.tw", "app_password": "Google 應用程式密碼"}`，各家填 `pdf_password`（帳單開啟密碼）。

```bash
python -m bank_sync fetch-statements          # 下載近 3 個月帳單到 ~/Bank account/statements/<銀行>/，並試開
python -m bank_sync check-statements          # 改了 pdf_password 後重新試開
```

| 銀行 | 細帳列 | 開啟密碼規則（銀行信件說明） |
|---|---|---|
| 富邦 | 信用卡-富邦 19 | 身分證字號（大寫）或約定密碼 |
| 台新 | 信用卡-台新 18 | 身分證後 2 碼＋生日月日 4 碼 |
| 渣打 | 信用卡-渣打 14 | 身分證字號 |
| 星展 | 信用卡-星展 08 | 身分證後 4 碼＋生日月日 4 碼 |
| 國泰世華 | 信用卡-國泰世華 24 | 身分證字號（無消費月份不寄） |
| 滙豐、聯邦 | 不記（平常不刷） | 出現帳單時提醒 |

信箱只讀不改；已下載過的信記在 `statements/_fetched.json`，不重抓。

找不到欄位時程式會提示，請在瀏覽器手動補填；手動點到登入頁後程式也會接著填（每家等 90 秒）。

## 信用卡 → 總帳

細帳月份＝**繳款截止日**的月份，金額＝**本期應繳總額**（已用 2026細帳 既有數字核對：台新、富邦、星展相符）。

```bash
python3 -m bank_sync fetch-statements --months 12   # 抓今年全部帳單
python3 -m bank_sync preview-statements             # 每份帳單解析結果（不需 Google 權限）
python3 -m bank_sync ledger                         # 只比對：產生 statements/_細帳比對_YYYYMMDD.xlsx
python3 -m bank_sync ledger --apply                 # 確認報表後才寫入
```

- **2026細帳**：金額不動，只在「信用卡-xx」列該月格子加備註（逐筆消費＋加註日期）；同一份帳單重跑會更新同一段備註。
- **2026細帳(含信用卡)**：第一次 --apply 時整張複製 2026細帳；每筆刷卡依分類規則以「+金額」加進零用金各項並附備註；同月刷卡合計同額加到第 25 列「零用金」（照 Jenny 記銀行支出的規則，現金餘額不變）；另加「零用金-信用卡消費」「零用金-現金消費」兩列。同一份帳單只加一次（記在 statements/_ledger_applied.json）。
- 每改一格發一則行事曆事件到 jennytsai26888@gmail.com。`fetch-statements` 抓到新帳單時也會發一則「【信用卡帳單】銀行 月份 應繳 X」（`--due-reminder` 另在截止日前一天提醒；`--no-notify` 關閉）。
- 分類規則：程式內建，另可在 `~/Bank account/category_rules.json` 加 `[["關鍵字", "零用金-餐費"], ...]`（優先）。對不到的放「零用金-其他」並標待分類。
- 寫入權限：不需服務帳號金鑰。執行一次 `python3 -m bank_sync google-login`，用 jennytsai26888@gmail.com 授權「試算表」「日曆活動」，
  refresh token 存進帳密檔（沿用 tool-system 的電腦版 OAuth 用戶端，從 ~/lemon/.streamlit/secrets.toml 讀；或給 client_secret JSON 路徑）。
  需要 `pip3 install gspread google-auth google-auth-oauthlib openpyxl`。
- 渣打 PDF 的中文字抽不出來（只有數字）：金額可對，商店名稱待處理。
