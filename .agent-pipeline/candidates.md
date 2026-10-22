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
