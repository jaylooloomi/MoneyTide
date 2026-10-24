| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| G1 | 盤中錄製順便記成交量（tick 聚合成本機 1 分 K） | 5 | 4 | 6 | 6 | 0.6 | Cites PKScreener and Kite forum for tick-to-OHLCV, so it is not forced to 1; gap is real but Yahoo fallback exists. Touches the every-poll recorder, blob format, and all linkage/N readers, and cumulative-volume reset and missed-poll handling add risk. |

TOP: none (all below 2)
