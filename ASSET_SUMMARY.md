# 總帳資產彙總

`asset_summary.py` 讀「總帳」試算表的某個月份，彙總成五項並算出扣掉寄放後的資產淨額（唯讀，不會改試算表）。

- 銀行total：「零用金-淨值」起的那段 `=SUM()` 小計
- 保險total：「台新保險」起
- 懷思投資：「懷思」起
- uncle待還：「叔叔」起
- 外幣total：「日幣 suica」起
- 其他：試算表總額中不屬於以上五項的部分（股票、基金、未命名列等）
- 寄放（待還）：預設用該月第 69 列（例如 10 月 FZ69、11 月 GB69），金額變動時改那一格即可；`--deposit` 可臨時指定，匯率取「總覽」分頁的買進價

## 每月欄位遞延、換檔都不用改程式

- 欄位：依第 1 列的日期找月份（例：10 月 FZ/GA、11 月 GB/GC、12 月 GD/GE），預設取今天以前最新的月份，也可用 `--month` 指定。
- 列：依 A 欄名稱和小計欄的 `=SUM(...)` 公式找範圍，中間插列也能抓到。
- 總額：沿著日期下一列的公式（`=GA70`）找到總額列；有指定 `--deposit` 時，把試算表扣的待還加回來改扣指定金額。
- 換檔：`--spreadsheet` 給新的網址或 ID，`--sheet` 給分頁名稱。

```bash
python asset_summary.py                                  # 本月
python asset_summary.py --month 2026/11                  # 指定月份
python asset_summary.py --spreadsheet "<新檔網址>" --sheet Jennyall
python asset_summary.py --deposit TWD=1500000 --deposit USD=3320 --rate USD=32
python asset_summary.py --json
```

憑證和台股回填共用：環境變數 `INVESTMENT_GOOGLE_SERVICE_ACCOUNT_JSON`，或 `--credentials-file`。該服務帳號要能讀取總帳試算表（把檔案分享給服務帳號的 email，檢視者即可）。

測試：`python3 -m unittest discover -s tests -p test_asset_summary.py`

## Streamlit 總覽頁與歷史市值

總覽頁的投資平台卡片下方有「🏦 其他資產」區塊，每次載入或按「更新即時價」都會重讀總帳（快取 10 分鐘）：

- 銀行total、保險total、懷思投資、uncle待還、外幣total：讀 Jennyall 下方每月彙總區（銀行 / 保險 / 懷思投資 / 叔叔借款 / 外幣 和下一列的待還），自動抓今天以前最新的月份欄。
- 每一項都能展開看明細，例如銀行展開後是零用金、台新、連線、將來、郵局、富邦。
- 扣除待還：彙總區「外幣」下一列（`=-FZ69` 那格），也就是試算表裡別人寄放的金額。
- 其他資產小計 = 五項合計 − 待還；總資產 = 投資總市值 + 其他資產小計。
- 🧮 每月加總：直接顯示「總覽」分頁「每月加總」區塊（項目、金額、台/外、預估）。

歷史市值每筆快照（手動按鈕、每天 08:00 / 20:00 排程）會多記銀行、保險、懷思投資、uncle待還、外幣、扣除待還、其他資產小計、總資產。

第一次使用前，請在 Supabase SQL Editor 執行 `supabase_schema.sql` 裡「其他資產」那段 `alter table`（app 上方「資料庫欄位提醒」也有）。還沒加欄位前，快照照常記錄投資市值，只是少了這幾欄。
