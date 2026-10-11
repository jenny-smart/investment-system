# Jenny 投資系統

Streamlit 主程式：`invesapp_supabase.py`（部署於 investment-system.streamlit.app，分支 `main`）。

## 功能列

| 功能列 | 內容 |
|---|---|
| 投資總覽 | 各投資平台市值、損益、配息與即時匯率 |
| 非投資總覽 | 銀行、保險、懷思投資、uncle待還、外幣與明細，每月加總（讀總帳試算表） |
| 📊 歷史記錄 | 每日快照：投資市值；自 2026/10/11 起另記其他資產、扣除待還、總資產 |
| 台股／美股／基富通／渣打基金／台新基金 | 各平台持倉明細與編輯 |
| 🔎 股票研究 | 持股分析、觀察股票池、熱門候選 |
| 資料安全 | 匯出備份、Supabase 欄位提醒 SQL |
| 工具 | 批次更新、修復排序、抓價測試 |
| 💰 配息記錄／📈 台股股利 | 基金配息與台股股利 |

最上方固定顯示總台幣市值等指標，下方一列為總資產（投資市值 + 其他資產 − 待還）。功能列一次只執行選到的那一頁，網址 `?page=` 記住目前頁面。

## 其他檔案

- `asset_summary.py`：總帳試算表解析（非投資總覽、命令列彙總），說明見 `ASSET_SUMMARY.md`
- `record_snapshot.py` + `.github/workflows/snapshot.yml`：每天 08:00／20:00 歷史快照
- `sync_tw_stock_prices.py`：台股股價回填 Google Sheets，見 `TW_STOCK_PRICE_SYNC.md`
- `stock_radar/`：台股每日雷達
- `supabase_schema.sql`：Supabase 資料表與欄位

## 銀行明細同步（本機）

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
