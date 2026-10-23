| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| P2 | K 個股走勢疊上大盤／OTC 漲幅線 | 5 | 4 | 2 | 2 | 5.0 | Requirement asks for 大盤/OTC comparison (scope §3); cites TradingView Compare and Yahoo. Overlay is not 扣掉大盤 (§4), so no rejection. Additive, about 40 lines. |
| P1 | N 卡片「🏦 法人」群組三大法人買賣超 | 7 | 5 | 3 | 3 | 3.9 | Requirement asks who drives the money (動機); cites Goodinfo, CMoney, TWSE T86. Uses existing inst_day, no new dep or table. Touches api.py, finder.py, finder.js and tests, so Blast is higher. |

TOP: P2 (5.0)
