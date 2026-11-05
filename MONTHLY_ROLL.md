# 月底轉值、月初換欄

`monthly_roll.py` 取代原本總帳裡做這兩件事的自動化，由 cron-job.org 觸發 GitHub Actions
**Monthly ledger roll**（`monthly-roll.yml`）。

| 時間（Asia/Taipei） | 做什麼 |
|---|---|
| 每月最後一天 23:50 | **月底轉值**：Jennyall 本月欄的基金／股票列，把還連到其他分頁的公式（`=總覽!H12`、`GOOGLEFINANCE(...)` 等）改成當下的數值 |
| 每月 1 日 00:10 | 補做上個月的轉值（月底那次沒跑到才會有東西改），接著**月初換欄**：總覽裡參照 Jennyall、`YYYY細帳` 上個月欄的公式改到本月的欄 |
| 每月 2～7 日 00:10 | 再檢查一次換欄，1 日沒跑到也會補上；已經換好就什麼都不改 |

其他時間觸發會直接略過。

## 怎麼判斷要改哪些格子

不寫死儲存格位址，跟 `asset_summary.py` 一樣靠內容找：

- **月份欄**：各分頁前 10 列裡月份最多的那一列當日期列（`2026/11/1`、`2026/11`、`11月` 都認得；
  `11月` 的年份取分頁名稱，例如 2026細帳）。Jennyall 的日期在每月兩欄的右邊那欄（小計欄），
  細帳的日期在每月區塊的第一欄。
- **轉值範圍**：Jennyall 日期列下一列到「零用金-淨值」上一列（投資列），只限要轉值那個月的欄。
  同分頁的公式（`=SUM(...)`、`=GA70`）不動；目前是錯誤值（`#N/A`）的格子保留公式並讓執行失敗，
  方便察覺。
- **換欄**：只移動總覽裡「最新月份」的參照，例如 10 月 → 11 月，月份區塊內位置不變
  （`Jennyall!GA5` → `Jennyall!GC5`）。12 月 → 1 月時 `2026細帳` 會換成 `2027細帳`。
  如果總覽另外有參照更早月份的公式（例如跟上月比較），預設不動並在紀錄裡列出；
  確定也要一起往後移時，手動執行勾 `shift_all`。
- 換欄前會先確認新月份欄已經存在，找不到就不寫入並讓執行失敗。

每次執行都會在 Actions 紀錄列出每一格「原本 → 改成」，可以對照。

## 第一次使用

1. **先預覽**：Actions → **Monthly ledger roll** → **Run workflow**，`job` 選 `roll`、勾 `dry_run`，
   看紀錄列出的格子對不對；`freeze` + `month: 2026/10` + `dry_run` 也預覽一次。
2. 沒問題就取消 `dry_run` 再跑一次：
   - `roll`（月份留空）：總覽換到 11 月欄。
   - `freeze`、`month: 2026/10`：10 月欄的基金／股票轉值。**注意寫入的是執行當下的價格**，
     不是 10/31 的；需要準確月底數字的話，轉值後再手動改那幾格（app「歷史記錄」有 10/31 的快照）。
3. cron-job.org 新增工作（設定方式見 `SCHEDULES.md`）：
   - URL：`https://api.github.com/repos/jenny-smart/investment-system/actions/workflows/monthly-roll.yml/dispatches`
   - Cron：`10,50 0,23 * * *`，時區 `Asia/Taipei`
   - Body：`{"ref":"main","inputs":{"job":"auto"}}`
4. 總帳 Apps Script 裡如果還留著舊的月底／月初觸發器，請停用，避免兩邊同時改。

服務帳號要有總帳的**編輯**權限（基金淨值排程已在寫總覽，應該已經有）。

## 本機

```bash
python monthly_roll.py roll --dry-run
python monthly_roll.py freeze --month 2026/10 --dry-run --credentials-file sa.json
python3 -m unittest tests.test_monthly_roll
```
