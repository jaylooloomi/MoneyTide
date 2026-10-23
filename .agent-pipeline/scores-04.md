| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| C2 | N 結果匯出 CSV | 5 | 3 | 2 | 2 | 3.8 | requirement needs repeatable condition comparison; B/C/D already export CSV, so the pattern is established and the change is small |
| C4 | N 卡片可排序 | 3 | 2 | 2 | 2 | 1.5 | results are usually a handful of cards per day, so sorting adds little; default order change touches existing behaviour |
| C3 | N 卡片連動趨勢（短窗 R vs 20 日 R） | 5 | 3 | 5 | 3 | 1.0 | rolling correlation supports "still co-invested", but the trend label is an interpretive addition and needs describe/JS/test changes |
| C6 | K 動畫標出同時爆量時間點 | 6 | 4 | 6 | 5 | 0.8 | directly tests the "same money entering at the same time" idea, but touches the central K payload and race.js rendering |

TOP: C2 (3.8)
