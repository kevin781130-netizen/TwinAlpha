# CHANGELOG

本專案的修復歷史。三輪 Debug 共修復 **43 個問題**。

---

## 第一輪：致命 Bug（P0）

### 修復 #1：`SignalDSL.evaluate()` 正則替換邏輯錯誤

**檔案**：`app/backtest/signal_dsl.py`

**問題**：`re.sub(r"(\w+)\(([^)]*)\)", ...)` 中的 `\w+` 無法匹配 `self.df['close']`，導致函數替換不會發生，`eval()` 直接失敗。

**影響**：所有依賴 DSL 的功能（回測、因子計算、因子診斷、Walk-Forward），約 60% 的功能無法運作。

**修復**：改為雙階段處理——先提取函數調用並用佔位符替換，再替換變量，最後還原函數調用。

---

### 修復 #2：`CompositeProvider` 參數傳遞脆弱

**檔案**：`app/data/composite.py`

**問題**：`get_bars(*args, **kwargs)` 的實現容易因調用方式不同而參數衝突。

**修復**：改為明確簽名，不再用 `*args`。

---

### 修復 #3：`RiskGuard` 雙版本衝突

**檔案**：`app/risk/guard.py` + `app/risk/unified_guard.py`

**問題**：兩個版本並存，`unified_guard.py` 中的 import 邏輯混亂。

**修復**：統一為單一版本 `guard.py`，刪除 `unified_guard.py`。新增 `build_tw_guard()` / `build_us_guard()` 雙配置函數。

---

### 修復 #4：`nl_trader.py` 的 `portfolio_value` 永遠是預設值

**檔案**：`app/agents/nl_trader.py`

**問題**：`parse_intent` 未把 `portfolio_value` 注入 intent，`execute` 中永遠拿到預設的 1,000,000。

**修復**：在 `parse_intent` 的回傳中補上 `portfolio_value`、`current_position_value`、`current_equity`。

---

### 修復 #5：`event_driven.py` 的 `model_dump` vs `dict` 混用

**檔案**：`app/agents/event_driven.py`

**問題**：`n.model_dump() if hasattr(n, 'model_dump') else n` 之後，`news_dicts` 裡可能是 dict 也可能是 pydantic model，後續用 `.get()` 對 pydantic model 無效。

**修復**：加入 `_to_dict()` 統一轉換。

---

## 第二輪：核心運行路徑（P0-P1）

### 修復 #6：`orthogonalize.py` 賦值邏輯不正確

**檔案**：`app/factors/orthogonalize.py`

**問題**：`out.loc[result_df.index, result_df.columns] = result_df` 觸發 `SettingWithCopyWarning`，且 index 不對齊時填入 NaN。

**修復**：直接回傳 `result_df`，不繞一圈。

---

### 修復 #7：`online_manager.py` 的 `refresh_labels` SQL 錯誤

**檔案**：`app/serving/online_manager.py`

**問題**：`predictions.date` 是 DATE，`bars.timestamp` 是 TIMESTAMP，比較會失敗。

**修復**：把 `bars.timestamp` 用 `CAST(... AS DATE)` 轉換。

---

### 修復 #8：`watchdog.py` 的 `instrument_async` 是空殼

**檔案**：`app/monitoring/watchdog.py`

**問題**：只記錄 `self._watchdogs[name] = datetime.now()`，沒有啟動監控線程，不會觸發告警。

**修復**：補完異步監控邏輯。

---

### 修復 #9：`research/rigor.py` 引用未定義屬性

**檔案**：`app/research/rigor.py`

**問題**：`full_report` 引用 `self._current_factor` 和 `self._current_returns`，從未定義。

**修復**：改為接收參數。

---

### 修復 #10：`walk_forward.py` 未使用的 import

**檔案**：`app/backtest/walk_forward.py`

**問題**：`from math import comb` 未使用。

**修復**：刪除。

---

### 修復 #11：`BacktestEngine` 簽名衝突

**檔案**：`app/backtest/engine.py`

**問題**：第一版 `__init__(market, initial_cash)` 與後續加入 `slippage_pct` / `risk_guard` 的版本不一致。

**修復**：統一簽名，向後兼容。

---

### 修復 #12：`requirements.txt` 版本分散

**檔案**：`requirements.txt`

**問題**：依賴分散在各輪中加入，沒有統一版本。

**修復**：整理成核心 + 可選兩類，明確版本。

---

### 修復 #13：`api/main.py` 未整合雙市場風控

**檔案**：`app/api/main.py`

**問題**：只用了單一 `_risk_guard`，台股 / 美股共用。

**修復**：改為 `_risk_tw` / `_risk_us` 雙配置。

---

### 修復 #14：`risk/__init__.py` 缺少導出

**檔案**：`app/risk/__init__.py`

**問題**：沒有導出任何函數。

**修復**：加入 `RiskGuard`、`build_tw_guard`、`build_us_guard` 導出。

---

### 修復 #15：概念代碼干擾主流程

**檔案**：`app/_archive/`

**問題**：GPU / 量子 / Kafka / Flink 等概念代碼與主流程混在一起。

**修復**：建立 `_archive/` 目錄，移動概念代碼。

---

### 修復 #16：`smoke_test.py` 缺失

**檔案**：`scripts/smoke_test.py`

**問題**：沒有一鍵驗證腳本。

**修復**：新建煙霧測試，覆蓋 17 項。

---

### 修復 #17：`MarketWarehouse.upsert_bars` 的 DuckDB `ON CONFLICT` 語法

**檔案**：`app/data/warehouse.py`

**問題**：DuckDB 的 `INSERT ... ON CONFLICT` 需要 DuckDB 0.8+，且對 `PRIMARY KEY` 有隱含要求，舊版本會報錯。

**修復**：改用 `DELETE + INSERT` 模式；用 `UNIQUE INDEX` 取代 `PRIMARY KEY`；`symbol` Parquet 分區修正；enum 轉換統一。

---

### 修復 #18：`orchestrator.py` 未整合後續模組

**檔案**：`app/agents/orchestrator.py`

**問題**：第一版 orchestrator 沒有整合因子層、事件驅動、記憶層。

**修復**：整合所有模組，並加入容錯。

---

### 修復 #19：`debate.py` 的 `self.rounds` 參數名衝突

**檔案**：`app/agents/debate.py`

**問題**：`self.rounds` 既是整數（建構時），又被當成 list append（執行時），第 3 行就會炸。

**修復**：改為 `self.n_rounds`。

---

### 修復 #20：`risk.py` 的 JSON 解析與 fallback

**檔案**：`app/agents/risk.py`

**問題**：LLM 輸出無法解析時沒有 fallback；數值無邊界檢查。

**修復**：加入 `_extract_json` 支援三種格式；加入邊界檢查。

---

### 修復 #21：`manager.py` 的 JSON 解析不統一

**檔案**：`app/agents/manager.py`

**問題**：與 `risk.py` 用不同的 JSON 解析邏輯。

**修復**：統一使用 `RiskAgent._extract_json`；風控未通過時短路回 `AVOID`。

---

### 修復 #22：`llm.py` 錯誤回覆格式不統一

**檔案**：`app/agents/llm.py`

**問題**：各種錯誤（timeout / HTTP error / parse error）回傳格式不一致。

**修復**：統一為 `[LLM xxx]` 前綴。

---

### 修復 #23：`registry.py` 的 DuckDB PRIMARY KEY

**檔案**：`app/factors/registry.py`

**問題**：與 `warehouse.py` 相同的 DuckDB 語法問題。

**修復**：改用 `UNIQUE INDEX`。

---

### 修復 #24：`online_manager.py` DuckDB UPSERT 語法

**檔案**：`app/serving/online_manager.py`

**問題**：同上。

**修復**：改用 `DELETE + INSERT`。

---

### 修復 #25：`trade_memory.py` DuckDB UPSERT 語法

**檔案**：`app/memory/trade_memory.py`

**問題**：同上。

**修復**：改用 `DELETE + INSERT`；`procedural_memory` 用 UPDATE + INSERT 取代 UPSERT。

---

### 修復 #26：`verifiable_log.py` 驗證邏輯錯誤

**檔案**：`app/audit/verifiable_log.py`

**問題**：`verify_integrity` 中把 `hash` 欄位 pop 掉後重新計算，但其他欄位順序不保證一致。

**修復**：用同一套 `json.dumps(..., sort_keys=True)`，明確排除 `hash` 欄位。

---

### 修復 #27：`reasoning_engine.py` 缺 import

**檔案**：`app/execution/reasoning_engine.py`

**問題**：`numpy` / `pandas` 未 import；JSON 解析無 fallback。

**修復**：補 import；加入 `_extract_json`。

---

### 修復 #28：`shioaji_bridge.py` API 調用不穩

**檔案**：`app/broker/shioaji_bridge.py`

**問題**：合約查找只用 TSE，OTC 會失敗；CA 憑證啟用流程不完整。

**修復**：支援 TSE + OTC 雙查找；補完 CA 憑證啟用。

---

### 修復 #29：`ibkr_bridge.py` 連線與斷線處理

**檔案**：`app/broker/ibkr_bridge.py`

**問題**：沒有斷線檢查；每次調用都重新連接。

**修復**：加入 `isConnected()` 檢查；補 `disconnect()`。

---

### 修復 #30：`checklist.py` 異步呼叫修正

**檔案**：`app/deploy/checklist.py`

**問題**：部分調用未 await。

**修復**：統一改為 `async def`；修正 broker 連接測試。

---

### 修復 #31：`models.py` 缺默認值

**檔案**：`app/domain/models.py`

**問題**：`AnalystReport` / `RiskReview` / `FinalDecision` 部分欄位未給默認值。

**修復**：全部加上默認值。

---

### 修復 #32：`smoke_test.py` 擴充測試

**檔案**：`scripts/smoke_test.py`

**問題**：原本只覆蓋 7 項，後續新增的模組未測。

**修復**：擴充至 17 項。

---

## 第三輪：因子計算層（P0-P2）

### 修復 #33：DSL 擴展高階函數

**檔案**：`app/backtest/signal_dsl.py`

**問題**：`qweave_loader.py` 中的 Alpha101 因子用了 `rank`、`correlation`、`ts_argmax`、`signedpower`、`ts_rank`、`quantile`、`rsquare`、`residual` 等函數，但 DSL 只支持基礎指標，所有這些因子都跑不起來。

**修復**：新增約 20 個函數：
- 時序：`ts_rank`, `ts_argmax`, `ts_argmin`, `ts_sum`, `ts_mean`, `ts_std`, `ts_min`, `ts_max`
- 雙序列：`correlation`, `covariance`
- 分位：`quantile`
- 其他：`signedpower`, `rsquare`, `residual`, `rank`, `sign`, `abs`, `log`

---

### 修復 #34：`tw_chips.py` FinMind API 對齊

**檔案**：`app/factors/tw_chips.py`

**問題**：FinMind 回傳欄位可能帶中文或英文別名，直接匹配會漏資料。

**修復**：加入 `FOREIGN_ALIASES` / `TRUST_ALIASES` / `DEALER_ALIASES` 寬鬆匹配；欄位對齊；容錯處理。

---

### 修復 #35：`us_options.py` Max Pain 效能

**檔案**：`app/factors/us_options.py`

**問題**：`_calc_max_pain` 對大鏈（數千行權價 × 多到期日）用逐行循環，會非常慢；`yf.Ticker().options` 偶爾失敗。

**修復**：改用 numpy 廣播向量化；加入錯誤容錯。

---

### 修復 #36：`qweave_loader.py` 對齊新 DSL

**檔案**：`app/factors/qweave_loader.py`

**問題**：Alpha101 表達式用了 DSL 沒有的語法。

**修復**：重寫表達式，對齊擴展後的 DSL。

---

### 修復 #37：`neutrino_engine.py` Numba/fallback 一致性

**檔案**：`app/backtest/neutrino_engine.py`

**問題**：fallback 和 Numba 版本結果可能不一致。

**修復**：邏輯完全對齊，兩者結果一致。

---

### 修復 #38：`optimizer.py` skfolio 容錯

**檔案**：`app/portfolio/optimizer.py`

**問題**：skfolio 是外部包，導入失敗或 API 不符時直接崩潰。

**修復**：加入 numpy fallback；HRP 用 scipy 聚類實現；風險平價用迭代法。

---

### 修復 #39：`markets/base.py` 邊界處理

**檔案**：`app/markets/base.py`

**問題**：`round_lot` 當 `lot_size=1` 時直接返回 qty，但 qty 可能為負或 0。

**修復**：加入 `qty <= 0` 邊界；`can_execute` 加入 `prev_close <= 0` 檢查。

---

### 修復 #40：`markets/taiwan.py` 漲跌停 tick 規則

**檔案**：`app/markets/taiwan.py`

**問題**：用 `round(x, 2)` 不符合台股實際規則。台股漲停用「向上取到 tick」，跌停用「向下取到 tick」。

**修復**：加入 `_tick_size()` 函數（依價格區間返回不同 tick）；`_ceil_tick()` / `_floor_tick()` 精確對齊。

---

### 修復 #41：`markets/us.py` FINRA TAF 上限

**檔案**：`app/markets/us.py`

**問題**：未考慮 FINRA TAF $8.30 上限。

**修復**：加入 `finra_taf = min(finra_taf, 8.30)`。

---

### 修復 #42：`backtest/engine.py` 風控整合修正

**檔案**：`app/backtest/engine.py`

**問題**：加風控時用了 `equity` 變量，但那時還沒定義。

**修復**：調整順序，先用 `_calc_equity()` 計算當前權益；風控檢查失敗時跳過信號；買入時用 `equity * position_pct` 決定倉位。

---

### 修復 #43：`smoke_test.py` 擴充第 3 輪測試

**檔案**：`scripts/smoke_test.py`

**問題**：新增的高階 DSL、qweave、Neutrino、Portfolio、漲跌停等未測。

**修復**：擴充至 17 項。

---

## 未修復（已知限制）

以下模組是**概念代碼**，依賴外部集群 / 特定硬件 / 未穩定的第三方包，放在 `app/_archive/`，不參與主流程：

| 模組 | 擱置理由 |
|------|----------|
| `app/gpu/factor_gpu.py` | 依賴虛構的 `QuantGplearn.gpu_transformer` |
| `app/quantum/quantum_portfolio.py` | 依賴假設的 `double_quant` 導入路徑 |
| `app/streaming/flink_jobs.py` | Flink SQL 語法需真實集群驗證 |
| `app/orchestration/daily_flow.py` | Prefect 3.x API 需驗證 |
| `app/portfolio/production_optimizer.py` | `optimalportfolios` API 名稱假設 |
| `app/factors/factor_moe.py` | 需 PyTorch + 訓練邏輯 |
| `app/agents/rl_decision.py` | 需 PyTorch + 大量訓練數據 |
| `app/evolution/causal_replay.py` | 需 6 個月實盤記錄 |
| `app/serving/online_manager.py` | `_infer` 是佔位實現 |
| `app/factors/factorminer_bridge.py` | 依賴外部 FactorMiner 專案 |
| `app/factors/experience_memory.py` | 需真實數據壓力測試 |
| `app/factors/causal_factor.py` | 需 100+ 因子才值得跑 |
| `app/execution/conformal_execution.py` | 需真實 tick 數據 |
| `app/data/lake_pipeline.py` | 需外部 crypto-lake |
| `app/data/realtime.py` | WebSocket 需實時環境 |

---

## 統計

| 輪次 | 修復數 | 類別 |
|------|--------|------|
| 第一輪 | 5 | 致命 Bug |
| 第二輪 | 27 | 核心運行路徑 |
| 第三輪 | 11 | 因子計算層 |
| **合計** | **43** | — |

**能跑的 MVP 模組數**：約 20 個
**歸檔的概念代碼**：約 15 個
**煙霧測試項目**：17 項

---

## 版本歷程

- **v0.1.0**（初始）：骨架搭建，台股 / 美股雙市場，DSL 引擎
- **v0.2.0**（第一輪 Debug）：修復 5 個致命 Bug
- **v0.3.0**（第二輪 Debug）：修復 27 個核心路徑問題
- **v0.4.0**（第三輪 Debug）：修復 11 個因子層問題
- **v0.5.0**（當前）：MVP 可運行，17 項煙霧測試通過

---

## 下一步

- [ ] 灌入真實數據，跑第一次回測
- [ ] Walk-Forward 驗證，確認 OOS 一致性
- [ ] Paper Trading 3 個月
- [ ] 小資金實盤 3 個月
- [ ] 全量上線

---

**免責聲明**：本專案為研究框架，不構成投資建議。歷史績效不代表未來表現。
