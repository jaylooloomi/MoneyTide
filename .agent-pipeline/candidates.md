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

# 加分候選（第 7 輪）
（V1 0.4 < 2，列入「判斷不值得做」）

## W1. B 排行加入多期間族群報酬欄（近 5／20／60 日）
因為原始需求是 **回溯強勢族群**，所以頂尖做法會順便做 **族群績效表同時列出 1 日／1 週／1 月／1 季報酬**（Finviz Groups「Performance」視圖：perf 1D/1W/1M/3M/6M；OpenBB CompareGroups 資料模型同樣欄位）；目前的成果 **只有部分**——B 只有當日，E 圖要另外選族群才看得到期間表現。
- 參考：OpenBB Compare Groups https://docs.openbb.co/platform/data_models/CompareGroups ；finvizfinance group performance https://finvizfinance.readthedocs.io/en/latest/group.html
- 範圍：metrics 以等權日報酬連乘算 5/20/60 日（沿用 group_index 的單次掃描邏輯）；/api/history/groups 附 perf_5/perf_20/perf_60；B 表多三欄可排序；測試。

## W2. B 排行加「領漲股」欄
因為原始需求是 **看哪些股票集體上漲、由誰帶動**，所以頂尖做法會順便做 **列出族群內漲幅最大的領漲股**（盤後報導普遍以「某族群由 X 領漲／強勢出擊」描述）；目前的成果 **沒有**——要點進 D 或放大 A 才知道。
- 參考：Yahoo 股市盤後新聞（族群強勢出擊）https://tw.stock.yahoo.com/news/%E5%85%A9%E8%90%AC%E9%BB%9E%E5%9B%9E%E4%BE%86%E5%95%A6-%E5%8F%B0%E7%A9%8D%E9%9B%BB%E4%B8%8A%E6%8F%9A%E6%8B%89%E6%8A%AC%E5%8F%B0%E8%82%A1%E6%94%B6%E6%BC%B2161-68%E9%BB%9E-%E5%B1%85%E5%AE%B6%E7%94%9F%E6%B4%BB%E6%97%8F%E7%BE%A4%E5%BC%B7%E5%8B%A2%E5%87%BA%E6%93%8A-071100849.html ；鉅亨網盤後 https://www.nstock.tw/news/article_c?id=307347
- 範圍：group_stats 加 leader（名稱、代號、漲幅）；B 表多一欄，點擊開 bonus-02 個股卡片；測試。

# 加分候選（第 8 輪）

## X1. 即時產業矩陣加入近 5／20 日欄
因為原始需求是 **盤中看產業熱力圖＋強勢族群**，所以頂尖做法會順便做 **族群績效表同時看當日與 1 週／1 月**（Finviz Groups Performance 視圖、OpenBB CompareGroups perf 1D/1W/1M）；目前的成果 **只有部分**——即時矩陣只有今日、本週（HiStock 週漲跌），歷史頁才有 5／20／60 日。
- 參考：OpenBB Compare Groups https://docs.openbb.co/platform/data_models/CompareGroups ；finvizfinance group performance https://finvizfinance.readthedocs.io/en/latest/group.html
- 範圍：即時頁載入一次 /api/history/periods（最新交易日）；產業矩陣多「20日」欄（可排序、上色）；app.js＋index.html；無後端改動。

## X2. 網址保存檢視狀態（日期／分組／模式），可加書籤
因為原始需求是 **回溯每一天的強勢族群**，所以頂尖做法會順便做 **把目前檢視編進網址，可分享／書籤**（Finviz map 以 map.ashx?t=sec 等參數指定地圖；提供嵌入產生器保存市場與期間選擇）；目前的成果 **沒有**——重新整理後回到最新日，無法把「10/16 概念股」存成書籤。
- 參考：Finviz 嵌入地圖（選市場、期間）https://finviz.com/blog/you-can-now-embed-finviz-maps-on-your-website-blog-or-app/ ；Finviz 熱力圖網址 finviz.com/map.ashx?t=sec（Optuma 論壇引用）https://forum.optuma.com/t/heat-map/4074
- 範圍：history.js 以 location.hash（#history/2026-10-16/concept）同步日期與分組，載入時讀取；app.js 模式切換寫入 hash；無後端改動。

# 加分候選（第 9 輪）

## Y1. 個股「同步股」：近 60 日日報酬相關性最高的股票
因為原始需求是 **看哪些股票集體上漲**，所以頂尖做法會順便做 **找出與某檔股票走勢高度連動的同伴（co-movement／correlation peers）**（dqydj Stock Correlation Calculator 列出最相關的股票對；開源 stock-correlation 技能以一年日資料、相關係數門檻 0.6 排出 co-movement peers）；目前的成果 **沒有**——只能靠官方產業或概念股分組推測。
- 參考：dqydj Stock Correlation Calculator https://dqydj.com/stock-correlation-calculator/ ；stock-correlation（co-movement discovery）https://skillselion.com/skills/himself65/finance-skills/stock-correlation ；MarketXLS Correlation Matrix guide https://marketxls.com/blog/correlation-matrix-stock-comparison-tool/
- 範圍：metrics.comovers（以 change_rows 取近 60 日，對全部普通股算皮爾森相關，取前 8 檔、至少 40 個共同交易日）；GET /api/history/comovers/{code}；歷史個股卡片（bonus-02 續做）加一行「同步股」可點開；測試。

# 加分候選（第 10 輪）
（第 9 輪 TOP: none）

## Z1. 歷史熱力圖顏色期間：1 日／5 日／20 日（個股區間報酬）
因為原始需求是 **回溯強勢族群、哪些股票集體上漲**，所以頂尖做法會順便做 **熱力圖可切換期間（1D／1W／1M…）**（Finviz 地圖嵌入工具提供 1 Day、1 Week、1 Month、3 Months、YTD、1 Year 期間選擇）；目前的成果 **只有部分**——歷史 A 只能看單日（tooltip 有 5 日）。與第 1 輪 C2 相比縮小範圍：只改 A 的顏色來源，不動 B。
- 參考：Finviz「You Can Now Embed Finviz Maps」（期間選擇）https://finviz.com/blog/you-can-now-embed-finviz-maps-on-your-website-blog-or-app/ ；第三方 Finviz 資料 App 期間選項 https://apptopia.com/google-play/app/com.cousinHub.HeatMap/about
- 範圍：day_stocks 已有 week_pct（5 日）；新增 period_20（收盤對 20 交易日前收盤）一個欄位；A 標題列「顏色：1日／5日／20日」切換；transform colorBy 增加 'p20'；測試。

## Z2. 即時個股卡片顯示近 20 日走勢小圖
因為原始需求是 **盤中看哪些股票上漲**，所以頂尖做法會順便做 **點個股即看近期走勢**（TradingView／Finviz 熱力圖點擊進入個股走勢）；目前的成果 **只有部分**——歷史卡片有 20 日小圖，即時卡片沒有。
- 參考：TradingView Heatmaps https://www.tradingview.com/support/solutions/43000766446 ；Finviz heatmap https://finviz.com/blog/evolving-the-heatmap-dow-jones-nasdaq-100-russell-2000-and-more
- 範圍：即時卡片呼叫既有 /api/history/stock/{code}（最新存檔日）畫迷你走勢；app.js；無後端改動。

# 加分候選（第 11 輪）
（Z2 1.5 < 2，列入「判斷不值得做」）

## AA1. 每日市場廣度月曆（一年每個交易日一格，點擊跳到該日）
因為原始需求是 **回溯每一天的強勢族群**，所以頂尖做法會順便做 **以日曆熱力圖呈現每天的漲跌廣度／報酬，快速找出值得回看的日子**（TradingView Seasonality Heatmap 以月／星期格子顯示報酬；thetrading.tools Market Heatmap 每日報告「多少檔收漲（% green）」；Strike Advance-Decline Heatmap 顯示漲跌家數）；目前的成果 **沒有**——要用 ◀▶ 一天天找哪天全面大漲。
- 參考：TradingView Seasonality Heatmap https://www.tradingview.com/script/Bfz2VMKL-Seasonality-Heatmap-QuantAlgo/ ；thetrading.tools Market Heatmap https://www.thetrading.tools/market-heatmap ；Strike Advance-Decline https://www.strike.money/?p=12411
- 範圍：store 一次 SQL 彙總每日上漲／下跌家數與等權平均漲幅；GET /api/history/calendar；歷史頁新增「F · 每日廣度月曆」（每列一個月、格子顏色＝上漲家數佔比，點擊切換日期，標示目前日期）；測試。

# 加分候選（第 12 輪）

## AB1. 族群成分股清單（點 B 列展開當日成分股表：漲幅、5／20 日、成交值，可排序）
因為原始需求是 **回溯強勢族群、哪些股票集體上漲**，所以頂尖做法會順便做 **點族群即看其成分股清單與表現**（MarketInOut 產業排行：點產業看其股票、點類股看全部成分股；Barchart Top Performing 族群點開顯示前幾名）；目前的成果 **只有部分**——A 放大可看格子，但沒有可排序的成分股表（小型股格子太小看不到）。
- 參考：MarketInOut Industry Growth https://www.marketinout.com/stock-screener/report/industry-growth ；Barchart Top Performing Stocks https://www.barchart.com/ca/investing-ideas/top-performing-stocks ；OpenBB Finviz groups https://docs.openbb.co/python/reference/equity/compare/groups
- 範圍：前端以已載入的 A 資料（st.stocks，含 change_pct／week_pct／period_20／turnover）過濾該族群；B 表下方展開成分股表（可排序、點擊開個股卡片）；history.js；無後端改動；測試以 transform 純函式 groupMembers()。

# 加分候選（第 13 輪）

## AC1. 即時產業矩陣「量能倍數」欄（今日成交值 ÷ 近 20 日平均）
因為原始需求是 **盤中用產業熱力圖找強勢族群**（使用者核准的版面草圖 C 就有「量能 1.8x」欄，當時規格因無歷史資料而延後），所以頂尖做法會順便做 **相對成交量（relative volume）**（TradingView heatmap 可依 relative volume 上色；Finviz 資料 App 提供 Relative Volume）；目前的成果 **沒有**——已有一年歷史可算 20 日平均。
- 參考：TradingView Heatmaps（color by relative volume）https://www.tradingview.com/support/solutions/43000766446 ；Finviz 資料 App（Relative Volume）https://apptopia.com/google-play/app/com.cousinHub.HeatMap/about ；本專案設計草圖 .superpowers/brainstorm（產業 × 指標矩陣「量能」欄）
- 範圍：store 單一 SQL 取近 20 交易日各產業成交值合計平均（依日期快取）；GET /api/history/turnover-avg；即時矩陣「量能」欄＝今日產業成交值 ÷ 20 日平均（上色、可排序）；測試。

# 加分候選（第 14 輪）

## AD1. 即時熱力圖的族群分類切換（官方產業／自訂／概念股）— 第 2 輪 R1 縮小重提
因為原始需求是 **產業熱力圖看盤＋強勢族群（含自訂、概念股）**，所以頂尖做法會順便做 **盤中就能以題材分組看熱力圖**（Finviz Themes 地圖；TradingView heatmap 可切分組）；目前的成果 **只有部分**——自訂／概念分組只在歷史頁。第 2 輪 R1（1.0）分高在 Effort／Blast；如今一檔多群組的格子 id、去重、分組 API 都已存在，改動縮小為：
- 參考：Finviz「Themes」地圖 https://finviz.com/blog/tag/heatmaps/ ；TradingView Heatmaps https://www.tradingview.com/support/solutions/43000766446
- 範圍：GET /api/groupings/{custom|concept}（代號→族群）；即時頁頂列加「分組」切換；app.js 在 filterStocks 後依對照把 industry 換成族群並複製多群組股票（沿用 transform 現有函式），矩陣與熱力圖自動跟著；測試。

# 加分候選（第 15 輪）

## AF1. 熱力圖快照（存成 PNG／複製圖片）
因為原始需求是 **回溯每一天的強勢族群**，所以頂尖做法會順便做 **把當下的圖存成圖片留存或分享**（TradingView「Take a snapshot」：下載圖片、複製到剪貼簿；Charting Library 預設提供 Download image／Copy image）；目前的成果 **沒有**——只能自己截圖。
- 參考：TradingView How to share a snapshot https://in.tradingview.com/support/solutions/43000482537 ；TradingView Charting Library Snapshots https://tradingview.com/charting-library-docs/v28/ui_elements/Snapshots
- 範圍：即時與歷史 A 標題列各一顆「📷」：ECharts getDataURL 產生 PNG（檔名含日期／分組），按 Shift 時複製到剪貼簿；app.js、history.js；無後端改動。

# 加分候選（第 16 輪）
（第 15 輪 TOP: none）

## AG1. B 排行「名次變化」欄（與前一交易日比較 ▲▼）
因為原始需求是 **回溯每天的強勢族群、看輪動**，所以頂尖做法會順便做 **排名變動（名次上升代表進入領漲、下降代表失去動能）**（TradingView Sector Rotation Dashboard 以 Rank 追蹤族群升降；Crypto Sector Rotation Radar 追蹤 3／7 期名次變化；Factor Investor 報告標示族群名次變動）；目前的成果 **只有部分**——C 矩陣看得出強弱，但沒有直接的名次升降。
- 參考：TradingView Sector Rotation Dashboard https://www.tradingview.com/script/dAOscEaH-Sector-Rotation-Dashboard-v1/ ；TradingView sector rotation scripts https://www.tradingview.com/scripts/sectorrotation/ ；Factor Investor Report https://factorinvestor.substack.com/p/factor-investor-report-april-2021
- 範圍：/api/history/groups 多回傳前一交易日的同指標名次（依目前排序指標 strong_ratio／avg_pct，取 daily_group_avgs 快取）；B 表「名次」欄顯示 ▲n／▼n；測試。

# 加分候選（第 17 輪）

## AH1. 啟動後背景預熱歷史快取（每日族群平均、20 日均量、月曆）
因為原始需求是 **回溯每一天的強勢族群**（打開歷史頁就要看），所以業界做法會順便做 **cache warming：重啟後先把可預期的熱門資料載入快取，避免第一批請求打到資料庫造成延遲尖峰**；目前的成果 **只有部分**——重啟後第一次開歷史頁的 5／20／60 日欄、E 圖、月曆要 4–7 秒（夜間實測），之後才快。
- 參考：OneUptime「Redis cache preloading at application startup」https://oneuptime.com/blog/post/2026-03-31-redis-cache-preloading-application-startup/view ；Aerospike「Cache warming explained」https://aerospike.com/blog/cache-warming-explained ；OneUptime Cache Warming Strategies https://oneuptime.com/blog/post/2026-01-30-cache-warming-strategies/view
- 範圍：HistoryCollector 每輪回補／累積結束後（及啟動後一次）在背景執行緒對最新 60 個交易日預先計算 industry 每日平均與 20 日均量（只算可預期的官方產業）；不改 API；測試。

# 加分候選（第 18 輪）

## AI1. HiStock 失效時改用證交所 MIS 即時報價備援
因為原始需求是 **盤中看產業熱力圖**（資料來源為第三方 HiStock），所以業界做法會順便做 **多資料源備援**（證交所 MIS getStockInfo.jsp 以 ex_ch 串接多檔查詢；第三方整理的限制約每 5 秒 3 個請求）；目前的成果 **沒有**——HiStock 改版或擋爬時，即時頁只能顯示舊資料。
- 參考：iT 邦幫忙 MIS API 範例 https://ithelp.ithome.com.tw/articles/10258478 ；tsrtc https://github.com/Asoul/tsrtc ；TWSE 即時資訊 FAQ https://www.twse.com.tw/pcversion/en/page/products/info-vendor/faq.html
- 範圍：sources/twse_mis.py（約 2,000 檔需分 40 批以上、受頻率限制，單次輪詢需 1 分鐘以上）；poller 在 HiStock 失敗時切換；測試。

## AI2. B 排行族群名稱篩選框
因為原始需求是 **回溯強勢族群**（概念股分組下 B 有 101 列），所以常見做法會順便做 **表格即時篩選**（MarketInOut 產業排行可依名稱檢索）；目前的成果 **沒有**——要捲動或排序才找得到特定族群。
- 參考：MarketInOut Industry Growth https://www.marketinout.com/stock-screener/report/industry-growth
- 範圍：B 標題列加輸入框，依名稱子字串過濾列；history.js；無後端改動。

# 加分候選（第 19 輪）

## AJ1. 熱力圖全螢幕模式
因為原始需求是 **以熱力圖為主畫面看盤**（約 2,400 檔、許多小格子），所以頂尖做法會順便做 **熱力圖全螢幕按鈕**（TradingView Heatmap 右上角 Fullscreen 按鈕開啟全尺寸檢視）；目前的成果 **沒有**——熱力圖受頂列、側欄、廣度列擠壓。
- 參考：TradingView How to set up the display of the Heatmap?（Fullscreen button）https://www.tradingview.com/support/solutions/43000707156-how-to-set-up-the-display-of-the-heatmap ；TradingView heatmaps https://www.tradingview.com/support/solutions/43000766446
- 範圍：即時與歷史 A 標題列各一顆「⛶」，用瀏覽器 Fullscreen API 放大熱力圖容器（Esc 離開），ECharts resize；app.js、history.js；無後端改動。

# 加分候選（第 20 輪）

## AK1. 熱力圖「最低成交值／最低市值」篩選
因為原始需求是 **用熱力圖看哪些股票集體上漲**（全市場約 2,400 格，冷門小型股雜訊多），所以頂尖做法會順便做 **熱力圖篩選條件**（TradingView heatmap 提供數十種篩選；Finviz 熱力圖可搭配篩選器）；目前的成果 **只有部分**——只能篩市場、ETF、自選。
- 參考：Liberated Stock Trader「Stock heat map」評測（TradingView heatmap filters）https://www.liberatedstocktrader.com/stock-heat-map/ ；TradeAlgo Best Heat Map Tools 2026 https://www.tradealgo.com/trading-guides/tools/best-heat-map-tools-for-stocks-options-and-crypto-in-2026 ；TradingView Heatmaps https://www.tradingview.com/support/solutions/43000766446
- 範圍：transform filterStocks 增加 minTurnover／minCap（純函式＋測試）；即時頂列與歷史 A 標題列各一個下拉（不限／成交值 ≥1 億／≥5 億、市值 ≥100 億）；app.js、history.js。

# 加分候選（第 21 輪）

## AL1. 即時熱力圖「找股票」搜尋框（代號／名稱 → 放大該產業並開啟資訊卡）
因為原始需求是 **在約 2,400 格的產業熱力圖上看盤、點個股開資訊卡**，所以頂尖做法會順便做 **快速定位特定個股**（Finviz／TradingView 熱力圖以滑鼠懸停查看個股；評測文章把定位速度列為重點）；目前的成果 **沒有**——即時頁只能在小格子裡用眼睛找，歷史頁 B 才有名稱篩選。
- 參考：Liberated Stock Trader Stock heat map 評測 https://www.liberatedstocktrader.com/stock-heat-map/ ；Finviz Matrix https://finviz.com/blog/the-finviz-matrix-market-breadth-visualized/ ；AAII StockMapper https://www.aaii.com/journal/article/stockmappercom
- 範圍：transform 加 findStock(stocks, query)（代號完全符合優先，其次名稱子字串；純函式＋測試）；app.js 頂列一個輸入框＋datalist，Enter 後放大該產業並開啟資訊卡；無後端改動。

## AL2. B 排行名次變化擴充為 1／5／20 日前（週、月）
因為原始需求是 **回溯強勢族群與輪動**，所以頂尖做法會順便做 **多期間名次變化**（Stage Analysis 的 IBD 族群表列出 1、2、4 週前的名次變動）；目前的成果 **只有部分**——bonus-18 只比較前一交易日。
- 參考：Stage Analysis IBD Industry Groups Bell Curve https://stageanalysis.net/blog/517246/ibd-industry-groups-bell-curve-bullish-percent
- 範圍：metrics.group_rank_change 加 lag 參數；api 回傳 5／20 日前名次；B 表名次欄 tooltip 或切換；屬 bonus-18 續做。

# 加分候選（第 22 輪）

## AM1. 熱力圖色階範圍可調（±3／±5／±7／±10%）
因為原始需求是 **用顏色看哪些產業／股票集體上漲**（目前今日色階固定 ±7%，平盤附近的日子幾乎全是淡色），所以常見做法會順便做 **可調整色階或更細的顏色層次**（Sharesight 使用者要求熱力圖顏色更有層次，並以 Finviz 的漸層為例；TradingView heatmap 有顯示設定）；目前的成果 **沒有**——COLOR_LIMITS 寫死。
- 參考：Sharesight Community「Heatmap needs to be a bit darker/lighter」https://community.sharesight.com/t/heatmap-needs-to-be-a-bit-darker-lighter/1610 ；TradingView How to set up the display of the Heatmap https://www.tradingview.com/support/solutions/43000707156-how-to-set-up-the-display-of-the-heatmap
- 範圍：transform colorLimit 接受覆寫（純函式＋測試）；即時頂列與圖例旁一個「色階」下拉，套用即時熱力圖、矩陣與圖例；偏好保存；歷史頁不動。

## AM2. 個股「量比」顏色模式（今日成交值 ÷ 20 日均成交值）
因為原始需求是 **找出集體上漲的股票**（量增價漲才是真的集體行動），所以頂尖做法會順便做 **以相對成交量著色**（LuxAlgo Heatmap Volume 以均量與標準差分級異常量）；目前的成果 **只有部分**——bonus-16 只有族群層級的量能欄。
- 參考：LuxAlgo Heatmap Volume https://www.luxalgo.com/library/indicator/unWex8N4-heatmap-volume ；TradingView Intraday Volume Spikes Heatmap https://de.tradingview.com/script/l4nZQnW2-Intraday-Volume-Spikes-Heatmap-everget/
- 範圍：新 API 回傳各股 20 日均成交值（store 查詢）；即時顏色多一個「量比」；transform 色階；後端＋前端約 5 檔。

# 加分候選（第 23 輪）

## AN1. 歷史 D「量增上漲」模式（當日漲幅 ≥ X% 且成交值 ≥ 前 20 日均值 2 倍）
因為原始需求是 **回溯每一天哪些股票集體上漲**，所以頂尖做法會順便做 **價量同步的篩選（相對成交量 > 1～2 且上漲）**（Finviz 篩選器以 Relative Volume 搭配 Change 篩選；交易教學建議以相對量 > 1 為起點）；目前的成果 **只有部分**——D 只有當日漲幅／區間累計／連續上漲三種模式，看不出是否有量。
- 參考：Daytradingz「How to Use Finviz」https://daytradingz.com/how-to-use-finviz/ ；TradingView VB Finviz-style MTF Screener https://it.tradingview.com/script/FygpRrxA-VB-Finviz-style-MTF-Screener
- 範圍：metrics.movers 加 mode=volume（以 store 前 20 個交易日成交值平均為基準，漲幅門檻沿用 value）；history.js D 多一顆「量增上漲」並在列中顯示倍數；pytest＋前端無新純函式；約 3–4 檔。

# 加分候選（第 24 輪）
（第 23 輪 TOP: none）

## AO1. 盤中族群轉強提醒（族群漲幅或 ≥5% 佔比「穿越」門檻時提示）
因為原始需求是 **盤中看產業熱力圖找強勢族群**（使用者不會一直盯著螢幕），所以業界做法會順便做 **族群門檻警示**（Kite 使用者要求自訂股票群組盤中漲 1% 時跳出提示；Trade-Ideas 有 Sector Breakout from Open 警示；Heat Map Monitor 以「市場＋族群＋指標門檻」規則推播）；目前的成果 **沒有**——只能自己看。
- 參考：Kite forum「front end development」（group 1% pop-up）https://kite.trade/forum/discussion/5981/front-end-development ；Trade-Ideas Sector Breakout (from Open) https://trade-ideas.com/help/alert/SBOO/ ；Heat Map Monitor https://wingstock.duckdns.org/heatmap-monitor.html
- 範圍：transform 加 crossedGroups(prev, next, rule)（純函式：只回報由下而上穿越的族群，避免每次刷新重複提醒；測試）；app.js 一個「提醒」下拉（關／族群漲幅 ≥2%／≥3%／≥5% 佔比 ≥30%），穿越時 toast，使用者按下後可選擇開啟瀏覽器通知；無後端改動；約 3 檔。
