# Night Shift Result（2026-10-25）

## 收尾
| 項目 | 狀態 | commit | 備註 |
|---|---|---|---|
| （無明確收尾項目） | — | — | 存疑兩項見「需要你決定的事」 |

## 加分項（每行一個，可獨立 revert）
| # | 名稱 | Score | 參考來源（競品 / 專案 / 文章） | 做了什麼 | 驗證指令 | 測試狀態 | 否決的替代作法 |
|---|---|---|---|---|---|---|---|
| 01 | 籌碼集中度 | 7.5（scores-01.md） | HiStock「主力進出」、CMoney／Goodinfo「籌碼集中度」（前 15 大券商買賣超 ÷ 成交量） | 從已存的分點算（前 15 大買超＋前 15 大賣超）÷ 成交量，資訊卡分點區與盤後報告每組顯示；空的分點頁不算 0%。動到 evidence.py、api.py、history.js、report.js。10/22：華經 +17.5%、驊宏資 +15.6%、鈦昇 −22.8% | `.venv/Scripts/python -m pytest -q tests/test_evidence.py`；`node --test tests/js/report.test.js` | ✅ pytest 284、node 119；瀏覽器確認卡片與報告 | ① 放進 🧾 證據計分（會改動證據強判定，Blast 大）② 用全部分點加總（我們只存前 15 名，算不出） |
| 02 | 主力成本線 | 4.5（scores-01.md） | HiStock 分點頁「均價」欄；XQ／CMoney「主力成本」指標 | 資訊卡分點區加一行：前 5 大買超分點均價（依買超張數加權）vs 收盤，標「帳上獲利／套牢」。動到 evidence.py、api.py、history.js。華經 10/22：54.43 vs 55 → +1.0% | `.venv/Scripts/python -m pytest -q tests/test_evidence.py` | ✅ pytest 285、node 119；瀏覽器確認卡片 | ① 累積多日持股成本（要長期分點序列，只有近期快照）② 用全部 15 名均價（後段分點買超小，雜訊大） |

## 判斷不值得做
-

## 需要你決定的事
- [存疑] 證據清單其他門檻要不要放進「條件」
- [存疑] 資料庫容量保留期限（1 分 K 一年約 1～2 GB）
- 開工時工作區乾淨，沒有 stash

## 統計
- 進行中
