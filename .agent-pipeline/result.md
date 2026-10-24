# Night Shift Result（2026-10-25）

## 收尾
| 項目 | 狀態 | commit | 備註 |
|---|---|---|---|
| 檢核：SQLite 鎖（WAL／busy_timeout） | 已符合 | — | 已開 WAL、連線 timeout 30 秒，寫入有 Python 鎖排隊 |
| 檢核：背景回算重複觸發 | 已符合 | — | 伺服器以（日期、找法、條件鍵）登記執行中任務，F5 或切回來會等同一個任務 |
| 檢核：中斷時的半成品 | 已符合 | — | N 結果整天算完才寫入；1 分 K 最後一次寫入；中斷就沒有那筆，下次重算 |
| 檢核：右欄 sticky 捲動 | 已符合 | 9b37b8d | max-height: calc(100vh - 220px)＋獨立捲動 |
| 檢核：當沖平均分母與四捨五入 | 已修 | 3983a39、854f4f7 | 分母＝有資料的成員；平均先四捨五入到 0.1% 再比 50%，🔥 行顯示平均 |
| 檢核：git 狀態 | 已符合 | — | data/（含 -wal、-shm）、__pycache__ 都在 .gitignore，git 沒追蹤任何 sqlite／log |
| 給其他 agent 的說明（3 處修正） | 已完成 | 0e9c079 | docs/agent-brief.md；另寫明「跌停一字線沒有排除」 |
| 追加：🔥 隔日沖組合也要找出來（隔日好空） | 已完成 | 6cd611e | N 篩選「🔥 隔日沖」；盤後報告最上方「🔥 隔日沖警示」＋前幾天 🔥 組合的隔天表現；複製文字也有。08/04 實測：21 組 🔥；前 4 天 40 組、86 檔次隔天開盤 +5.82%、收盤 +6.70%、開高走低只有 15%——那段時間是強勢多頭，資料不支持「隔天好空」，要多累積日子再看 |
| 追加：study.md 整理 | 已完成 | 85d49cb | docs/study.md；逐點對照程式現況（扣指數已是估計 β 殘差、外盤估計其實是 CLV 不是 BVC） |
| 追加：大神做法實驗（分支 night-shift/methods-2026-10-25） | 已完成 | 2f57c35 | research/REPORT.md：罕見度加權建議採用（同爆量隨機出現率 40%、法人同向 51% 被高估）；lead-lag 峰值與 DTW（AUC 0.87）可當新證據；PCA 只去大盤；聚類不能直接取代；BVC 與 CLV 結論一致 |
| 追加：痛點實驗（分支 night-shift/study-2026-10-25） | 已完成 | 5b7c0fa | research/REPORT.md：①組數起伏跟大盤無關，門檻很敏感；每天依隨機配對 99.5 分位定門檻（0.29～0.48）稍穩；②偽陽性不是瓶頸（同日跨產業隨機 0.09%；BH 5% 切點 R≈0.17，0.4 已很保守）；③程式本來就估 β（中位 0.96、p10 0.23、p90 1.84），比 β=1 乾淨；另發現 5 分 K 下高點差 8 分＝5 分 |
| 自我審查（審查代理看今晚全部改動） | 已修 6 項 | a5cf67a | ①報告換日期時晚到的回應會畫回前一天 ②隔天統計的快取鍵用最新一天的分類，最新一天沒新聞族群時統計全空 ③主力連續買超在當天未入庫時跳過昨天 ④存檔超過 400 交易日時 500 ⑤隔天統計讀全部結果大欄位與整天全部股票（849→298 ms）⑥🔥 天數合併少算 |
| 資料：用預設條件把 N 補算到 60 天（07/29～10/22，分 K 快取，0 錯誤） | 已完成 | — | 只存進 data/（不進 git）。隔天統計樣本 12→60 天：🔥 396 組隔天收 +0.63%（扣大盤 −0.21%）、盤中 −0.51%、開高走低 58%；其他 394 組收 +1.74%（+0.61%）、開高走低 51%；🔥 突然湧入 8 組 16 檔次 盤中 −2.42%、開高走低 88%、收 −0.82% |
| 研究追加：證據能不能預測後續（study 分支 exp5，21756a6） | 已完成 | 21756a6 | 60 天、793 組：證據 ✓≤1 的組合 1／3／5 天後扣大盤 +1.40%／+3.00%／+3.90%（信賴區間不含 0），✓≥4 的約 0；🔥 在每個時間點都落後其他組合。解讀：證據衡量「同步得多整齊」，整齊同步像拉抬高潮、延續性差。限制：多頭期、同日組合不獨立 |
| 研究追加：報告名單事後驗證（study 分支 exp6，5c7b315） | 已完成 | 5c7b315 | 60 天：補漲候選 5 天後扣大盤 +0.74%（組合本身 +2.22%）——沒有明顯補漲，報告說明已改寫；高點錯開但走勢一樣 +1.77%。另：exp5 前後半段都是「證據越少後續越強」，✓≥4 只出現在有 1 分 K 的最近 30 天（混淆因素已寫進報告說明） |
| 問題：分類有沒有集團／概念股／轉投資 | 已回答＋做成加分項 08 | 31f9237、d0ae4ae | 概念股原本就有；集團（轉投資／董監）新增為分類 |

## 加分項（每行一個，可獨立 revert）
| # | 名稱 | Score | 參考來源（競品 / 專案 / 文章） | 做了什麼 | 驗證指令 | 測試狀態 | 否決的替代作法 |
|---|---|---|---|---|---|---|---|
| 01 | 籌碼集中度 | 7.5（scores-01.md） | HiStock「主力進出」、CMoney／Goodinfo「籌碼集中度」（前 15 大券商買賣超 ÷ 成交量） | 從已存的分點算（前 15 大買超＋前 15 大賣超）÷ 成交量，資訊卡分點區與盤後報告每組顯示；空的分點頁不算 0%。動到 evidence.py、api.py、history.js、report.js。10/22：華經 +17.5%、驊宏資 +15.6%、鈦昇 −22.8% | `.venv/Scripts/python -m pytest -q tests/test_evidence.py`；`node --test tests/js/report.test.js` | ✅ pytest 284、node 119；瀏覽器確認卡片與報告 | ① 放進 🧾 證據計分（會改動證據強判定，Blast 大）② 用全部分點加總（我們只存前 15 名，算不出） |
| 02 | 主力成本線 | 4.5（scores-01.md） | HiStock 分點頁「均價」欄；XQ／CMoney「主力成本」指標 | 資訊卡分點區加一行：前 5 大買超分點均價（依買超張數加權）vs 收盤，標「帳上獲利／套牢」。動到 evidence.py、api.py、history.js。華經 10/22：54.43 vs 55 → +1.0% | `.venv/Scripts/python -m pytest -q tests/test_evidence.py` | ✅ pytest 285、node 119；瀏覽器確認卡片 | ① 累積多日持股成本（要長期分點序列，只有近期快照）② 用全部 15 名均價（後段分點買超小，雜訊大） |
| 03 | 出貨警示（消失的組合） | 3.3（scores-01.md） | Wyckoff 派發（distribution）判讀：爆量下跌 | 跨天追蹤裡消失的組合，當天成員過半「下跌且量比 ≥ 2」→「消失・疑似出貨（爆量收黑）」，否則「消失・不再同步」；新增 /api/history/quotes（漲跌＋5 日量比）。動到 api.py、report.js、app.css。08/04：43 組消失中 1 組疑似出貨 | `node --test tests/js/report.test.js`；`.venv/Scripts/python -m pytest -q tests/test_money_flow.py` | ✅ pytest 286、node 120；瀏覽器確認追蹤表 | ① 看隔天跌幅（報告日之後的資料不一定有）② 用分點賣超判斷（消失組合多半沒抓分點） |
| 04 | 主力連續買超 | 4.0（scores-02.md） | HiStock「主力進出」、CMoney「主力連續買超」排行 | 資訊卡分點區的前 5 大買超分點旁標「連買 N 天」（往回最多 10 個交易日，只用已存的分點；沒存的日子中斷計數）。動到 evidence.py、api.py、history.js。2492 10/22：元大、宏遠 連買 2 天 | `.venv/Scripts/python -m pytest -q tests/test_evidence.py` | ✅ pytest 287、node 120；瀏覽器用頁面模組確認卡片 HTML | ① 沒存的日子即時去 HiStock 抓（會吃每日 300 頁上限）② 用賣超名單算連賣（卡片放不下，先做買方） |
| 05 | 補漲候選（同群落後股） | 2.0（scores-02.md） | Moskowitz & Grinblatt (1999) "Do Industries Explain Momentum?"；Hou (2007) 產業內資訊擴散 | 盤後報告每組一行「同族群未跟上（分類：群組）」：從組合最小的已知分類（含過半成員、≤ 40 檔）中挑今天漲不到組合平均一半的股票，成交值大的先列，可點開資訊卡。動到 finder.py、api.py、report.js。08/04：46 組中 32 組有名單，例如記憶體族群的群聯、威剛 | `.venv/Scripts/python -m pytest -q tests/test_finder.py`；`node --test tests/js/report.test.js` | ✅ pytest 288、node 121；瀏覽器確認報告 | ① 用官方產業（太大，只會列出台積電這類權值股）② 排序用漲幅最低（會列出逆勢下跌、不像補漲的股票） |
| 06 | 報告複製文字加入新欄位 | 21.0（scores-03.md） | 盤後籌碼日報類產品（如 CMoney 盤後籌碼日報）文字版與網頁版一致的慣例 | 「複製成文字」每組加上籌碼集中度、同族群未跟上；消失的組合分成「消失・疑似出貨」與「消失」兩行。只動 report.js。08/04 實測文字 7,818 字，含 5 組集中度、32 組補漲候選、疑似出貨一行 | `node --test tests/js/report.test.js` | ✅ node 122；瀏覽器攔截剪貼簿確認 | ① 輸出 Markdown 表格（貼到聊天室會變亂碼）② 另開下載 .txt（多一個按鈕，使用者沒要求） |
| 07 | 外資分點 vs 官方外資 | 3.0（scores-03.md） | 台灣籌碼分析常見的「外資分點 vs 外資買賣超」比對（HiStock、CMoney 籌碼 K 線） | 資訊卡分點區加一行：分點名單（前 15 大買超／賣超）裡外資券商的合計 vs 證交所／櫃買公布的外資買賣超，方向相反時標「方向相反」。動到 evidence.py、api.py、history.js。10/22：2468 +2,021 vs +1,991、2492 −8,608 vs −10,106（同向） | `.venv/Scripts/python -m pytest -q tests/test_evidence.py` | ✅ pytest 289、node 122；瀏覽器用頁面模組確認卡片 HTML | ① 放進 🧾 證據（只有前 15 名，會漏算）② 用券商代號對照表（HiStock 只給名稱） |
| 08 | 集團當成一種分類（2 片） | 2.5（scores-04.md） | XQ 全球贏家、CMoney 的「集團股」類股；MoneyDJ 轉投資資料 | 片1：伺服器把轉投資／董監串起來的集團做成分組（「XX集團」，203 個），B 區新增「集團」按鈕，網址 #…/group 可直接開。片2：N 找法1 的分類可勾「集團」，預設不勾（避免預先算好的結果全部失效）。動到 api.py、history/api.py、finder.py、index.html、history.js、finder.js（分兩片，各 ≤ 5 檔） | `.venv/Scripts/python -m pytest -q tests/test_relations.py`；`node --test tests/js/finder.test.js` | ✅ pytest 291、node 123；瀏覽器確認 B 區集團排行與 N 勾選 | ① 預設就勾集團（每天預先算好的 N 結果都會變成另一把快取鍵）② 用持股 ≥ 50% 的子公司關係（太嚴，大多數集團會被拆散） |
| 09 | 當沖比與平常比較 | 2.3（scores-03.md） | 異常量分析（相對自身歷史，Campbell, Grossman & Wang 1993 的量訊息觀念） | N 卡片 🔥 行每檔加「（平常 X%）」＝前 20 個交易日平均，今天 ≥ 2 倍標紅；🔥 判定仍是 50%。動到 api.py、linkage.py、finder.js。10/22：華經 61.2%（平常 60%，本來就常被當沖）、耀登 60.2%（平常 38%） | `.venv/Scripts/python -m pytest -q tests/test_money_flow.py`；`node --test tests/js/finder.test.js` | ✅ pytest 291、node 124；瀏覽器確認 N 卡片 | ① 改成用 z 分數判定 🔥（會改使用者定的 50% 規則）② 用 60 日平均（上櫃只回補 60 天，前段沒資料） |
| 10 | 隔天表現統計（所有已存日子，🔥 vs 其他） | 3.0（scores-05.md） | MacKinlay (1997) 事件研究；Alphalens 依分組比較 forward returns | 新 /api/history/next-day：掃描同條件下所有已存的 N 結果（兩種找法合併），🔥 與其他組合分開統計成員隔天開盤跳空、收盤（含扣大盤）、開高走低、收黑比例；盤後報告 🔥 區顯示。動到 store.py、linkage.py、api.py、report.js。實測 10 天：🔥 81 組隔天開盤 +4.26%、收盤 +3.82%（扣大盤 +0.39%）、開高走低 42%；其他 129 組 收盤 +4.75%（扣大盤 +1.78%）、開高走低 31% | `.venv/Scripts/python -m pytest -q tests/test_money_flow.py`；`node --test tests/js/report.test.js` | ✅ pytest 292、node 127；瀏覽器確認報告 | ① 在前端逐日抓 quotes（10 天要 20 次請求）② 把「證據強」也分一類（證據計算在前端，伺服器端要重寫一份，先不做） |
| 11 | 證據項目的「隨機也會出現」比例 | 10.5（scores-06.md） | 基準率／−log p 權重觀念；本專案 research/m5_weights.py 實測（10,557 對隨機配對） | 🧾 清單（K 交集、N 卡片 tooltip）每項附「隨機配對約 X% 也會出現」：扣指數 <1%、隨機 10%、同爆量 40%、同分鐘 5%、同漲跌 6%、籌碼 51%；只顯示，✓ 計數與證據強判定不變。只動 evidence.js | `node --test tests/js/evidence.test.js` | ✅ node 128；瀏覽器確認 N 卡片 tooltip | ① 直接改成加權計分（改判定，需使用者決定）② 每天即時重算基準率（每天要多跑上萬對配對，太慢） |
| 12 | 昨天的組合今天表現 | 4.2（scores-07.md） | MacKinlay (1997) 單一事件異常報酬；盤後日報的「昨日強勢股追蹤」 | 跨天追蹤表加「今天漲跌」欄：昨天就有的組合，成員今天平均漲跌（括號＝扣大盤）。只動 report.js、app.css。10/22：晶技＋台嘉碩 −5.78%（−3.97%）、百容＋晟鈦 −4.69%（疑似出貨） | `node --test tests/js/report.test.js` | ✅ node 129；瀏覽器確認追蹤表 | ① 新開一張「昨日追蹤」表（與跨天追蹤重複）② 用開盤到收盤（隔日沖才需要，已在 🔥 區） |
| — | 效能修正：當沖比只讀成員成交量 | — | — | 加分項 09 的「平常當沖比」讓每次讀 N 結果都載入 21 天全部日資料，盤後報告同時 10 個請求要 47～54 秒；改用 store.volumes 只查成員成交量，10 個並發 3.5 秒。動到 store.py、linkage.py（e0b451b） | `.venv/Scripts/python -m pytest -q` | ✅ pytest 292 | — |
| 13 | 互相關峰值落點（誰先動） | 2.7（scores-07.md） | Bacry et al. (2015) lead-lag；本專案 research/m2（N 組合 77% 峰值在 0 分） | minute_evidence 多回傳 peak_lag（−5～+5 分）；K 🔗 交集「同分鐘」說明加「峰值在同一分鐘（像同時下單）」或「峰值錯開 k 分：X 先動」；配對順序反過來時自動翻正負。只顯示，✓ 判定不變。動到 evidence.py、evidence.js、race.js。10/22 華經＋驊宏資：峰值 0 分 | `.venv/Scripts/python -m pytest -q tests/test_evidence.py`；`node --test tests/js/race.test.js tests/js/evidence.test.js` | ✅ pytest 293、node 131；API 確認 | ① 改用峰值落點判定「同分鐘」（改判定）② 標出群組的領頭股（實驗顯示同一對隔天領頭股不固定，會誤導） |
| 14 | 高點差門檻依分 K 解析度說清楚 | 3.0（scores-08.md） | 本專案 research/exp1（5 分 K 下 ≤ 8 與 ≤ 5 結果相同） | 「條件」高點差說明、5 分 K 卡片提示、agent-brief.md 各補一句：5 分 K 的日子高點時間只落在 5 的倍數，≤ 8 實際等於 ≤ 5。動到 finder.js、agent-brief.md | `node --test tests/js/finder.test.js` | ✅ node 132 | ① 依解析度自動換算門檻（改判定）② 隱藏 5 分 K 日子的高點差欄（資訊變少） |
| 15 | 交接文件補上研究結論 | 3.0（scores-08.md） | 本專案兩個研究分支的 REPORT.md | docs/study.md 每節末加「實驗結果」，指向 night-shift/study-* 與 night-shift/methods-* | — | 文件 | ① 把 REPORT.md 整份搬進主分支（研究分支各自保留比較清楚） |
| 16 | 高點錯開但走勢一樣（可能分批推進） | 2.0（scores-09.md） | Sakoe & Chiba (1978) DTW；本專案 research/m2 | N 計算時，對「只因高點差太大被刷掉」的候選配對算分時形狀距離（DTW，帶寬 6），≤ 2.5 的前 10 對存進結果 shape_pairs；盤後報告加一區列出。N 群組與證據不變；FINDER_VERSION 升到 10（舊結果會重算）。動到 evidence.py、finder.py、report.js、app.css。離線 53 天找出 143 對（國巨＋千如、陽明＋萬海、茂矽＋漢磊、台塑＋台化…）；上線 10/21：光頡＋金山電（高點差 9 分）、國巨＋立隆電（28 分）等 5 對 | `.venv/Scripts/python -m pytest -q tests/test_evidence.py`；`node --test tests/js/report.test.js` | ✅ pytest 294、node 133；瀏覽器確認 10/21 報告 | ① 直接把這些配對併進 N 群組（改判定）② 對全部前 150 檔配對都算（上線要多抓分 K） |
| 17 | 🔥 再分「突然湧入」與「平常就這樣」 | 2.2（scores-10.md） | 異常量事件研究（MacKinlay 1997；Campbell, Grossman & Wang 1993） | /api/history/next-day 把 🔥 拆成 surge（成員當沖比平均 ≥ 平常 2 倍）與 habitual；盤後報告 🔥 區多兩行。統計也採用條件相同、版本 ≥ 9 的舊結果（v10 只多欄位）。動到 linkage.py、store.py、api.py、report.js。11 天：87 組 🔥 中 85 組是平常就這樣（隔天收 +3.67%、開高走低 44%）；突然湧入只有 2 組 4 檔次，隔天全數開高走低、收 −0.63%（扣大盤 −1.42%）——方向符合「隔日好空」，但樣本太少 | `.venv/Scripts/python -m pytest -q tests/test_money_flow.py tests/test_finder.py`；`node --test tests/js/report.test.js` | ✅ pytest 296、node 135；API 確認 | ① 用 z 分數分類（20 天樣本太短）② 只採同版本結果（版本一升樣本就歸零） |
| 18 | N 卡片也顯示籌碼集中度 | 3.8（scores-11.md） | HiStock「主力進出」、CMoney／Goodinfo「籌碼集中度」；加分項 01 | N 卡片在 🏦 分點行下多一行「🏦 籌碼集中度 甲 +17.5%、乙 −3.0%」（伺服器已算好 g.concentration）。只動 finder.js | `node --test tests/js/finder.test.js` | ✅ node 136 | ① 放進卡片標題列（太擠）② 算群組平均（成員有正有負時平均會誤導） |
| 19 | 證據多寡的隔天表現（重估 D1） | 7.0（scores-12.md） | MacKinlay (1997) 事件研究；Alphalens 依因子分組的 forward returns | /api/history/next-day 依已存群組的 5 項伺服器端證據 ✓ 數分成 ≥4／2～3／≤1 三組各自統計隔天；盤後報告 🔥 區顯示。沒資料的項目不算 ✓。動到 linkage.py、api.py、report.js。60 天：✓≥4 86 組 隔天扣大盤 −0.02%、開高走低 60%；✓2～3 622 組 +0.06%、54%；✓≤1 82 組 +1.48%、50%——證據越多隔天越弱 | `.venv/Scripts/python -m pytest -q tests/test_money_flow.py`；`node --test tests/js/report.test.js` | ✅ pytest 298、node 137；API 確認 | ① 用前端完整 10 項證據（伺服器端要重寫一份，留待使用者決定是否改計分）② 只看證據強（樣本太小） |

## 判斷不值得做
- C2 群組外盤估計 / 1.7 / 要動 N 結果、卡片與報告，Blast 大，單檔版已在 K 走勢資訊欄
- C5 誰先動（lead-lag）/ 0.4 / 1 分 K 雜訊大、計算量高、要動 N 計算路徑
- D1 隔天表現回測 / 1.7 / 當時 N 結果只部分存在；補算到 60 天後重估為 Q1（7.0），已做成加分項 19
- D2 今日資金網路圖 / 0.8 / 只改呈現方式，不幫判斷有無計畫
- G2 隔日沖個股排行 / 0.5 / 使用者說的「這種」是指 🔥 組合，不是全部個股
- H2 DTW 形狀相似度 / 1.3 / 不計入證據，只多一列資訊，改動 race.js 與 payload 成本高
- N2 「高點錯開但走勢一樣」跨天出現次數 / 0.8 / 只有內部概念、沒有外部來源

## 需要你決定的事
- 補漲候選：60 天回測沒有補漲效果（5 天後只跑贏大盤 0.74%）。要保留（當觀察用）、拿掉，或改成別的定義，請你決定
- 證據與隔天表現：60 天樣本顯示「證據越多、隔天越弱」（✓≥4 扣大盤 −0.02%、開高走低 60%；✓≤1 +1.48%、50%）。證據目前衡量的是「同步得多整齊」，不是「隔天會不會續漲」；要不要把這個解讀寫進動機判讀，或用它調整證據強的用途，請你決定
- 隔日沖：60 天樣本顯示 🔥 組合隔天扣大盤 −0.21%、開高走低 58%（其他組合 +0.61%、51%）；「突然湧入」16 檔次盤中 −2.42%、開高走低 88%。要不要把「突然湧入」做成獨立的篩選或警示，請你決定
- [存疑] 證據清單其他門檻要不要放進「條件」——今晚實驗（methods/m5）顯示「同爆量」隨機出現率 40%、「籌碼／法人同向」51%，等權計票會高估它們；要不要調嚴或降權，請你決定
- [存疑] 資料庫容量保留期限（1 分 K 一年約 1～2 GB）
- 開工時工作區乾淨，沒有 stash

## 統計
- 進行中
