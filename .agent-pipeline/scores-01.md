| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| C1 | 等大小（Mono）格子選項 | 6 | 5 | 2 | 2 | 7.5 | Requirement is group-strength heatmap; top tools (TradingView Mono) offer size-free view; concept mode is dominated by TSMC and small caps are hidden. |
| C5 | 歷史頁點個股資訊卡＋20日小圖 | 6 | 6 | 4 | 2 | 4.5 | Requirement asks which stocks rose together; D list only links out, and TradingView/Finviz offer click-through; reuses existing card. |
| C3 | 相對成交量（量能倍數） | 6 | 4 | 5 | 3 | 1.6 | Requirement is spotting capital-inflow groups; TradingView colors by relative volume; needs new metric and B/C changes. |
| C4 | 族群連續強勢天數 | 4 | 3 | 4 | 2 | 1.5 | Rotation analysis by persistence is supported only by news commentary, not product implementations; new rotation logic plus B column. |
| C2 | 1日／5日／20日期間切換 | 7 | 4 | 5 | 4 | 1.4 | Multi-period views serve retrospection; Finviz cited, but sources are a 2010 blog and a third-party app; changes day_stocks API signature and A/B. |

TOP: C1 (7.5)
