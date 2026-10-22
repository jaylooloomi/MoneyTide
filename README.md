# Open Market — 台股產業熱力圖

在本機執行的台股（上市＋上櫃）產業熱力圖看盤介面：

- **樹狀熱力圖**：依產業分區，格子大小可選市值或成交值，顏色代表今日或本週漲跌（紅漲綠跌）。點產業標題可放大到該產業。
- **產業矩陣**：今日、本週、振幅、成交值占比、漲跌家數，可排序。滑過某列時，熱力圖上的對應產業會加框。
- **個股資訊卡**與**自選清單**，可切換「只看自選」。
- 盤中依設定頻率自動更新（預設 60 秒，最低 30 秒），13:35 抓收盤後的最後一次。

只看盤，不下單。

## 執行

需要 [uv](https://docs.astral.sh/uv/)，以及能連到 HiStock、證交所、櫃買中心與 cdnjs 的網路。

```bash
uv sync
uv run python -m openmarket
```

或直接雙擊專案資料夾裡的 `openmarket.bat`。啟動後會自動開啟 <http://127.0.0.1:8765>；若已在執行，只會開啟瀏覽器。關閉那個命令列視窗就會停止伺服器。第一次啟動時，證交所 ISIN 產業分類清單約 9 MB，下載需要 10–50 秒。下載完成前，股票會暫時歸在「其他」，完成後畫面會自動更新。

| 環境變數 | 預設 | 說明 |
|---|---|---|
| `OPENMARKET_PORT` | `8765` | 連接埠 |
| `OPENMARKET_DATA_DIR` | `./data` | 快取、設定與自選清單存放位置 |

加上 `--no-browser` 參數可以不自動開瀏覽器。

## 資料來源

- 報價：HiStock 排行頁（`https://histock.tw/stock/rank.aspx?p=all`）。這是第三方網站，**僅供個人本機使用**。
- 產業分類：證交所 ISIN 公開清單（快取 7 天）。
- 已發行股數（計算市值用）：證交所與櫃買中心 OpenAPI（快取 7 天）。

## 測試

```bash
uv run pytest -q -p no:warnings
```

```bash
node --test "tests/js/*.test.js"
```

設計規格見 [docs/superpowers/specs/2026-10-12-industry-heatmap-design.md](docs/superpowers/specs/2026-10-12-industry-heatmap-design.md)。
