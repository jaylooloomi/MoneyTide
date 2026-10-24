# Night Shift Result（2026-10-25）

## 收尾
| 項目 | 狀態 | commit | 備註 |
|---|---|---|---|
| （無明確收尾項目） | — | — | 存疑兩項見「需要你決定的事」 |

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

## 判斷不值得做
- C2 群組外盤估計 / 1.7 / 要動 N 結果、卡片與報告，Blast 大，單檔版已在 K 走勢資訊欄
- C5 誰先動（lead-lag）/ 0.4 / 1 分 K 雜訊大、計算量高、要動 N 計算路徑
- D1 隔天表現回測 / 1.7 / 需要 60 天的 N 結果，目前只部分存在，成本高
- D2 今日資金網路圖 / 0.8 / 只改呈現方式，不幫判斷有無計畫
- E2 當沖比異常倍數 / 2.3 / 先處理使用者半夜追加的檢核項目，時間允許再做

## 需要你決定的事
- [存疑] 證據清單其他門檻要不要放進「條件」
- [存疑] 資料庫容量保留期限（1 分 K 一年約 1～2 GB）
- 開工時工作區乾淨，沒有 stash

## 統計
- 進行中
