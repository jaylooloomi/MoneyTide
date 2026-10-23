# 加分候選（第 1 輪）

錨點：scope.md 第 1 節——「多維度分析金錢為什麼這樣流動」；N · 資金連動搜尋（找出共同注資的組合、找可能的新組合，門檻要保留彈性）。

## C1 · N 的結果一鍵存成自訂族群
因為原始需求是**找出「可能的新組合」（找法2 跨族群新組合）並持續觀察資金是否還在**，所以頂尖做法會順便做**把篩選結果直接存成清單（watchlist／自訂族群），之後在其他畫面追蹤**；目前的成果**沒有**——N 找到的組合只能看當天，要追蹤得手動到「管理族群」一檔檔加。
- 參考：TradingView Import watchlist（https://cn.tradingview.com/chart/NIFTY/qNGKMbgU-How-to-import-watchlist-in-TradingView）；Chartink / Screener.in 的「screener → watchlist」擴充（https://chromeboard.com/extension/screener-to-tradingview-mcfligcbhdnbfhkbcpoclgcanimnoiha）
- 預估：finder.js（卡片按鈕）＋既有 /api/groups 端點；≤3 檔、<120 行。

## C2 · N 結果匯出 CSV
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

## C5 · N 卡片加「資金規模」：群組總成交值與平均漲幅
因為原始需求是**找資金（多少錢、往哪去）背後的動機**，所以頂尖做法會順便做**每個組合的成交值總和與漲跌摘要**（熱力圖／screener 的 market-cap、volume 欄）；目前的成果**只有部分**——卡片列成員漲跌，但沒有群組的成交值總和、占全市場比重。
- 參考：Twelve Data 熱力圖相關分析（https://twelvedata.com/news/analyzing-the-correlation-of-u-s-stocks-using-heat-maps）；TradingView screener volume / market cap 欄（https://barbucket.readthedocs.io/en/latest/tv_screener/）
- 預估：finder.py describe＋finder.js＋測試；≤3 檔、<60 行。

## C6 · K 動畫時間軸標出「同時爆量」的時間點
因為原始需求是**看是不是同一筆資金在同一時間進場**，所以頂尖做法會順便做**在走勢上標出量能異常的時間點**（XQ「大戶買賣力」盤中逐筆）；目前的成果**只有部分**——N 卡片寫出同時爆量時間，但 K 動畫上看不到。
- 參考：XQ 全球贏家「大戶買賣力」盤中逐筆指標（https://www.moneyweekly.com.tw/_Article?AID=75294）
- 預估：linkage payload 加每檔爆量時段＋race.js 畫標記；≤4 檔、<150 行。
