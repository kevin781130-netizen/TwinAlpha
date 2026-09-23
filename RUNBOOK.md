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
