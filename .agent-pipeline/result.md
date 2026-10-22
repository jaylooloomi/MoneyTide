# Night Shift Result（2026-10-23）

分支：`night-shift/2026-10-23`（自 main 48d4c7c）。開工時工作區乾淨，無 stash。

## 收尾
| 項目 | 狀態 | commit | 備註 |
|---|---|---|---|
| ② 自訂族群 | ✅ 完成 | 1f06237 | 管理面板（建立／改名／刪除／加入移出，可用代號或名稱）、即時資訊卡「加入自訂族群」下拉、歷史頁分組切換；一檔可屬多群組、可含 ETF。106 py＋15 js 測試通過，headless e2e 驗證 |
| ③ 概念股族群 | ✅ 完成 | 3d24208 | 來源 Yahoo 股市 /class 索引（101 個概念）＋ StockServices.getClassQuotes JSON（分頁 30）；背景載入約 4 分鐘、快取 7 天、失敗每小時重試；歷史頁「概念股」切換於載入完成後啟用。112 py＋15 js 測試，實際載入 101 個族群並 headless e2e 驗證 |
| 即時頁產業指標切換 | [存疑] 跳過 | | 使用者未選套用方式，歷史頁 B 已涵蓋 |

## 加分項（每行一個，可獨立 revert）
| # | 名稱 | Score | 參考來源（競品 / 專案 / 文章） | 做了什麼 | 驗證指令 | 測試狀態 | 否決的替代作法 |
|---|---|---|---|---|---|---|---|
| 01 | 等大小（Mono）格子 | 7.5（scores-01.md） | TradingView Heatmaps「Mono」大小選項 https://www.tradingview.com/support/solutions/43000766446 | c8ecd1a：即時頁與歷史頁 A 的大小切換多一顆「等大小」，每檔一格只看顏色（產業面積＝家數）；概念股模式下不再被台積電占滿 | `node --test "tests/js/*.test.js"` | ✅ 16/16 js；headless：101 族群、2,631 格全為 1 | ① 依 log(市值) 縮放：仍有大小偏差、使用者難解讀；② 只在概念股模式強制等大小：行為不一致 |
| 02 | 歷史頁個股資訊卡＋近 20 日走勢 | 4.5（scores-01.md） | TradingView Heatmaps 點擊進入個股 https://www.tradingview.com/support/solutions/43000766446 ；Finviz heatmap https://finviz.com/blog/evolving-the-heatmap-dow-jones-nasdaq-100-russell-2000-and-more | 566ff9f：store.stock_rows＋metrics.stock_history＋GET /api/history/stock/{code}；歷史頁 A 點個股、D 點股票標籤即開卡片（當日價量、近 20 日走勢小圖與區間漲幅、HiStock 連結；Ctrl＋點擊仍直接開 HiStock）| `uv run pytest -q tests/test_history.py` | ✅ 113 py／16 js；headless：2468 華經卡片 20 點走勢 | ① 直接連到 HiStock 個股頁：離開回溯脈絡、看不到當日資料；② 開新的完整個股頁（K 線）：超出規模 |
| 03 | 個股卡片顯示所屬族群 | 2.5（scores-02.md） | Yahoo 股市個股頁「類股／盤點概念股」 https://tw.stock.yahoo.com/quote/6691.TW | e46eaeb：GET /api/membership/{code}（概念＋自訂）；即時與歷史個股卡片多一行「概念：…／自訂：…」，超過 8 個顯示「等 N 個」並以 tooltip 列全 | `uv run pytest -q tests/test_api.py` | ✅ 114 py／16 js；headless：2468→雲端產業、2330→26 個概念 | ① 前端下載整份 code→概念對照（約 2,600 筆）自行查：多傳不必要資料；② 卡片內列出族群並可點擊切換到該族群：需改歷史頁狀態流程，超出本項 |
| 04 | 族群累積報酬比較走勢 | 3.0（scores-03.md） | TradingView Cumulative Outperformance https://www.tradingview.com/script/3AZSiUEa-Cumulative-Outperformance-viResearch ；StockCharts RRG 輪動文章 https://articles.stockcharts.com/article/articles-rrg-2020-08-sector-rotation-from-materials-756/ | 0ecf5cb：metrics.group_index（單次掃描，族群等權日報酬連乘＋全市場虛線基準）；GET /api/history/index；歷史頁新增「E · 族群走勢比較」（20／60／120 日，預設期間前 5 名，可下拉加入／移除族群、回到前 5 名；過期回應丟棄）。順帶修正：歷史頁格線列改 max-content——寬度 ≤1100px 時 C/D 區塊原本會塌成 2px（夜間發現的既有 bug） | `uv run pytest -q tests/test_history.py` | ✅ 115 py／16 js；headless：期間切換、加入、移除、重設皆通過；端點 20 日 0.65–1 s、120 日 4 s | ① 市值加權指數：被台積電主導、與 B 表等權口徑不一致；② 直接用 C 矩陣每日值加總：忽略複利、與實際報酬不符 |
| 05 | 全市場廣度列 | 3.3（scores-04.md） | TradingView Market breadth https://www.tradingview.com/support/solutions/43000794825/ ；Strike Money Market Breadth https://www.strike.money/stock-market/market-breadth | 4b35a2e：transform.js marketBreadth()／breadthBarHtml()；即時頁頂列與歷史 A 標題列顯示紅灰綠比例條＋上漲／平盤／下跌家數、漲停／跌停（≥9.5%）、上漲股成交值占比（隨篩選即時重算；自訂／概念分組下每檔只算一次）| `node --test "tests/js/*.test.js"` | ✅ 115 py／17 js；headless：歷史 10/22 ▲393／▼1413、即時 ▲391／▼1416 | ① 後端算好放進 snapshot：前端篩選（市場／ETF／自選）後數字會對不上；② 另開一個大面板：佔版面、資訊量不需要 |
| 06 | 歷史頁逐日播放 | 3.0（scores-05.md） | MotiveWave Replay Mode https://www.motivewave.com/support/replay_mode.htm ；TradingView Bar Replay https://www.tradingview.com/chart/BTCUSD/qmCyeQyK-How-To-Use-The-Bar-Replay-Tool-Rewatch-Trading-History | 9c63ae9：歷史頁頂列 ▶ 旁新增「▶▶ 播放／⏸」與速度（1／2／4 秒/日）；從目前日期逐日往後切換（A–E 全部跟著換、C 欄位同步標示），在最新日時從 20 個交易日前開始；到最新日、按 ◀▶／方向鍵／日曆／點 C 格子即停止 | 在 App 瀏覽器窗格：播放→09-21→09-22→09-23→09-24，暫停有效 | ✅ 115 py／17 js；App 窗格實測通過（headless Chrome 背景分頁計時器被節流，僅驗證到開始／暫停／手動停止）| ① 用動畫內插熱力圖顏色：ECharts treemap 重建會重設，實作成本高；② 一次載入整段期間資料預先快取：記憶體與首載時間大增 |
| 07 | 匯出 CSV（B／C／D） | 3.0（scores-05.md） | Goodinfo 資料頁匯出工具列（HTML／XLS／CSV）例 https://goodinfo.tw/tw/DayTrading.asp | bd212a7：transform.js toCsv()（RFC 4180 跳脫＋UTF-8 BOM）；歷史頁 B／C／D 標題列各一顆「CSV」，匯出畫面上的資料（B 依目前排序；檔名含日期、指標／模式、分組，例：強勢族群_2026-10-22_官方產業.csv）| `node --test "tests/js/*.test.js"` | ✅ 115 py／18 js；headless：3 檔皆產生（34／34／45 列） | ① 後端產生 XLSX：要新增套件（禁止）；② 只匯出 B：C/D 才是回溯分析最常要帶走的資料 |
| 08 | 熱力圖標示漲停／跌停 | 2.3（scores-06.md） | 工商時報盤勢報導（強勢漲停板）https://ctee.com.tw/news/stock/409205.html ；經濟日報（盤中跌停家數）https://money.udn.com/money/amp/story/5607/9459612 | 8e071bd：transform.js limitTag()／limitStyle()；今日漲跌 ≥9.5% 的格子加黃框、≤−9.5% 加青框，標籤與 tooltip 加「漲停／跌停」（即時頁與歷史 A 共用，顏色指標選「本週」時仍依今日判斷）| `node --test "tests/js/*.test.js"` | ✅ 115 py／19 js；headless：10/22 漲停 21、跌停 19 格皆加框 | ① 另做漲停清單面板：D 已有當日漲幅清單；② 用券商漲停價判斷：HiStock 無漲停價欄位，需新資料源 |
| 09 | B 排行「領漲股」欄 | 2.7（scores-07.md） | Yahoo 股市盤後新聞（族群強勢出擊）；鉅亨網盤後 https://www.nstock.tw/news/article_c?id=307347 | b276f7f：group_stats 每族群附 leader（當日漲幅最大者）；B 表新增可排序的「領漲股」欄（名稱＋漲幅），點擊開個股卡片 | `uv run pytest -q tests/test_history.py` | ✅ 116 py／19 js；headless：排序與點擊開卡片（2468 華經）通過 | ① 列出前 3 名：欄位過寬、B 表已很擠；② 以成交值最大者為領頭羊：與「漲幅帶動」語意不同 |
| 10 | B 排行多期間報酬（5／20／60 日） | 2.5（scores-07.md） | OpenBB Compare Groups（perf 1D/1W/1M/3M）https://docs.openbb.co/platform/data_models/CompareGroups ；finvizfinance group performance https://finvizfinance.readthedocs.io/en/latest/group.html | 33ec487：store.change_rows()（精簡欄位查詢）＋metrics.group_periods()（一次掃 60 日，等權日報酬連乘取 5／20／60 日）；GET /api/history/periods；B 表在平均／市值加權後新增「5日／20日／60日」三欄（上色、可排序），B 先顯示、期間欄非同步補上並依日期＋分組快取 | `uv run pytest -q tests/test_history.py` | ✅ 117 py／19 js；headless：20 日排序前三 鋼鐵 +6.92%（與 E 圖一致）；端點冷啟 6.8 s／熱 0.69 s | ① 併入 /groups 同步回傳：每次換日 B 都要等 60 日運算；② 用收盤價直接算個股區間報酬再平均：與 E 圖、C 矩陣的等權日報酬口徑不一致 |
| 11 | 即時產業矩陣「20日」欄 | 2.0（scores-08.md） | OpenBB Compare Groups https://docs.openbb.co/platform/data_models/CompareGroups ；finvizfinance group performance https://finvizfinance.readthedocs.io/en/latest/group.html | 2220fe6：即時產業矩陣在「本週」後新增「20日」欄（最新已存交易日的 20 日等權報酬，上色、可排序；每 10 分鐘最多檢查一次是否有新交易日）；無後端改動 | App 窗格：欄位與歷史 B 一致（鋼鐵 +6.92%）、排序正常 | ✅ 117 py／19 js | ① 也加 5／60 日：即時矩陣寬度有限，5 日與 HiStock 週漲跌重複；② 盤中把今日漲幅併入 20 日：與歷史口徑不同，易混淆 |
| 12 | 網址保存檢視狀態（可書籤） | 2.0（scores-08.md） | Finviz 嵌入地圖（保存市場、期間選擇）https://finviz.com/blog/you-can-now-embed-finviz-maps-on-your-website-blog-or-app/ ；Finviz 熱力圖網址參數 map.ashx?t=sec https://forum.optuma.com/t/heat-map/4074 | edad79e：網址同步 `#live` 或 `#history/日期/分組`（replaceState，不產生瀏覽紀錄）；開書籤直接進到該日該分組（第一次選日就用書籤日期，不會被晚到的載入覆蓋）；手動改網址（hashchange）即套用 | headless：開 #history/2026-10-16/concept → 10-16 概念股；◀ → 10-15；改成 #history/2026-10-01/industry → 套用；即時↔歷史切換網址正確 | ✅ 117 py／19 js | ① 用 query string：重新整理會打 server 新路徑、與靜態檔混用；② localStorage 記住上次日期：無法書籤或分享特定一天 |
| 13 | 歷史熱力圖顏色期間（1／5／20 日） | 2.2（scores-10.md） | Finviz 地圖期間選擇 https://finviz.com/blog/you-can-now-embed-finviz-maps-on-your-website-blog-or-app/ ；Finviz 資料 App 期間選項 https://apptopia.com/google-play/app/com.cousinHub.HeatMap/about | ff15c8e：day_stocks 多回傳 period_20（收盤對 20 個交易日前收盤）；transform 支援 colorBy 'p20'（色階 ±25%）並彙總到產業標題；歷史 A 標題列新增「顏色：1日／5日／20日」切換（記住選擇）| `uv run pytest -q tests/test_history.py` ＋ `node --test "tests/js/*.test.js"` | ✅ 118 py／20 js；headless：2330 20 日 −3.83%（與獨立計算一致） | ① 期間改用等權日報酬連乘：個股層級應看實際價格漲幅；② 直接加 60 日：一年資料下 60 日色階仍可，但 A 標題列空間有限，先做 20 日 |
| 14 | 每日市場廣度月曆 | 2.4（scores-11.md） | TradingView Seasonality Heatmap https://www.tradingview.com/script/Bfz2VMKL-Seasonality-Heatmap-QuantAlgo/ ；thetrading.tools Market Heatmap（% closed higher）https://www.thetrading.tools/market-heatmap ；Strike Advance-Decline https://www.strike.money/?p=12411 | 75525de：store.daily_breadth()（單一 SQL 彙總每日漲跌家數與平均漲幅，0.6 s）；GET /api/history/calendar；歷史頁新增「F · 每日廣度月曆」：每列一個月、每格一個交易日、顏色＝上漲家數佔比，tooltip 顯示家數與平均漲幅，點格子切換日期（停止播放、同步網址），目前日期加白框 | `uv run pytest -q tests/test_history.py` | ✅ 119 py／20 js；headless：242 格、13 個月，點 2025-11-04 → 日期與網址切換 | ① 依星期對齊的 GitHub 式日曆：一年 52 欄太寬、交易日不連續留白多；② 顏色用指數漲幅：本專案無指數資料，廣度更貼近「集體上漲」 |
| 15 | 族群成分股清單 | 3.3（scores-12.md） | MarketInOut Industry Growth（點產業看成分股）https://www.marketinout.com/stock-screener/report/industry-growth ；Barchart Top Performing Stocks https://www.barchart.com/ca/investing-ideas/top-performing-stocks | 50dc299：點 B 表任一族群，B 區塊下方展開該族群成分股表（代號、名稱、漲幅、5日、20日、成交值，可排序、漲停標示，點列開個股卡片，✕ 關閉；換日自動更新）；資料取自已載入的 A，無後端改動 | `node --test "tests/js/*.test.js"` | ✅ 120 py／21 js；headless：航運業 34 檔、20 日排序、點列開卡、◀ 後更新為 10-21 | ① 新 API 取成分股：A 已有同一份資料，多一次請求；② 用彈出視窗：會擋住 A 熱力圖的對照 |
| 16 | 即時矩陣「量能」倍數 | 3.5（scores-13.md） | TradingView Heatmaps（relative volume）https://www.tradingview.com/support/solutions/43000766446 ；Finviz 資料 App（Relative Volume）https://apptopia.com/google-play/app/com.cousinHub.HeatMap/about ；使用者核准草圖 C 的「量能」欄 | 3fbf628：store.group_turnover_avg()（單一 SQL，依產業×市場算近 20 交易日日均成交值，快取）；GET /api/history/turnover-avg；即時產業矩陣在「量占比」後新增「量能」＝今日產業成交值 ÷ 20 日均（盤中按已開盤時間比例換算、隨上市／上櫃篩選、只看自選時不顯示），上色、可排序 | `uv run pytest -q tests/test_history.py` | ✅ 121 py／21 js；headless：半導體 0.7x、航運 0.7x、鋼鐵 1.2x，與獨立計算一致 | ① 不做盤中換算直接相除：開盤初期數字永遠遠小於 1，失去意義；② 只算全市場、不分上市／上櫃：篩選上市或上櫃時倍數失真 |
| 17 | 即時熱力圖族群分類切換 | 3.9（scores-14.md） | Finviz Themes 地圖 https://finviz.com/blog/tag/heatmaps/ ；TradingView Heatmaps https://www.tradingview.com/support/solutions/43000766446 | f0d4a06：GET /api/groupings/{custom|concept}；transform regroupStocks()；即時頁頂列新增「官方產業／自訂族群／概念股」切換（記住選擇），熱力圖與產業矩陣依分組重排（一檔多群組各出現一次），廣度列仍以不重複股票計；概念股未就緒時提示並退回官方產業；自訂族群編輯後即時更新 | `uv run pytest -q tests/test_api.py` ＋ `node --test "tests/js/*.test.js"` | ✅ 123 py／22 js；headless：概念股 101 族群／2,627 格、矩陣與放大正常、主控台無錯誤 | ① 後端產生分組後的快照：每次輪詢要算三份、浪費；② 只做概念股：自訂族群同樣需要 |
| 18 | B 排行名次變化（▲▼） | 3.3（scores-16.md） | TradingView Sector Rotation Dashboard https://www.tradingview.com/script/dAOscEaH-Sector-Rotation-Dashboard-v1/ ；Factor Investor Report（名次變動）https://factorinvestor.substack.com/p/factor-investor-report-april-2021 | 06603f6：metrics.group_rank_change()（依等權平均漲幅排名、與前一交易日比，沿用每日快取）；/api/history/groups 每族群附 rank／rank_change；B 表在族群名後新增「名次」欄（今日名次＋▲n／▼n，可依變化排序） | `uv run pytest -q tests/test_history.py` | ✅ 124 py／22 js；headless：10/22 名次上升最多 貿易百貨 ▲28 | ① 依 B 目前排序欄位動態算名次：每次排序都要回 server、口徑不固定；② 用強勢佔比排名：小族群常 0% 同名次、變動無意義 |
| 19 | 啟動後背景預熱歷史快取 | 2.2（scores-17.md） | OneUptime cache preloading at startup https://oneuptime.com/blog/post/2026-03-31-redis-cache-preloading-application-startup/view ；Aerospike Cache warming explained https://aerospike.com/blog/cache-warming-explained | d640416：ingest.warm_history_cache()——每輪回補／累積結束（含啟動後第一輪）在背景執行緒預先算好最新 60 個交易日的官方產業每日平均與 20 日均量；不改 API | `uv run pytest -q tests/test_history.py` | ✅ 126 py／22 js；重啟後首次請求：periods 6.8 s → 7 ms、index → 7 ms、turnover-avg → 6 ms | ① 把快取寫進 SQLite 持久化：要改 schema（屬 migration，夜班禁改）；② 預熱所有分組：自訂／概念股成員會變、白算 |
| 20 | B 排行族群名稱篩選 | 6.0（scores-18.md） | MarketInOut Industry Growth https://www.marketinout.com/stock-screener/report/industry-growth | 3f1c512：B 標題列新增「篩選族群名稱…」輸入框，依名稱子字串即時過濾（不分大小寫，換日／換分組保留，Esc 清除）；無後端改動 | headless：概念股 101 列 → 輸入 AI 剩 3 列、換日仍 3 列、Esc 回 101 | ✅ 126 py／22 js | ① 下拉選單選族群：101 個選項不好找；② 拼音／模糊搜尋：需新套件 |
| 21 | 熱力圖全螢幕 | 3.0（scores-19.md） | TradingView Heatmap Fullscreen 按鈕 https://www.tradingview.com/support/solutions/43000707156-how-to-set-up-the-display-of-the-heatmap | 56a2d4a：即時熱力圖與歷史 A 右下角新增「⛶」按鈕（Fullscreen API，再按或 Esc 離開；即時資訊卡在全螢幕內仍可用、圖表自動重繪）| headless（CDP 真實點擊）：即時 760→900 px、歷史 397→900 px，離開正常 | ✅ 126 py／22 js | ① 自製「放大」把側欄隱藏：仍受瀏覽器外框限制；② 開新視窗只放熱力圖：狀態不同步 |
| 22 | 熱力圖最低成交值／市值篩選 | 2.2（scores-20.md） | Liberated Stock Trader 熱力圖評測（TradingView filters）https://www.liberatedstocktrader.com/stock-heat-map/ ；TradingView Heatmaps https://www.tradingview.com/support/solutions/43000766446 | transform MIN_FILTERS／passesMin()（純函式＋測試）並接入 filterStocks；即時頂列與歷史 A 標題列各一個「門檻」下拉（不限／成交值 ≥1 億／≥5 億／市值 ≥100 億） | `node --test "tests/js/*.test.js"`；headless：即時 1981→221 檔（≥5 億）、歷史 1945→677 檔（市值 ≥100 億）、偏好保存 | ✅ 75f42d7（pytest 126、node 23） | ① 自由輸入數字：多數人只需幾個常用門檻；② 也套用到歷史 B／D：會改變族群統計口徑，易與其他日比較時混淆 |
| 23 | 即時熱力圖「找股票」搜尋框 | 4.2（scores-21.md） | Liberated Stock Trader 熱力圖評測 https://www.liberatedstocktrader.com/stock-heat-map/ ；Finviz Matrix https://finviz.com/blog/the-finviz-matrix-market-breadth-visualized/ ；AAII StockMapper https://www.aaii.com/journal/article/stockmappercom | transform findStock()（代號→名稱→代號前綴→名稱子字串；純函式＋測試）；即時頂列輸入框＋datalist（2,386 檔），Enter 或選取後放大該產業並開啟資訊卡；被篩選隱藏時只開卡並提示 | `node --test "tests/js/*.test.js"`；headless：2330→半導體業＋資訊卡、長榮→航運業、zzzz→提示 | ✅ cda5dd6（pytest 126、node 24） | ① 在熱力圖上高亮閃爍該格：小格子仍難看見，放大產業更直接；② 後端搜尋 API：前端已有完整快照，不必多一次請求 |
| 24 | 即時熱力圖「量比」顏色模式 | 2.0（scores-22.md） | LuxAlgo Heatmap Volume https://www.luxalgo.com/library/indicator/unWex8N4-heatmap-volume ；TradingView Intraday Volume Spikes Heatmap https://de.tradingview.com/script/l4nZQnW2-Intraday-Volume-Spikes-Heatmap-everget/ | /api/history/stock-turnover-avg（各股前 20 個交易日平均成交值，不含當天，需至少半數天數有值，快取）；transform withRelVolume()／fmtRvol（log2 色階：2x 全紅、½x 全綠，族群＝成交值總和÷基準總和）；即時顏色多一顆「量比」，標籤與 tooltip 顯示倍數、圖例改 ½x／2x | `uv run pytest -q`；`node --test "tests/js/*.test.js"`；headless：2,397 檔有基準、半導體業 0.7x、台積電 0.8x、圖例切回 +7% | ✅ f4d1ee5（pytest 127、node 25）；續做 50a4f09：盤中依已交易時間比例換算基準（與 bonus-16 量能同規則，調研 Finviz session-adjusted relative volume 時發現） | ① 用成交量（張）而非成交值：除權與股價變化會扭曲張數比較；② 以 z-score 分級：分級門檻需調參，倍數最直觀 |
| 25 | 即時熱力圖色階範圍可調 | 2.0（scores-22.md） | Sharesight Community「Heatmap needs to be a bit darker/lighter」https://community.sharesight.com/t/heatmap-needs-to-be-a-bit-darker-lighter/1610 ；TradingView How to set up the display of the Heatmap https://www.tradingview.com/support/solutions/43000707156-how-to-set-up-the-display-of-the-heatmap | transform TODAY_SCALES＋colorLimit(colorBy, todayScale)（只覆寫今日色階；本週／20 日／量比不變；純函式＋測試）；圖例旁「色階 ±3／5／7／10%」下拉，套用熱力圖、圖例與矩陣今日欄，偏好保存；非今日模式時停用 | `node --test "tests/js/*.test.js"`；headless：±3% 時 -1.45% 格子由 #375247 變 #2f6e48、圖例 +3%、重新整理後保留、本週模式仍 ±15% | ✅ 08c640c（pytest 127、node 26） | ① 自動依當日波動調整色階：每次刷新顏色意義會變，難以跨時比較；② 也套用到歷史頁：歷史 A 已有 1／5／20 日色階切換，先不擴大範圍 |

## 夜間程式碼審查修正
獨立審查代理分兩輪檢查程式變更（XSS、監聽器重複、非同步競態、多族群重複計數、API 邊界、主控台錯誤）：第一輪 6 項＋1 小項、第二輪 3 項、第三輪 3 項、第四輪 3 項，另有夜間實測發現的換日延遲，全部已修：
| 問題 | 修正 commit |
|---|---|
| 歷史頁快速切換日期／分組時，A/B/C/D 舊回應覆蓋新資料（含 B 期間欄卡在「…」） | bc9e2a1 |
| 自訂族群編輯後 5／20／60 日快取不失效 | bc9e2a1 |
| D 在自訂／概念分組下重複計數股票 | bc9e2a1 |
| 切換分組後 E 圖保留不存在的族群 | bc9e2a1 |
| 族群名稱「.」「..」使 URL 路徑被正規化、「,」破壞 E 圖查詢 | 24197b3 |
| 即時個股卡片每次輪詢重建，關掉展開中的下拉選單並重抓所屬族群 | 0f5aee4 |
| 第二輪審查（bonus-11–14）：每次載入主控台 ReferenceError（livePeriods 宣告順序） | 97913af |
| 第二輪審查：已開啟的分頁貼上書籤網址（#history/… 或 #live）不會切換模式 | 97913af |
| 第二輪審查：較慢且失敗的舊請求會清空已載入的新資料（A／B） | 97913af |
| 夜間實測：換日要 7–23 秒（5／20／60 日欄與 E 圖的重運算搶 GIL，拖慢當日面板）→ 每日族群平均值依分組快取、期間欄延後載入，降到約 0.65 秒 | ced1df6 |
| 第三輪審查：collector 存檔時清快取與請求競態 → KeyError 500（快取改一次讀出、commit 後才清） | 3760c43 |
| 第三輪審查：切換分組後成分股表仍顯示舊族群；量能欄抓取失敗後整天不重試 | 3760c43 |
| 第四輪審查（bonus-17／18）：概念股暫時未就緒時覆寫掉已存的分組偏好；自訂族群名稱與產業同名時誤顯示產業的 20日／量能；編輯族群時與進行中請求的競態 | d92b001 |

## 判斷不值得做
- AN1 歷史 D「量增上漲」模式 — 1.5（scores-23.md，第 23 輪 TOP: none）：來源只是一般篩選器教學，屬 D 的精修
- C3 相對成交量（量能倍數）— 1.6（scores-01.md）：要新增指標並改 B/C，效益對影響範圍不划算
- C4 族群連續強勢天數 — 1.5：只有新聞評論支持，無產品實作參考
- C2 1日／5日／20日期間切換 — 1.4：改 day_stocks API 與 A/B，影響範圍大
- R1 即時熱力圖切換族群分類 — 1.0（scores-02.md）：要改 transform、即時頁與矩陣，影響範圍大
- S2 族群相對輪動圖（RRG）— 1.3（scores-03.md）：計算與散點尾跡實作量大，C 矩陣已能看每日輪動
- T2 創新高／創新低家數 — 1.0（scores-04.md）：歷史約 242 日不足 52 週，早期數值不完整
- V1 盤中族群轉強桌面通知 — 0.4（scores-06.md）：超出「只看盤」需求、需權限與去重邏輯
- 第 9 輪 TOP: none — Y1 個股同步股（相關性）1.9（scores-09.md）：加分性質、需新指標／API／卡片
- 第 15 輪 TOP: none — AF1 熱力圖 PNG 快照 1.5（scores-15.md）：OS 截圖可替代、非需求核心
- AI1 HiStock 失效改用證交所 MIS 備援 — 0.2（scores-18.md）：單次輪詢需 40+ 批請求、超過 60 秒預設頻率，且目前無失效證據
- Z2 即時卡片 20 日小圖 — 1.5（scores-10.md）：引用來源不支持、即時卡片顯示歷史資料易混淆

## 需要你決定的事
- 即時頁的產業指標切換（等權平均漲幅／≥5% 佔比用在即時熱力圖的哪裡）：你當時沒選套用方式就改提歷史需求，所以本夜沒做；歷史頁 B 已有這些指標。要不要做、做成哪種（產業總覽模式／只換標題排序／只加矩陣欄），請決定。
- 概念股資料來自 Yahoo 股市（第三方網站，與 HiStock 相同屬「個人本機使用」）。

## 統計
