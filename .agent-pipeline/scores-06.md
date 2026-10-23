| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| E1 | N 漏斗：每關刷掉幾對、最常卡哪關 | 7 | 6 | 3 | 2 | 7.0 | Because the requirement is thresholds that get tuned repeatedly, top screeners show per-filter rejection counts so the user knows which threshold to loosen; pair_check reasons already exist, only the aggregation is missing. Not in section 4, no new dependency. |
| E2 | N 條件預設組：嚴格／標準／寬鬆 一鍵切換 | 5 | 4 | 2 | 3 | 3.3 | Because the requirement is flexible thresholds, top screeners ship presets plus custom; the 條件 form and 恢復預設 already cover most of this, and presets touch the defaults that 恢復預設 relies on. Not in section 4, no new dependency. |

TOP: E1 (7.0)
