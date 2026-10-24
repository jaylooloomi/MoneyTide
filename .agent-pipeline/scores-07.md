| # | Candidate | Impact | Urgency | Effort | Blast | Score | Reason |
|---|---|---|---|---|---|---|---|
| J1 | 昨天的組合今天表現（逐組） | 5 | 5 | 3 | 2 | 4.2 | 需求是分辨有計畫的資金與巧合，逐組次日追蹤可驗證判讀；來源 MacKinlay 1997 可引用。但 🔥 次日統計與 5 日追蹤已部分覆蓋，故 Impact 降為 5。只改 report.js 一欄，用既有 API。 |
| J2 | 互相關峰值落點（誰先動） | 6 | 4 | 3 | 3 | 2.7 | 需求是看資金路徑，峰值落點能回答誰先動；來源 Bacry et al. 2015 與 research/m2 可引用。但需改 minute_evidence 回傳格式並連動 evidence.js，影響面較大，且「同分鐘」已能回答部分問題，Urgency 只給 4。 |

TOP: J1 (4.2)
