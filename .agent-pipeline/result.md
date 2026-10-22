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

## 夜間程式碼審查修正
獨立審查代理檢查 main..HEAD 全部程式變更（XSS、監聽器重複、非同步競態、多族群重複計數、API 邊界），回報 6 項＋1 小項，全部已修：
| 問題 | 修正 commit |
|---|---|
| 歷史頁快速切換日期／分組時，A/B/C/D 舊回應覆蓋新資料（含 B 期間欄卡在「…」） | bc9e2a1 |
| 自訂族群編輯後 5／20／60 日快取不失效 | bc9e2a1 |
| D 在自訂／概念分組下重複計數股票 | bc9e2a1 |
| 切換分組後 E 圖保留不存在的族群 | bc9e2a1 |
| 族群名稱「.」「..」使 URL 路徑被正規化、「,」破壞 E 圖查詢 | 24197b3 |
| 即時個股卡片每次輪詢重建，關掉展開中的下拉選單並重抓所屬族群 | 0f5aee4 |

## 判斷不值得做
- C3 相對成交量（量能倍數）— 1.6（scores-01.md）：要新增指標並改 B/C，效益對影響範圍不划算
- C4 族群連續強勢天數 — 1.5：只有新聞評論支持，無產品實作參考
- C2 1日／5日／20日期間切換 — 1.4：改 day_stocks API 與 A/B，影響範圍大
- R1 即時熱力圖切換族群分類 — 1.0（scores-02.md）：要改 transform、即時頁與矩陣，影響範圍大
- S2 族群相對輪動圖（RRG）— 1.3（scores-03.md）：計算與散點尾跡實作量大，C 矩陣已能看每日輪動
- T2 創新高／創新低家數 — 1.0（scores-04.md）：歷史約 242 日不足 52 週，早期數值不完整
- V1 盤中族群轉強桌面通知 — 0.4（scores-06.md）：超出「只看盤」需求、需權限與去重邏輯

## 需要你決定的事
- 即時頁的產業指標切換（等權平均漲幅／≥5% 佔比用在即時熱力圖的哪裡）：你當時沒選套用方式就改提歷史需求，所以本夜沒做；歷史頁 B 已有這些指標。要不要做、做成哪種（產業總覽模式／只換標題排序／只加矩陣欄），請決定。
- 概念股資料來自 Yahoo 股市（第三方網站，與 HiStock 相同屬「個人本機使用」）。

## 統計
