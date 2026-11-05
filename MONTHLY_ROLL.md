# 月底轉值、月初換欄

`monthly_roll.py` 取代原本總帳裡做這兩件事的自動化。排程放在 tool-system 主控表的
「排程設定」分頁（系統名稱 `investment-system`），由 tool-system 的 Cloud Schedule Router
派送本 repo 的 **Monthly ledger roll**（`monthly-roll.yml`）。改時間只要改那張表。

| 功能代號 | 預設時間 | job | 做什麼 |
|---|---|---|---|
| `invest_month_end` | 每月月底 23:50 | `month-end` | Jennyall 本月欄：第 4～36 列的**股票區塊**＋第 64～67 列，公式全部改成數值 |
| `invest_fund_freeze` | 每月 1～7 日 00:30～23:30 每小時 | `fund` | 第 4～36 列的**基金區塊**：等總覽 G 欄每檔基金的淨值日期都到了上個月最後一個工作天才轉值；還沒到就這次不轉。7 日 23:00 以後仍沒到齊，用當下的值轉值並讓執行失敗寄信提醒 |
| `invest_month_roll` | 每月 1～7 日 00:10 | `roll` | 總覽裡參照 Jennyall、`YYYY細帳` 上個月欄的公式改到本月的欄；已換好就不動（2～7 日是補跑） |

基金淨值通常隔一個工作天才公布，偶爾再晚一天，例如 10/30（五）的淨值 11/2 或 11/3 才出來。
基金淨值排程（`fund-nav.yml`）寫進總覽 G/H 之後，下一個整點半就會轉值。

## 轉哪些格子

- **月份欄**：Jennyall 第 1 列是日期列，日期在每月兩欄的右邊那欄（例如 10 月 FZ、GA；日期在 GA1）。
  第 3 列的日期（在左邊那欄）不使用。
- **列**：第 4～36 列（投資區）、第 64～67 列（月底列）。可用環境變數
  `MONTHLY_ROLL_INVEST_ROWS`、`MONTHLY_ROLL_MONTH_END_ROWS` 調整（例如 `4:38`），
  **Jennyall 插入或刪除列時要記得改**。
- **股票／基金**：投資區依 A 欄名稱分區塊，A 欄空白的列跟著上面最近有名稱的列。
  名稱含「台股」「美股」「股票」的區塊算股票（例如 台股、渣打-美股），
  其餘算基金（例如 富邦奈米投、基富通-台／日／人民幣、渣打-基金大華、渣打-美金、渣打-南非）。
  關鍵字可用 `MONTHLY_ROLL_STOCK_LABELS` 調整。
- **轉值**：上述列在該月兩欄裡的公式全部改成目前顯示的值。已經是數值的不動；
  目前是錯誤值（`#N/A`）的格子保留公式並讓執行失敗。
- **換欄**：只移動總覽裡「最新月份」的參照，例如 10 月 → 11 月，月份區塊內位置不變
  （`Jennyall!GA5` → `Jennyall!GC5`）。12 月 → 1 月時 `2026細帳` 會換成 `2027細帳`。
  另有參照更早月份的公式（例如跟上月比較）預設不動並在紀錄列出；也要一起移時手動執行勾 `shift_all`。
  新月份欄還沒建立就不寫入並讓執行失敗。

每次執行都會在 Actions 紀錄列出每一格「原本 → 改成」，並標示 `[股票 …]`、`[基金 …]`、`[月底列 …]`。

## 第一次使用

1. **先預覽**：Actions → **Monthly ledger roll** → **Run workflow**：
   - `job=roll`、勾 `dry_run`：看總覽要換哪些格子。
   - `job=freeze`、`month=2026/10`、勾 `dry_run`：看 10 月欄要轉哪些格子、股票／基金分得對不對。
2. 沒問題就取消 `dry_run` 各跑一次：
   - `roll`（月份留空）：總覽換到 11 月欄。
   - `freeze`、`month=2026/10`：10 月欄轉值。**寫入的是執行當下的值**，不是 10 月底的；
     需要準確月底數字的話，轉值後再手動改那幾格（app「歷史記錄」有 10/31 的快照）。
3. 排程：合併 tool-system 對應的 PR（排程設定表新增上面三列與「系統名稱」欄），並在 tool-system 加
   Secret `INVESTMENT_SYSTEM_DISPATCH_TOKEN`（fine-grained token，只給 investment-system 的
   Actions: Read and write）。不需要另外開 cron-job.org 工作。
4. 總帳 Apps Script 裡如果還留著舊的月底／月初觸發器，請停用，避免兩邊同時改。

服務帳號要有總帳的**編輯**權限（基金淨值排程已在寫總覽，應該已經有）。

## 手動選項

| 選項 | 用途 |
|---|---|
| `job=freeze`＋`only` | 手動轉值，`only` 填 `stock`、`fund`、`extra`（64～67 列）其中幾個，逗號分隔 |
| `wait_nav` | `freeze` 基金列也要等淨值更新到月底才轉 |
| `month` | 轉值預設：1～15 日執行＝上個月、16 日以後＝本月；換欄預設本月 |
| `shift_all` | `roll` 時較舊月份的參照也一起往後移 |
| `dry_run` | 只列出會改的格子，不寫入 |
| `job=auto` | 不靠排程設定表時用（例如臨時改回 cron-job.org）：程式依日期自己判斷要做哪幾件 |

## 本機

```bash
python monthly_roll.py roll --dry-run
python monthly_roll.py freeze --month 2026/10 --only fund --wait-nav --dry-run --credentials-file sa.json
python3 -m unittest tests.test_monthly_roll
```
