| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| S2 | 法人附加資料的 API 層測試（with_history 的 🏦／連買路徑） | 3 | 3 | 2 | 1 | 4.5 | Tests guard the trust of N's motive evidence; bonus-20 already showed this layer has bugs. Cited source is generic test-practice, not a finder-specific practice. Test-only change. Confirm the tmp-store test never reaches the network. |
| S1 | N 卡片「法人占成交」：法人淨買賣金額 ÷ 組合成交值 | 5 | 3 | 2 | 2 | 3.8 | Directly serves "is institutional money driving it" and the ratio is a standard metric (Goodinfo/CMoney cited). Users currently do the division by hand. Small change to one file, but it touches the card's fact display. |

TOP: S2 (4.5)
