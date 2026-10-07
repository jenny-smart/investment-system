# 台股股價每日回填

cron-job.org 每天台北時間 15:00（Asia/Taipei）觸發 GitHub Actions 回填。GitHub 原生 schedule 已移除，避免重複執行；工作流程仍需等待 Runner，回填可能稍晚完成。

排程管理：https://console.cron-job.org/jobs/8593700

觸發方式：POST `https://api.github.com/repos/jenny-smart/investment-system/actions/workflows/tw-stock-prices.yml/dispatches`，JSON body 為 `{"ref":"main"}`。沿用 cron-job.org 的 `tool-system-cloud-scheduler` token，授權儲存庫為 tool-system、investment-system，權限為 Actions 讀寫及 Metadata 讀取。

- 試算表：`17HPytZKOPR_9Od_wor-xEx9kpccJlPS2v6B0Dz6MRYc`
- 分頁 ID：`0`（台股）、`1591931043`（「台股」的副本）
- 股票：`4401`、`6261`、`00740B`、`00927`、`6244`、`5314`
- 每次搜尋 C 欄代號，將所有相符持倉的 J 欄改成數字股價；原有查價公式會被替換，其他欄與格式不變。
- 優先查證交所 MIS 最新成交，失敗改查 Yahoo 最新未調整收盤價；週末與休市沿用最近報價，拒絕超過七日的資料。
- 查價失敗保留該股票的原值，成功股票照常更新，工作流程會顯示失敗並留下紀錄。
- 任一分頁缺少指定股票或查詢期間列號變動時，停止所有寫入。

## 憑證與手動執行

Repository Actions Secret：`INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON`，內容是有此試算表編輯權限的 Google 服務帳號 JSON。不得提交憑證到 Git。

在 Actions → **Taiwan stock prices to Google Sheets** → **Run workflow** 可立即執行；勾選 `dry_run` 只查價並預覽。

本機驗證：`python3 -m unittest discover -s tests -p test_tw_stock_prices.py`。
