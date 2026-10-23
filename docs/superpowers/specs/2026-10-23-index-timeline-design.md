# 大盤＋櫃買時間軸（歷史頁 G 面板）— 設計規格

- 日期：2026-10-23
- 狀態：已與使用者確認設計，待審閱規格
- 範圍：「多維度看金錢流動」需求拆出的 5 個子項目中的 ④。其餘子項目各自另開規格：
  ① 漲停家數佔比／≥5% 佔比指標、② 細產業分類（CMoney／XQ 無公開資料，需確認替代來源）、
  ③ 台灣地圖金錢熱力圖（依公司地址）、⑤ AI 新聞分析（漲跌前三名原因）。

## 1. 目標

在歷史頁底部顯示加權指數與櫃買指數的日 K 線＋成交值，讓使用者先看大盤背景，再點某一天，讓上方熱力圖與 B～F 面板一起切換到那一天。

## 2. 資料來源（皆為官方，按月查詢）

| 內容 | 端點 | 欄位與單位 |
|---|---|---|
| 加權指數開高低收 | `https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?date=YYYYMM01&response=json` | 日期（民國 `115/09/01`）、開盤、最高、最低、收盤指數；千分位字串 |
| 上市成交值 | `https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date=YYYYMM01&response=json` | 日期（民國）、成交股數、**成交金額（元）**、成交筆數、加權指數、漲跌點數 |
| 櫃買指數開高低收 | `https://www.tpex.org.tw/www/zh-tw/indexInfo/inx?date=YYYY/MM/01&response=json` | `tables[0].data`：日期（西元 `2026/09/01`）、開、高、低、收、漲跌 |
| 上櫃成交值 | `https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingIndex?date=YYYY/MM/01&response=json` | `tables[0].data`：日期（民國）、成交股數（千股）、**成交金額（千元）**、成交筆數、櫃買指數、漲跌 |

- 回應以 UTF-8 JSON 解析（2026-10-23 實測四個端點皆回 200 與上述欄位）。
- 證交所 `stat != "OK"` 或資料為空，視為該月沒有資料。
- 上櫃成交金額 × 1000 換成元。民國年 + 1911 換成西元。

## 3. 儲存

`data/history.sqlite` 新增一張表（`CREATE TABLE IF NOT EXISTS`，與既有表的建立方式相同）：

```
index_daily(date TEXT, market TEXT /* 上市|上櫃 */, open REAL, high REAL, low REAL, close REAL,
            change REAL, turnover_yuan REAL, PRIMARY KEY (date, market))
index_month(market TEXT, month TEXT /* YYYY-MM */, fetched_at TEXT, rows INTEGER, PRIMARY KEY (market, month))
```

- 同一天的開高低收（MI_5MINS_HIST／inx）與成交值（FMTQIK／tradingIndex）按日期合併成一列。只有其中一邊有值時，另一邊存 NULL。
- `index_month` 記錄已抓完的月份。**當月**與**上個月**每次都重抓，因為月中仍在增加資料；更早的月份抓過就不再抓。

## 4. 回補與每日更新

- 由現有 `HistoryCollector.run_once()` 在個股回補之後順帶處理，不另開背景工作：
  - 缺的月份（近 12 個月＋當月）由新到舊抓，每個月 4 次請求，間隔沿用 `REQUEST_DELAY_SECONDS`（3 秒）。完整回補約 52 次請求、約 2.5 分鐘。
  - 交易日 15:30 之後重抓當月，讓當天的 K 棒入庫。
- 單一月份失敗只記錄 `log.warning`，寫入 `state.error`，下一輪重試；不影響個股歷史。

## 5. API

`GET /api/history/index?days=250`（1 ≤ days ≤ 500）

```json
{
  "days": [
    {"date": "2026-10-22",
     "twse": {"open": 0, "high": 0, "low": 0, "close": 0, "change": 0, "turnover_yuan": 0},
     "tpex": {"open": 0, "high": 0, "low": 0, "close": 0, "change": 0, "turnover_yuan": 0},
     "strong_ratio": 4.6, "limit_up": 41}
  ],
  "backfill": {"months_done": 12, "months_total": 13}
}
```

- 日期取 `index_daily` 與 `trading_day(status=ok)` 的聯集，由舊到新排序，取最後 `days` 天。
- 某個市場沒有資料時，該欄為 `null`。
- `strong_ratio`：當天普通股（kind=stock）中漲幅 ≥ 5% 的比例（%）。`limit_up`：漲幅 ≥ 9.5% 的家數。兩者都用 `daily_quote` 一次彙總查詢算出，結果放進 `derived_cache`（`save_day` 後清除）。沒有個股資料的日子為 `null`。

## 6. 前端：G 面板「大盤＋櫃買」

位置：歷史頁最底部，位於 F 月曆之後，佔滿整列寬度。

- **兩張上下排列的 K 線**：加權、櫃買。每張下方各有一條成交值柱（紅＝收盤 ≥ 開盤，綠＝收盤 < 開盤，與 K 棒同色）。
- **均線**：MA5、MA20、MA60（收盤價簡單平均；天數不足的前幾天不畫）。
- **共用時間軸**：兩張共用一個 dataZoom（滑桿＋滾輪），預設顯示最近約 3 個月（60 個交易日），可拖曳看全部。
- **強勢日標記**：當天 `strong_ratio ≥ 10` 或 `limit_up ≥ 90` 時，在加權 K 棒上方畫一個標記點。依 2026-10 的一年資料，≥5% 佔比的第 90 百分位為 10.0%，漲停家數的第 90 百分位為 89 家，所以一年約 25～30 天會被標記。門檻寫成常數（`STRONG_DAY = { ratio: 10, limitUp: 90 }`）。
- **tooltip**：日期、兩個指數的開高低收與漲跌、兩市場成交值（億），以及當天的 ≥5% 佔比與漲停家數。
- **點擊某一天**（K 棒、成交值柱、標記點都可以）：呼叫現有的 `selectDate(date)`，所以熱力圖 A、B～F、日期選單、F 月曆與網址書籤（`#history/<date>/<grouping>`）全部同步。沒有個股資料的日子（只有指數）不切換，改顯示 toast「這天沒有個股資料」。
- **目前日期**：在兩張圖上以一條垂直 markLine 標示目前選中的日期。日期從其他地方改變時跟著移動，該日在可視範圍外時自動捲到它。
- 資料在第一次進入歷史頁時載入一次，之後換日不重抓；每日更新（15:30 後）以頁面重新載入或切換模式時重抓為準。

## 7. 程式結構

| 單元 | 職責 |
|---|---|
| `src/openmarket/sources/official_index.py` | 抓 4 個端點並解析成 `IndexRow(date, market, open, high, low, close, change, turnover_yuan)`；純解析函式與 HTTP 分開，方便用 fixture 測試 |
| `src/openmarket/history/store.py` | `index_daily`／`index_month` 建表、`save_index_month()`、`index_months()`、`index_rows(days)`、`daily_strength()` |
| `src/openmarket/history/ingest.py` | `HistoryCollector` 增加 `collect_index()`（缺月計算＋抓取） |
| `src/openmarket/history/api.py` | `/api/history/index` |
| `static/js/indexchart.js`（新檔） | 純函式 `movingAverage()`、`isStrongDay()`、`buildIndexOption()`，以及 G 面板的掛載、點擊與 markLine 同步 |
| `static/js/history.js` | 掛載 G 面板、在 `selectDate` 之後通知 G 更新 markLine |
| `static/index.html`／`static/app.css` | G 面板容器與版面 |

## 8. 錯誤處理

- 指數尚未回補：G 面板顯示「大盤資料回補中（n／13 個月）」，每 30 秒重抓一次 API，直到有資料。
- API 失敗：顯示「大盤資料載入失敗」與重試按鈕，不影響其他面板。
- 某天只有個股、沒有指數：K 線該日留空（ECharts 以 `'-'` 表示），仍可從 F 月曆或日期選單切換。

## 9. 測試

- `tests/fixtures/`：四個端點各存一份 2026-09 的回應樣本。
- pytest：
  - 解析：民國／西元日期、千分位、`--` 與空值、上櫃千元換算、`stat != OK`。
  - store：同月重存會覆蓋；開高低收與成交值合併；`index_months()` 判斷缺月，且當月與上月一律視為要重抓。
  - `daily_strength()`：≥5% 佔比與漲停家數的計算，ETF 不算在內。
  - API：日期聯集、`days` 截斷、缺市場時為 `null`。
- node：`movingAverage()`（前段不足天數為 null）、`isStrongDay()` 門檻邊界、`buildIndexOption()` 的 markLine 日期。
- headless Chrome：G 面板出現兩張 K 線；點擊某天後 `#hDate`、網址 hash 與熱力圖日期都變成那天；markLine 跟著移動。

## 10. 不做（YAGNI）

- 即時頁不放 G 面板（使用者選擇只放歷史頁）。
- 不做分 K、技術指標（KD、MACD）、成交值 20 日均量線。
- 強勢日門檻不開放在介面上調整（之後有需要再加）。
