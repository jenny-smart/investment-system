# 台股股價排程

cron-job.org 依台北時間觸發 GitHub Actions **Taiwan stock prices to Google Sheets**，
在**開盤日 08:30–14:30 每 10 分鐘**更新一次兩個分頁的 J 欄股價：

1. 讀取 A7 起 C 欄非空白的列。
2. 每個股票代號第一次出現的列，J 欄寫入最新股價。
3. 同一代號之後再出現的列，J 欄寫入公式 `=J<第一列>`，直接引用上方第一個相同代號的 J 欄。
4. 兩個分頁的 A2 寫入本次更新的日期與時間（例如 `2026/10/29 10:30`），每次覆蓋前一次。

C 欄不是台股代號的列（例如 `AAPL`）不會變動。查不到報價的代號保留原值，
其他列照常更新，工作流程標示失敗以便察覺。

## Cronjobs 設定

建立一個工作，時區 `Asia/Taipei`，排程 `*/10 8-14 * * 1-5`，以 workflow_dispatch 傳入 `mode=auto`。
程式只在週一至週五 08:30–14:30 之間更新，08:00、08:10、08:20、14:40、14:50 觸發時會直接略過。
另會查詢交易所休市日（`openapi.twse.com.tw` 的 holidaySchedule），休市日整天略過；
查詢失敗時視為開盤照常更新。颱風等臨時休市無法預知，會照常寫入最近收盤價。
14:30 那次若 Runner 延遲，09 分鐘內開始都仍會執行。

原有的排程 `8631524`（temporary）、`8631529`（restore）、`8593700`（fixed）請停用或刪除；
這些模式已從程式移除，再觸發會失敗。

## 注意

- J 欄原本的 `GOOGLEFINANCE` 公式會被股價數值（或 `=J<第一列>`）取代。
- 只更新值，不改動儲存格底色；之前暫填股價留下的黃色底色需手動調整。
- 隱藏工作表 `_tw_price_formula_backup` 已不再使用，可自行刪除。
- 查價優先使用交所 MIS（每 20 檔合併一次請求），失敗時改用 Yahoo 最近收盤價，拒絕超過七日的報價。
- 寫入前會重新讀取 C 欄；查價期間若有插入或刪除列，該次不寫入。

## 手動執行

Actions → **Taiwan stock prices to Google Sheets** → **Run workflow**：

- `auto`：只在開盤日 08:30–14:30 執行。
- `update`：不論時間、是否開盤，立即更新。
- `dry_run`：只預覽，不寫入。

本機測試：`python3 -m unittest discover -s tests -p test_tw_stock_prices.py`。

## 美股（總覽 G/H）

`sync_us_stock_prices.py` 由 cron-job.org 觸發，週一至週五台北時間 **21:00 至隔天 06:00 每 30 分鐘**更新，
讀取 `總覽` F 欄「美股」標題下方到第一個空白列為止的代號（目前 `pypl`、`xyz`），
以 Yahoo 最新價格寫入 G（報價日期，美東日期）與 H（價格）。

所有排程與 cron-job.org、GitHub、Streamlit 的設定方式見 `SCHEDULES.md`。
