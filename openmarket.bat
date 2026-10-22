@echo off
chcp 65001 >nul
title 台股產業熱力圖
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo 找不到 uv。請先安裝：https://docs.astral.sh/uv/
    pause
    exit /b 1
)

echo 啟動中，瀏覽器會自動開啟 http://127.0.0.1:8765
echo 關閉這個視窗就會停止熱力圖伺服器。
echo.
uv run python -m openmarket
if errorlevel 1 pause
