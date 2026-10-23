# 漲跌原因（AI 新聞分析）— 設計規格

- 日期：2026-10-23
- 狀態：依 docs/goal-prompt.md 的定案實作（子項目 ⑤）
- 目的：補上「為什麼」這個維度，說明當天漲最多、跌最多的股票背後有哪些新聞。

## 1. 範圍

- 對象：歷史頁選中的那一天，或即時頁收盤後（盤中回 409）。即時資料的日期由 `live_quote_day` 決定：開盤前和週末取上一個交易日。
- 漲跌幅各前 3 名的普通股，排除成交值 < 1 億的股票（冷門股雜訊多）。

## 2. 新聞（`sources/google_news.py`）

- Google News RSS 搜尋：`"<名稱>" <代號> after:<日-2> before:<日+3>`，參數 `hl=zh-TW&gl=TW&ceid=TW:zh-Hant`。
- 只保留發布時間在該日 ±2 天（臺北時間）內的新聞，依標題去重，新到舊排序，每檔最多 8 則。
- 只取標題、來源與連結，不抓文章內文。

## 3. AI（`ai.py`）

- 只用 httpx 呼叫，不新增 SDK 套件。設定只從環境變數讀：
  - `OPENMARKET_AI_FORMAT`：
    - `openai`（預設）：`POST {base}/chat/completions`。
    - `anthropic`：`POST {base}/v1/messages`，`anthropic-version: 2026-10-21`（這個版本不送 temperature）。
  - `OPENMARKET_AI_BASE_URL`／`OPENMARKET_AI_KEY`／`OPENMARKET_AI_MODEL`。
- 預設：
  - `openai`：Groq（`https://api.groq.com/openai/v1`，`qwen/qwen3-32b`）。選擇理由：有持續的免費額度、OpenAI 相容、中文能力足夠。
  - `anthropic`：`https://api.anthropic.com`，`claude-opus-5-5`。
- `anthropic` 格式直連 api.anthropic.com 時，加上 server-side refusal fallback（`fallbacks: "default"`）；接本機代理（例如 free-claude-code）時不送，避免代理不認得這個欄位。`stop_reason: "refusal"` 會顯示為「AI 拒絕回答」。
- 回答開頭的 `<think>…</think>` 推理段落一律移除（Qwen3、DeepSeek-R1 等模型會輸出）。
- 逾時 30 秒；429、5xx 或連線錯誤最多重試 2 次（間隔 2、4 秒）；其他 4xx 不重試。錯誤訊息不含金鑰。
- free-claude-code 是 AGPL：只能當獨立程式透過 HTTP 呼叫，不複製它的程式碼。

## 4. 分析流程（`explain.py`）

- system prompt 要求：只根據提供的標題、用繁體中文寫 2～3 句、不給投資建議，只輸出 `{"reason": "…", "sources": [標題編號]}`。資訊不足時 reason 必須是 `INSUFFICIENT`。
- 沒有新聞時不呼叫 AI，直接回「找不到足夠新聞，無法判斷。」。
- `INSUFFICIENT` 也轉成同一句話；回答不是 JSON 時，照原文顯示並附前 3 則標題；引用編號無效時也附前 3 則。
- 同時最多 3 個 AI 請求（新聞搜尋則 6 檔同時進行）。
- 快取：`ai_reason(date, code, reason, links, model, created_at)` 存在 `data/history.sqlite`，同一天同一檔只問一次。失敗不快取，下次再按會重試。

## 5. API

- `GET /api/ai/status`：`{configured, format, model, host}`，不含金鑰。
- `GET /api/ai/reasons?source=history&date=…` 或 `?source=live`：回傳選出的 6 檔和已快取的原因，**不呼叫 AI**。
- `POST /api/ai/reasons?…`：替尚未快取的股票呼叫 AI。
  - 必須帶 `X-OpenMarket-Action: explain` 標頭。自訂標頭會觸發 CORS 預檢，其他網頁就無法替使用者觸發付費呼叫；缺少標頭回 403。
  - 沒有金鑰時回 400，並說明要設定哪些環境變數。

## 6. 前端（`static/js/ainews.js`）

- 歷史頁 I 面板「漲跌原因（AI 新聞分析）」：
  - 跟著選中的日期，自動顯示已快取的結果。
  - 「分析這一天」按鈕送出 POST。沒有金鑰時按鈕停用，並提示要設定的環境變數。
- 即時頁頂列「AI 解讀」按鈕：盤中停用（提示「盤中不分析」），收盤後打開浮動面板。
- 每張卡片：代號、名稱、漲跌幅、產業、成交值、原因（或「尚未分析」、錯誤訊息）、引用的新聞連結（只接受 http/https，新分頁開啟，`rel="noopener noreferrer"`）。所有文字都經過 escape。

## 7. 驗收

- 測試一律 mock HTTP，不實際呼叫 AI：
  - 兩種 API 格式的請求內容、退回 fallback 的情況、refusal。
  - 重試次數、錯誤訊息不含金鑰。
  - RSS 解析、挑選規則、回答解析、快取（失敗不快取、沒新聞不問 AI）。
  - API 的 403／400／404／422。
  - 前端卡片的 escape 與連結過濾。
- headless 實測：用本機假 AI 端點加上真的 Google News，歷史頁 6 檔約 2 秒完成並附連結；換日期再切回來會讀快取；收盤後即時頁的「AI 解讀」可用；沒有金鑰時按鈕停用並顯示提示。
