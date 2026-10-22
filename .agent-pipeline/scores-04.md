| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| T1 | 全市場廣度列（上漲／下跌家數、上漲成交值占比） | 5 | 4 | 3 | 2 | 3.3 | Requirement is 集體上漲 judgment; breadth is cited (TradingView, Strike Money). Pure function plus one status-bar row. Drop 漲停/跌停 unless the data has limit flags. |
| T2 | 創新高／創新低家數（52 週） | 4 | 3 | 4 | 3 | 1.0 | Breadth cited (Strike Money, StockCharts). Store holds ~242 days, below the 252 needed for a true 52-week window, so early-day values would be incomplete. Touches metrics, group_stats, and B table. |

TOP: T1 (3.3)
