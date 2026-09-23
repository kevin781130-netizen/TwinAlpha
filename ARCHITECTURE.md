# 系統架構

## 一、系統全景

```text
┌─────────────────────────────────────────────────────────────────┐
│                        使用者介面層                              │
│  FastAPI /docs   │   Streamlit 前端   │   Shioaji Pro（可選）    │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                        編排與服務層                              │
│  InvestmentOrchestrator  │  OnlineServingEngine  │  Prefect      │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
┌───────▼────────┐  ┌────────▼────────┐  ┌────────▼────────┐
│   Agent 決策層  │  │   因子層         │  │   組合層         │
│  - 分析師       │  │  - DSL 引擎      │  │  - 優化器        │
│  - 辯論         │  │  - 因子庫        │  │  - 風險模型      │
│  - 風控         │  │  - 籌碼/期權     │  │  - 歸因          │
│  - 經理         │  │  - 正交化        │  │                 │
│  - 事件驅動     │  │  - 診斷          │  │                 │
└───────┬────────┘  └────────┬────────┘  └────────┬────────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                        風控與執行層                              │
│  RiskGuard  │  ReasoningEngine  │  Shioaji/IBKR  │  AuditLog  │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                        回測與研究層                              │
│  BacktestEngine  │  WalkForward  │  NeutrinoEngine  │  VectorBT │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                        數據層                                    │
│  CompositeProvider  │  MarketWarehouse  │  RealtimeFeed         │
│  FinMind  │  yfinance  │  DuckDB  │  Parquet                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                        市場規則層                                │
│  TaiwanRules（T+2, ±10%, tick）  │  USRules（T+1, 無漲跌幅）     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、分層說明

### 2.1 市場規則層

**職責**：將不同市場的交易規則抽象為統一接口。

| 類別 | 檔案 | 說明 |
|------|------|------|
| `MarketRules` | `markets/base.py` | 抽象基類 |
| `TaiwanRules` | `markets/taiwan.py` | 台股規則 |
| `USRules` | `markets/us.py` | 美股規則 |
| `get_rules()` | `markets/registry.py` | 規則查找 |

**設計原則**：所有市場相關的邏輯（費用、交割、漲跌幅、交易單位）都必須通過這一層，禁止在回測引擎中硬編碼。

### 2.2 數據層

**職責**：統一數據接入、本地緩存、數據倉庫。

```text
                    ┌──────────────────┐
                    │ CompositeProvider│
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
       ┌──────▼──────┐ ┌─────▼──────┐ ┌────▼─────┐
       │FinMindProvider│ │YFinanceProv│ │（可擴展）│
       └──────┬──────┘ └─────┬──────┘ └────┬─────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────▼─────────┐
                    │ MarketWarehouse  │
                    │  - DuckDB        │
                    │  - Parquet       │
                    └──────────────────┘
```

**三層快取策略**：
1. **記憶體**：Python dict（當次請求內）
2. **DuckDB**：結構化查詢（跨請求）
3. **Parquet**：冷數據歸檔（長期保存）

### 2.3 因子層

**職責**：因子計算、管理、驗證、正交化。

| 元件 | 檔案 | 說明 |
|------|------|------|
| DSL 引擎 | `backtest/signal_dsl.py` | 表達式求值 |
| 因子庫 | `factors/registry.py` | 元數據 + 版本 + 生命週期 |
| 台股籌碼 | `factors/tw_chips.py` | 三大法人 / 融資券 / 當沖 |
| 美股期權 | `factors/us_options.py` | PCR / IV / Max Pain |
| 內置因子庫 | `factors/qweave_loader.py` | Alpha101/158/191 子集 |
| 正交化 | `factors/orthogonalize.py` | 對稱 / 施密特 / PCA |
| 診斷 | `factors/inspect.py` | IC / 分層 / 衰減 |

### 2.4 Agent 決策層

**職責**：多 Agent 協作決策。

```text
                     ┌────────────────┐
                     │ InvestmentOrch │
                     └────────┬───────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   ┌────▼────┐          ┌─────▼─────┐         ┌────▼────┐
   │分析師群  │          │事件驅動    │         │記憶層   │
   │- 技術    │          │Trader     │         │- 相似交易│
   │- 基本面  │          └─────┬─────┘         │- 紀律漂移│
   │- 新聞    │                │               └────┬────┘
   │- 籌碼    │                │                    │
   │- 期權    │                │                    │
   └────┬────┘                │                    │
        │                     │                    │
        └─────────┬───────────┴────────────────────┘
                  │
            ┌─────▼─────┐
            │ DebateEngine│
            └─────┬─────┘
                  │
            ┌─────▼─────┐
            │ RiskAgent  │
            └─────┬─────┘
                  │
            ┌─────▼─────┐
            │ManagerAgent│
            └───────────┘
```

### 2.5 回測層

**職責**：策略驗證。

| 引擎 | 檔案 | 用途 |
|------|------|------|
| `BacktestEngine` | `backtest/engine.py` | 精確事件驅動 |
| `WalkForwardEngine` | `backtest/walk_forward.py` | 滾動窗口 + CSCV |
| `NeutrinoEngine` | `backtest/neutrino_engine.py` | Numba 向量化 |
| `VectorBTEngine` | `backtest/vectorbt_engine.py` | 多資產組合 |

### 2.6 風控與執行層

**職責**：保護資金、執行訂單。

```text
                     訂單請求
                        │
                  ┌─────▼─────┐
                  │RiskGuard  │ ← 倉位 / 回撤 / Kelly
                  └─────┬─────┘
                        │ approved?
                  ┌─────▼─────────┐
                  │ReasoningEngine│ ← LLM 推理過濾
                  └─────┬─────────┘
                        │ decision?
                  ┌─────▼─────┐
                  │Verifiable │ ← 寫入審計日誌
                  │AuditLog   │
                  └─────┬─────┘
                        │
                  ┌─────▼─────┐
                  │Broker     │
                  │Shioaji/IBKR│
                  └───────────┘
```

### 2.7 審計與監控層

| 元件 | 檔案 | 說明 |
|------|------|------|
| `VerifiableAuditLog` | `audit/verifiable_log.py` | SHA-256 哈希鏈 |
| `TradingWatchdog` | `monitoring/watchdog.py` | 心跳監控 |
| `ResearchRigor` | `research/rigor.py` | 排列檢驗 + 多重校正 |
| `TradeMemoryLayer` | `memory/trade_memory.py` | 五層記憶 |

---

## 三、數據流

### 3.1 從數據到決策

```text
FinMind / yfinance
       │
       ▼
CompositeProvider.get_bars()
       │
       ▼
MarketWarehouse.upsert_bars()
       │
       ├──────────────► DuckDB（結構化）
       │
       └──────────────► Parquet（歸檔）
       │
       ▼
SignalDSL.evaluate(expr)
       │
       ▼
因子值（Series）
       │
       ▼
AnalystAgent.analyze()
       │
       ▼
AnalystReport
       │
       ▼
DebateEngine.run()
       │
       ▼
DebateResult
       │
       ▼
RiskAgent.review()
       │
       ▼
RiskReview
       │
       ▼
ManagerAgent.decide()
       │
       ▼
FinalDecision
```

### 3.2 從決策到執行

```text
FinalDecision
       │
       ▼
RiskGuard.check_order()
       │
       ├─── REJECT ──► 記錄到 audit_log
       │
       └─── APPROVE ─┐
                     │
                     ▼
              ReasoningEngine.filter_order()
                     │
                     ├─── REJECT ──► 記錄
                     │
                     └─── APPROVE ─┐
                                   │
                                   ▼
                          VerifiableAuditLog.append()
                                   │
                                   ▼
                          Broker.place_order()
                                   │
                                   ▼
                          AuditLog.log_order()
```

### 3.3 每日流水線

```text
開盤前（08:30）
  ├── 拉取隔夜新聞
  ├── 掃描 ADR-台股套利機會
  └── 生成盤前策略

收盤後（15:00 台股 / 17:00 美股）
  ├── Ingest 行情數據
  ├── 計算因子
  ├── 模型推理（OnlineServingEngine.routine）
  ├── 刷新標籤
  ├── 因子挖掘（FactorMiner）
  ├── 因果回放（CausalReplayArena）
  └── 生成歸因報告

週末
  ├── 全因子 IC 掃描
  ├── Walk-Forward 驗證
  └── 模型重訓練
```

---

## 四、模組依賴關係

### 4.1 核心依賴（無循環）

```text
config.py
    ↑
domain/models.py
    ↑
markets/*
    ↑
data/*
    ↑
backtest/*
    ↑
factors/*
    ↑
agents/*
    ↑
api/main.py
```

### 4.2 可選依賴

```text
risk/guard.py         ← 被 backtest 和 agents 使用
audit/verifiable_log  ← 被 execution 使用
monitoring/watchdog   ← 被 data 使用
memory/trade_memory   ← 被 agents 使用
portfolio/optimizer   ← 被 api 使用
```

### 4.3 依賴規則

1. **下層不能 import 上層**
2. **同層之間可以互相 import**
3. **可選依賴用 try/except 包裝**，失敗時 fallback

---

## 五、狀態管理

### 5.1 持久化狀態

| 狀態 | 存放位置 | 用途 |
|------|----------|------|
| 行情數據 | `data_lake/market.duckdb` | K 線、籌碼、期權 |
| 因子庫 | `data_lake/factors.duckdb` | 因子元數據 |
| 記憶 | `data_lake/memory.duckdb` | 交易記錄、模式 |
| 審計日誌 | `data_lake/audit/events.jsonl` | 不可篡改記錄 |
| 風控狀態 | `data_lake/risk_state_*.json` | 熔斷狀態 |
| 模型預測 | `data_lake/serving.duckdb` | 線上推理結果 |

### 5.2 記憶體狀態

| 狀態 | 生命週期 | 說明 |
|------|----------|------|
| `BacktestEngine` 內部狀態 | 單次回測 | 現金、持倉、交易 |
| `RiskGuard` | 整個 session | 峰值權益、熔斷計時 |
| `TradingWatchdog` | 整個 process | 各模組心跳 |
| `NLTrader.audit_log` | 整個 process | 記憶體審計（同步寫檔） |

### 5.3 狀態恢復

- **RiskGuard**：`persist()` / `load()` 支援重啟恢復
- **DuckDB**：事務保證，崩潰不會寫壞
- **AuditLog**：append-only，可從最後一條恢復
- **記憶體狀態**：不恢復，重啟即重置

---

## 六、配置管理

### 6.1 環境變數

| 變數 | 預設 | 說明 |
|------|------|------|
| `DATA_ROOT` | `./data_lake` | 數據根目錄 |
| `FINMIND_TOKEN` | 空 | FinMind API token |
| `LLM_BASE_URL` | OpenAI | LLM API base |
| `LLM_API_KEY` | 空 | LLM API key |
| `LLM_MODEL` | `gpt-4o-mini` | LLM 模型 |

### 6.2 預設費用參數

```python
# 台股
default_tw_fee_rate = 0.001425
default_tw_fee_discount = 0.6
default_tw_min_fee = 20.0
default_tw_tax_rate_sell = 0.003

# 美股
default_us_sec_fee_rate = 0.0000278
default_us_finra_taf_per_share = 0.000166
default_us_commission = 0.0
```

### 6.3 風控預設

```python
# 台股
max_position_pct = 0.15
max_daily_loss_pct = 0.025
max_drawdown_pct = 0.12
circuit_breaker_levels = {
    "reduce": 0.06,
    "halt": 0.10,
    "kill": 0.15,
}

# 美股
max_position_pct = 0.20
max_daily_loss_pct = 0.03
max_drawdown_pct = 0.15
```

---

## 七、擴展指南

### 7.1 新增一個市場

1. 在 `app/markets/` 下新增 `xxx.py`
2. 繼承 `MarketRules`
3. 實作 `calc_fees()` 和 `price_limits()`
4. 在 `registry.py` 註冊

### 7.2 新增一個數據源

1. 在 `app/data/` 下新增 `xxx_provider.py`
2. 繼承 `DataProvider`
3. 實作 `get_bars()` / `get_fundamentals()` / `get_news()`
4. 在 `composite.py` 註冊

### 7.3 新增一個因子

1. 用 DSL 表達式描述
2. 在 `FactorRegistry.register()` 註冊
3. 用 `FactorInspector` 診斷
4. 用 `ResearchRigor.permutation_test()` 驗證
5. 若顯著，用 `validate()` 升為 `production`

### 7.4 新增一個 Agent

1. 在 `app/agents/` 下新增
2. 提供 `async def analyze(symbol, market, context) -> AnalystReport`
3. 在 `build_analysts()` 註冊

---

## 八、已知限制

| 限制 | 影響 | 緩解 |
|------|------|------|
| 單機架構 | 無法水平擴展 | 用 Prefect 分散任務 |
| DuckDB 單寫 | 併發寫入會鎖 | 讀寫分離，寫入排隊 |
| yfinance 不穩定 | 美股數據偶爾失敗 | 重試 + fallback |
| FinMind 限流 | 台股數據有配額 | 本地快取優先 |
| LLM 成本 | 大量分析會花錢 | 用便宜模型 + 快取 |
| 無實盤驗證 | Broker 橋接未經真實測試 | Paper Trading 先行 |

---

## 九、設計原則

1. **模組化**：每個模組職責單一，可獨立測試
2. **可降級**：外部依賴失敗時 fallback 到純 Python 實現
3. **可審計**：所有交易決策寫入不可篡改日誌
4. **防過擬合**：強制 Walk-Forward 驗證
5. **風控優先**：任何訂單先過風控，再過推理，最後執行
6. **誠實定位**：這是研究框架，不是印鈔機
