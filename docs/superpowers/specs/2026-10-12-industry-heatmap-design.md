# 台股產業熱力圖看盤介面 — 設計規格

- 日期：2026-10-12
- 狀態：已與使用者逐段確認，待最終審閱

## 1. 目標與範圍

在自己電腦上執行的台股（上市＋上櫃）產業熱力圖看盤介面。一眼看出全市場資金與漲跌分布，並能比較各產業強弱。

**要做**

- Finviz 式樹狀熱力圖（主畫面），依產業分區，可放大到單一產業
- 產業 × 指標矩陣（右側欄），可排序，與樹狀圖連動
- 個股資訊卡、滑鼠提示、自選清單、只看自選
- 盤中依設定頻率自動更新（預設 60 秒，最低 30 秒）

**不做（第一版）**

- 下單（真實或模擬）
- 歷史資料、量能倍數、K 線圖
- 多人使用、登入、部署到伺服器
- 國定假日行事曆（假日照常嘗試抓取，資料不變不影響正確性）

**使用限制**：行情資料來自 HiStock 第三方網站，僅供個人本機使用，不對外提供。

## 2. 資料來源

| 資料 | 來源 | 更新 | 用途 |
|---|---|---|---|
| 報價 | HiStock 排行頁 `https://histock.tw/stock/rank.aspx?p=all`（單頁約 2,500 列） | 盤中每 N 秒 | 價格與量價欄位 |
| 產業、市場別、證券類別 | 證交所 ISIN 公開清單：上市 `https://isin.twse.com.tw/isin/C_public.jsp?strMode=2`、上櫃 `...strMode=4`（MS950 編碼） | 快取 7 天 | 代號 → 產業別、上市/上櫃、是否 ETF |
| 已發行股數 | 證交所 OpenAPI `https://openapi.twse.com.tw/v1/opendata/t187ap03_L`；櫃買 OpenAPI `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O` | 快取 7 天 | 市值 = 價格 × 股數 |

**HiStock 欄位**（表格欄序）：代號、名稱、價格、漲跌、漲跌幅、周漲跌、振幅、開盤、最高、最低、昨收、成交量（張）、成交值（億）。解析時依表頭文字對應欄位，而非固定欄序；表頭缺少任一必要欄位即視為解析失敗。數字需去除 `▲▼`、`+`、`%`、千分位逗號；無法解析的值記為 `None`。

**抓取規範**：一般瀏覽器 User-Agent、逾時 15 秒、失敗重試 1 次（間隔 3 秒）。全系統只有後端在抓，前端不直接連外部網站。

## 3. 架構

```
┌──────────────── 本機 Python 程式（FastAPI, 127.0.0.1） ────────────────┐
│ sources/histock.py   報價解析                                          │
│ sources/twse_isin.py 產業/市場/ETF 對照解析                             │
│ sources/shares.py    已發行股數解析                                      │
│ cache.py             JSON 檔快取（7 天過期）                            │
│ snapshot.py          合併 → 個股清單 + 產業彙總                          │
│ market_clock.py      交易時段判斷（Asia/Taipei）                         │
│ poller.py            背景輪詢、失敗保留舊資料                             │
│ watchlist.py         自選清單讀寫                                       │
│ api.py               REST API + 提供 static/                           │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ 前端每 10 秒以 ETag 詢問是否有新快照
                 ┌─────────────▼──────────────┐
                 │ static/index.html + ECharts │
                 └────────────────────────────┘
```

技術選型：Python ≥ 3.12、uv、FastAPI、uvicorn、httpx、lxml；前端為無建置步驟的原生 JS（ES modules）＋ ECharts 5（CDN 固定版本）。

### 3.1 專案結構

```
open-market/
  pyproject.toml
  src/openmarket/
    __main__.py        # python -m openmarket：啟動伺服器並自動開瀏覽器
    config.py          # 連接埠（預設 8765，環境變數 OPENMARKET_PORT）、data 路徑
    models.py          # dataclass：Quote, StockInfo, Stock, IndustryStat, Snapshot
    sources/histock.py
    sources/twse_isin.py
    sources/shares.py
    cache.py
    snapshot.py
    market_clock.py
    poller.py
    settings_store.py  # data/settings.json：更新秒數
    watchlist.py       # data/watchlist.json
    api.py
  static/
    index.html  app.css
    js/transform.js    # 純函式：快照 + 篩選條件 → ECharts option、矩陣列
    js/app.js          # DOM、事件、ECharts 綁定、輪詢
  tests/
    fixtures/          # 真實頁面/JSON 樣本
    test_*.py
    js/transform.test.js
  data/                # 執行期資料（git 忽略）
```

每個 `sources/*` 模組都分成 `fetch_*()`（網路）與 `parse_*(raw)`（純函式），測試只測 parse。

## 4. 資料模型

```python
Quote:        code, name, price, change, change_pct, week_pct, amplitude_pct,
              open, high, low, prev_close, volume_lots, turnover_100m
StockInfo:    code, name, industry, market ("上市"|"上櫃"), is_etf
Stock:        Quote 全部欄位 + industry, market, is_etf, market_cap (元, 可為 None)
IndustryStat: name, change_pct, week_pct, amplitude_pct, turnover_100m,
              up_count, down_count, flat_count, stock_count
Snapshot:     version (int, 每次成功抓取 +1), as_of (ISO 時間, 抓取完成時間),
              status ("ok"|"stale"|"error"), message, market_open (bool),
              stocks: list[Stock], industries: list[IndustryStat]
```

## 5. 計算規則

- **產業歸屬**：以 ISIN 清單的產業別為準。HiStock 有、ISIN 查不到的代號 → 產業「其他」、市場「未知」。
- **ETF 判定**：ISIN 清單中屬 ETF／受益憑證類別者（CFICode 以 `CE` 開頭）；ISIN 查不到時，代號以 `00` 開頭者視為 ETF。ETF 的產業一律為「ETF」。
- **市值**：`price × 已發行股數`。股數缺漏則 `market_cap = None`。
- **產業今日／本週漲跌**：以市值加權平均成分股的 `change_pct`／`week_pct`；成分股缺市值時，該產業改用等權平均（不混用）。
- **產業振幅**：成分股 `amplitude_pct` 等權平均。
- **漲跌家數**：`change > 0` 為漲，`< 0` 為跌，`= 0` 或 `None` 為平。
- **成交值占比**（前端計算）：產業成交值 ÷ 目前篩選後全部股票成交值。
- 後端產業彙總以「全部股票、不含 ETF」計算一份；前端套用市場／ETF／自選篩選時，以 `transform.js` 在前端重新彙總（同一套規則，JS 實作）。

## 6. 交易時段與輪詢

- 時區：Asia/Taipei。週一至週五 09:00–13:30 為盤中（`market_open = true`）。
- 程式啟動時無論時間，立即抓取一次（讓盤後也能看到最後收盤資料）。
- 盤中依設定秒數輪詢（預設 60，允許範圍 30–600）。
- 13:35 再抓最後一次（收盤撮合結果），之後停止直到下一個交易日 09:00。
- 產業對照與股數：啟動時若快取不存在或超過 7 天就重抓；抓失敗時沿用舊快取，若完全沒有快取則產業歸「其他」、市值為 None，並在 `message` 註明。
- **錯誤處理**：
  - 抓取或解析失敗 → 保留上一份快照，`status = "stale"`，`message` 寫原因，`version` 不變。
  - 從未成功抓過 → `status = "error"`，`stocks` 為空。
  - 下一次成功即恢復 `ok`。所有錯誤寫入日誌（stderr）。

## 7. API

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/api/snapshot` | 回傳 Snapshot JSON；回應帶 `ETag: "<version>-<status>"`，請求帶相同 `If-None-Match` 時回 304 |
| GET | `/api/settings` | `{"poll_seconds": 60}` |
| PUT | `/api/settings` | 更新 `poll_seconds`，超出 30–600 回 422 |
| POST | `/api/refresh` | 立即觸發一次抓取（距上次抓取未滿 30 秒回 429） |
| GET | `/api/watchlist` | `{"codes": ["2330", ...]}` |
| PUT | `/api/watchlist/{code}` | 加入（已存在則無動作） |
| DELETE | `/api/watchlist/{code}` | 移除 |
| GET | `/` | 前端頁面（static） |

JSON 欄位名稱一律使用 snake_case。

## 8. 前端介面

配置（已確認的畫面草圖）：上方篩選列、左側主畫面樹狀圖、右側欄（產業／自選分頁）。

1. **篩選列**：市場（全部／上市／上櫃）、格子大小（市值／成交值）、顏色指標（今日／本週）、範圍（全市場／只看自選）、含 ETF（預設不含）。這些設定存在 localStorage。
2. **狀態區**：資料時間 `as_of`、更新頻率（⚙ 開啟設定，呼叫 `PUT /api/settings`）、手動重新整理（`POST /api/refresh`）。燈號規則：綠 = ok；黃 = stale（滑過顯示 message）；紅 = error。非盤中顯示「已收盤」。
3. **樹狀圖**（ECharts treemap，兩層：產業 → 個股）
   - 大小：市值或成交值。若選市值，缺市值的股票不顯示，並在圖下方註明「N 檔缺市值未顯示」；若選成交值，成交值為 0 或 None 的股票不顯示。
   - 顏色依台股慣例，紅漲綠跌、0 為灰。今日漲跌的色階以 ±7% 為上下限，本週漲跌以 ±15% 為上下限。
   - 產業標題顯示「產業名 ± 漲跌%」，格子內顯示名稱與漲跌%，格子太小時不顯示文字。
   - 點產業標題放大到該產業，麵包屑可返回上一層。
4. **Tooltip**：代號、名稱、價格、漲跌、漲跌幅、成交值、市值。
5. **個股資訊卡**：點個股開啟，包含全部欄位、加入／移除自選、HiStock 個股頁連結（`https://histock.tw/stock/{code}`，另開分頁）、關閉。
6. **產業矩陣**（產業分頁）：欄位為產業、今日、本週、振幅、成交值占比、漲／跌家數。點欄名排序，預設依「今日」由高到低。今日與本週兩欄依同一色階上色。滑過某列時，樹狀圖對應產業加黃框；點某列時，樹狀圖放大到該產業。
7. **自選分頁**：自選股列表，欄位為代號、名稱、價格、漲跌幅、本週、成交值，可排序。點某列開啟資訊卡，每列有移除按鈕。
8. **更新**：每 10 秒以 `If-None-Match` 輪詢 `/api/snapshot`。收到新資料時就地更新圖表，並保留目前的放大層級與資訊卡。

## 9. 測試

- **解析器**：以 `tests/fixtures/` 的真實 HiStock HTML、ISIN HTML（上市、上櫃）、OpenAPI JSON 樣本做 pytest，包含欄位缺漏、表頭改版會丟出解析錯誤等情況。
- **snapshot**：合併、ETF 判定、「其他」歸類、市值加權與等權回退、漲跌家數。
- **market_clock**：盤前、盤中、13:30–13:35 之間、13:35 最後一抓、盤後、週末。現在時間以參數注入。
- **poller**：成功時遞增 version；失敗時保留舊資料並設為 stale；從未成功時為 error；恢復後回到 ok。抓取函式與時鐘以注入方式提供。
- **API**：FastAPI TestClient，涵蓋 ETag／304、settings 範圍驗證、refresh 節流、watchlist CRUD。
- **前端純函式**：`node --test tests/js/`，測篩選、前端重新彙總、ECharts option 結構、色階上下限。
- **端對端**：在瀏覽器窗格實際啟動並操作：篩選、切換大小與顏色、放大與返回、資訊卡、加入／移除自選、矩陣排序與連動。

## 10. 執行方式

```bash
uv sync
uv run python -m openmarket
```

啟動後自動開啟 `http://127.0.0.1:8765`。
