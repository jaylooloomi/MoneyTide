| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| Y1 | N 回應的法人連續天數查詢只抓卡片成員 | 3 | 3 | 2 | 2 | 2.3 | Requirement's 1-min target is already met (0.38 s); cuts ~0.25 s of full-market reads on 3 calls/load, cited "only fetch what you need" is generic, and the change touches shared store query signatures (optional param only). |

TOP: Y1 (2.3)
