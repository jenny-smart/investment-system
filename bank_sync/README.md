# 銀行明細同步（本機）

帳密只放在本機 `~/Bank account/personal_bank_accounts.json`（和 tool-system 的 `bank_accounts.json` 同資料夾，權限 600，不進 git）。
程式開 Chrome 預填帳密，**圖形驗證碼由本人輸入**；登入狀態保留在 `~/Bank account/chrome_profile_personal/`。

## 第一次使用

```bash
pip install playwright && playwright install chrome
python -m bank_sync setup taishin      # 逐家輸入帳密（輸入時不顯示），或照範本手動建檔
python -m bank_sync list               # 看哪幾家已設定
```

範本：`bank_sync/personal_bank_accounts.example.json`

## 登入

```bash
python -m bank_sync login              # 帳密檔裡有的銀行全部開好、預填，一家一個分頁
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
| ubot | 聯邦（信用卡） | 從官網首頁進入 |
| cathay | 國泰世華（信用卡） | |

星展沒有電腦版網銀：信用卡帳單 PDF 放 `~/Bank account/statements/星展/`（後續步驟讀取）。

找不到欄位時程式會提示，請在瀏覽器手動補填；手動點到登入頁後程式也會接著填（每家等 90 秒）。
