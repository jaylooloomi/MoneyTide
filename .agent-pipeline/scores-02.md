| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| D4 | 主力連續買超 | 6 | 4 | 3 | 2 | 4.0 | Requirement tracks money across days and 資金證據; 分點 data exists per stock/day, but the since-10/22 snapshot is short, so the 5-day count depends on backfill. Adds only to 資訊卡. |
| D3 | 補漲候選（同群落後股） | 4 | 3 | 3 | 2 | 2.0 | Cited diffusion papers support the "where money flows next" angle, but the "same group, not yet moved" rule is a loose fit for separating planned from coincidental moves. |
| D1 | 證據有沒有用：隔天表現回測 | 6 | 5 | 6 | 3 | 1.7 | Validating evidence strength directly serves the goal and cites MacKinlay and Alphalens. Needs a 60-day N-result history that is only partly stored, so the cost is high. |
| D2 | 今日資金網路圖 | 4 | 3 | 5 | 3 | 0.8 | Mantegna is a real source, but a network graph changes presentation rather than the planned-vs-coincidence judgment. ECharts is already loaded, so no new dependency. |

TOP: D4 (4.0)
