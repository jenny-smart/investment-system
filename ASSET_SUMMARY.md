# 總帳資產彙總

`asset_summary.py` 讀「總帳」試算表的某個月份，彙總成五項並算出扣掉寄放後的資產淨額（唯讀，不會改試算表）。

- 銀行total：「零用金-淨值」起的那段 `=SUM()` 小計
- 保險total：「台新保險」起
- 懷思投資：「懷思」起
- uncle待還：「叔叔」起
- 外幣total：「日幣 suica」起
- 其他：試算表總額中不屬於以上五項的部分（股票、基金、未命名列等）
- 寄放（預設）：台幣 1,500,000、日幣 300,000、美金 1,400+960+960、人民幣 5,000，匯率取「總覽」分頁的買進價

## 每月欄位遞延、換檔都不用改程式

- 欄位：依第 1 列的日期找月份（例：10 月 FZ/GA、11 月 GB/GC、12 月 GD/GE），預設取今天以前最新的月份，也可用 `--month` 指定。
- 列：依 A 欄名稱和小計欄的 `=SUM(...)` 公式找範圍，中間插列也能抓到。
- 總額：沿著日期下一列的公式（`=GA70`）找到總額列，再把它扣掉的舊寄放加回來，改扣新的寄放。
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
