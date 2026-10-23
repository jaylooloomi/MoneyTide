| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| C5 | N 卡片加群組總成交值與平均漲幅 | 6 | 5 | 3 | 2 | 5.0 | Requirement is 找資金背後的動機; cited screener volume/market-cap columns support it, but the Twelve Data source is about correlation heatmaps, so the citation is weak. |
| C2 | N 結果匯出 CSV | 4 | 3 | 2 | 2 | 3.0 | Multi-dimension, repeatable comparison; TradingView CSV export is cited; reuses the CSV_EXPORTS table. |
| C6 | K 時間軸標出同時爆量時點 | 7 | 5 | 4 | 3 | 2.9 | Directly tests 同一筆資金同時進場; XQ 大戶買賣力 is cited; touches K payload and race.js. |
| C4 | N 卡片可排序 | 3 | 3 | 2 | 2 | 2.3 | UX convenience; does not advance the funding-motive goal; cited TradingView sorting is generic. |
| C3 | N 卡片顯示連動趨勢（短窗 vs 20 日 R） | 6 | 5 | 5 | 3 | 2.0 | Tests whether co-funding linkage is still current; rolling-correlation sources cited; touches finder.py, finder.js, and tests. |

TOP: C5 (5.0)
