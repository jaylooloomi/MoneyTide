# Night Shift Result（2026-10-24）

## 收尾
| 項目 | 狀態 | commit | 備註 |
|---|---|---|---|
| K 動畫最上方固定大盤／OTC（夜班中你新增） | ✅ 完成 | 5b733d3 | 不編號、不參與排名；1 分 K（舊日 5 分 K），對齊官方指數、收在官方收盤；10/22 加權 −1.81%、櫃買 −3.47% |
| 縣市點擊顯示公司明細 | 跳過 [存疑] | — | 版面 A／B 你還沒選（scope-reviewer 複核後改為存疑） |

## 加分項（每行一個，可獨立 revert）
| # | 名稱 | Score | 參考來源（競品 / 專案 / 文章） | 做了什麼 | 驗證指令 | 測試狀態 | 否決的替代作法 |
|---|---|---|---|---|---|---|---|
| 01 | N 卡片「存成自訂族群」 | 6.0（scores-01.md） | TradingView Import watchlist；Chartink／Screener.in 的 screener→watchlist 擴充 | N 每張卡片右上「＋族群」：跳出名稱（預設「N1022 華經+驊宏資」，可改），用既有 /api/groups 建立並加入成員，按鈕變「✓ 已存」；不會同時展開卡片。改 finder.js、app.css、finder.test.js（49 行） | `npm test`（78 ✅）；瀏覽器實測存成「ZZ夜班測試」→ API 查到 2 檔 → 已刪除還原；續做：按鈕不再折行 | ✅ | ① 後端新增批次端點（不必要，既有 API 足夠）② 自動存不問名稱（會塞滿族群清單） |
| 02 | N 卡片「資金規模」 | 5.0（scores-02.md） | TradingView screener volume／market cap 欄；Twelve Data 熱力圖文章 | 卡片多一行「💰 成交值 18.72 億（占全市場 0.18%）　平均漲幅 +9.98%」。改 finder.py（money_size、FINDER_VERSION→3）、finder.js、app.css、兩邊測試。順便看出找法2 有的組合只有 0.1 億（小錢） | `uv run pytest`（240 ✅）、`npm test`（78 ✅）；10/22 瀏覽器實測 | ✅ | ① 前端自己加總（拿不到全市場總成交值，占比算不出）② 只顯示成交值不顯示占比（不同日子無法比較） |
| 03 | 找法2 成交量門檻（≥300 張） | 6.2（scores-03.md） | TradingView screener volume 篩選；你為找法1 指定的「至少>300張」 | 找法2 的「條件」多「成交量 ≥（張）」，預設 300；候選池先濾掉小量股。10/22：3 組 0.1～0.75 億的小量配對消失，只留華新科+金山電（260 億）。改 finder.py、finder.js、兩邊測試 | `uv run pytest`（240 ✅）、`npm test`（78 ✅）；10/22 實跑 | ✅ | ① 改用成交值門檻（張數跟找法1 一致，比較好懂）② 跟找法1 共用同一個欄位（兩種找法要能分開調） |
| 04 | N 結果匯出 CSV | 3.8（scores-04.md） | TradingView screener 下載 .csv | N 標題列「CSV」：匯出目前顯示的卡片（依篩選按鈕），一列一檔成分股＋群組指標＋當天條件；檔名含找法、日期、篩選。改 finder.js、finder.test.js | `npm test`（79 ✅）；瀏覽器擷取檔案：10/22 細產業 → 表頭＋6 列 | ✅ | ① 加進 history.js 的 CSV_EXPORTS（N 在那之後才掛上，按鈕掛不到）② 一列一群組（成員擠在一格，Excel 不好篩） |
| 05 | N 漏斗統計 | 7.0（scores-06.md） | TradingView screener standard/custom levels；Chaikin preset screens | 統計列下多一行漏斗。10/22 找法1：「進入分時比對 197 對 → 刷掉：分時相關不足 143、開盤即高點（假同步） 46、高點時間差太大 2 → 三關都過 6 對 → 6 群」——**分時相關 ≥0.5 是最嚴的一關**。改 finder.py（confirm 彙總、FINDER_VERSION→4）、finder.js、app.css、兩邊測試 | `uv run pytest`（240 ✅）、`npm test`（80 ✅）；10/22 瀏覽器實測 | ✅ | ① 前端自己數（拿不到被刷掉的配對）② 只顯示通過數（看不出哪個條件最嚴） |
| 06 | N 條件預設組 嚴格／標準／寬鬆 | 2.0（scores-07.md） | TradingView screener standard/custom levels；fffinstill、Chaikin presets | 「條件」最前面一排：嚴格（0.85／0.6／5 分）、標準（0.8／0.5／8 分）、寬鬆（0.7／0.35／15 分）；只改日相關、分時相關、高點差，其他設定不動；手動改值就顯示「自訂」。10/22 找法1：標準 6 群 → 寬鬆 38 群。改 finder.js、app.css、finder.test.js | `npm test`（81 ✅）；瀏覽器實測切寬鬆再切回標準 | ✅ | ① 預設組也改振幅／成交量／分類（會蓋掉你自己設的條件）② 存成後端設定（不必要，偏好本來就存在瀏覽器） |
| 07 | 背景預算最近 5 個交易日 | 6.0（scores-08.md） | maverick-mcp cache warmer；Barchart 收盤後排程掃描；StocksCafe 只預算會用到的 | 背景預算從「最新一天」改成「最近 5 個交易日、兩種找法、預設門檻」；已存過的跳過，真的算了才休息 5 秒。重啟後 03:42:30 開始、03:43:35 補齊 10/16～10/22 共 10 份（10/22 已有，跳過）。改 api.py | `uv run pytest`（240 ✅）；唯讀查 finder_result：2/10 → 10/10 | ✅ | ① 預算全部歷史日（StocksCafe 的教訓：算一堆用不到的）② 把使用者自訂門檻也預算（伺服器不知道瀏覽器裡的設定） |
| 08 | B 排行標出 N 找到共同注資的族群 | 3.3（scores-10.md） | Futu Market Monitor（watchlist 上標 unusual activity）；Acuity Market Reader | finder API 加 stored_only（只讀已存結果；沒有就回空，0.19 秒，絕不觸發計算）；B 族群名稱前加 🔗，滑鼠移上去看哪幾檔與日R／分時R／高點差。10/22 官方產業：資訊服務業（華經、驊宏資）、電子零組件業（興勤、金山電）。改 api.py、history.js、finder.js、兩邊測試 | `uv run pytest`（241 ✅）、`npm test`（82 ✅）；瀏覽器實測只發出一個 stored_only 請求 | ✅ | ① B 自己觸發搜尋（會在瀏覽 B 時偷跑幾秒到幾十秒）② 連找法2 也標（找法2 沒有來源分類，對不到 B 的列） |
| 09 | N 卡片「近 5 天出現 N 次」 | 2.9（scores-11.md） | stock-correlation skill（rolling correlation）；Futu Market Monitor | 卡片標題旁「🔁 近 5 天第 N 次」或「🆕 首次」（滑鼠看是哪幾天）。10/22：華經+驊宏資 10/16、10/19 也出現（第 3 次）；雷科+鈦昇、凱美+金山電各第 2 次。只讀前 4 天已存結果，成員重疊過半算同一組合。改 finder.py、api.py、finder.js、app.css、兩邊測試 | `uv run pytest`（242 ✅）、`npm test`（82 ✅）；10/22 瀏覽器實測 | ✅ | ① 存進快取（前幾天的結果晚點才算好，徽章會過期）② 用完全相同成員比對（多一兩檔就對不上，太嚴） |
| 10 | N 卡片「📰 新聞題材」 | 3.7（scores-13.md） | Finviz screener News 欄／Daily Digest；Benzinga Why Is It Moving | 卡片多一行「📰 題材：被動元件（2）」，成員 tooltip 列各自題材；近 3 個新聞日裡提到這檔的關鍵字，回傳時附上（不改快取），過濾「音量🔊」這類解析殘渣。實測抓到 api.py 裡同名的 news_themes 路由遮住匯入（500），已改名並補端點測試。新聞多半只點名大型股，小型股配對常沒有題材。改 finder.py、api.py、finder.js、app.css、兩邊測試 | `uv run pytest`（244 ✅）、`npm test`（82 ✅）；10/22 瀏覽器實測 | ✅ | ① 算進快取（新聞會補抓，存進去會過期）② 每檔都列一長串題材（卡片會爆；只取前 3） |
| 11 | 卡片明細帶入 🔁／📰 | 7.5（scores-15.md） | Finviz screener → quote 頁帶 News | 點卡片展開的 K 檢視標題列，帶上卡片的「🔁 近 5 天第 N 次」與「📰 題材」（直接取卡片上已畫好的內容，不動卡片程式）。改 finder.js、app.css | `npm test`（82 ✅）；瀏覽器實測展開 10/22 卡片 | ✅ | ① 抽共用函式重寫卡片（會動到 bonus-09／10 的程式）② 明細再打一次 API 取資料（資料已在卡片上） |
| 12 | 工具列「💡 資金連動」摘要 | 3.3（scores-16.md） | moomoo Market Monitor float bar／bottom bar | 歷史頁工具列（狀態燈前）「💡 資金連動：找法1 6 群（🔁 3）／找法2 1 群」，點了捲到 N（避開黏在上方的 A／B）；只讀已存結果，沒存過的日子（如 9/01）不顯示。改 history.js、finder.js、app.css、finder.test.js | `npm test`（83 ✅）；瀏覽器實測 10/22 文字、點擊後 N 位於可視區頂端 8px、9/01 隱藏 | ✅ | ① 放進黏在頂端的 A／B 面板（會擠到熱力圖）② 共用 bonus-08 的讀取（會改到 bonus-08 的程式） |
| 13 | C 族群輪動捲到才載入 | 7.0（scores-17.md） | Front-End Checklist section-level deferral／import on visibility；Core Web Vitals：別延後首屏內容 | 所有觸發 C 的地方都經過 loadRotation：開頁先等 3 秒讓 K／N／J 撐開版面，之後 C 在可視範圍 300px 內才真的發請求，否則記著、捲近時才載（換日期時 C 不在畫面也一樣）。改 history.js | `npm test`（83 ✅）；瀏覽器實測：開頁 0 個 rotation 請求 → 捲到 C 觸發後 36 列 | ✅ | ① 改後端讓 rotation 變快（冷啟動慢的根因在同時太多冷計算，不在 rotation 演算法）② C 改成按鈕才載入（多一個動作） |

## 判斷不值得做
- C4 N 卡片可排序（1.5，scores-04.md）：每天篩完通常只剩幾張卡，排序幫助不大，還會改到現有預設順序。
- C3 N 卡片連動趨勢（短窗 R vs 20 日 R）（1.0）：「趨勢」是詮釋性標籤，要改 describe／前端／測試多處，效益不明確。
- C6 K 動畫標出同時爆量時間點（0.8）：要改 K 的核心 payload 與動畫渲染，影響範圍大。
- 第 2 輪 TOP: none（scores-05.md）：D2 PTT 討論熱度（1.5，只有標題、沒有回文數，量到的是關注度不是資金動機）；D1 從一檔股票找同夥（0.9，新分頁＋API＋約 200 行，太重）。
- F2 N 卡片 20 日迷你走勢（1.0，scores-08.md）：不是你要求的，多檔改動，而且每次搜尋多算 20 日路徑，跟 1 分鐘目標相衝。
- 第 5 輪 TOP: none（scores-09.md）：G1 盤中錄製順便記成交量（0.6）：要改每次輪詢的錄製器、資料格式和所有讀取端，累計量歸零／漏輪詢的處理風險高；目前有 Yahoo 補。
- 第 7 輪剩下 TOP: none（scores-12.md）：I2 K 動畫標出 N 找到的成員（1.8）：只涵蓋找法1 且在前 8 大的成員，又要動剛大改過的 race.js。
- 第 8 輪剩下 TOP: none（scores-14.md）：J6 兩種找法雙重確認（1.0）：同一套漏斗跑兩次，等於重複計算同一證據；10/22 兩邊沒有任何相同組合，標記幾乎不會出現。

## 需要你決定的事
- 縣市點擊看公司明細：請在方案 A（右側清單往下鑽成公司明細，我推薦）與方案 B（列內展開前 10＋看全部）之間選一個，我就做。
- [存疑] 扣掉大盤的驗證、資金動機產出形式（A/B/C）：未動。

## 統計
- （收工時填）
