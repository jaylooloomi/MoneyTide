| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| H1 | 證據項目的「隨機也會出現」比例 | 7 | 6 | 2 | 2 | 10.5 | 依需求「分辨有計畫與巧合」，附基準率只改顯示、不改判定；來源為 Easley 基準率觀念與本專案實測，引用偏籠統；常數需標來源與日期。 |
| H2 | 分時曲線形狀相似度（DTW）當參考資訊 | 5 | 4 | 5 | 3 | 1.3 | 來源充分，但不計入證據、只是 K 的 🔗 交集多一列，對目標助益有限；需逐對計算且改動 race.js 與 payload；若實作用 tslearn/dtaidistance 則為 NEEDS-DEP（須手寫）。 |

TOP: H1 (10.5)
