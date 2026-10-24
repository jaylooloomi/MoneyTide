| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| C1 | 籌碼集中度（分點） | 6 | 5 | 2 | 2 | 7.5 | Requirement is "same batch of money"; branch_day already holds the top-15 data, and display-only keeps blast low. |
| C3 | 主力成本線 | 3 | 3 | 2 | 1 | 4.5 | Average cost is a trader heuristic, weakly tied to proving coordinated buying; cited sources are retail sites; avg price already stored. |
| C4 | 出貨警示（消失的組合） | 5 | 4 | 3 | 2 | 3.3 | Separates 出貨 from 不再同步 on the tracking table, which the requirement covers; needs per-member volume ratio; Wyckoff citation is generic. |
| C2 | 群組外盤估計 | 5 | 4 | 4 | 3 | 1.7 | Extends existing single-stock BVC to groups (Easley et al. cited); touches N payload, cards and report. |
| C5 | 誰先動（領先落後） | 5 | 2 | 6 | 4 | 0.4 | Lead-lag is valid and cited, but noisy on 1-min bars, high compute cost, and touches the N computation path. |

TOP: C1 (7.5)
