好，批次 4。把下面整段替换掉 `invest-os.html` 里的 `<section id="batch4">...</section>`（placeholder 整段删掉）。

---

```html
<section id="batch4">
<script type="text/plain" data-title="RUNBOOK + CHANGELOG">
# RUNBOOK — 操作手冊

所有 API 端點、CLI 腳本、常見錯誤排除。

---

## 一、快速開始

```bash
# 1. 安裝
pip install -r requirements.txt

# 2. 設定環境變數
cp .env.example .env
# 編輯 .env 填入 FINMIND_TOKEN / LLM_API_KEY

# 3. 灌入數據
python scripts/ingest_real_data.py --market TW --symbols 2330 --with-chips

# 4. 跑第一次回測
python scripts/run_first_backtest.py --symbol 2330 --market TW --multi --walk-forward

# 5. 啟動 API
uvicorn app.api.main:app --reload

# 6. 煙霧測試
python scripts/smoke_test.py

# 7. 模擬盤
python scripts/tw_paper_trading.py --symbols 2330 --dry-run
```

---

## 二、API 端點完整列表

### 2.1 健康檢查

```bash
curl http://127.0.0.1:8000/health
```

**回應**：
```json
{"ok": true, "app": "TW/US Invest OS"}
```

### 2.2 市場規則

```bash
curl http://127.0.0.1:8000/rules/TW
curl http://127.0.0.1:8000/rules/US
```

**回應**：
```json
{
  "market": "TW",
  "settlement_days": 2,
  "price_limit_pct": 0.1,
  "lot_size": 1
}
```

### 2.3 多 Agent 分析

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "2330",
    "market": "TW",
    "start": "2024-01-01",
    "end": "2025-01-01"
  }'
```

**回應**（簡化）：
```json
{
  "symbol": "2330",
  "market": "TW",
  "action": "BUY",
  "confidence": 0.75,
  "target_position_pct": 0.1,
  "thesis": "...",
  "reports": [],
  "debate": {},
  "risk": {},
  "event_driven": {}
}
```

### 2.4 回測

```bash
curl -X POST "http://127.0.0.1:8000/backtest" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "2330",
    "market": "TW",
    "start": "2022-01-01",
    "end": "2025-12-31",
    "expr": "ema(close,10)/ema(close,30)-1",
    "upper": 0.02,
    "lower": -0.02
  }'
```

**回應**：
```json
{
  "trades": [],
  "equity_curve": [],
  "final_cash": 1050000,
  "positions": {},
  "metrics": {
    "sharpe": 1.23,
    "total_return": 0.45,
    "max_drawdown": -0.15,
    "num_trades": 42
  }
}
```

### 2.5 Walk-Forward 回測

```bash
curl -X POST "http://127.0.0.1:8000/backtest/walk-forward?symbol=2330&market=TW&start=2022-01-01&end=2025-12-31&expr=ema(close,10)/ema(close,30)-1"
```

**回應**：
```json
{
  "windows": [],
  "summary": {
    "num_windows": 12,
    "sharpe_mean": 0.85,
    "sharpe_std": 0.42,
    "oos_consistency": 2.02
  }
}
```

### 2.6 參數掃描

```bash
curl -X POST "http://127.0.0.1:8000/backtest/sweep?symbol=2330&market=TW&start=2022-01-01&end=2025-12-31&fast_range=5,10,15,20&slow_range=20,30,40,50"
```

### 2.7 台股籌碼因子

```bash
curl -X POST "http://127.0.0.1:8000/factors/tw-chips?symbol=2330&start=2024-01-01&end=2025-12-31"
```

**回應**：
```json
[
  {
    "date": "2025-01-15",
    "foreign_net_5d": 12500000,
    "trust_net_20d": -800000,
    "margin_ratio": 0.98,
    "chip_concentration": 1.23
  }
]
```

### 2.8 美股期權因子

```bash
curl -X POST "http://127.0.0.1:8000/factors/us-options?symbol=AAPL"
```

**回應**：
```json
{
  "put_call_volume_ratio": 0.85,
  "atm_iv": 0.28,
  "iv_skew": 0.05,
  "max_pain": 175.0,
  "gamma_exposure": 1.2e10
}
```

### 2.9 qweave 批量因子

```bash
curl -X POST "http://127.0.0.1:8000/factors/qweave/batch?symbol=2330&market=TW&start=2024-01-01&end=2025-12-31&categories=alpha158"
```

### 2.10 因子診斷

```bash
curl -X POST "http://127.0.0.1:8000/factors/inspect?symbol=2330&market=TW&start=2024-01-01&end=2025-12-31&factor_expr=rsi(close,14)"
```

### 2.11 排列檢驗

```bash
curl -X POST "http://127.0.0.1:8000/research/validate-factor?symbol=2330&market=TW&start=2024-01-01&end=2025-12-31&factor_expr=rsi(close,14)"
```

**回應**：
```json
{
  "factor": "rsi(close,14)",
  "result": {
    "actual_ic": 0.035,
    "p_value": 0.023,
    "significant": true
  },
  "verdict": "因子顯著"
}
```

### 2.12 組合優化

```bash
curl -X POST "http://127.0.0.1:8000/portfolio/optimize?symbols=2330,2317,2454,2412&market=TW&start=2023-01-01&end=2025-12-31&method=hrp"
```

**回應**：
```json
{
  "method": "hrp",
  "weights": {
    "2330": 0.35,
    "2317": 0.25,
    "2454": 0.22,
    "2412": 0.18
  },
  "metrics": {
    "sharpe": 1.15,
    "total_return": 0.52,
    "max_drawdown": -0.12
  }
}
```

### 2.13 風控檢查

```bash
curl -X POST "http://127.0.0.1:8000/risk/check?market=TW&symbol=2330&side=BUY&qty=1000&price=850&portfolio_value=1000000"
```

**回應**：
```json
{
  "approved": true,
  "adjusted_qty": 176,
  "reason": "POSITION_LIMIT_85.00%"
}
```

### 2.14 Kill Switch

```bash
curl -X POST "http://127.0.0.1:8000/risk/kill-switch?reason=manual"
```

### 2.15 自然語言下單

```bash
curl -X POST "http://127.0.0.1:8000/trade/natural?text=幫我買一張台積電&portfolio_value=1000000&dry_run=true"
```

### 2.16 帶風控下單

```bash
curl -X POST "http://127.0.0.1:8000/trade/order-protected?symbol=2330&market=TW&side=BUY&price=850&qty=1000&portfolio_value=1000000&dry_run=true"
```

### 2.17 審計日誌

```bash
curl "http://127.0.0.1:8000/trade/audit-log?limit=50"
```

---

## 三、CLI 腳本

### 3.1 `scripts/smoke_test.py` — 煙霧測試

```bash
python scripts/smoke_test.py
```

**預期**：17 項全 PASS，退出碼 0。

### 3.2 `scripts/ingest_real_data.py` — 數據灌入

```bash
# 台股
python scripts/ingest_real_data.py --market TW --symbols 2330,2317,2454 --with-chips

# 美股
python scripts/ingest_real_data.py --market US --symbols AAPL,MSFT,NVDA

# 同時
python scripts/ingest_real_data.py --market BOTH \
    --tw-symbols 2330,2317 --us-symbols AAPL,MSFT
```

### 3.3 `scripts/run_first_backtest.py` — 回測

```bash
# 單策略
python scripts/run_first_backtest.py --symbol 2330 --market TW

# 多策略對比 + Walk-Forward
python scripts/run_first_backtest.py --symbol 2330 --market TW --multi --walk-forward

# 自訂表達式
python scripts/run_first_backtest.py --symbol AAPL --market US \
    --expr "rsi(close,14) - 50" --upper 20 --lower -20
```

### 3.4 `scripts/tw_paper_trading.py` — 模擬盤

```bash
# Dry run
python scripts/tw_paper_trading.py --symbols 2330 --dry-run

# 實際模擬下單
python scripts/tw_paper_trading.py --symbols 2330 --strategy ma_cross
```

---

## 四、常見錯誤排除

### 4.1 安裝類

#### 錯誤：`ModuleNotFoundError: No module named 'app'`

**原因**：從錯誤的目錄執行，或沒設定 `PYTHONPATH`。

**解法**：
```bash
cd invest-os  # 專案根目錄
python scripts/smoke_test.py
```

所有腳本都有 `sys.path.insert(0, ROOT)`，從專案根目錄執行即可。

#### 錯誤：`ImportError: cannot import name 'FinMind'`

**解法**：
```bash
pip install FinMind
```

#### 錯誤：`ModuleNotFoundError: No module named 'shioaji'`

**解法**：
```bash
pip install shioaji
```

#### 錯誤：`ModuleNotFoundError: No module named 'duckdb'`

**解法**：
```bash
pip install duckdb>=1.0.0
```

---

### 4.2 數據類

#### 錯誤：`FinMind login failed`

**原因**：Token 過期或未設定。

**解法**：
1. 到 https://finmindtrade.com/ 申請免費 token
2. 在 `.env` 加入 `FINMIND_TOKEN=your_token`
3. 重啟服務

**注意**：無 token 也能抓部分數據，只是配額較低。

#### 錯誤：`yfinance fetch error: No data found`

**原因**：
- 標的代碼錯誤
- 網路問題
- Yahoo Finance 臨時故障

**解法**：
```bash
# 測試 yfinance 是否正常
python -c "import yfinance as yf; print(yf.Ticker('AAPL').history(period='5d'))"
```

#### 錯誤：`no data` (404)

**原因**：該標的在指定時間範圍內無數據。

**解法**：
1. 確認標的代碼格式：
   - 台股：`2330`（4 位數字）
   - 美股：`AAPL`（大寫）
2. 確認時間範圍合理（避免未來日期）

#### 錯誤：`insufficient data (N bars)`

**原因**：數據量不足以計算指標。

**解法**：至少需要 60 筆數據。如果標的剛上市，改用其他標的。

---

### 4.3 回測類

#### 錯誤：`DSL eval error: name 'xxx' is not defined`

**原因**：表達式用了 DSL 不支援的函數。

**解法**：檢查 DSL 支援的函數列表：
```
sma, ema, mean, std, stdev, rsi, atr, zscore,
highest, lowest, max, min, slope,
delay, delta, ts_rank, ts_argmax, ts_argmin,
ts_sum, ts_mean, ts_std, ts_min, ts_max,
rank, sign, abs, log, correlation, covariance,
quantile, signedpower, rsquare, residual
```

#### 錯誤：`DSL eval error: invalid syntax`

**原因**：表達式語法錯誤。

**解法**：常見問題：
- ❌ `ema(close, 10) - ema(close, 30) / ema(close, 30)`（運算優先級）
- ✅ `(ema(close, 10) - ema(close, 30)) / ema(close, 30)`
- ❌ `close > 100`（不支援布林運算）
- ✅ `sign(close - 100)`

#### 錯誤：回測結果 `num_trades: 0`

**原因**：信號從未觸發。

**解法**：
1. 檢查 `upper` / `lower` 閾值是否過嚴
2. 用 `--upper 0.01 --lower -0.01` 放寬
3. 用 `--expr "close / delay(close, 20) - 1"` 測試簡單策略

---

### 4.4 風控類

#### 錯誤：`KILL_SWITCH_ACTIVE`

**原因**：Kill Switch 被觸發過。

**解法**：
```bash
# 重新啟動服務（記憶體狀態重置）
# 或刪除狀態檔案
rm data_lake/risk_state_tw.json
```

#### 錯誤：`CIRCUIT_BREAKER_KILL`

**原因**：回撤超過 15%，觸發熔斷。

**解法**：等待冷卻時間（預設 60 分鐘），或調整 `circuit_breaker_levels`。

#### 錯誤：`POSITION_LIMIT_xx%`

**原因**：單一倉位超過上限。

**解法**：風控會自動減倉（回傳 `adjusted_qty`），不需要手動處理。

---

### 4.5 審計類

#### 錯誤：`audit verification failed`

**原因**：審計日誌被手動修改。

**解法**：
```bash
# 檢查損壞位置
python -c "
from app.audit.verifiable_log import VerifiableAuditLog
log = VerifiableAuditLog()
print(log.verify_integrity())
"
```

如果日誌損壞，只能刪除重建：
```bash
rm data_lake/audit/events.jsonl
```

---

### 4.6 Shioaji 類

#### 錯誤：`login failed`

**原因**：帳號或密碼錯誤。

**解法**：
1. 確認 `.env` 中的 `SHIOAJI_PERSON_ID` 和 `SHIOAJI_PASSWORD`
2. 模擬帳號可從 https://www.sinotrade.com.tw/shioaji/ 申請

#### 錯誤：`contract not found`

**原因**：股票代碼不在合約清單。

**解法**：
```python
# 列出可用合約
import shioaji as sj
api = sj.Shioaji(simulation=True)
api.login(person_id="...", passwd="...")
print(list(api.Contracts.Stocks.TSE.keys())[:20])
```

#### 錯誤：`ca not activated`（實盤）

**原因**：實盤需要 CA 憑證。

**解法**：
1. 到永豐申請 CA
2. 下載 `.pfx` 檔案
3. 在 `.env` 設定 `CA_PATH` 和 `CA_PASSWORD`
4. 修改 `ShioajiBridge(simulation=False, ca_path="...", ca_passwd="...")`

---

### 4.7 監控類

#### 錯誤：`[CRITICAL] xxx 已 60 秒無心跳`

**原因**：某個模組停止回應。

**解法**：
1. 檢查對應模組的日誌
2. 如果是 WebSocket 斷線，重啟服務
3. 調整 timeout：`watchdog.monitor("xxx", timeout_seconds=120)`

---

### 4.8 效能類

#### 問題：回測很慢

**解法**：
1. 縮短時間範圍
2. 減少標的數量
3. 使用 `NeutrinoEngine`（Numba 加速）
4. 安裝 `numba`：`pip install numba`

#### 問題：DuckDB 鎖定

**原因**：多個 process 同時寫入。

**解法**：
- DuckDB 是單寫入者模型
- 讀寫分離：讀用 `read_only=True`，寫入排隊
- 或用 `PostgreSQL` 替代（需自行擴展）

---

## 五、上線檢查清單

### Phase 1：Paper Trading（2 週）

- [ ] `python scripts/smoke_test.py` 全 PASS
- [ ] `python scripts/ingest_real_data.py` 成功灌入數據
- [ ] `python scripts/run_first_backtest.py --walk-forward` OOS 一致性 > 1.0
- [ ] `python scripts/tw_paper_trading.py --dry-run` 執行 2 週無崩潰
- [ ] 審計日誌完整性驗證通過

### Phase 2：小規模實盤（1 個月）

- [ ] 資金限制：≤ 5% 總資金
- [ ] 單標的起步（1-2 檔）
- [ ] 風控參數保守（單筆虧損 ≤ 0.3%）
- [ ] 執行偏差 < 0.3%
- [ ] 每週復盤交易記錄

### Phase 3：全量上線（3 個月起）

- [ ] Kill Switch 測試通過
- [ ] 心跳監控正常
- [ ] 自動重啟機制驗證
- [ ] 告警通道（Slack / Telegram）正常
- [ ] 每日 DuckDB 快照備份

---

## 六、環境變數速查

```env
# 數據存放
DATA_ROOT=./data_lake

# FinMind
FINMIND_TOKEN=

# LLM
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=
LLM_MODEL=gpt-4o-mini

# Shioaji（模擬盤）
SHIOAJI_PERSON_ID=
SHIOAJI_PASSWORD=

# Shioaji（實盤）
SHIOAJI_API_KEY=
SHIOAJI_SECRET_KEY=
SHIOAJI_CA_PATH=
SHIOAJI_CA_PASSWORD=
```

---

## 七、檔案位置速查

| 檔案 | 用途 |
|------|------|
| `data_lake/market.duckdb` | 行情 / 籌碼 / 期權 |
| `data_lake/factors.duckdb` | 因子庫 |
| `data_lake/memory.duckdb` | Agent 記憶 |
| `data_lake/serving.duckdb` | 模型預測 |
| `data_lake/audit/events.jsonl` | 主審計日誌 |
| `data_lake/audit/paper_trading.jsonl` | 模擬盤審計 |
| `data_lake/paper_trading_state.json` | 模擬盤狀態 |
| `data_lake/paper_trading_trades.jsonl` | 模擬盤交易記錄 |
| `data_lake/parquet/` | Parquet 冷數據 |
| `reports/backtest_*.md` | 回測報告 |
| `reports/backtest_*.json` | 回測原始數據 |

---

## 八、緊急處理

### 緊急停止所有交易

```bash
# 1. Kill Switch
curl -X POST "http://127.0.0.1:8000/risk/kill-switch?reason=emergency"

# 2. 終止 process
pkill -f tw_paper_trading.py
pkill -f uvicorn

# 3. 檢查未平倉
python -c "
from app.broker.shioaji_bridge import ShioajiBridge
b = ShioajiBridge(simulation=True)
b.connect()
print(b.get_positions())
"
```

### 資料庫損壞

```bash
# 備份
cp data_lake/market.duckdb data_lake/market.duckdb.bak

# 重建（會丟失數據，需重新灌入）
rm data_lake/market.duckdb
python scripts/ingest_real_data.py --market TW --symbols 2330
```

### 審計日誌損壞

```bash
# 備份
cp data_lake/audit/events.jsonl data_lake/audit/events.jsonl.bak

# 從最後一條有效記錄恢復
python -c "
import json
from app.audit.verifiable_log import VerifiableAuditLog
log = VerifiableAuditLog()
v = log.verify_integrity()
print(f'有效記錄: {v[\"total_records\"] - v[\"errors\"]} / {v[\"total_records\"]}')
"
```

---

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
</script>
</section>
```

---

## 使用方式

1. 打開 `invest-os.html`
2. 找到 `<section id="batch4">...</section>`（目前是 placeholder）
3. **整段替換**為上面這段
4. 存檔 → 重新整理
5. 側邊欄點「📘 RUNBOOK + CHANGELOG」查看

批次 5 待命。要繼續就說「批次 5」。