# 資金流向指標（成交比重 Z、法人買賣超、價量資金流、週轉率）＋新聞／PTT 熱度竄升 — 設計規格

- 日期：2026-10-23
- 狀態：使用者選定全部四項（1、2a、2b＋2c、3）
- 目的：從「量、錢、法人、討論度」四個角度判斷資金真正流向哪個族群。

## 1. 指標定義（每個族群、每一天）

只算普通股；同一檔在同一族群只算一次。

| 指標 | 定義 | 用途 |
|---|---|---|
| 成交比重 | 族群成交值 ÷ 全市場普通股成交值 × 100 | 錢佔多少 |
| 比重 Z（5 日／20 日） | （當天比重 − 前 N 個交易日比重的平均）÷ 前 N 日標準差；標準差下限 0.05 個百分點，避免冷門族群除以接近 0 | 冷門族群突然被點火：**Z ≥ 2 標示「點火」** |
| 價量資金流（類 Chaikin Money Flow） | Σ CLV × 成交值 ÷ Σ 成交值 × 100，CLV = ((收−低) − (高−收)) ÷ (高−低)，高＝低時為 0；範圍 −100～+100 | 收在高檔＝買盤推升；爆量卻收低＝倒貨 |
| 週轉率 | Σ 成交股數 ÷ Σ 發行股數 × 100；發行股數 = 市值 ÷ 收盤 | 籌碼換手的熱度 |
| 法人淨買超 | Σ 三大法人買賣超股數 × 收盤價（元），另列佔族群市值的百分比 | 真正買進去的錢（盤後資料） |

- 即時頁：比重、資金流、週轉率用即時快照計算。比重是相除的結果，盤中成交量不完整的影響會互相抵消；比重 Z 的基準取歷史資料最近的 5／20 個交易日。法人資料只在盤後出現，即時頁不顯示。

## 2. 三大法人資料（`sources/institutional.py`）

- 證交所 `https://www.twse.com.tw/rwd/zh/fund/T86?date=YYYYMMDD&selectType=ALLBUT0999&response=json`
  - 欄位：外資＝外陸資（不含外資自營商）＋外資自營商，投信，自營商，合計＝三大法人買賣超股數（最後一欄）。
- 櫃買中心 `https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?type=Daily&sect=EW&date=YYYY/MM/DD&response=json`
  - `tables[0]`：外資合計＝第 10 欄，投信＝第 13 欄，自營合計＝第 22 欄，三大法人合計＝第 23 欄。
- 存放：
  - `inst_daily(date, code, foreign, trust, dealer, total)`：股數。
  - `inst_day(date, rows, fetched_at)`：記錄哪幾天已抓過，沒資料的日子也記錄，避免重抓。
- 由 HistoryCollector 回補最近 250 個已存的交易日；每天 2 次請求，間隔 3 秒，約 25 分鐘。之後每天盤後補當天。

## 3. 計算與快取（`history/metrics.py`）

- `daily_group_flows(store, dates, grouping)`：每天每個族群的成交值、Σ CLV×成交值、成交股數、發行股數、市值、法人淨買金額，以及全市場成交值。
  - 快取在 `derived_cache`，鍵包含分組 cache_key、日期和法人資料版本，法人回補時不會一直清掉其他快取。
- `group_flows(store, day, grouping)`：上表各指標。
- `flow_baseline(store, grouping, days)`：最近 5／20 日每個族群比重的平均與標準差（即時頁用）。
- C 輪動新增指標「比重 Z」：每天各族群的 20 日比重 Z。

## 4. API

- `GET /api/history/flows?date=&grouping=` → `{date, groups: {name: {share, z5, z20, mf, turnover_rate, inst_net, inst_ratio}}}`
- `GET /api/history/flow-baseline?grouping=` → `{as_of, groups: {name: {m5, s5, m20, s20}}}`
- `/api/history/rotation?metric=share_z`

## 5. 畫面

- 歷史 B 新增欄：比重 Z（20 日；≥2 時族群名稱旁顯示 🔥 點火）、資金流、週轉率、法人（億元，紅買綠賣）。
  - 標題列加「只看點火」核取方塊。
- 即時產業矩陣新增欄：比重 Z、資金流、週轉率。
- C 輪動指標新增「比重 Z」。

## 6. 新聞＋PTT 熱度竄升（第二階段）

- PTT 股版：`https://www.ptt.cc/bbs/Stock/index.html` 往前翻頁，取近 25 天的文章標題（含日期），每頁間隔 2 秒。存 `ptt_day(date, titles)`。
- 詞頻：每天的詞包含
  - 新聞族群詞（既有的 news_day）。
  - PTT 標題中的族群詞（同一套抽取規則）。
  - 英數技術詞（例如 HBM、CPO、CoWoS、ASIC；2～8 個字元、含字母）。
  - 現有概念股／細產業族群名稱的出現次數。
- 竄升：期望次數 E = 前 20 天日平均 × 3，Z =（近 3 天次數 − E）÷ √(E + 1)（Poisson 式，適合次數少的計數）；Z ≥ 2 且近 3 天合計 ≥ 3 次就算竄升。原本用「標準差下限 1」的版本在 PTT 每天約 50 篇的量下幾乎抓不到任何詞，已改掉。
- J 面板：竄升的族群加「竄升」標記；另列「新興關鍵字」（前 15 個竄升詞，附次數）。名稱能對到熱門族群時，點了切到該族群。
- 不使用 LDA（需要新增斷詞與機器學習套件，而且對短標題效果差）。

## 7. 測試

- 指標公式（比重、Z、CLV、週轉率、法人金額）、快取。
- 法人兩個端點的解析（fixture）、collector 回補。
- PTT 頁面解析與年份推斷、竄升計算。
- headless：B 新欄位與點火標示、即時矩陣、C 指標。
