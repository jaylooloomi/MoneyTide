# Candidates（2026-10-25 夜，第 13 輪）

錨點：scope.md 第 1 節（分辨有計畫的資金與巧合）；今晚 exp5 的發現：證據越少後續越強、🔥 落後。

## S1 報告的後續統計加上 3 天、5 天
因為原始需求要分辨資金性質，而隔天一天的報酬雜訊很大（exp5 的 1 天區間寬、3／5 天差距才明顯），所以頂尖做法會同時看多個持有期（forward returns at several horizons）；目前的成果**只有部分**（盤後報告只有隔天）。
- 來源：Alphalens 的多持有期 forward returns（1D／5D／10D）；MacKinlay (1997) 事件窗。
- 範圍：next_day_stats 加 horizons（1、3、5 個交易日，扣同期大盤）；/api/history/next-day 回傳；盤後報告 🔥 區與依證據數那幾行改成三欄。只顯示。
