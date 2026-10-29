# Jenny 投資系統

Streamlit 主程式：`invesapp_supabase.py`（部署於 investment-system.streamlit.app，分支 `main`）。
主程式只負責讀資料、最上方指標與功能列，各頁程式在 `invest_app/`；一頁出錯只影響該頁。

| 模組 | 內容 |
|---|---|
| `invest_app/core.py` | 設定、Supabase、持倉讀寫、報價／匯率、enrich 計算、總帳讀取 |
| `invest_app/overview.py` | 投資總覽 |
| `invest_app/non_investment.py` | 非投資總覽、總資產列、快照的非投資欄位 |
| `invest_app/history.py` | 歷史記錄 |
| `invest_app/platform_page.py` | 台股／美股／基富通／渣打基金／台新基金 |
| `invest_app/research.py` | 股票研究 |
| `invest_app/positions_admin.py` | 平台持倉編輯表、上傳檔讀取 |
| `invest_app/dividends.py` | 基金配息與配息記錄 |
| `invest_app/stock_dividends.py` | 台股股利 |

## 功能列

| 功能列 | 內容 |
|---|---|
| 投資總覽 | 各投資平台市值、損益、配息與即時匯率 |
| 非投資總覽 | 銀行、保險、懷思投資、uncle待還、外幣與明細，每月加總（讀總帳試算表） |
| 歷史記錄 | 每日快照：投資市值；自 2026/10/11 起另記其他資產、扣除待還、總資產 |
| 台股／美股／基富通／渣打基金／台新基金 | 各平台持倉明細與編輯 |
| 股票研究 | 持股分析、觀察股票池、熱門候選 |
| 配息記錄／台股股利 | 基金配息與台股股利 |

最上方固定顯示總台幣市值等指標，下方一列為總資產（投資市值 + 其他資產 − 待還）。功能列一次只執行選到的那一頁，網址 `?page=` 記住目前頁面。

## 其他檔案

- `asset_summary.py`：總帳試算表解析（非投資總覽、命令列彙總），說明見 `ASSET_SUMMARY.md`
- `record_snapshot.py` + `.github/workflows/snapshot.yml`：每天 08:00／20:00 歷史快照
- `sync_tw_stock_prices.py`：台股股價（開盤日 08:30–14:30 每 10 分鐘）更新 Google Sheets，見 `TW_STOCK_PRICE_SYNC.md`
- `sync_us_stock_prices.py`：美股股價（台北 21:00–06:00 每 30 分鐘）更新 總覽 G/H 欄
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
