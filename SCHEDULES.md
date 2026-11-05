# 排程與設定

GitHub 原生排程（workflow 裡的 `schedule`）是「盡量執行」，負載高時會延遲或直接丟掉，
曾經一晚應跑 16 次只跑 1 次。所以 workflow 只保留 `workflow_dispatch`（手動 / API 觸發）。

**2026-11 起，所有排程都在 tool-system 主控表的「排程設定」分頁管理**（系統名稱 `investment-system`）：
tool-system 的 Cloud Schedule Router 每 10 分鐘讀那張表，到時間就派送本 repo 的 workflow
（帶 `scheduled_slot`，GitHub 上的執行名稱是 `cloud-<時段>-<功能代號>`）。改時間只要改那張表。
cron-job.org 上 investment-system 的工作都可以停用。

## 排程一覽（時區 Asia/Taipei，預設值）

| 功能代號 | Workflow 檔 | 預設時間 | 說明 |
|---|---|---|---|
| invest_tw_prices | `tw-stock-prices.yml` | 週一至五 08:30–14:30 每 10 分鐘 | 台股價格；休市日程式自己略過 |
| invest_us_prices_night | `us-stock-prices.yml` | 週一至五 21:00–23:50 每 10 分鐘 | 美股價格（晚上） |
| invest_us_prices_morning | `us-stock-prices.yml` | 週二至六 00:00–06:00 每 10 分鐘 | 美股價格（凌晨） |
| invest_fund_nav | `fund-nav.yml` | 全天每 10 分鐘 | 基金淨值＋Richart 匯率；只寫有變的列 |
| invest_month_end_ledger | `month-end-ledger.yml` | 每月 1–10、28–31 日每 10 分鐘 | 月底固定／月初切換總覽（程式依日期判斷，見 `month_end_ledger.py`） |
| invest_keepalive | `keepalive.yml` | 每 30 分鐘 | App 喚醒 |
| invest_snapshot | `snapshot.yml` | 08:00、20:00 | 資產快照 |
| invest_stock_radar | `stock-radar.yml` | 週一至五 14:30 | 台股雷達 |
| ~~Richart 匯率~~（已停用） | `richart-fx.yml` | — | 匯率由「基金淨值／匯率」一併更新；此 workflow 保留供手動執行 |

時段外的觸發由程式自己略過（`auto` 模式）。

## 更新記錄

每個排程 workflow 最後一步執行 `run_log.py`，把結果寫進「更新記錄」試算表
（`1oCblr-zksaLsmK10i20PLMeDZtzk22N8QyyMuivwPOw` 的 gid `613651036` 分頁）：

- 有寫入資料的成功執行（台股／美股／基金／匯率有變、月底固定、換欄）、快照、雷達 → 寫一筆「成功」
- 失敗或取消 → 寫一筆；同一功能同一天同樣的錯誤只寫一次
- 時段外略過、資料沒變、App 喚醒成功 → 不寫
- 欄位依分頁第 1 列標題對應（執行時間、系統、功能、執行方式、期別/日期、目標位置、結果、訊息…）；
  第 1 列空白時寫入各系統統一的執行 Log 標題。訊息後面附這次 GitHub 執行的連結。

服務帳號（`INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON` 的 client_email）要設成這個試算表的**編輯者**。
寫入失敗只會在執行紀錄印 WARN，不會讓排程失敗。

## 一、GitHub：建立 token

tool-system 的 Router 和 app 都要用 token 呼叫 GitHub API 觸發 workflow。

1. GitHub 右上角頭像 → **Settings** → 左側最下方 **Developer settings**
   → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**。
2. 填寫：
   - **Token name**：例如 `investment-system-actions`
   - **Expiration**：選最長（或 No expiration）；到期前 GitHub 會寄信提醒。
   - **Repository access**：**Only select repositories** → 選 `jenny-smart/investment-system`
   - **Permissions** → **Repository permissions** → **Actions**：**Read and write**
     （Metadata 會自動變成 Read-only，保持即可）
3. 按 **Generate token**，複製 `github_pat_…` 開頭的字串。**只會顯示這一次**，先貼到安全的地方。

## 二、tool-system：設定派送 token

tool-system → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**：
Name `INVESTMENT_SYSTEM_DISPATCH_TOKEN`，Value 貼第一步的 token。
確認 Router 有派送成功（GitHub Actions 出現 `cloud-…` 的執行）之後，再到 cron-job.org 停用
investment-system 的工作（台股價格、美股價格、基金淨值／匯率、App 喚醒、台股雷達、資產快照、月底固定），
避免同一時段跑兩次。

## 三、GitHub：執行失敗通知

GitHub 右上角頭像 → **Settings** → **Notifications** → **System** → **Actions**：
勾選 **Email**，並選 **Only notify for failed workflows**。程式出錯（例如查不到報價）會寄信。

## 四、Streamlit：設定 token

app 用 token 讀取各 workflow 最後成功時間、顯示「資料更新狀態」，並在資料太舊時觸發更新。

1. 到 https://share.streamlit.io → 找到 investment-system app → 右側 **⋮** → **Settings** → **Secrets**。
2. 在既有內容（`SUPABASE_URL` 等）下面加一行：
   ```toml
   GITHUB_TOKEN = "github_pat_…"
   ```
3. 按 **Save changes**，app 會自動重啟。

沒設定時，app 照舊即時抓價，更新狀態列顯示「未設定 GITHUB_TOKEN」。

## App 如何使用總覽資料

- **夠新**：最後一次有寫入的成功執行，不早於「最近一個排程時間點的前一個排程時間點」，也就是最多漏跑一次。
  預覽（dry-run）和時段外略過的執行不算（依 workflow 的 run-name 判斷；排程派送的 `cloud-…` 依開始時間是否在時段內）。
  台股、美股、基金都是 10 分鐘一次，約 20 分鐘內；時段外則看時段內最後一次。
- 夠新時，美股價格與基金淨值直接用總覽 G/H 欄的值，與總帳完全一致；
  太舊或無法判斷時改為 app 即時抓價，畫面標示「總覽未更新，使用即時價」。
- 太舊時 app 會自動觸發一次更新（同一項 15 分鐘內只觸發一次），也可以按「立即更新」。
- 匯率一律讀總覽 R 欄，最慢 2 分鐘反映。台股價格 app 仍用交易所即時報價（比 10 分鐘排程更即時）。
