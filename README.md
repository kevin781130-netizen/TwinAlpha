# TW/US Invest OS

台股 / 美股量化研究框架。

> **定位聲明**：本專案是**研究框架**，不是實盤交易系統。
> 它幫你驗證策略想法、管理數據、做正確的費用與交割計算、用風控保護資金。
> **賺錢的部分取決於你的策略，不取決於模組數量。**

---

## 一、這個框架能做什麼

| 能力 | 狀態 | 說明 |
|------|------|------|
| 台股 / 美股數據接入 | ✅ | FinMind + yfinance |
| 本地數據倉庫 | ✅ | DuckDB + Parquet |
| 市場規則層 | ✅ | 台股 T+2 / ±10% / tick；美股 T+1 / 無漲跌幅 |
| 因子計算 | ✅ | DSL 引擎 + Alpha158 子集 + 台股籌碼 |
| 回測引擎 | ✅ | 含交割佔用資金 + 滑點 + 風控 |
| Walk-Forward | ✅ | 滾動窗口 + CSCV 過擬合檢測 |
| 多 Agent 決策 | ✅ | 多分析師 + 多空辯論 + 風控 + 經理決策 |
| 事件驅動決策 | ✅ | 新聞 + 技術面整合 |
| 自然語言下單 | ✅ | 意圖解析 + 風控 + 審計 |
| 組合優化 | ✅ | HRP / 風險平價 / 最大分散化 |
| 實盤風控 | ✅ | 倉位上限 / 回撤熔斷 / Kelly |
| Broker 橋接 | ⚠️ | Shioaji / IBKR，模擬盤可跑，實盤未驗證 |
| 可驗證審計 | ✅ | SHA-256 哈希鏈 + Merkle 根 |
| 心跳監控 | ✅ | Dead-man's switch |

---

## 二、快速開始

### 2.1 環境需求

- Python 3.11+
- 作業系統：Linux / macOS / Windows（WSL2）
- 記憶體：8 GB 以上

### 2.2 安裝

```bash
git clone <your-repo>
cd invest-os

# 建立虛擬環境
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 安裝核心依賴
pip install -r requirements.txt
```

### 2.3 設定環境變數

建立 `.env`：

```env
# 資料存放位置
DATA_ROOT=./data_lake

# FinMind（台股數據，免費申請）
FINMIND_TOKEN=

# LLM（可選，沒有則 Agent 走 mock 模式）
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=
LLM_MODEL=gpt-4o-mini
```

### 2.4 啟動服務

```bash
uvicorn app.api.main:app --reload
```

打開 `http://127.0.0.1:8000/docs` 看 API 文件。

### 2.5 五分鐘驗證

```bash
# 健康檢查
curl http://127.0.0.1:8000/health

# 市場規則
curl http://127.0.0.1:8000/rules/TW
curl http://127.0.0.1:8000/rules/US

# 第一次回測（台積電，MA 交叉）
curl -X POST "http://127.0.0.1:8000/backtest?symbol=2330&market=TW&start=2022-01-01&end=2025-12-31&expr=ema(close,10)/ema(close,30)-1&upper=0.02&lower=-0.02"

# 風控 dry-run
curl -X POST "http://127.0.0.1:8000/trade/order-protected?symbol=2330&market=TW&side=BUY&price=850&qty=1000&portfolio_value=1000000&current_position_value=0&current_equity=1000000&dry_run=true"
```

### 2.6 煙霧測試

```bash
python scripts/smoke_test.py
```

**預期輸出**：17 項全部 PASS。

---

## 三、目錄結構

```text
invest-os/
├── README.md                    # 本文件
├── ARCHITECTURE.md              # 系統架構
├── MODULES.md                   # 所有模組完整程式碼
├── RUNBOOK.md                   # 操作手冊
├── CHANGELOG.md                 # 修復歷史
├── requirements.txt
├── .env
├── app/
│   ├── config.py
│   ├── domain/models.py
│   ├── markets/                 # 市場規則層
│   ├── data/                    # 數據層
│   ├── factors/                 # 因子層
│   ├── agents/                  # Agent 決策層
│   ├── backtest/                # 回測層
│   ├── portfolio/               # 組合層
│   ├── risk/                    # 風控層
│   ├── broker/                  # Broker 橋接
│   ├── execution/               # 執行層
│   ├── audit/                   # 審計層
│   ├── monitoring/              # 監控層
│   ├── research/                # 研究紀律層
│   ├── memory/                  # Agent 記憶層
│   ├── serving/                 # 模型服務層
│   ├── api/main.py              # FastAPI 入口
│   └── _archive/                # 歸檔的概念代碼
├── frontend/                    # Streamlit 前端
├── scripts/
│   ├── smoke_test.py
│   ├── ingest_real_data.py
│   ├── run_first_backtest.py
│   └── tw_paper_trading.py
└── data_lake/
    ├── market.duckdb
    ├── factors.duckdb
    ├── memory.duckdb
    └── parquet/
```

---

## 四、核心概念

### 4.1 市場規則層

不同市場的交易規則差異是回測準確性的**地基**：

| 維度 | 台股 | 美股 |
|------|------|------|
| 交割 | T+2 | T+1 |
| 漲跌幅 | ±10%（tick 對齊） | 無 |
| 交易單位 | 1 股（可零股） | 1 股 |
| 證交稅 | 0.3%（賣出） | 無 |
| 手續費 | 0.1425% × 折 | SEC + FINRA |

### 4.2 DSL 信號引擎

用緊湊表達式描述策略，直接回測：

```text
rsi(close, 14) - 50
ema(close, 10) / ema(close, 30) - 1
correlation(open, volume, 10)
ts_rank(close, 20)
```

支持的函數：`sma, ema, mean, std, rsi, atr, zscore, highest, lowest, slope, delay, delta, ts_rank, ts_argmax, ts_argmin, ts_sum, correlation, covariance, quantile, signedpower, rsquare, residual, rank, sign, abs, log`

### 4.3 多 Agent 決策流程

```text
數據 + 因子 + 記憶
    ↓
多分析師並行分析（技術 / 基本面 / 新聞 / 籌碼 / 期權）
    ↓
多空辯論（N 輪）
    ↓
風控審查
    ↓
投資組合經理決策
    ↓
事件驅動決策（並行）
    ↓
最終決策
```

### 4.4 風控三層防護

1. **RiskGuard**：倉位上限、回撤熔斷、Kelly 動態倉位
2. **ReasoningEngine**：執行前 LLM 推理過濾
3. **MarketRegimeDetector**：根據市場狀態動態縮放倉位

---

## 五、API 端點

| 端點 | 方法 | 說明 |
|------|------|------|
| `/health` | GET | 健康檢查 |
| `/rules/{market}` | GET | 市場規則查詢 |
| `/analyze` | POST | 多 Agent 分析 |
| `/backtest` | POST | DSL 回測 |
| `/backtest/walk-forward` | POST | Walk-Forward 回測 |
| `/backtest/sweep` | POST | 參數掃描 |
| `/factors/tw-chips` | POST | 台股籌碼因子 |
| `/factors/us-options` | POST | 美股期權因子 |
| `/factors/qweave/batch` | POST | qweave 批量因子 |
| `/factors/inspect` | POST | 因子診斷 |
| `/research/validate-factor` | POST | 排列檢驗 |
| `/portfolio/optimize` | POST | 組合優化 |
| `/risk/check` | POST | 風控檢查 |
| `/risk/kill-switch` | POST | Kill Switch |
| `/trade/natural` | POST | 自然語言下單 |
| `/trade/order-protected` | POST | 帶風控下單 |
| `/trade/audit-log` | GET | 審計日誌 |

---

## 六、常見問題

### Q1：沒有 FinMind Token 能跑嗎？

可以。FinMind 部分數據集無需 token，但建議申請免費 token 以獲得完整數據。

### Q2：沒有 LLM API Key 能跑嗎？

可以。`LLMClient` 在無 key 時會回傳 `[MOCK LLM]` 前綴的假回應，所有 Agent 流程仍可跑通，但決策質量會很低。

### Q3：回測結果的 Sharpe 很高，能直接上實盤嗎？

**不能**。務必先跑 Walk-Forward，看 `oos_consistency`。如果低於 0.5，策略就是過擬合。

### Q4：如何從回測過渡到實盤？

三個階段：
1. **Paper Trading**（3 個月）：Shioaji 模擬盤 / IBKR Paper
2. **小資金實盤**（3 個月）：5% 資金
3. **全量上線**：逐步加倉

### Q5：系統支援高頻交易嗎？

**不支援**。這是日線級別的研究框架。高頻需要 Kafka + Flink + 專用硬件。

---

## 七、能力邊界

### 這個框架能做的

- 日線級別的策略驗證
- 台股 / 美股市場規則的正確模擬
- 多因子分析與組合
- 多 Agent 決策輔助
- 風控與審計

### 這個框架不能做的

- 高頻 / 日內 tick 級交易
- 期貨 / 選擇權 / 加密貨幣（架構可擴展，但未實作）
- 全自動實盤（需自行驗證 Broker 橋接）
- 保證獲利

---

## 八、授權

MIT License

---

## 九、免責聲明

本框架僅供研究與教育用途。使用本框架進行實盤交易所產生的一切後果，由使用者自行承擔。作者不對任何財務損失負責。
