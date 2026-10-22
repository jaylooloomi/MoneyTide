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

## 判斷不值得做
- C3 相對成交量（量能倍數）— 1.6（scores-01.md）：要新增指標並改 B/C，效益對影響範圍不划算
- C4 族群連續強勢天數 — 1.5：只有新聞評論支持，無產品實作參考
- C2 1日／5日／20日期間切換 — 1.4：改 day_stocks API 與 A/B，影響範圍大

## 需要你決定的事
- 即時頁的產業指標切換（等權平均漲幅／≥5% 佔比用在即時熱力圖的哪裡）：你當時沒選套用方式就改提歷史需求，所以本夜沒做；歷史頁 B 已有這些指標。要不要做、做成哪種（產業總覽模式／只換標題排序／只加矩陣欄），請決定。
- 概念股資料來自 Yahoo 股市（第三方網站，與 HiStock 相同屬「個人本機使用」）。

## 統計
