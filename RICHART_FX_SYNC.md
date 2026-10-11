# Richart 匯率同步

- 來源：<https://richart.tw/TSDIB_RichartWeb/foreign-currency/demand-deposit>，取「賣外幣」（銀行買入）匯率。
- App：`fetch_fx` 先用 Richart（快取 5 分鐘），抓不到才改用 Yahoo／備援，投資總覽匯率列會標示來源。
- 總帳：GitHub Actions `Richart FX to 總帳 R column`（`.github/workflows/richart-fx.yml`）
  週一至週五台北 09:30、12:30、15:30 執行 `sync_richart_fx.py`，
  把「總覽」Q 欄第一組 美金／南非／人民／日幣 對應的 R 欄改成 Richart 匯率。
- 需求：總帳試算表要「共用」給 `INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON` 裡的 `client_email`（編輯者）。
- 第一次請手動執行 workflow 並勾 `dry_run`，確認 log 中 `Richart {...}` 匯率正確再正式執行。
