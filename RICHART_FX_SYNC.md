# Richart 匯率同步

- 來源：<https://richart.tw/TSDIB_RichartWeb/foreign-currency/demand-deposit>，取「賣外幣」（銀行買入）匯率。
- App：`fetch_fx` 先用 Richart（快取 5 分鐘），抓不到才改用 Yahoo／備援，投資總覽匯率列會標示來源。
- 總帳：GitHub Actions `Richart FX to 總帳 R column`（`.github/workflows/richart-fx.yml`）
  由 cron-job.org 每半小時觸發（workflow_dispatch）執行 `sync_richart_fx.py`，
  把「總覽」Q 欄第一組 美金／南非／人民／日幣 對應的 R 欄改成 Richart 匯率。
- 匯率來源：頁面隱藏欄位 `exchangeRateArray` 的 `richartBuyRates`（賣外幣表的 Richart 欄）。
- 權限：總帳已共用給 `tool-system@tool-495212.iam.gserviceaccount.com`（編輯者）。
- 第一次請手動執行 workflow 並勾 `dry_run`，確認 log 中 `Richart {...}` 匯率正確再正式執行。
