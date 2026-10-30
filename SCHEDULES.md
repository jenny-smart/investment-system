# 排程與設定

GitHub 原生排程（workflow 裡的 `schedule`）是「盡量執行」，負載高時會延遲或直接丟掉，
曾經一晚應跑 16 次只跑 1 次。所以**所有排程都改由 cron-job.org 觸發**，workflow 只保留
`workflow_dispatch`（手動 / API 觸發）。

## 排程一覽（時區 Asia/Taipei）

| cron-job.org 工作 | Workflow 檔 | Cron | Body（inputs） | 實際更新時段 |
|---|---|---|---|---|
| 台股價格 | `tw-stock-prices.yml` | `*/10 8-14 * * 1-5` | `{"ref":"main","inputs":{"mode":"auto"}}` | 開盤日 08:30–14:30 |
| 美股價格 | `us-stock-prices.yml` | `0,30 0-6,21-23 * * *` | `{"ref":"main","inputs":{"mode":"auto"}}` | 週一至週五 21:00 至隔天 06:00 |
| 基金淨值／匯率 | `fund-nav.yml` | `0,30 * * * *` | `{"ref":"main"}` | 全天 |
| App 喚醒 | `keepalive.yml` | `*/30 * * * *` | `{"ref":"main"}` | 全天 |
| 台股雷達 | `stock-radar.yml` | `30 14 * * 1-5` | `{"ref":"main"}` | 週一至週五 14:30 |
| 資產快照（既有） | `snapshot.yml` | `0 8,20 * * *` | `{"ref":"main"}` | 08:00、20:00 |
| Richart 匯率（既有） | `richart-fx.yml` | 每 30 分鐘 | `{"ref":"main"}` | 全天 |

時段外的觸發由程式自己略過（`auto` 模式），所以 cron 可以寫得比較寬。

## 一、GitHub：建立 token

cron-job.org 和 app 都要用 token 呼叫 GitHub API 觸發 workflow。

1. GitHub 右上角頭像 → **Settings** → 左側最下方 **Developer settings**
   → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**。
2. 填寫：
   - **Token name**：例如 `investment-system-actions`
   - **Expiration**：選最長（或 No expiration）；到期前 GitHub 會寄信提醒。
   - **Repository access**：**Only select repositories** → 選 `jenny-smart/investment-system`
   - **Permissions** → **Repository permissions** → **Actions**：**Read and write**
     （Metadata 會自動變成 Read-only，保持即可）
3. 按 **Generate token**，複製 `github_pat_…` 開頭的字串。**只會顯示這一次**，先貼到安全的地方。

cron-job.org 現有的台股工作已經有一組 token；可以沿用舊的，也可以換成這組新的（兩邊都要能觸發 Actions）。

## 二、cron-job.org：新增工作

建議直接複製既有的「台股價格」工作再改，Header 就不用重填：

1. 登入 cron-job.org → **Cronjobs** → 在既有台股工作右側選 **Clone**（或 **Create cronjob**）。
2. **Common** 分頁：
   - **Title**：例如「美股價格」
   - **URL**：`https://api.github.com/repos/jenny-smart/investment-system/actions/workflows/<Workflow 檔>/dispatches`
     （`<Workflow 檔>` 換成上表的檔名，例如 `us-stock-prices.yml`）
   - **Execution schedule** → **Custom** → 填上表的 Cron，時區選 **Asia/Taipei**。
3. **Advanced** 分頁：
   - **Request method**：`POST`
   - **Headers**：
     - `Authorization`：`Bearer github_pat_…`（第一步的 token）
     - `Accept`：`application/vnd.github+json`
     - `X-GitHub-Api-Version`：`2022-11-28`
   - **Request body**：上表的 Body。
4. **Notifications**：勾選 **execution of the cronjob fails**（以及 **succeeds again after failure**），失敗會寄信。
5. 存檔後按 **Test run**，回應碼是 **204** 就代表成功；到 GitHub → **Actions** 會看到一筆新的執行。

要新增：美股價格、基金淨值／匯率、App 喚醒、台股雷達。
台股價格若還沒建，照第一列設定；舊的 `8631524`、`8631529`、`8593700` 請停用或刪除。

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

- **夠新**：最後一次成功執行不早於「最近一個排程時間點的前一個間隔」，也就是最多漏跑一次。
  台股（10 分鐘一次）約 20 分鐘內、美股和基金（30 分鐘一次）約 60 分鐘內；時段外則看時段內最後一次。
- 夠新時，美股價格與基金淨值直接用總覽 G/H 欄的值，與總帳完全一致；
  太舊或無法判斷時改為 app 即時抓價，畫面標示「總覽未更新，使用即時價」。
- 太舊時 app 會自動觸發一次更新（同一項 15 分鐘內只觸發一次），也可以按「立即更新」。
- 匯率一律讀總覽 R 欄，最慢 2 分鐘反映。台股價格 app 仍用交易所即時報價（比 10 分鐘排程更即時）。
