# 加分候選（第 1 輪）

錨點：scope.md 第 1 節——「多維度分析金錢為什麼這樣流動」；N · 資金連動搜尋（找出共同注資的組合、找可能的新組合，門檻要保留彈性）。

## C1 · N 的結果一鍵存成自訂族群（✅ 已完成 bonus-01, 1c596b3）
因為原始需求是**找出「可能的新組合」（找法2 跨族群新組合）並持續觀察資金是否還在**，所以頂尖做法會順便做**把篩選結果直接存成清單（watchlist／自訂族群），之後在其他畫面追蹤**；目前的成果**沒有**——N 找到的組合只能看當天，要追蹤得手動到「管理族群」一檔檔加。
- 參考：TradingView Import watchlist（https://cn.tradingview.com/chart/NIFTY/qNGKMbgU-How-to-import-watchlist-in-TradingView）；Chartink / Screener.in 的「screener → watchlist」擴充（https://chromeboard.com/extension/screener-to-tradingview-mcfligcbhdnbfhkbcpoclgcanimnoiha）
- 預估：finder.js（卡片按鈕）＋既有 /api/groups 端點；≤3 檔、<120 行。

## C2 · N 結果匯出 CSV（✅ 已完成 bonus-04）
因為原始需求是**多維度分析且條件要能反覆調整比較**，所以頂尖做法會順便做**篩選結果下載 CSV**；目前的成果**只有部分**——B/C/D 有 CSV，N 沒有。
- 參考：TradingView screener 下載 .csv（https://barbucket.readthedocs.io/en/latest/tv_screener/）
- 預估：finder.js＋history.js 的 CSV 匯出表；≤2 檔、<60 行。

## C3 · N 卡片顯示連動趨勢（短窗 R vs 20 日 R：增強／減弱）
因為原始需求是**判斷連動是不是「因為資金共同注資」而產生（而且是現在進行式）**，所以頂尖做法會順便做**滾動相關（rolling correlation）看關係是否正在變強**；目前的成果**沒有**——卡片只有單一個 20 日（或 10 日）R。
- 參考：stock-correlation skill「track rolling or regime-dependent correlation」（https://tessl.io/registry/skills/github/himself65/finance-skills/stock-correlation）；20-day rolling correlation heatmap（https://docs.openalgo.in/trading-platform/python/visualization/correlation-heatmap）
- 預估：finder.py（describe 多算短窗 R）＋finder.js（顯示箭頭）＋測試；≤4 檔、<100 行。

## C4 · N 卡片可排序（日 R／分時 R／檔數／平均漲幅／成交值）
因為原始需求是**從大量結果找出最值得注意的資金組合**，所以頂尖做法會順便做**結果欄位排序**；目前的成果**沒有**——卡片固定依檔數、分時 R 排。
- 參考：TradingView screener 欄位排序（https://barbucket.readthedocs.io/en/latest/tv_screener/）；stock-correlation skill 輸出「strongest and weakest pairs」
- 預估：finder.js＋測試；≤2 檔、<80 行。

## C5 · N 卡片加「資金規模」：群組總成交值與平均漲幅（✅ 已完成 bonus-02, 6db6715）
因為原始需求是**找資金（多少錢、往哪去）背後的動機**，所以頂尖做法會順便做**每個組合的成交值總和與漲跌摘要**（熱力圖／screener 的 market-cap、volume 欄）；目前的成果**只有部分**——卡片列成員漲跌，但沒有群組的成交值總和、占全市場比重。
- 參考：Twelve Data 熱力圖相關分析（https://twelvedata.com/news/analyzing-the-correlation-of-u-s-stocks-using-heat-maps）；TradingView screener volume / market cap 欄（https://barbucket.readthedocs.io/en/latest/tv_screener/）
- 預估：finder.py describe＋finder.js＋測試；≤3 檔、<60 行。

## C6 · K 動畫時間軸標出「同時爆量」的時間點
因為原始需求是**看是不是同一筆資金在同一時間進場**，所以頂尖做法會順便做**在走勢上標出量能異常的時間點**（XQ「大戶買賣力」盤中逐筆）；目前的成果**只有部分**——N 卡片寫出同時爆量時間，但 K 動畫上看不到。
- 參考：XQ 全球贏家「大戶買賣力」盤中逐筆指標（https://www.moneyweekly.com.tw/_Article?AID=75294）
- 預估：linkage payload 加每檔爆量時段＋race.js 畫標記；≤4 檔、<150 行。

## C7 · 找法2 也加成交量門檻（預設與找法1 相同：≥ 300 張）（✅ 已完成 bonus-03）
因為原始需求是**找「資金」共同注資的組合**，所以頂尖做法會順便做**候選池先濾掉成交量太小的股票**（screener 的 volume filter），否則兩檔小量股巧合同步就會被當成「資金組合」；目前的成果**只有部分**——找法1 有 ≥300 張，找法2 沒有；bonus-02 的 💰 顯示 10/22 找法2「勝昱+全景軟體」整組只有 0.1 億成交值。
- 參考：TradingView screener volume 欄篩選（https://barbucket.readthedocs.io/en/latest/tv_screener/）；使用者自己為找法1 指定「增加成交量 過濾 預設 至少>300張」
- 預估：finder.py candidate_pool＋finder.js 欄位＋測試；≤3 檔、<40 行。

# 加分候選（第 2 輪）

## D1 · 「這檔跟誰一起動」：從一檔股票找同夥（N 第三種找法）
因為原始需求是**找出因為共同注資而一起動的股票**，所以頂尖做法會順便做**給一檔股票，自動找出全市場跟它相關最高的同夥並排序**；目前的成果**沒有**——找法1/2 都是從一群股票裡找，不能從「我正在看的這檔」出發。
- 參考：stock-correlation skill「finds peers for a ticker … ranks peers by absolute correlation … 0.60 threshold, top ten」（https://tessl.io/registry/skills/github/himself65/finance-skills/stock-correlation）；arXiv 1204.5103 高頻資料看即時共同走勢（https://ar5iv.arxiv.org/html/1204.5103）
- 預估：finder.py（peer 候選：對全市場算日 R 取前 N，再走分時／高點兩關，只檢查與目標股的配對）＋api 參數＋finder.js（第三個分頁＋代號輸入）＋測試；4 檔、約 200 行。

## D2 · N 卡片加「PTT 討論熱度」當動機證據
因為原始需求是**找資金背後的動機**，所以頂尖做法會順便做**社群討論熱度（同一批股票近幾天被提到的次數比平常多）**；目前的成果**只有部分**——卡片有「新聞同時提到兩檔」，沒有個股在 PTT 的討論增幅（J 區只有族群層級的熱度）。
- 參考：政大論文：PTT 個股回文數與後續報酬的關係（https://nccur.lib.nccu.edu.tw/handle/140.119/98565）；北科論文：PTT 股版情緒結合換手率等指標（https://thesis.lib.nccu.edu.tw/thesis/detail/a226b628d8b1f7e3bb3d5416c0183480/）
- 預估：finder.py（成員名稱在近 3 天 PTT 標題的次數 vs 前 20 天）＋finder.js＋測試；3 檔、約 80 行。

# 加分候選（第 3 輪）——錨點：「要幫我保留變數彈性 後面可能會調整!!!」

## E1 · N 顯示「漏斗：每一關刷掉幾對、最常卡在哪一關」（✅ 已完成 bonus-05）
因為原始需求是**門檻會反覆調整**，所以頂尖做法會順便做**讓使用者看見每個條件刷掉多少、哪個條件最嚴**，才知道該放寬哪一個；目前的成果**只有部分**——統計列只有「日相關通過 N 組／找到 M 群」，看不到分時相關、高點差、假同步各刷掉幾對（pair_check 其實已經有 reason，只是沒彙總）。
- 參考：TradingView screener「standard levels … Custom section for alternative values」（https://www.tradingview.com/blog/en/new-screeners-stock-crypto-coins-etf-42346）；Chaikin 預設篩選從 universe 一路篩下（https://help.chaikinanalytics.com/en_US/screener/360041564913-Preset-Screens）
- 預估：finder.py（confirm 彙總 reason 次數、run_search 放進 stats）＋finder.js（統計列下一行小字）＋測試；3 檔、約 60 行。

## E2 · N 條件預設組：嚴格／標準／寬鬆 一鍵切換（✅ 已完成 bonus-06）
因為原始需求是**門檻要保留彈性、常常要調**，所以頂尖做法會順便做**預設篩選組（presets）＋自訂**；目前的成果**只有部分**——只有逐欄輸入和「恢復預設」。
- 參考：TradingView「standard levels … Custom section」（https://www.tradingview.com/blog/en/new-screeners-stock-crypto-coins-etf-42346）；fffinstill screener presets（https://fffinstill.com/learning/concepts/screener-presets）；Chaikin preset screens（https://help.chaikinanalytics.com/en_US/screener/360041564913-Preset-Screens）
- 預估：finder.js（三個按鈕套用一組參數）＋測試；2 檔、約 50 行。

# 加分候選（第 4 輪）

## F1 · 背景預算最近 5 個交易日（不只最新一天）（✅ 已完成 bonus-07）
因為原始需求是**整個搜尋要在 1 分鐘內、最好打開就有**，所以頂尖做法會順便做**收盤後批次預算並快取、打開時直接讀**（cache warmer）；目前的成果**只有部分**——只預算「最新一天＋預設門檻」，往前翻一天就要現算（剛重啟時可能要 30 秒以上）。
- 參考：maverick-mcp cache warmer（https://glama.ai/mcp/servers/@wshobson/maverick-mcp/blob/e0e1dd2c7d5833cd01a7168f85f9f268758a8894/maverick_mcp/utils/cache_warmer.py）；Barchart 收盤後排程掃描、結果是快照（https://www.barchart.com/stocks/stocks-screener）；StocksCafe 的取捨：只預算真的會用到的（https://blog.stocks.cafe/888/screener-updates/）
- 預估：api.py finder_precompute（最新 → 往前 5 天、兩種找法、預設門檻；已有結果就跳過）；1 檔、約 15 行。

## F2 · N 卡片加 20 日迷你走勢（群組累積漲幅 vs 大盤）
因為原始需求是**看資金是不是持續在流入這群股票**，所以頂尖做法會順便做**結果旁的 sparkline 迷你走勢**；目前的成果**沒有**——卡片只有當天數字，看不出這群是這幾天才被拉、還是一路被買上來。
- 參考：TradingView Sparklines 指標（最近 20 點的迷你圖＋績效，https://www.tradingview.com/scripts/sparklines/）；Google Sheets SPARKLINE（https://support.google.com/docs/answer/3093289）
- 預估：finder.py（describe 帶出群組 20 日等權累積漲幅；大盤用 index_rows）＋finder.js（SVG 小折線）＋測試；3～4 檔、約 120 行。

# 加分候選（第 5 輪）

## G1 · 盤中錄製順便記成交量（之後的日子不用再跟 Yahoo 抓分 K）
因為原始需求是**整個搜尋 1 分鐘內、資料要準**，所以頂尖做法會順便做**盤中把即時 tick 聚合成本機 1 分 K（OHLCV）、盤後直接用**；目前的成果**只有部分**——錄製只存價格（沒有成交量），所以自錄的日子 N 的爆量、個股走勢的均價／成交量都缺，還是得回頭抓 Yahoo。
- 參考：PKScreener InMemoryCandleStore「turns ticks into OHLCV candles … replaces Yahoo Finance as the primary data source during market hours」（https://pkscreener.readthedocs.io/en/latest/HIGH_PERFORMANCE_DATA.html）；Kite 論壇：用 tick 自己的時間戳聚合分 K（https://kite.trade/forum/discussion/comment/46172/）
- 預估：intraday.py（記 price＋累計量）＋store.py（tick blob 相容舊格式，不改 schema）＋linkage tick_bars（由累計量差算每分鐘量）＋測試；4 檔、約 100 行。

# 加分候選（第 6 輪）

## H1 · B 族群排行標出「N 今天找到共同注資」的族群（✅ 已完成 bonus-08）
因為原始需求是**多維度看資金往哪個族群流、是不是同一筆錢**，所以頂尖做法會順便做**在使用者瀏覽的清單上直接標旗（watchlist／monitor 的 unusual activity 標記）**；目前的成果**沒有**——N 的結論只在 N 區，B 排行看不到「這族群今天有被找到同步拉抬」。
- 參考：Futu Market Monitor「show the unusual activities of the stocks in your watchlists」（https://support.futunn.com/en/topic106）；Acuity Market Reader 熱力圖用亮度標出異常移動（https://knowledgebase.acuitytrading.com/en/acuity-client-knowledge-base/platform-navigation-visual-tools-and-output-formats）
- 預估：history.js（B 列名稱旁加小圖示；讀 N 已存的當天找法1 結果，不觸發計算）＋finder.js 匯出查詢小函式＋測試；3 檔、約 80 行。

# 加分候選（第 7 輪）

## I1 · N 卡片標「近 5 天出現 N 次」（同一組合連續被找到）（✅ 已完成 bonus-09）
因為原始需求是**判斷連動是不是因為資金「共同注資」（持續性的）而不是一天的巧合**，所以頂尖做法會順便做**滾動／跨期追蹤：同一關係在最近幾期是否持續成立**；目前的成果**沒有**——每天的結果各自獨立；bonus-07 之後最近 5 天的結果都已存好，比對幾乎零成本。
- 參考：stock-correlation skill「track rolling or regime-dependent correlation」「60-day rolling correlation statistics」（https://tessl.io/registry/skills/github/himself65/finance-skills/stock-correlation）；Futu Market Monitor 追蹤自選股異動（https://support.futunn.com/en/topic106）
- 預估：api.py（finder_result 讀前 4 個交易日同條件的已存結果，比對成員重疊 ≥ 一半）＋finder.js（卡片徽章）＋測試；3～4 檔、約 80 行。

## I2 · K 動畫標出 N 找到的成員
因為原始需求是**看族群裡哪幾檔是被同一筆錢拉**，所以頂尖做法會順便做**在使用者正在看的視圖直接標出異常成員**；目前的成果**只有部分**——bonus-08 在 B 列標了 🔗，但點進 K 看族群時，不知道是哪幾檔。
- 參考：Futu Market Monitor（https://support.futunn.com/en/topic106）；Acuity Market Reader 以亮度標異常（https://knowledgebase.acuitytrading.com/en/acuity-client-knowledge-base/platform-navigation-visual-tools-and-output-formats）
- 預估：history.js（把 finderMarks 傳給 K）＋linkage.js／race.js（成員名稱旁加 🔗）＋測試；3～4 檔、約 50 行。

# 加分候選（第 8 輪）

## J6 · 兩種找法都找到同一組合 → 「雙重確認」標記
因為原始需求是**判斷是不是同一筆資金**，所以頂尖做法會順便做**多個掃描同時成立時加權（confluence）**；目前的成果**沒有**——找法1、找法2 的結果互不知道。
- 參考：TradingView Augury Grid 多時框同時成立加分（https://ar.tradingview.com/script/H2REdDlY-Augury-Grid-Multi-Timeframe-Scanner/）；Confluence Hunter（https://de.tradingview.com/script/uCbNwVse-Confluence-Hunter/）。注意：兩種找法用同一套漏斗，可能只是重複計算同一證據。
- 預估：api.py（讀同一天另一找法的已存結果比對）＋finder.js 徽章＋測試；3 檔、約 50 行。

## J7 · N 卡片每檔成員列出當天新聞題材（「為什麼在動」）（✅ 已完成 bonus-10）
因為原始需求是**找資金背後的動機**，所以頂尖做法會順便做**每檔股票旁邊直接標它的新聞題材／催化劑**；目前的成果**只有部分**——卡片只在「同一則標題同時提到兩檔」時才列新聞，大部分組合沒有任何動機線索；但新聞資料其實已經記了每個關鍵字提到哪些代號（news_day 的 codes）。
- 參考：Finviz screener 的 News 欄與 Daily Digest（每檔一行最新相關新聞，https://finviz.com/blog/news-column-and-stock-flags-now-in-the-finviz-screener/）；Benzinga「Why Is It Moving」（https://www.benzinga.com/apis/cloud-product/bz-why-is-it-moving/）
- 預估：finder.py（code → 近 3 天提到它的題材關鍵字，取前 3）＋api.py 傳入＋finder.js（成員 tooltip 與卡片一行「📰 題材」）＋測試；4 檔、約 80 行。

# 加分候選（第 9 輪）

## K1 · 歷史頁頂端一行「今天 N 找到 X 群（🔁 Y 群持續）」，點了跳到 N（✅ 已完成 bonus-12）
因為原始需求是**每天先看資金往哪裡、是不是同一筆錢**，所以頂尖做法會順便做**一條常駐的摘要列（float bar／bottom bar）顯示今天偵測到幾個訊號、點了直接進明細**；目前的成果**沒有**——N 在頁面中段，要捲下去才知道今天有沒有找到東西。
- 參考：moomoo Market Monitor float bar「displays unusual activity … the latest unusual activity data」、bottom bar「total number of bullish and bearish signals detected」（https://www.moomoo.com/us/support/topic3_70、https://moomoo.com/us/manual/topic-14-84）
- 預估：history.js（讀 bonus-08 已有的 stored_only 找法1 結果＋找法2 結果，標題列加一行，點了捲到 N）；1～2 檔、約 50 行。

## K2 · N 卡片展開的 K 檢視補上 🔁 天數與 📰 題材（✅ 已完成 bonus-11）
因為原始需求是**看動機與持續性**，所以頂尖做法會順便做**明細頁帶著清單上的摘要資訊**；目前的成果**只有部分**——卡片上有，但點開的明細（K 動畫）沒有。
- 參考：Finviz screener → quote 頁帶 News（https://finviz.com/blog/news-column-and-stock-flags-now-in-the-finviz-screener/）
- 預估：finder.js（展開時在明細標題帶入）；1 檔、約 15 行。

# 加分候選（第 10 輪）

## L7 · C 族群輪動改成「捲到才載入」（避開重啟後的冷啟動塞車）（✅ 已完成 bonus-13）
因為原始需求是**整個流程要快（1 分鐘內），而且你抱怨過「跑太久」**，所以頂尖做法會順便做**畫面外的區塊等接近可視範圍才載入（section-level deferral）**；目前的成果**只有部分**——N 已經是捲到才載入，但 C 一開頁就算最重的冷啟動（今晚量到 C 一次 94 秒，還拖慢同時間的 N／K）；A／B／K 才是開頁要看的。
- 參考：Front-End Checklist「Use Intersection Observer for Section-Level Deferral」「import on visibility」（https://frontendchecklist.io/rules/performance/lazy-loading、https://frontendchecklist.io/rules/performance/import-on-visibility）；「Don't lazy-load above-the-fold content」（https://corewebvitals.io/pagespeed/fix-defer-offscreen-images-lighthouse）
- 預估：history.js（loadRotation 改成 C 進入可視範圍前 600px 才發；換日期時若 C 不在畫面就標記待載）；1 檔、約 40 行。

## L2 · 即時頁收盤後也顯示「💡 資金連動」摘要，點了開歷史頁 N
因為原始需求是**每天先看資金往哪裡**，所以頂尖做法會順便做**常駐的訊號摘要列**；目前的成果**只有部分**——bonus-12 只在歷史頁；收盤後停在即時頁看不到。
- 參考：moomoo Market Monitor float bar（https://www.moomoo.com/us/support/topic3_70）
- 預估：app.js（收盤後讀最新已存日期的 stored_only 結果，工具列一顆按鈕）；1～2 檔、約 40 行。

# 加分候選（第 11 輪）

## M1 · 審查夜班所有程式改動並修正確認的缺陷（✅ 已完成 bonus-14）
因為原始需求是**N／K 的結果要可信（拿來判斷是不是同一筆資金）**，所以頂尖做法會順便做**合併前逐項 code review，找出邊界條件與整合錯誤**；目前的成果**只有部分**——每項都有單元測試，但今晚的實測已抓到兩個測試沒抓到的整合錯誤（api.py 同名函式遮住匯入、黏性面板下的捲動位移），表示還可能有類似問題。
- 參考：Google Engineering Practices「What to look for in a code review」（https://google.github.io/eng-practices/review/reviewer/looking-for.html）
- 預估：審查 4b489b8..HEAD 的 src／static，只修有具體失敗情境的問題；每個修正獨立 commit，≤ 5 檔、≤ 300 行。

# 加分候選（第 12 輪，預先調研）

## N1 · N 卡片標「誰先動」：組合內的領先者與落後分鐘數（✖ 實驗後放棄：真實資料沒有可量到的領先）
因為原始需求是**找出同一筆資金怎麼進場（先買哪檔、再帶動哪檔）**，所以頂尖做法會順便做**lead-lag：在幾個位移量上算分時相關，相關最高的位移就是領先時間**；目前的成果**只有部分**——N 只比「日內最高點」的時間差（一個點），沒有用整段分時走勢判斷誰帶頭。
- 參考：Huth & Abergel：流動性高的股票通常領先、lead-lag 隨時段變化（https://www.arxiv.org/pdf/1111.7103）；OFR Working Paper 2015-15 Lead-Lag Correlations（https://www.financialresearch.gov/working-papers/files/OFRwp-2015-15_Lead-Lag-Correlations.pdf）
- 預估：finder.py（pair_check 多算位移 −3…+3 根 5 分 K 的相關，取最大）＋describe＋finder.js 一行「領先：A 早 10 分」＋測試；3～4 檔、約 100 行。

# 加分候選（第 13 輪）

## O1 · K 的分時相關也排除鎖漲停的平線（與 N 一致）
因為原始需求是**用分時相關判斷是否共同注資（你也同意「漲停會破壞分時相關」）**，所以頂尖做法會順便做**計算相關前處理漲跌停限制造成的失真**；目前的成果**只有部分**——N 的分時相關已排除鎖漲停的平線，但 K 的分時相關矩陣沒有，同一對股票在 K、N 可能得到不同的 R，最強的漲停股在 K 反而看起來「不連動」。
- 參考：台灣股市研究「limit observations distort the true relationship among stock returns … price-limit effect has a stronger impact on the correlation than the trading volume」（https://ah.lib.nccu.edu.tw/bitstream/140.119/73973/1/S0927538X98000110.pdf）；Kim & Rhee (1997) 價格限制的延遲價格發現（https://www.bayes.citystgeorges.ac.uk/__data/assets/pdf_file/0007/29077/Price_Limits.pdf）
- 預估：linkage.py returns() 或 api.py linkage_payload（每個交易日依當日漲停價把兩端都在漲停的 5 分 K 報酬設為空）＋測試；2～3 檔、約 40 行。

## 第 14 輪調研

## P1 · N 卡片「🏦 法人」：群組三大法人合計買賣超
因為原始需求是 **多維度分析金錢為什麼這樣流動，尋找資金＝背後的動機**，所以頂尖做法會順便做 **把「誰在買」（三大法人買賣超）掛在共同注資的組合上**；目前的成果 **沒有**：N 卡片只有成交值（💰）、新聞（📰）、持續（🔁），沒有資金是誰的。
- 參考：Goodinfo! 台灣股市資訊網「三大法人買賣超—依產業／族群」；CMoney／財報狗 籌碼面「法人連買」；TWSE T86 三大法人買賣超日報（資料本專案已入庫 inst_day）。
- 預估：describe 或 api with_history 依 store.inst_net 取當天，合計淨買（張與億元＝股數×收盤／1e8）＋買超檔數／賣超檔數；finder.js 卡片多一行；當天法人資料未出 → 不顯示。改 api.py／finder.py／finder.js／2 個測試檔，約 60 行。不新增套件、不新表。

## P2 · K 右側個股走勢疊上大盤／OTC 漲幅線
因為原始需求是 **觀察類股／個股相對大盤強弱（使用者要求在 K 放大盤、OTC 方便比較）**，所以頂尖做法會順便做 **個股分時圖可疊加指數線（Compare）**；目前的成果 **只有部分**：K 時間軸有大盤／OTC 列，但點個股後右側走勢圖只有個股自己。
- 參考：TradingView「Compare or Add Symbol」；Yahoo 奇摩股市個股走勢「加權指數」對照。
- 預估：intradaychart.js 加一條淡色 % 線（benchmarks 已在 K payload），race.js 傳入；約 40 行、2–3 檔。

> P1 前提修正（實作前查證）：N 卡片 facts 已有「法人 ±X 億／萬」（finder.js:86，describe 的 inst_net，單位是**股數**），所以 P1 原句「目前沒有」不成立 → 作廢，改提 P1b。

## P1b · N 卡片法人改成「張＋金額」，並在回應時補上（盤後才公布的法人不再永遠空白）
因為原始需求是 **尋找資金＝背後的動機（誰在買）**，所以頂尖做法會順便做 **用投資人習慣的單位（張、億元）並且資料一公布就反映**；目前的成果 **只有部分**：(1) 卡片顯示「法人 +1.2 億」實際是 1.2 億**股**，容易被讀成 1.2 億元；(2) inst_net 在搜尋當下算好存進 finder_result，盤後 15:00 前就搜（或背景預算在法人公布前跑）→ 這天的法人永遠是空的。
- 參考：Goodinfo!／CMoney 三大法人買賣超皆以「張」與「金額（億）」呈現；TWSE T86 公布時間約 15:00–16:30。
- 預估：api with_history 依 store.inst_net 重新附上（不存）；finder.py 加 inst_summary（張、億元＝股×收盤、買超／賣超檔數）；finder.js facts 改「法人 +3.2 萬張（≈ 12.3 億）」；2 個測試檔。5 檔、約 50 行。

## 第 15 輪調研

## Q1 · N 卡片法人「連買／連賣 N 天」
因為原始需求是 **尋找資金＝背後的動機（是不是有人在持續佈局）**，所以頂尖做法會順便做 **法人連續買超／賣超天數**；目前的成果 **只有部分**：bonus-17 有當天法人張數，看不出是一天的進出還是連續佈局。
- 參考：Goodinfo!「三大法人連續買超天數」排行；CMoney 選股「投信連買 N 日」；Yahoo 股市 法人買賣超「連續買超」欄。
- 預估：finder.py inst_streak（組合合計 inst_net 從當天往回同號的天數，最多回看 20 個有法人的交易日）；api with_history 取 inst_net(近 20 天)；finder.js 法人那格加「連買 3 天」；2 個測試檔。5 檔、約 45 行。

## Q2 · N 卡片成員 chip 的 tooltip 列出各檔法人張數
因為原始需求是 **看出資金是誰的**，所以頂尖做法會順便做 **組合內逐檔的法人分佈（是一檔被買還是全部被買）**；目前的成果 **只有部分**：只有合計與買超／賣超檔數。
- 參考：Goodinfo! 個股法人買賣超；財報狗 籌碼分佈。
- 預估：finder.js chip 的 title 加「法人 +1,234 張」；1 檔＋測試，約 10 行。

## 第 16 輪調研

## R1 · 審查 bonus-15～19 的改動並修正確認的缺陷（同 M1 的作法）
因為原始需求是 **N／K 給出可信的資金連動判斷**，所以頂尖做法會順便做 **每批改動由不看實作過程的人做 code review**；目前的成果 **只有部分**：bonus-01～13 已審（bonus-14），15～19 動到 K 的相關計算、K 的圖表、N 的回應組裝（with_history 多兩段查詢），尚未獨立審查。
- 參考：Google eng-practices「What to look for in a code review」；SmartBear／Cisco code review study（每次審 200–400 行效果最好）。
- 預估：獨立審查員只讀 `git diff 017426e~5..017426e`，只修確認的缺陷；≤ 5 檔。

## R2 · K 時間軸成員列 tooltip 加當天法人張數
因為原始需求是 **看出資金是誰的**，所以頂尖做法會順便做 **在連動檢視裡也看到逐檔法人**；目前的成果 **只有部分**：B 有族群法人淨買超、N 卡片有逐檔法人，但 K（點族群後的連動檢視）沒有。
- 參考：Goodinfo! 個股法人買賣超；CMoney 族群法人進出。
- 預估：linkage_payload members 加 inst_net（store.inst_net([d])），race.js 列 title 加「法人 ±N 張」；api.py／race.js／2 測試檔，約 20 行。

## 第 17 輪調研

## S1 · N 卡片「法人占成交」：法人淨買賣金額 ÷ 組合成交值
因為原始需求是 **尋找資金＝背後的動機（是法人在推，還是法人以外的資金）**，所以頂尖做法會順便做 **法人買賣超占成交量／成交值的比例**；目前的成果 **只有部分**：卡片有法人 ≈ 億元（bonus-17）和成交值（💰 bonus-02），但沒算兩者的比，使用者要自己心算「1.6 億 ÷ 40 億」。
- 參考：Goodinfo!「法人買賣超佔成交量比重」；CMoney 籌碼「法人持股／成交比重」；玩股網 主力進出占比。
- 預估：finder.js instText 旁加「占成交 4%」（amount_100m ÷ turnover_100m，兩者都在卡片資料裡），附 title 說明；1 檔＋測試，約 12 行。

## S2 · 法人附加資料的 API 層測試（with_history 的 🏦／連買路徑）
因為原始需求是 **資金動機的判斷要可信**，所以頂尖做法會順便做 **回應組裝路徑的整合測試**；目前的成果 **只有部分**：inst_summary／inst_streak 有單元測試，但 api with_history 把它們串起來的地方沒有（bonus-20 的審查就是在這層抓到「缺日被接成連續」）。
- 參考：Google Testing Blog「Test Sizes」(medium tests)；Martin Fowler「Practical Test Pyramid」。
- 預估：tests/test_finder.py 加一個用 tmp store 的端點測試（存一個 finder 結果＋三天法人、中間缺一天 → 連買只算到缺日前），約 40 行、1 檔。

## 第 18 輪調研

## T1 · N 卡片法人拆成「外資／投信／自營」
因為原始需求是 **尋找資金＝背後的動機**，所以頂尖做法會順便做 **把法人拆成外資、投信、自營商**（三者動機不同：投信常是作帳／主題佈局，外資看大盤權值，自營多短線避險）；目前的成果 **只有部分**：卡片只有三大法人合計。資料其實已入庫（inst_daily 的 foreign_net／trust_net／dealer_net 欄位，10/22 華經：外資 +1,991 張、投信 0、自營 +19 張），只是沒讀出來。
- 參考：TWSE T86「三大法人買賣超日報」分欄；CMoney「投信連買」「外資連買」選股；Goodinfo! 法人買賣超（外資／投信／自營分欄）。
- 預估：store 加 inst_split(day)（讀既有欄位，不改表）；finder.py 加 inst_split_summary（組合合計三欄，張）；api with_history 附上；finder.js 在法人那格的 tooltip／下一行顯示「外資 +2,000／投信 0／自營 +19 張」；測試。5 檔、約 60 行。

## 第 19 輪調研

## U1 · 點 N 卡片展開的 K 檢視標題列也帶上 🏦 法人
因為原始需求是 **看資金連動的同時看出資金是誰的**，所以頂尖做法會順便做 **明細檢視保留摘要卡的關鍵欄位**；目前的成果 **只有部分**：bonus-11 讓展開的 K 檢視帶上卡片的 🔁 與 📰，但 bonus-17～24 新增的 🏦 法人那行沒有帶過去，看動畫時要捲回卡片才看得到。
- 參考：Finviz screener → quote 頁帶入同一組欄位；moomoo 個股卡展開後保留資金區塊。
- 預估：finder.js 展開時複製 `.fd-inst` 到標題列下方；finder.test.js 無法測 DOM（只能瀏覽器驗證），約 4 行、1 檔。

## U2 · B 族群排行的「法人」欄 tooltip 拆外資／投信／自營
因為原始需求是 **多維度分析金錢為什麼這樣流動**，所以頂尖做法會順便做 **族群層級也能看出是哪一類法人**；目前的成果 **只有部分**：B 的法人欄只有三大法人合計（N 卡片已拆）。
- 參考：Goodinfo!「三大法人買賣超—依產業」分欄；TWSE T86。
- 預估：metrics.py 的族群資金流多算三欄（要動 flows 快取與版本）、history.js 欄位 title；3–4 檔、約 50 行。

## 第 20 輪調研

## V1 · 融資融券（散戶槓桿資金）當動機證據
因為原始需求是 **尋找資金＝背後的動機**，所以頂尖做法會順便做 **法人之外也看散戶融資增減**；目前的成果 **沒有**。
- 參考：TWSE MI_MARGN 融資融券彙總；Goodinfo!「資券變化」。
- 判斷：要新資料源＋新資料表（= DB migration，圍欄禁止）→ 不做，寫進 result.md「需要你決定」。

## V2 · N 篩選 chip 加「🏦 法人買超／賣超」
因為原始需求是 **快速找出有特定資金在推的連動組合**，所以頂尖做法會順便做 **依資金來源篩選結果**；目前的成果 **只有部分**：chip 只能依分類／種類篩，不能「只看法人買超的組合」。
- 參考：Finviz screener「Institutional Transactions」篩選；Goodinfo! 選股「法人買超」條件。
- 預估：finder.js 的 filterOptions／matchesFilter 加兩個 key（inst+／inst−，依 g.inst.lots 正負；兩種找法都適用），不重算；CSV 沿用同一篩選；finder.test.js。2 檔、約 25 行。

## 第 21 輪調研

## W1 · 審查 bonus-21～25、11b、24b 的改動並修正確認的缺陷
因為原始需求是 **N／K 給出可信的資金判斷**，所以頂尖做法會順便做 **每批改動做獨立審查**；目前的成果 **只有部分**：15～19 已審（bonus-20 抓到漲停價 bug），21～25 動了 K payload、store 新查詢、with_history 第三段查詢與卡片排版，尚未審。
- 參考：Google eng-practices；SmartBear code review study（200–400 行一批）。
- 預估：審查員只讀 `git diff c374cff~2..8eadbee`，只修確認缺陷；≤ 5 檔。

## W2 · N 卡片「投信連買 N 天」（只看投信）
因為原始需求是 **尋找資金＝背後的動機**，所以頂尖做法會順便做 **投信連買**（台股最常用的「主題／作帳佈局」訊號，比三大法人合計更有指向性）；目前的成果 **只有部分**：bonus-19 是三大法人合計的連買，bonus-24 有當天投信張數，沒有投信自己的連續天數。
- 參考：CMoney 選股「投信連買 3 日」；Goodinfo!「投信連續買超」排行；財報狗 投信動向。
- 預估：store.inst_split 改成可吃多天（續 bonus-24）；with_history 依 trust 欄算連續天數（沿用 inst_streak 的邏輯）；卡片 🏦 行加「投信連買 N 天」；測試。4–5 檔、約 40 行。
