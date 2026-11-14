# 銀行明細同步（本機）

帳密只放在本機 `~/Bank account/personal_bank_accounts.json`（和 tool-system 的 `bank_accounts.json` 同資料夾，權限 600，不進 git）。
程式開 Chrome 預填帳密，**圖形驗證碼由本人輸入**；登入狀態保留在 `~/Bank account/chrome_profile_personal/`。

## 第一次使用

```bash
pip install playwright "pypdf[crypto]" && playwright install chrome
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
| sc | 渣打 | |
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
