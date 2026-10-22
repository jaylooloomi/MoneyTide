# 歷史紀錄與族群回溯 — 設計規格

- 日期：2026-10-23
- 狀態：已與使用者確認，進入開發
- 範圍：子項目 1／3（歷史紀錄＋官方產業）。自訂族群、概念股族群是後續子項目，透過本規格的「分組來源」接入。

## 1. 目標

每天保存收盤資料（含回補近一年），用來回溯每一天的強勢族群，以及哪些股票集體上漲。

## 2. 資料來源與儲存

| 市場 | 來源 | 內容 |
|---|---|---|
| 上市 | `https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=YYYYMMDD&type=ALLBUT0999&response=json` | 「每日收盤行情」表：代號、名稱、成交股數、成交金額、開高低收、漲跌(+/-)、漲跌價差 |
| 上櫃 | `https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date=YYYY/MM/DD&type=EW&response=json` | 「上櫃股票每日收盤行情」：代號、名稱、收盤、漲跌、開高低、成交股數、成交金額、發行股數 |

- 非交易日：官方沒有資料，記錄為 `no_data`，之後不再重抓。
- 儲存：`data/history.sqlite`（stdlib `sqlite3`）
  - `daily_quote(date, code, name, market, industry, kind, close, prev_close, change, change_pct, open, high, low, volume_shares, turnover_yuan, market_cap)`，主鍵 `(date, code)`
  - `trading_day(date, status ok|no_data, fetched_at, rows)`
- 產業與類別在寫入時依當下的 ISIN 對照填入（回補的資料用目前的分類）。ISIN 查不到的代號不存。
- 市值：上櫃用當日發行股數；上市用目前股數（近似值）。
- 漲跌幅 = 漲跌 ÷ 昨收，昨收 = 收盤 − 漲跌。沒有成交（收盤為 `--`）時，收盤與漲跌皆為 None。

## 3. 回補與每日累積

- 啟動後在背景補齊「近 365 天內、尚未存在於 `trading_day` 的平日」，由新到舊。
- 每次請求間隔 3 秒（證交所頻率限制），失敗時記錄錯誤，下一輪重試。可以中斷續補。
- 每日累積：交易日 15:30 之後抓當天資料，抓不到就每 30 分鐘重試，直到 20:00。
- 進度可以從 `/api/history/days` 查到，前端顯示「回補中 n/m」。

## 4. 分組來源

- 介面 `Grouping`：`name`、`groups_of(code) -> list[str]`，一檔股票可以屬於多個族群。
- 第一版只做 `IndustryGrouping`（使用 `daily_quote.industry`）。
- 只計入 `kind == stock` 的股票。

## 5. 指標（每個族群、每天）

- `avg_pct`：等權平均漲幅
- `cap_pct`：以昨收市值加權的漲幅
- `strong_ratio`：漲幅 ≥ 門檻的家數 ÷ 有漲跌幅的家數（門檻預設 5%，API 參數可調）
- `limit_up`：漲幅 ≥ 9.5% 的家數；`limit_down`：漲幅 ≤ −9.5% 的家數
- `count`：家數；`turnover`：成交值合計

## 6. API

| 路徑 | 說明 |
|---|---|
| `GET /api/history/days` | `{days:[{date,status}], backfill:{running, done, total, error}}` |
| `GET /api/history/day/{date}` | 當日個股，格式同即時快照的 stocks，額外附 `week_pct`（5 個交易日） |
| `GET /api/history/groups?date=&threshold=5` | 當日族群指標列表 |
| `GET /api/history/rotation?days=20&metric=strong_ratio&threshold=5` | `{dates:[...], groups:[{name, values:[...]}]}` |
| `GET /api/history/movers?from=&to=&min=5&mode=day|range|streak` | 依族群分組的個股清單 |

## 7. 畫面

- 頂部「即時 ｜ 歷史」切換。
- 歷史頁頂列：◀ 日期 ▶、日曆、門檻（%）、輪動天數（10／20／60）、輪動指標。
- 主區四個區塊：
  - **A**：當日熱力圖，沿用即時頁的 treemap 元件。
  - **B**：當日族群排行表，可排序。
  - **C**：族群輪動矩陣（列：族群、欄：日期），點任一格切換到那天。
  - **D**：集體上漲清單，依族群分組；可切換為「當日」「區間累計 ≥ N%」「連漲 N 天」。

## 8. 測試

- 官方回應的解析器用真實樣本（fixtures）測試，包含非交易日、沒有成交、除權息的漲跌符號。
- store 的寫入與查詢、指標計算、回補排程（續傳、`no_data`、頻率限制）、API 都有測試。
- 最後在瀏覽器實際操作四個區塊。
