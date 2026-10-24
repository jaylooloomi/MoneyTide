| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| F1 | 背景預算最近 5 個交易日 | 6 | 6 | 2 | 3 | 6.0 | Requirement is the whole search under 1 min; cites cache-warmer and post-close snapshot practice (maverick-mcp, Barchart). Limited to one file (api.py), ~15 lines, but extra background load at startup. |
| F2 | N 卡片 20 日迷你走勢（群組累積 vs 大盤） | 5 | 4 | 5 | 4 | 1.0 | Ties to capital-motive persistence, with sourced sparkline precedents (TradingView, Google Sheets). Not requested by the user, 3-4 files, and computing 20-day group paths adds per-search cost against the 1-min goal. |

TOP: F1 (6.0)
