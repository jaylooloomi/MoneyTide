| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| C1 | N 結果一鍵存成自訂族群 | 6 | 6 | 3 | 2 | 6.0 | Requirement is finding and tracking new combinations; uses existing /api/groups, but writes to user's custom groups. |
| C2 | N 結果匯出 CSV | 4 | 3 | 2 | 1 | 6.0 | Repeats the B/C/D CSV pattern in one panel; low value for the goal, very low blast. |
| C4 | N 卡片可排序 | 3 | 3 | 2 | 1 | 4.5 | Panel already has group/kind filters; sorting is a convenience, not a requirement gap. |
| C3 | 卡片顯示連動趨勢（短窗 R vs 20 日 R） | 6 | 4 | 4 | 2 | 3.0 | Directly tests whether co-investment linkage is current, but needs rolling-R logic in finder.py plus tests. |
| C5 | N 卡片加群組成交值總和 | 4 | 3 | 2 | 2 | 3.0 | Adds money-size context to motive search; cited screener volume columns are generic, not a clear gap. |
| C6 | K 時間軸標出同時爆量時間點 | 5 | 4 | 4 | 3 | 1.7 | Ties to "same money entering at same time," but touches the animated K payload and renderer. |

TOP: C1 (6.0)
