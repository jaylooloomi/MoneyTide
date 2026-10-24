| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| Y1 | 收盤後預先計算天數 5 → 20 | 5 | 5 | 2 | 3 | 4.2 | Requirement needs multi-day money-flow evidence; next-day and cross-day stats read only stored N, so a 5-day window starves them. Cited sources (MacKinlay 1997, Alphalens) are generic, so the "top implementations also do Y" link is only partly supported. Change is one constant, but it adds background compute after each close and a 20-day rebuild after each FINDER_VERSION bump. |

TOP: Y1 (4.2)
