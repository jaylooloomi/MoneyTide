| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| 1 | AH1 啟動後背景預熱歷史快取 | 4 | 5 | 3 | 3 | 2.2 | Requirement is browsing past days' strong groups, and the 4–7 s cold start hits that directly; sources are generic Redis/Aerospike cache-warming posts, not heatmap apps; background thread touches HistoryCollector and SQLite timing. |

TOP: 1 (2.2)
