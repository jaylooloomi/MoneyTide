# 加分候選（第 1 輪）

原始需求錨點：台股產業熱力圖（即時）＋「回溯每一天的強勢族群，或是哪些股票集體上漲」（官方／自訂／概念股族群，歷史頁 A/B/C/D）。

## C1. 格子大小「等大小（Mono）」選項
因為原始需求是 **用熱力圖看族群強弱、哪些股票集體上漲**，所以頂尖做法會順便做 **不依市值的等大小格子**（TradingView 的 size 選項有 Mono：拿掉大小編碼只看顏色）；目前的成果 **沒有**——只有市值／成交值，概念股模式下台積電出現在約 30 個族群並占滿版面、小型股幾乎看不到（visibleMin 隱藏）。
- 參考：TradingView Heatmaps 說明 https://www.tradingview.com/support/solutions/43000766446
- 範圍：transform.js sizeOf 加 'equal'；即時頁與歷史頁 A 的大小切換多一顆按鈕；測試。

## C2. 歷史熱力圖與排行的「期間」切換（1 日／5 日／20 日累積漲幅）
因為原始需求是 **回溯強勢族群**，所以頂尖做法會順便做 **週／月期間的熱力圖**（Finviz map 提供當日、一週、一個月、一年等期間視圖，用來比較不同週期的廣度）；目前的成果 **只有部分**——A 只能看單日漲跌（tooltip 有 5 日），B 只算單日。
- 參考：Finviz 熱力圖多期間（Credit Writedowns 2010 文章展示 day/week/month/year 視圖）https://creditwritedowns.com/2010/07/stat-of-the-day-heat-map-of-stock-performance-looks-good-today.html ；第三方 Finviz 資料 App 列出 1D/1W/1M/3M/6M/1Y/YTD https://apptopia.com/google-play/app/com.cousinHub.HeatMap/about
- 範圍：後端 day_stocks 加 period 參數計算 N 日累積報酬；前端 A 顏色切換 1D/5D/20D；測試。

## C3. 相對成交量（量能倍數）指標
因為原始需求是 **找出資金湧入的強勢族群**，所以頂尖做法會順便做 **相對成交量（今日成交值 ÷ 近 N 日平均）**（TradingView heatmap 可依 relative volume 上色；Finviz 資料 App 也提供 Relative Volume）；目前的成果 **沒有**——原始草圖中的「量能倍數」因當時無歷史而延後，現在已有一年歷史可計算。
- 參考：TradingView Heatmaps 說明（color by relative volume）https://www.tradingview.com/support/solutions/43000766446 ；https://apptopia.com/google-play/app/com.cousinHub.HeatMap/about
- 範圍：metrics.group_stats 加 rel_turnover（族群今日成交值 ÷ 前 20 日平均）；B 表多一欄、C 輪動多一個指標；測試。

## C4. 族群「連續強勢天數」
因為原始需求是 **回溯每天的強勢族群**，所以頂尖做法會順便做 **族群連續上榜天數／持續性**（財經媒體分析族群輪動時以「連續強勢、資金是否延續」判斷主流族群）；目前的成果 **沒有**——C 矩陣要用眼睛數。
- 參考：鉅亨網族群輪動分析 https://news.cnyes.com/news/id/4917042 ；經濟日報「強勢族群輪動加快」 https://money.udn.com/money/amp/story/5607/9037985
- 範圍：rotation 結果中為每族群計算截至選定日「平均漲幅 > 0 且強勢佔比 ≥ 中位數」的連續天數，B 表多一欄；測試。

## C5. 歷史頁點個股開資訊卡（含近 20 日走勢小圖）
因為原始需求是 **看哪些股票集體上漲**，所以頂尖做法會順便做 **點擊個股即看該股細節與近期走勢**（TradingView heatmap 點擊進入個股；Finviz map 點擊開個股頁）；目前的成果 **沒有**——歷史頁 A 點個股沒有反應、D 只連到 HiStock。
- 參考：TradingView Heatmaps 說明（click-through to symbols）https://www.tradingview.com/support/solutions/43000766446 ；Finviz heatmap blog https://finviz.com/blog/evolving-the-heatmap-dow-jones-nasdaq-100-russell-2000-and-more
- 範圍：新 API /api/history/stock/{code}?to=&days=20；前端卡片＋ ECharts 小折線；測試。

# 加分候選（第 2 輪）
（第 1 輪剩餘 C3 1.6、C4 1.5、C2 1.4 皆 < 2，已列入 result.md「判斷不值得做」）

## R1. 即時熱力圖也能切換族群分類（官方產業／自訂／概念股）
因為原始需求是 **產業熱力圖看盤＋強勢族群**，所以頂尖做法會順便做 **以題材（theme）分組的即時熱力圖**（Finviz 新增「Themes」市場地圖；TradingView heatmap 可切換分組方式）；目前的成果 **只有部分**——自訂／概念股分組只在歷史頁，盤中即時熱力圖與產業矩陣只能看官方產業。
- 參考：Finviz「New Stock Market Maps for Market Cap, 52-Week Highs, Lows, Themes…」https://finviz.com/blog/tag/heatmaps/ ；TradingView Heatmaps https://www.tradingview.com/support/solutions/43000766446
- 範圍：後端 GET /api/concepts/map（code→概念）；前端即時頁加分組切換，transform 依分組重排 industry（一檔多群組複製）；矩陣同步；測試。

## R2. 個股卡片顯示所屬族群（自訂＋概念股）
因為原始需求是 **看哪些股票集體上漲、屬於哪個族群**，所以頂尖做法會順便做 **個股頁列出所屬類股／概念股**（Yahoo 股市個股頁提供「類股」「盤點概念股」入口）；目前的成果 **沒有**——即時與歷史卡片只顯示官方產業。
- 參考：Yahoo 股市個股頁 https://tw.stock.yahoo.com/quote/6691.TW
- 範圍：後端 GET /api/concepts/of/{code}；兩張卡片多一行「概念：…」「自訂：…」；測試。

# 加分候選（第 3 輪）
（R1 1.0 < 2，列入「判斷不值得做」）

## S1. 族群累積報酬比較走勢（族群指數線圖）
因為原始需求是 **回溯每天的強勢族群**，所以頂尖做法會順便做 **把幾個族群（與全市場）的累積報酬畫成走勢線比較**（TradingView「Cumulative Outperformance」以回顧期間累積報酬比較標的與基準；RRG 的出發點也是看相對表現而非單日）；目前的成果 **沒有**——C 輪動矩陣只有每日數字，看不出一段期間誰真正領先。
- 參考：TradingView Cumulative Outperformance https://www.tradingview.com/script/3AZSiUEa-Cumulative-Outperformance-viResearch ；StockCharts RRG 族群輪動文章 https://articles.stockcharts.com/article/articles-rrg-2020-08-sector-rotation-from-materials-756/
- 範圍：metrics.group_index（族群等權日報酬連乘，加全市場基準）；GET /api/history/index；歷史頁 C 區塊加「走勢比較」：勾選 B 表族群（預設前 5 名）畫線；測試。

## S2. 族群相對輪動圖（RRG：RS-Ratio × RS-Momentum）
因為原始需求是 **看族群輪動、找強勢族群**，所以頂尖做法會順便做 **相對輪動圖**（JdK RS-Ratio／RS-Momentum 四象限：領先、轉弱、落後、改善，族群順時針輪動）；目前的成果 **沒有**。
- 參考：StockCharts RRG https://articles.stockcharts.com/article/articles-rrg-2020-08-sector-rotation-from-materials-756/ ；State Street Sector Momentum Map https://www.ssga.com/uk/en_gb/intermediary/insights/guide-to-sector-momentum-map ；LuxAlgo RRG 概念 https://www.luxalgo.com/library/concept/relative-rotation-graphs.md
- 範圍：metrics.rrg（族群相對全市場的比值平滑、動能）；API；新區塊 ECharts 散點＋尾跡；測試。

# 加分候選（第 4 輪）
（S2 1.3 < 2，列入「判斷不值得做」）

## T1. 全市場廣度列（上漲／下跌／平盤家數、漲停／跌停、上漲成交值占比）
因為原始需求是 **看盤時用熱力圖判斷強弱、哪些股票集體上漲**，所以頂尖做法會順便做 **市場廣度（advancing vs declining、漲跌成交量）總覽**（TradingView「Market breadth: Advancing and declining」；廣度常用指標包含漲跌家數與漲跌成交量）；目前的成果 **只有部分**——產業矩陣有各產業漲/跌，沒有全市場一眼看得到的總覽。
- 參考：TradingView Market breadth https://www.tradingview.com/support/solutions/43000794825/ ；Strike Money Market Breadth https://www.strike.money/stock-market/market-breadth
- 範圍：transform.js 新增 marketBreadth()（純函式，有測試）；即時頁頂部狀態列旁顯示一條比例長條＋數字；歷史頁 A 標題列同樣顯示當日數字。

## T2. 族群「創新高／創新低」家數（52 週或期間）
因為原始需求是 **回溯強勢族群**，所以頂尖做法會順便做 **新高 vs 新低家數**（廣度指標：每日創 52 週新高與新低的家數，新高激增代表樂觀）；目前的成果 **沒有**——已有約一年歷史可計算。
- 參考：Strike Money（52-week highs vs lows）https://www.strike.money/stock-market/market-breadth ；StockCharts 廣度文章 https://stockcharts.com/articles/dancing/2017/05/you-need-to-understand-what-market-breadth-offers.html ；Fidelity Market Breadth PDF https://fidelity.com/bin-public/060_www_fidelity_com/documents/MarketBreadth_01_2010_V2.pdf
- 範圍：metrics 計算每檔截至該日 N 日最高／最低收盤；group_stats 加 new_high／new_low；B 表多兩欄；測試。

# 加分候選（第 5 輪）
（T2 1.0 < 2，列入「判斷不值得做」）

## U1. 歷史頁逐日「播放」（回放）
因為原始需求是 **回溯每一天的強勢族群**，所以頂尖做法會順便做 **從任一過去日期開始逐日播放、可暫停與調速**（MotiveWave Replay Mode：start at any past day and play back, speed up/slow down/pause；TradingView Bar Replay：選起點並調整播放速度）；目前的成果 **只有部分**——只能按 ◀▶ 一天一天手動切。
- 參考：MotiveWave Replay Mode https://www.motivewave.com/support/replay_mode.htm ；TradingView Bar Replay https://www.tradingview.com/chart/BTCUSD/qmCyeQyK-How-To-Use-The-Bar-Replay-Tool-Rewatch-Trading-History
- 範圍：history.js 頂列加 ▶播放／⏸、速度（1／2／4 秒）；從目前日期往後逐日 selectDate，到最新日自動停止；app.css 少量；不改後端。

## U2. 匯出 CSV（B 排行、C 輪動、D 集體上漲）
因為原始需求是 **回溯強勢族群、哪些股票集體上漲**，所以頂尖做法會順便做 **資料表匯出（XLS／CSV）供自行分析**（Goodinfo 各資料頁工具列提供 HTML／XLS／CSV／複製）；目前的成果 **沒有**。
- 參考：Goodinfo 匯出工具列（例：https://goodinfo.tw/tw/StockCashFlow.asp 、https://goodinfo.tw/tw/DayTrading.asp）
- 範圍：前端以目前資料組 CSV（UTF-8 BOM，Excel 可開）並觸發下載；三個區塊各一顆「CSV」；transform 純函式 toCsv 加測試。

# 加分候選（第 6 輪）

## V1. 盤中族群轉強提醒（桌面通知）
因為原始需求是 **盤中用熱力圖找強勢族群**，所以頂尖做法會順便做 **條件觸發的即時提醒（桌面／推播通知）**（TradingView Alerts：價格警示、桌面與手機通知）；目前的成果 **沒有**——得一直盯著畫面。
- 參考：TradingView Creating and Managing Alerts https://tradingview.com/wiki/Creating_and_Managing_Alerts ；Introduction to TradingView alerts https://in.tradingview.com/support/solutions/43000520149
- 範圍：前端設定「某產業 ≥5% 家數佔比超過 X% 或漲停 ≥ N 檔」，每次快照更新時判斷，用瀏覽器 Notification API 通知（同一族群當日只提醒一次）；transform 純函式找出觸發族群＋測試。

## V2. 熱力圖標示漲停／跌停個股
因為原始需求是 **看哪些股票集體上漲**，所以頂尖做法會順便做 **突顯漲停板個股**（台股盤勢報導普遍以漲停／跌停家數與強勢漲停股描述族群強弱）；目前的成果 **只有部分**——漲停只是顏色最深，與 +7% 以上無法區分。
- 參考：工商時報盤勢報導（強勢漲停板）https://ctee.com.tw/news/stock/409205.html ；經濟日報（盤中跌停家數）https://money.udn.com/money/amp/story/5607/9459612
- 範圍：transform.js 葉節點在 ≥9.5%／≤−9.5% 時加亮色邊框，標籤加「漲停／跌停」，tooltip 註明；即時與歷史 A 共用；測試。
