# 銀行明細同步（本機）

帳密只存 macOS Keychain；圖片驗證碼由本人手動輸入。

```bash
python -m bank_sync list
python -m bank_sync setup taishin_jenny_twd
python -m bank_sync open taishin_jenny_twd
```

郵局媽媽帳號使用 `post_mom_twd`。將來銀行也使用無障礙網頁版：

```bash
python -m bank_sync setup next_jenny_twd
python -m bank_sync open next_jenny_twd
```

首次使用：`pip install playwright && playwright install chromium`
