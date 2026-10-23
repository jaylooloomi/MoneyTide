# 目標：完成「多維度看金錢流動」五個子項目（④→①→②→③→⑤）

## 背景
專案 D:\git\open-market：台股上市櫃產業熱力圖，只看盤、不下單。
- 後端 FastAPI（uv、Python 3.12），歷史資料存在 data/history.sqlite。
- 前端是單頁 ECharts（static/js）。
- 目前已有：即時頁、歷史頁 A～F 面板、三種分組（官方產業／概念股／自訂族群）。

目的是用多種維度分析「錢為什麼這樣流動」。五個子項目依下面的順序完成，每項都要可以獨立使用。

## 子項目與已定案的決定

### ④ 大盤＋櫃買時間軸（規格已定）
- 完全依照 docs/superpowers/specs/2026-10-23-index-timeline-design.md 實作，不重新設計。
- 驗收：
  - 歷史頁底部的 G 面板有加權、櫃買兩張日 K，疊 MA5／20／60，下面有成交值，並標出強勢日。
  - 點某一天，熱力圖 A、B～F、日期選單、網址 hash 都換到那天，K 線上的直線標示跟著移動。

### ① 漲停家數佔比、≥5% 漲幅佔比
- 定義：
  - 漲停佔比 = 漲幅 ≥ 9.5% 的家數 ÷ 族群家數。
  - ≥5% 佔比 = 漲幅 ≥ 5% 的家數 ÷ 族群家數。
  - 都只算普通股，與現有 LIMIT_PCT、strong_ratio 的定義一致。
- 即時頁：
  - 產業矩陣加「漲停%」「≥5%」兩欄，可排序，上色方式和歷史頁 B 一致。
  - 熱力圖的產業標題可切換顯示「市值加權漲幅／≥5% 佔比／漲停佔比」，用頂列下拉切換，偏好要保存。
- 歷史頁 B 加「漲停%」欄，CSV 匯出也要帶這欄。
- 驗收：
  - 這些數字與 /api/history/groups 同日計算的結果一致。
  - 在自訂、概念分組下也正確，同一檔股票在同一族群不重複計數。

### ② 細產業分類
- CMoney、XQ 是付費軟體的自家資料，沒有公開來源，所以不做，也不爬它們。
- 改用櫃買中心「產業價值鏈資訊平台」https://ic.tpex.org.tw 的產業鏈子分類，當作第 4 種分組「細產業」。
  - 一檔股票可以屬於多個子分類。
  - 快取 7 天，做法比照 concepts.py／yahoo_concepts.py。
- 即時頁和歷史頁的分組切換都要加「細產業」。
- 如果該網站無法抓取（需要登入、被擋、結構無法解析）：
  - 停下這項，在報告寫清楚原因與實測證據。
  - 不改抓其他第三方網站。
  - 接著做 ③。
- 驗收：
  - 至少涵蓋 80% 的上市櫃普通股。
  - 歷史頁可以用「細產業」看 B～F。

### ③ 台灣地圖金錢熱力圖
- 公司地址來源：證交所 OpenAPI 的上市公司基本資料，以及櫃買中心 OpenAPI 的上櫃公司基本資料。
- 只用地址字串取「縣市」，例如臺／台要統一。粒度到縣市，不做鄉鎮或地理編碼。
- 地圖：
  - 台灣縣市界線 GeoJSON 放在 static/geo/，來源必須是開放授權（例如 g0v twgeojson），並在 README 註明來源與授權。
  - 用 ECharts 內建的 map 系列畫，不新增 npm 或 pip 套件。
- 呈現：
  - 新增「地圖」分頁或面板，各縣市依「成交值總和」決定顏色深淺，可切換為「市值加權漲幅」。
  - tooltip 顯示家數、成交值、漲跌幅、前 3 大成交值個股。
  - 即時頁顯示今天的資料；歷史頁跟著選中的日期。
- 驗收：
  - 22 縣市都有對應。
  - 地址無法判斷的公司數量要列在畫面註記中。

### ⑤ AI 新聞分析（漲跌前三名為什麼）
- 範圍：
  - 歷史頁某一天，以及即時頁收盤後，各取漲幅前 3、跌幅前 3 的普通股。
  - 排除成交值 < 1 億的股票，避免冷門股雜訊。
- 新聞來源：Google News RSS 搜尋（「股票名稱 代號」，限該日前後 2 天），每檔最多 8 則標題、來源與連結。
- AI 提供者可設定：新增 src/openmarket/ai.py，只用 httpx 呼叫，不新增任何 SDK 套件。
  - 支援兩種格式，用 OPENMARKET_AI_FORMAT 切換：
    - `openai`（預設）：POST {base}/chat/completions，可接 Groq、OpenRouter、NVIDIA NIM、Gemini 的 OpenAI 相容端點等免費服務。
    - `anthropic`：POST {base}/v1/messages（標頭 x-api-key、anthropic-version: 2023-06-01），可接正版 Claude API，或本機的 free-claude-code 代理。
  - 設定全部只從環境變數讀：OPENMARKET_AI_BASE_URL、OPENMARKET_AI_KEY、OPENMARKET_AI_MODEL。金鑰不寫進任何檔案、log 或 API 回應。
  - 預設提供者：從 cheahjs/free-llm-api-resources 清單中挑一家「有持續免費額度、有 OpenAI 相容端點、中文能力足夠」的服務。挑之前先查它目前的額度與條款，把選擇理由寫進 README。
  - 不得複製 free-claude-code 的程式碼（AGPL-3.0），只能把它當獨立程式，透過 HTTP 呼叫。
  - 失敗處理：逾時 30 秒、HTTP 429／5xx 最多重試 2 次，之後在畫面顯示「AI 服務暫時無法使用」，不影響其他功能。
- 輸出：
  - 每檔一段 2～3 句的原因摘要，附引用的新聞連結。
  - 新聞不足時，明確寫「找不到足夠新聞，無法判斷」，不要自行推測。
- 快取：同一天同一檔只問一次，結果存在 data/ 底下的 SQLite 表。
- 沒有設定 OPENMARKET_AI_KEY（或 BASE_URL）時，按鈕停用，並提示要設定哪些環境變數。
- 測試：一律 mock HTTP，不實際呼叫 API。
- 驗收：
  - 有金鑰時，按「分析」約 30 秒內出現 6 檔的摘要與連結。
  - 沒有金鑰時，畫面清楚提示，其他功能都不受影響。

## 每個子項目的做法
1. 先讀相關程式碼，沿用既有模式。
   - 後端：sources/、history/ 的分層。
   - 前端：transform.js 放純函式，history.js、app.js 負責畫面。
   - 狀態物件要宣告在 main() 之前，避免 TDZ 錯誤。
2. ④ 已有規格。①②③⑤ 先各寫一份簡短規格，放在 docs/superpowers/specs/2026-MM-DD-<topic>-design.md，內容照上面的決定，不再詢問。
3. 用測試驅動實作：
   - 解析器用 tests/fixtures 的小樣本，每份 < 300 KB。
   - pytest 只跑不碰網路的測試。
   - 純函式用 node --test。
4. 驗證：
   - uv run pytest -q
   - node --test "tests/js/*.test.js"
   - 用 headless Chrome 實際操作驗收項目，並檢查主控台沒有錯誤。
5. 每個子項目完成後，自我審查一次 diff（競態、快取失效、重複計數、XSS、時區用 Asia/Taipei），修完再 commit。
   - commit 訊息：feat(<子項目>): …
   - 可以拆成多個小 commit。

## 硬性限制
- 只在目前分支 night-shift/2026-10-23（或從它開出的新分支）工作，不 merge／rebase／force，不 push。這個 repo 沒有 remote。
- 絕對不 commit data/ 底下的任何東西（history.sqlite 超過 100 MB）。新的資料表、快取、匯出都放在 data/。
- 不新增 pip 或 npm 套件，不改 pyproject.toml、uv.lock。
- 爬官方網站時，請求間隔至少 3 秒。第三方網站只能用 Google News RSS 與櫃買產業價值鏈平台。
- 不破壞既有功能，既有測試全部要保持通過。

## 完成條件（全部成立才算完成）
- ④①②③⑤ 的驗收項目都通過；② 若無法抓取，要有實測證據並記錄。
- pytest 與 node 測試全部通過，並附上輸出。
- README.md 補上新功能、資料來源與授權、AI 提供者的設定方式（OPENMARKET_AI_FORMAT／BASE_URL／KEY／MODEL，含接 Groq、接正版 Claude、接 free-claude-code 代理三個範例）。
- 最後輸出一份報告，包含：
  - 每個子項目的狀態、commit 清單、驗收結果。
  - 沒做或卡住的項目與原因。
  - `git log --oneline main..HEAD` 和 `git status --short`。
