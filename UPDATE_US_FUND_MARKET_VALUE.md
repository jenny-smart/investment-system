# 美股與基金現值更新說明

主檔：`invesapp_supabase.py`

這次只處理兩件事：

1. 美股、基金要先抓到即時價格 / 淨值，才能算出台幣現值。
2. 「投資管道明細」併入「所有投資管道總覽」卡片，卡片直接顯示現值 / 成本、損益 / 淨利率。

## 已更新內容

- 美股：
  - 先用 Yahoo Finance。
  - Yahoo 抓不到時，改用 Google Finance fallback。
  - Google Finance 會用 `ticker + exchange` 定位價格資料，例如 `PYPL:NASDAQ`、`XYZ:NYSE`。
  - 只要價格與匯率都有抓到，狀態就顯示成功。

- 基金：
  - MoneyDJ 基金使用 `fund_code + fund_pattern`，例如 `acft94 + yp010000`。
  - 鉅亨基金可用代碼格式，例如 `A45089`；`fund_pattern` 可填 `anue`，或留空讓程式自動判斷。
  - MoneyDJ 頁面用 Big5 內容解析，優先抓基金頁上方淨值表格。

- 總覽卡片：
  - 主數字改為 `現值 / 成本`。
  - 漲跌欄改為 `損益 / 淨利率`。
  - 卡片底下會顯示抓價狀態：`抓價 ✓` 或 `價格缺 N｜匯率缺 N`。
  - 原本下方的「投資管道明細」表格已移除，避免重複顯示。

## 自行更新步驟

1. 到 GitHub 開啟 `invesapp_supabase.py`。
2. 用本機這份檔案內容更新 GitHub 上的同名檔案。
3. Streamlit Cloud 會重新部署；若沒有自動部署，按 `Reboot app` 或重新部署。
4. 進入 app 後按上方 `更新即時價`。
5. 到 `抓價測試` 分頁測：
   - 美股：`PYPL`、`XYZ`
   - MoneyDJ 基金：`acft94` + `yp010000`
   - 鉅亨基金：`A45089` + `anue`

## 若現值仍是 0

- 先看卡片底下是否顯示 `價格缺` 或 `匯率缺`。
- 如果是美股價格缺：
  - 確認 `ticker` 是否正確。
  - 確認 `US_STOCK_EXCHANGES` 內是否有正確交易所，例如 `PYPL: NASDAQ`、`XYZ: NYSE`。
- 如果是基金價格缺：
  - MoneyDJ 確認 `fund_code` 與 `fund_pattern` 都有填。
  - 鉅亨基金確認代碼類似 `A45089`，`fund_pattern` 填 `anue`。
- 如果匯率缺：
  - 到 `抓價測試` 分頁下方確認 USD、CNY、JPY、ZAR 匯率是否有抓到。
