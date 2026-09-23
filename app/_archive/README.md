# 歸檔的概念代碼

原始批次只提供歸檔清單與說明，沒有提供這些模組的可執行源碼，因此本打包版**不虛構缺失實作**。

| 模組 | 歸檔理由 |
|------|----------|
| `app/gpu/factor_gpu.py` | 依賴虛構的 `QuantGplearn.gpu_transformer` |
| `app/quantum/quantum_portfolio.py` | 依賴假設的 `double_quant` 導入路徑；需要 Qiskit |
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
