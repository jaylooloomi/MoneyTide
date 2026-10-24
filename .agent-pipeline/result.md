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
| 追加：痛點實驗（分支 night-shift/study-2026-10-25） | 進行中 | e99a3f8 | 痛點 2：錯日配對偽陽性 0.4%、同日跨產業隨機 0.09% vs 候選 2.81%；痛點 3：β 中位 0.96（p10 0.23、p90 1.84），估計 β 比 β=1 乾淨；痛點 1 門檻掃描跑中 |
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

## 判斷不值得做
- C2 群組外盤估計 / 1.7 / 要動 N 結果、卡片與報告，Blast 大，單檔版已在 K 走勢資訊欄
- C5 誰先動（lead-lag）/ 0.4 / 1 分 K 雜訊大、計算量高、要動 N 計算路徑
- D1 隔天表現回測 / 1.7 / 需要 60 天的 N 結果，目前只部分存在，成本高
- D2 今日資金網路圖 / 0.8 / 只改呈現方式，不幫判斷有無計畫
- G2 隔日沖個股排行 / 0.5 / 使用者說的「這種」是指 🔥 組合，不是全部個股
- H2 DTW 形狀相似度 / 1.3 / 不計入證據，只多一列資訊，改動 race.js 與 payload 成本高

## 需要你決定的事
- [存疑] 證據清單其他門檻要不要放進「條件」——今晚實驗（methods/m5）顯示「同爆量」隨機出現率 40%、「籌碼／法人同向」51%，等權計票會高估它們；要不要調嚴或降權，請你決定
- [存疑] 資料庫容量保留期限（1 分 K 一年約 1～2 GB）
- 開工時工作區乾淨，沒有 stash

## 統計
- 進行中
