| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| V2 | 熱力圖標示漲停／跌停個股 | 3 | 3 | 2 | 2 | 2.3 | Requirement is 看集體上漲; sources are TW news reports on 漲停 counts, not heatmap implementations, so Impact capped at 3. Small change in transform.js. |
| V1 | 盤中族群轉強提醒（桌面通知） | 3 | 2 | 5 | 3 | 0.4 | Not in requirement (看盤 only); TradingView alerts are per-price, not sector-level. Needs threshold logic, permissions, dedupe, touches snapshot loop. |

TOP: V2 (2.3)
