# PACKAGE NOTES

本專案由對話中提供的 5 個批次整理、抽取並打包。

## 原始內容保留

- 批次 2、3、5 的每個具名程式碼區塊已抽出到對應 `app/`、`frontend/`、`scripts/` 路徑。
- 批次 4 已拆成 `RUNBOOK.md` 與 `CHANGELOG.md`。
- 批次 1 的 README、ARCHITECTURE 與單文件 HTML 設計已整合。
- 原始上傳批次保留在 `source_batches/`，方便比對。

## 打包時新增/補齊的整合檔

為了讓資料不是只有「文檔」，而是可解壓後直接作為專案使用，打包時新增或補齊了以下整合層：

- `requirements.txt`、`.env.example`、`.gitignore`
- Python package 所需的空白 `__init__.py`
- `frontend/utils/metrics.py`：原前端 Dashboard 有 import，但批次 5 未提供此檔
- `app/api/main.py`：保留原有端點並把文件列出的 Walk-Forward、Sweep、因子、組合、風控端點接上現有模組
- `scripts/smoke_test.py`：原批次 5 此檔只有 2 項實作與「見前次交付」省略文字，打包版補成 17 項本地測試
- `scripts/tw_paper_trading.py`：原批次 5 在「風控 + 下單」處省略，打包版補上 Dry Run / 模擬下單、風控、狀態及審計記錄流程
- `start_backend.*`、`start_frontend.*`、`QUICK_START.md`
- `app/_archive/README.md`：依原批次的概念模組清單建立說明；未虛構未提供的概念代碼

## 驗證狀態

- 所有 Python 檔案已通過 `compileall` / 語法編譯檢查。
- 靜態檢查未發現缺失的 `app.*` 本地 import。
- 本打包環境缺少 `duckdb`、`yfinance`、`FinMind`、`streamlit`，且環境無法連外安裝，因此沒有在此環境完成「安裝依賴後的 17 項 runtime smoke test」。解壓後先依 `QUICK_START.md` 安裝依賴，再執行 `python scripts/smoke_test.py`。

## 重要邊界

本專案仍依原始資料定位為研究框架。Broker 實盤橋接未經真實帳戶驗證，打包版也沒有替你啟用實盤下單；請先使用 Dry Run / Paper Trading。
