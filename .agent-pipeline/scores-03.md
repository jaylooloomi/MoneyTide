| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| C7 | 找法2 加成交量門檻（≥300 張） | 8 | 7 | 3 | 3 | 6.2 | Directly cuts false "資金組合" from illiquid stocks; the 10/22 勝昱+全景軟體 example (0.1 億) is a concrete miss; ≤40 lines. |
| C4 | N 卡片可排序 | 4 | 4 | 3 | 2 | 2.7 | Helps scan large result sets; sourced to screener column sorting; additive UI, ≤80 lines. |
| C2 | N 結果匯出 CSV | 4 | 3 | 3 | 2 | 2.0 | Supports repeated condition comparison outside the app; reuses the CSV_EXPORTS table; not requested by user. |
| C3 | N 卡片連動趨勢（短窗 R vs 20 日 R） | 7 | 4 | 6 | 3 | 1.6 | Addresses "still co-injected now" directly; needs statistics change in finder.py plus tests across 4 files. |
| C6 | K 時間軸標出同時爆量時點 | 5 | 3 | 5 | 3 | 1.0 | Useful visual check for same-time entry; touches K payload and race.js rendering, up to 150 lines. |

TOP: C7 (6.2)
